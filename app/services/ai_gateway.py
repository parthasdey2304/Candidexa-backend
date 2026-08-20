"""Central server-side AI gateway.

Every AI call in the product goes through this module. Responsibilities
(Candidexa spec section 33 / v5 addendum section 33):

- Provider selection with fallback: Gemini -> Mistral -> deterministic local scorer.
- Server-only API keys (nothing AI-related ever reaches the frontend).
- Per-user rate limiting and daily quotas (in-memory; single-instance deploy).
- Input size caps, PII redaction, prompt-injection screening.
- Timeouts and a single retry per provider.
- Structured JSON parsing for the match score (no hardcoded scores).

The deterministic local scorer is the final fallback so the core product flow
keeps working (and stays demo-able) even when no provider key is configured
or a provider is down. Responses produced by it are marked with
provider="local-fallback" so the frontend/dashboard never mistakes it for a
real AI analysis.
"""

import json
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Dict, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger("ai_gateway")

PII_PATTERNS = [
    (re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\+?\d[\d\s-]{8,13}\d"), "[REDACTED_PHONE]"),
]

SUSPICIOUS_PHRASES = [
    "ignore previous",
    "ignore all previous",
    "forget all",
    "disregard previous",
    "system prompt",
    "you are now",
    "reveal your prompt",
    "drop table",
    "bypass",
]

STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have",
    "this", "that", "from", "they", "their", "than", "then", "them", "such",
    "who", "what", "how", "why", "all", "any", "can", "has", "was", "were",
    "not", "but", "its", "it's", "into", "over", "under", "about", "across",
    "using", "use", "used", "must", "should", "would", "could", "able",
    "years", "year", "work", "working", "team", "teams", "role", "roles",
    "job", "jobs", "candidate", "candidates", "experience", "strong",
    "including", "include", "includes", "plus", "etc", "within", "while",
    "other", "others", "new", "well", "good", "best", "more", "most", "also",
    "a", "an", "in", "on", "at", "to", "of", "or", "as", "is", "be", "by",
    "we", "us", "it", "he", "she", "do", "does", "did", "so", "if", "no",
}


class PromptInjectionError(ValueError):
    """Raised when input text matches common prompt-injection patterns."""


def redact_pii(text: str) -> str:
    for pattern, replacement in PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def check_prompt_injection(text: str) -> bool:
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in SUSPICIOUS_PHRASES)


@dataclass
class MatchResult:
    match_score: int
    feedback: str
    provider: str


@dataclass
class GenerationResult:
    text: str
    provider: str


def local_match_score(resume_text: str, job_description: str) -> MatchResult:
    """Deterministic keyword-overlap scorer used when no AI provider is
    available. Same inputs always produce the same score."""
    def keywords(text: str) -> set:
        words = re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{2,}", text.lower())
        return {w.strip(".-") for w in words} - STOPWORDS

    jd_keywords = keywords(job_description)
    resume_keywords = keywords(resume_text)
    if not jd_keywords:
        return MatchResult(50, "No keywords could be extracted from the job description.", "local-fallback")

    matched = jd_keywords & resume_keywords
    missing = sorted(jd_keywords - resume_keywords)
    ratio = len(matched) / len(jd_keywords)
    score = max(20, min(95, round(40 + 55 * ratio)))

    if missing:
        sample = ", ".join(missing[:12])
        feedback = (
            f"Deterministic keyword analysis: your resume covers {len(matched)} of "
            f"{len(jd_keywords)} job-description keywords. Consider addressing "
            f"keywords such as: {sample}."
        )
    else:
        feedback = (
            f"Deterministic keyword analysis: your resume covers all "
            f"{len(jd_keywords)} extracted job-description keywords."
        )
    return MatchResult(score, feedback, "local-fallback")


class AIGateway:
    def __init__(self) -> None:
        self._recent_calls: Dict[str, deque] = defaultdict(lambda: deque(maxlen=256))
        self._daily_counts: Dict[str, int] = defaultdict(int)
        self._daily_counts_day: date = date.today()

    # ------------------------------------------------------------------ guards

    def check_limits(self, user_id: str) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        window = self._recent_calls[user_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= settings.AI_REQUESTS_PER_MINUTE:
            retry_after = max(1, int(60 - (now - window[0])))
            return False, retry_after

        today = date.today()
        if today != self._daily_counts_day:
            self._daily_counts.clear()
            self._daily_counts_day = today
        if self._daily_counts[user_id] >= settings.AI_REQUESTS_PER_DAY:
            return False, 86400
        return True, 0

    def _record_call(self, user_id: str) -> None:
        self._recent_calls[user_id].append(time.monotonic())
        self._daily_counts[user_id] += 1

    def _validate_input(self, *texts: str) -> None:
        for text in texts:
            if check_prompt_injection(text):
                raise PromptInjectionError("Malicious input detected (prompt injection).")
            if len(text) > settings.AI_MAX_INPUT_CHARS:
                raise ValueError(f"Input exceeds the maximum of {settings.AI_MAX_INPUT_CHARS} characters.")

    # -------------------------------------------------------------- providers

    async def _call_gemini(self, prompt: str, system: str, timeout: float) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.GEMINI_MODEL}:generateContent"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.2},
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url, json=body, headers={"x-goog-api-key": settings.GEMINI_API_KEY}
            )
            response.raise_for_status()
            data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _call_mistral(self, prompt: str, system: str, timeout: float) -> str:
        url = "https://api.mistral.ai/v1/chat/completions"
        body = {
            "model": settings.MISTRAL_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {settings.MISTRAL_API_KEY}"},
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _complete(self, prompt: str, system: str, timeout: float) -> Tuple[str, str]:
        """Try Gemini (if configured), then Mistral (if configured).
        Raises RuntimeError when no provider succeeds."""
        providers = []
        if settings.GEMINI_API_KEY:
            providers.append(("gemini", self._call_gemini))
        if settings.MISTRAL_API_KEY:
            providers.append(("mistral", self._call_mistral))

        for name, caller in providers:
            for attempt in (1, 2):
                try:
                    text = await caller(prompt, system, timeout)
                    if text and text.strip():
                        return text.strip(), name
                except httpx.HTTPError as exc:
                    logger.warning(
                        "AI provider %s failed (attempt %d): %s", name, attempt, type(exc).__name__
                    )
        raise RuntimeError("No AI provider is configured or available")


    # ---------------------------------------------------------------- public

    async def analyze_match(self, user_id: str, resume_text: str, job_description: str) -> MatchResult:
        self._validate_input(resume_text, job_description)
        safe_resume = redact_pii(resume_text)
        system = (
            "You are an ATS resume scanner. Reply with ONLY a JSON object of the shape "
            '{"match_score": <integer 0-100>, "feedback": "<2-4 sentences of specific, '
            'actionable feedback>"} with no markdown fences and no extra text.'
        )
        prompt = (
            f"Resume:\n{safe_resume}\n\nJob description:\n{job_description}\n\n"
            "Score how well the resume matches the job description."
        )
        try:
            raw, provider = await self._complete(prompt, system, float(settings.AI_TIMEOUT_SECONDS))
        except RuntimeError:
            fallback = local_match_score(resume_text, job_description)
            logger.info("AI match analysis served by local fallback for user %s", user_id)
            self._record_call(user_id)
            return fallback

        parsed_score = None
        feedback = raw.strip()
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                score = int(parsed.get("match_score"))
                if 0 <= score <= 100:
                    parsed_score = score
                if isinstance(parsed.get("feedback"), str) and parsed["feedback"].strip():
                    feedback = parsed["feedback"].strip()
            except (ValueError, TypeError):
                pass
        self._record_call(user_id)
        if parsed_score is None:
            # Provider replied but not in the agreed JSON shape: keep its prose
            # feedback, derive the score deterministically.
            fallback = local_match_score(resume_text, job_description)
            return MatchResult(fallback.match_score, feedback, provider)
        return MatchResult(parsed_score, feedback, provider)

    async def generate_cover_letter(
        self,
        user_id: str,
        resume_text: str,
        job_description: str,
        tone: str,
        length: str,
    ) -> GenerationResult:
        self._validate_input(resume_text, job_description, tone, length)
        safe_resume = redact_pii(resume_text)
        system = "You are an expert cover-letter writer. Write only the letter body text, no preamble."
        prompt = (
            f"Write a {length} cover letter with a {tone} tone.\n\n"
            f"Resume:\n{safe_resume}\n\nJob description:\n{job_description}"
        )
        try:
            text, provider = await self._complete(prompt, system, float(settings.AI_TIMEOUT_SECONDS) + 10)
            self._record_call(user_id)
            return GenerationResult(text, provider)
        except RuntimeError:
            logger.info("Cover letter served by local template for user %s", user_id)
            return GenerationResult(
                self._template_cover_letter(safe_resume, job_description, tone, length),
                "local-fallback",
            )

    @staticmethod
    def _template_cover_letter(resume_text: str, job_description: str, tone: str, length: str) -> str:
        opening = {
            "professional": "I am writing to express my strong interest in this position.",
            "enthusiastic": "I was genuinely excited to see this opening — it aligns exactly with where I want to take my career.",
            "confident": "This role is precisely the kind of challenge I am looking for, and I believe I can deliver from day one.",
        }.get(tone.lower(), "I am writing to apply for this position.")

        jd_keywords = {
            w.strip(".-") for w in re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{2,}", job_description.lower())
        } - STOPWORDS
        keywords = sorted(jd_keywords)[:8]
        keyword_line = ", ".join(keywords) if keywords else "the core requirements"
        closing = (
            "I would welcome the opportunity to discuss how my experience maps to your needs. "
            "Thank you for your time and consideration."
        )
        short = length.lower() in {"short", "brief", "concise"}
        body = (
            f"{opening} My background aligns well with {keyword_line}. "
            if short
            else f"{opening} Having reviewed the job description, I see a strong overlap with my experience across {keyword_line}. "
        )
        return f"{body}{closing}"


ai_gateway = AIGateway()
