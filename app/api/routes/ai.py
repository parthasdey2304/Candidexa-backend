from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services.ai_gateway import PromptInjectionError, ai_gateway

router = APIRouter()


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


def _enforce_limits(request: Request, user: Dict[str, Any]) -> None:
    allowed, retry_after = ai_gateway.check_limits(str(user["id"]))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="AI rate limit or daily quota exceeded. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/match", response_model=AIMatchResponse)
async def analyze_match(
    payload: AIMatchRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    _enforce_limits(request, current_user)
    try:
        result = await ai_gateway.analyze_match(
            str(current_user["id"]), payload.resume_text, payload.job_description
        )
    except PromptInjectionError:
        raise HTTPException(status_code=400, detail="Malicious input detected (prompt injection).")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return AIMatchResponse(
        match_score=result.match_score, feedback=result.feedback, provider=result.provider
    )


@router.post("/cover-letter", response_model=CoverLetterResponse)
async def generate_cover_letter(
    payload: CoverLetterRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    _enforce_limits(request, current_user)
    try:
        result = await ai_gateway.generate_cover_letter(
            str(current_user["id"]),
            payload.resume_text,
            payload.job_description,
            payload.tone,
            payload.length,
        )
    except PromptInjectionError:
        raise HTTPException(status_code=400, detail="Malicious input detected (prompt injection).")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return CoverLetterResponse(cover_letter=result.text, provider=result.provider)
