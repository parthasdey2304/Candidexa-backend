from __future__ import annotations
import json
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.ai_guard import enforce_ai_limits, record_ai_usage, call_with_timeout, breakers
from app.core.errors import ServiceUnavailableError


# Pricing in USD per 1K tokens - adjust per provider docs.
_PRICING = {
    "gemini": {"input": 0.000075, "output": 0.0003},     # gemini-1.5-flash-ish
    "mistral": {"input": 0.00017, "output": 0.00051},
}


async def ai_request(
    *, db: AsyncSession, user_id: str, request: Request, route: str,
    provider: str, prompt: str, max_output_tokens: int | None = None,
    schema_validator=None,
) -> dict:
    request_id = getattr(request.state, "request_id", "unknown")

    # 1. Hard input cap (prevents prompt-injection / abuse)
    if len(prompt) > settings.AI_MAX_INPUT_TOKENS * 4:   # ~4 chars/token
        raise ValueError("input_too_long")

    # 2. Quota + rate limit + spend
    await enforce_ai_limits(db, user_id, request)

    # 3. Provider key on server only
    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ServiceUnavailableError("gemini_not_configured")
        api_key = settings.GEMINI_API_KEY
        coro = _call_gemini(api_key, prompt, max_output_tokens or settings.AI_MAX_OUTPUT_TOKENS)
    elif provider == "mistral":
        if not settings.MISTRAL_API_KEY:
            raise ServiceUnavailableError("mistral_not_configured")
        api_key = settings.MISTRAL_API_KEY
        coro = _call_mistral(api_key, prompt, max_output_tokens or settings.AI_MAX_OUTPUT_TOKENS)
    else:
        raise ValueError(f"unknown_provider:{provider}")

    # 4. Call with timeout + circuit breaker
    breaker = breakers[provider]
    try:
        raw, in_tok, out_tok = await call_with_timeout(coro, settings.AI_TIMEOUT_SECONDS, breaker)
    except TimeoutError:
        breaker.record_failure()
        await record_ai_usage(db, user_id=user_id, provider=provider, route=route,
                             input_tokens=0, output_tokens=0, cost_usd=0,
                             request_id=request_id, status_="timeout")
        raise ServiceUnavailableError("ai_timeout")
    except Exception as e:
        breaker.record_failure()
        await record_ai_usage(db, user_id=user_id, provider=provider, route=route,
                             input_tokens=0, output_tokens=0, cost_usd=0,
                             request_id=request_id, status_="error")
        raise ServiceUnavailableError("ai_provider_error")

    breaker.record_success()

    # 5. Structured-output validation
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        raise ValueError("ai_response_not_json")
    if schema_validator is not None:
        parsed = schema_validator(parsed).model_dump()

    # 6. Cost accounting
    price = _PRICING[provider]
    cost = (in_tok / 1000 * price["input"]) + (out_tok / 1000 * price["output"])
    await record_ai_usage(
        db, user_id=user_id, provider=provider, route=route,
        input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
        request_id=request_id, status_="ok",
    )
    return parsed


async def _call_gemini(api_key: str, prompt: str, max_tokens: int):
    import httpx
    async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as c:
        resp = await c.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
            headers={"x-goog-api-key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"maxOutputTokens": max_tokens}},
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        return text, int(usage.get("promptTokenCount", 0)), int(usage.get("candidatesTokenCount", 0))


async def _call_mistral(api_key: str, prompt: str, max_tokens: int):
    import httpx
    async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as c:
        resp = await c.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens},
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


# Local fallback - deterministic scorer
import re

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


def extract_keywords(text: str) -> set:
    words = re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{2,}", text.lower())
    return {w.strip(".-") for w in words} - STOPWORDS


def local_match_score(resume_text: str, job_description: str) -> dict:
    """Deterministic keyword-overlap scorer used when no AI provider is available."""
    jd_keywords = extract_keywords(job_description)
    resume_keywords = extract_keywords(resume_text)
    if not jd_keywords:
        return {"match_score": 50, "feedback": "No keywords could be extracted from the job description.", "provider": "local-fallback"}

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
    return {"match_score": score, "feedback": feedback, "provider": "local-fallback"}


def template_cover_letter(resume_text: str, job_description: str, tone: str, length: str) -> str:
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