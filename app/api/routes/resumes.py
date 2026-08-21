from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_current_user_strict, get_db_session
from app.db.models import User, Resume
from app.core.crypto import encrypt_field, decrypt_field
from app.core.config import settings
from app.services.storage_service import save_private_object
import uuid
try:
    import magic  # python-magic — requires libmagic (fails on Windows)
    def _detect_mime(blob: bytes) -> str:
        return magic.from_buffer(blob, mime=True)
except Exception:  # pragma: no cover - Windows fallback
    def _detect_mime(blob: bytes) -> str:
        # fallback: sniff PDF/DOCX magic bytes
        if blob.startswith(b"%PDF"):
            return "application/pdf"
        if blob.startswith(b"PK\x03\x04"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return "application/octet-stream"

router = APIRouter(prefix="/api/v1/resumes", tags=["resumes"])
ALLOWED_MIME = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_BYTES = settings.MAX_RESUME_SIZE_MB * 1024 * 1024


@router.post("", status_code=201)
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user_strict),
    db: AsyncSession = Depends(get_db_session),
):
    # 1. Size check by streaming - never trust Content-Length
    blob = await file.read(MAX_BYTES + 1)
    if len(blob) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file_too_large")

    # 2. MIME by magic bytes, not extension
    mime = _detect_mime(blob)
    if mime not in ALLOWED_MIME:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_file_type")

    # 3. Store with random key (never user filename) - and the *path* itself is encrypted
    storage_key = f"resumes/{user.id}/{uuid.uuid4()}"
    await save_private_object(storage_key, blob)

    # 4. PII stored encrypted; never log
    rec = Resume(
        user_id=user.id,
        filename_enc=encrypt_field(file.filename),
        storage_key_enc=encrypt_field(storage_key),
        raw_text_enc=None,  # populated later by isolated parsing worker
    )
    db.add(rec)
    await db.commit()
    return {"id": rec.id}


@router.get("/{resume_id}")
async def get_resume(
    resume_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    rec = await db.get(Resume, resume_id)
    if rec is None or rec.user_id != user.id:     # object-level authz
        raise HTTPException(status.HTTP_404_NOT_FOUND, "resource_not_found")
    return {
        "id": rec.id,
        "filename": decrypt_field(rec.filename_enc),
        "created_at": rec.created_at.isoformat(),
    }


@router.get("")
async def list_resumes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    skip: int = 0,
    limit: int = 100,
):
    limit = min(max(1, limit), 100)
    res = await db.execute(
        select(Resume).where(Resume.user_id == user.id).offset(skip).limit(limit)
    )
    resumes = res.scalars().all()
    return [
        {
            "id": r.id,
            "filename": decrypt_field(r.filename_enc),
            "created_at": r.created_at.isoformat(),
            "ats_score": r.ats_score,
        }
        for r in resumes
    ]


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: str,
    user: User = Depends(get_current_user_strict),
    db: AsyncSession = Depends(get_db_session),
):
    rec = await db.get(Resume, resume_id)
    if rec is None or rec.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "resource_not_found")
    await db.delete(rec)
    await db.commit()
    return None


@router.post("/{resume_id}/match")
async def analyze_resume_match(
    resume_id: str,
    job_description: str,
    user: User = Depends(get_current_user_strict),
    db: AsyncSession = Depends(get_db_session),
    request: Request = None,
):
    """Analyze how well a resume matches a job description."""
    from app.services.ai_gateway import ai_request, local_match_score
    from app.core.ai_guard import validate_input

    rec = await db.get(Resume, resume_id)
    if rec is None or rec.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "resource_not_found")

    validate_input(job_description)
    resume_text = decrypt_field(rec.raw_text_enc) if rec.raw_text_enc else ""

    try:
        result = await ai_request(
            db=db, user_id=str(user.id), request=request, route="match",
            provider="gemini" if settings.GEMINI_API_KEY else "mistral",
            prompt=f"Resume:\n{resume_text}\n\nJob description:\n{job_description}\n\nScore how well the resume matches the job description. Reply with JSON: {{\"match_score\": <int 0-100>, \"feedback\": \"...\"}}",
            schema_validator=None,
        )
    except Exception:
        # Local fallback
        result = local_match_score(resume_text, job_description)

    # Update ATS score
    rec.ats_score = result.get("match_score", 0)
    await db.commit()

    return result