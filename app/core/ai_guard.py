"""AI request validation and guardrails.

Provides input validation, PII redaction, prompt injection detection,
and structured output parsing for AI requests.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger("ai_guard")

# PII patterns to redact before sending to AI providers
PII_PATTERNS = [
    (re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\+?\d[\d\s-]{8,13}\d"), "[REDACTED_PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[REDACTED_CARD]"),
]

# Common prompt injection patterns
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
    "override",
    "pretend to be",
    "act as",
    "simulate",
    "ignore instructions",
    "new instructions",
    "forget instructions",
    "previous instructions",
]

# Common stopwords for keyword extraction
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


class InputTooLargeError(ValueError):
    """Raised when input exceeds maximum allowed size."""


class InvalidProviderResponseError(ValueError):
    """Raised when AI provider returns malformed response."""


def redact_pii(text: str) -> str:
    """Redact PII from text before sending to AI providers."""
    for pattern, replacement in PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def check_prompt_injection(text: str) -> bool:
    """Check if text contains suspicious prompt injection patterns."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in SUSPICIOUS_PHRASES)


def validate_input_size(text: str, max_chars: Optional[int] = None) -> None:
    """Validate input size against configured limits."""
    limit = max_chars or settings.AI_MAX_INPUT_CHARS
    if len(text) > limit:
        raise InputTooLargeError(
            f"Input exceeds maximum of {limit} characters (got {len(text)})"
        )


def validate_input(*texts: str) -> None:
    """Validate all input texts for injection and size."""
    for text in texts:
        if check_prompt_injection(text):
            raise PromptInjectionError("Malicious input detected (prompt injection).")
        validate_input_size(text)


@dataclass
class MatchResult:
    """Structured result from resume-job match analysis."""
    match_score: int
    feedback: str
    provider: str


@dataclass
class GenerationResult:
    """Structured result from text generation."""
    text: str
    provider: str


def extract_keywords(text: str) -> set:
    """Extract meaningful keywords from text."""
    words = re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{2,}", text.lower())
    return {w.strip(".-") for w in words} - STOPWORDS


def local_match_score(resume_text: str, job_description: str) -> MatchResult:
    """Deterministic keyword-overlap scorer used as final fallback."""
    jd_keywords = extract_keywords(job_description)
    resume_keywords = extract_keywords(resume_text)
    
    if not jd_keywords:
        return MatchResult(
            50,
            "No keywords could be extracted from the job description.",
            "local-fallback"
        )

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


def parse_match_response(raw: str) -> Tuple[Optional[int], str]:
    """Parse AI response for match score and feedback.
    
    Returns (score, feedback) where score is None if parsing failed.
    """
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            score = int(parsed.get("match_score"))
            if 0 <= score <= 100:
                feedback = parsed.get("feedback", "").strip()
                if feedback:
                    return score, feedback
                return score, raw.strip()
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    return None, raw.strip()


def template_cover_letter(
    resume_text: str,
    job_description: str,
    tone: str,
    length: str,
) -> str:
    """Generate a template cover letter as fallback."""
    opening = {
        "professional": "I am writing to express my strong interest in this position.",
        "enthusiastic": "I was genuinely excited to see this opening — it aligns exactly with where I want to take my career.",
        "confident": "This role is precisely the kind of challenge I am looking for, and I believe I can deliver from day one.",
    }.get(tone.lower(), "I am writing to apply for this position.")

    jd_keywords = extract_keywords(job_description)
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