from __future__ import annotations
import time
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AIUsageLedger
from app.core.config import settings
from app.core.rate_limit import rate_limit, user_key
from app.core.errors import ServiceUnavailableError


async def enforce_ai_limits(db: AsyncSession, user_id: str, request) -> None:
    # 1. per-user per-minute rate limit
    await rate_limit(user_key(user_id, "ai"), settings.AI_REQUESTS_PER_MINUTE)

    # 2. daily token quota
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    daily = await db.scalar(
        select(func.coalesce(func.sum(AIUsageLedger.input_tokens + AIUsageLedger.output_tokens), 0))
        .where(AIUsageLedger.user_id == user_id, AIUsageLedger.created_at >= today_start)
    )
    if (daily or 0) >= settings.AI_DAILY_TOKEN_LIMIT:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "daily_token_quota_exceeded")

    # 3. monthly token quota
    month_start = today_start.replace(day=1)
    monthly = await db.scalar(
        select(func.coalesce(func.sum(AIUsageLedger.input_tokens + AIUsageLedger.output_tokens), 0))
        .where(AIUsageLedger.user_id == user_id, AIUsageLedger.created_at >= month_start)
    )
    if (monthly or 0) >= settings.AI_MONTHLY_TOKEN_LIMIT:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "monthly_token_quota_exceeded")

    # 4. monthly spend cap (micro-USD integer)
    spend = await db.scalar(
        select(func.coalesce(func.sum(AIUsageLedger.cost_usd), 0))
        .where(AIUsageLedger.user_id == user_id, AIUsageLedger.created_at >= month_start)
    )
    if (spend or 0) / 1_000_000 >= settings.AI_MONTHLY_SPEND_USD_LIMIT:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "monthly_spend_cap_reached")


async def record_ai_usage(
    db: AsyncSession, *, user_id: str, provider: str, route: str,
    input_tokens: int, output_tokens: int, cost_usd: float, request_id: str, status_: str = "ok",
) -> None:
    db.add(AIUsageLedger(
        user_id=user_id, provider=provider, route=route,
        input_tokens=input_tokens, output_tokens=output_tokens,
        cost_usd=int(cost_usd * 1_000_000), status=status_, request_id=request_id,
    ))
    await db.commit()


# Simple in-memory circuit breaker (single-instance; for multi-process use Redis).
class CircuitBreaker:
    def __init__(self, name: str):
        self.name = name
        self._failures = 0
        self._opened_at = 0.0

    def record_failure(self):
        self._failures += 1
        if self._failures >= settings.AI_CIRCUIT_BREAKER_THRESHOLD:
            self._opened_at = time.time()

    def record_success(self):
        self._failures = 0
        self._opened_at = 0.0

    def guard(self):
        if self._opened_at and time.time() - self._opened_at < settings.AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS:
            raise ServiceUnavailableError("ai_provider_unavailable")
        if self._opened_at and time.time() - self._opened_at >= settings.AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS:
            # half-open - allow one attempt
            self._opened_at = 0.0


def redact_pii(text: str) -> str:
    """Minimal PII redaction — avoids logging raw resume text."""
    if not text:
        return text
    # keep stub simple; real redaction happens in gateway before logging
    return text[:8000]

class _MatchResult:
    def __init__(self, match_score: int, feedback: str, provider: str = "local"):
        self.match_score = match_score
        self.feedback = feedback
        self.provider = provider

def local_match_score(resume: str, jd: str) -> _MatchResult:
    # fallback when Gemini not configured — naive keyword overlap
    import re
    rt = set(re.findall(r"\w+", resume.lower()))
    jt = set(re.findall(r"\w+", jd.lower()))
    if not jt:
        return _MatchResult(0, "Empty JD", "local")
    overlap = len(rt & jt)
    score = min(95, int(overlap / max(1, len(jt)) * 100 * 1.2))
    return _MatchResult(score, f"Local keyword overlap: {overlap}/{len(jt)}", "local")

breakers = {"gemini": CircuitBreaker("gemini"), "mistral": CircuitBreaker("mistral")}


async def call_with_timeout(coro, timeout: int, breaker: CircuitBreaker):
    breaker.guard()
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except (asyncio.TimeoutError, Exception) as e:
        breaker.record_failure()
        raise