from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List, Dict, Any
from supabase import Client

from app.api.deps import get_db, get_current_user
from app.schemas.core import ResumeCreate, ResumeUpdate, ResumeInDB
from app.services.resume_service import ResumeService, get_resume_service

router = APIRouter()


def get_resume_svc(db: Client = Depends(get_db)) -> ResumeService:
    return get_resume_service(db)


@router.post("/", response_model=ResumeInDB)
def create_resume(
    resume_in: ResumeCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    resume_svc: ResumeService = Depends(get_resume_svc),
):
    return resume_svc.create_resume(current_user["id"], resume_in)


@router.get("/", response_model=List[ResumeInDB])
def read_resumes(
    skip: int = 0,
    limit: int = 100,
    current_user: Dict[str, Any] = Depends(get_current_user),
    resume_svc: ResumeService = Depends(get_resume_svc),
):
    limit = min(max(1, limit), 100)
    return resume_svc.get_resumes(current_user["id"], skip, limit)


@router.get("/{resume_id}", response_model=ResumeInDB)
def read_resume(
    resume_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    resume_svc: ResumeService = Depends(get_resume_svc),
):
    resume = resume_svc.get_resume(current_user["id"], resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


@router.patch("/{resume_id}", response_model=ResumeInDB)
def update_resume(
    resume_id: int,
    resume_in: ResumeUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    resume_svc: ResumeService = Depends(get_resume_svc),
):
    resume = resume_svc.update_resume(current_user["id"], resume_id, resume_in)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    resume_svc: ResumeService = Depends(get_resume_svc),
):
    if not resume_svc.delete_resume(current_user["id"], resume_id):
        raise HTTPException(status_code=404, detail="Resume not found")
    return None


@router.post("/{resume_id}/match")
def analyze_resume_match(
    resume_id: int,
    job_description: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    resume_svc: ResumeService = Depends(get_resume_svc),
):
    """Analyze how well a resume matches a job description."""
    try:
        return resume_svc.analyze_resume_match(current_user["id"], resume_id, job_description)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/upload", response_model=ResumeInDB)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    resume_svc: ResumeService = Depends(get_resume_svc),
):
    """Upload and parse a resume file (PDF or DOCX)."""
    content = await file.read()
    try:
        return resume_svc.upload_resume_file(
            current_user["id"], content, file.filename or "resume.pdf", file.content_type or "application/pdf"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
