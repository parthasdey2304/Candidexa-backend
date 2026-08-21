from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Dict, Any, Optional
from supabase import Client

from app.api.deps import get_db, get_current_user
from app.schemas.core import JobCreate, JobUpdate, JobInDB
from app.services.job_service import JobService, get_job_service

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def get_job_svc(db: Client = Depends(get_db)) -> JobService:
    return get_job_service(db)


@router.post("/", response_model=JobInDB, status_code=status.HTTP_201_CREATED)
def create_job(
    job_in: JobCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    job_svc: JobService = Depends(get_job_svc),
):
    return job_svc.create_job(current_user["id"], job_in)


@router.get("/", response_model=List[JobInDB])
def read_jobs(
    skip: int = 0,
    limit: int = 100,
    q: Optional[str] = Query(None, description="Search query for title"),
    company: Optional[str] = Query(None, description="Filter by company"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    job_svc: JobService = Depends(get_job_svc),
):
    limit = min(max(1, limit), 100)
    if q or company:
        return job_svc.search_jobs(current_user["id"], q, company, skip, limit)
    return job_svc.get_jobs(current_user["id"], skip, limit)


@router.get("/{job_id}", response_model=JobInDB)
def read_job(
    job_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    job_svc: JobService = Depends(get_job_svc),
):
    job = job_svc.get_job(current_user["id"], job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}", response_model=JobInDB)
def update_job(
    job_id: int,
    job_in: JobUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    job_svc: JobService = Depends(get_job_svc),
):
    job = job_svc.update_job(current_user["id"], job_id, job_in)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    job_svc: JobService = Depends(get_job_svc),
):
    if not job_svc.delete_job(current_user["id"], job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return None


@router.post("/deduplicate", response_model=dict)
def deduplicate_jobs(
    current_user: Dict[str, Any] = Depends(get_current_user),
    job_svc: JobService = Depends(get_job_svc),
):
    """Remove duplicate jobs (same title + company)."""
    deleted = job_svc.deduplicate_jobs(current_user["id"])
    return {"deleted": deleted}
