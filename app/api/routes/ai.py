from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.services.ai_gateway import ai_request, local_match_score, template_cover_letter
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class AIMatchRequest(BaseModel):
    resume_text: str = Field(min_length=1)
    job_description: str = Field(min_length=1)


class AIMatchResponse(BaseModel):
    match_score: int
    feedback: str
    provider: str


class CoverLetterRequest(BaseModel):
    resume_text: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    tone: str = Field(default="professional", max_length=30)
    length: str = Field(default="medium", max_length=30)


class CoverLetterResponse(BaseModel):
    cover_letter: str
    provider: str


@router.post("/match", response_model=AIMatchResponse)
async def analyze_match(
    payload: AIMatchRequest,
    request: Request,
    user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        result = await ai_request(
            db=db,
            user_id=str(user.id),
            request=request,
            route="match",
            provider="gemini" if settings.GEMINI_API_KEY else "mistral",
            prompt=(
                "You are an ATS resume scanner. Reply with ONLY a JSON object of the shape "
                '{"match_score": <integer 0-100>, "feedback": "<2-4 sentences of specific, actionable feedback>"} '
                "with no markdown fences and no extra text.\n\n"
                f"Resume:\n{payload.resume_text}\n\nJob description:\n{payload.job_description}\n\n"
                "Score how well the resume matches the job description."
            ),
        )
    except Exception:
        # Local fallback
        result = local_match_score(payload.resume_text, payload.job_description)

    return AIMatchResponse(
        match_score=result.get("match_score", 0),
        feedback=result.get("feedback", ""),
        provider=result.get("provider", "local-fallback"),
    )


@router.post("/cover-letter", response_model=CoverLetterResponse)
async def generate_cover_letter(
    payload: CoverLetterRequest,
    request: Request,
    user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        result = await ai_request(
            db=db,
            user_id=str(user.id),
            request=request,
            route="cover_letter",
            provider="gemini" if settings.GEMINI_API_KEY else "mistral",
            prompt=(
                "You are an expert cover-letter writer. Write only the letter body text, no preamble.\n\n"
                f"Write a {payload.length} cover letter with a {payload.tone} tone.\n\n"
                f"Resume:\n{payload.resume_text}\n\nJob description:\n{payload.job_description}"
            ),
        )
    except Exception:
        result = {"text": template_cover_letter(payload.resume_text, payload.job_description, payload.tone, payload.length), "provider": "local-fallback"}

    return CoverLetterResponse(cover_letter=result.get("text", ""), provider=result.get("provider", "local-fallback"))