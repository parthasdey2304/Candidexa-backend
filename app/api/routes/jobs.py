from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from supabase import Client

from app.api.deps import get_db, get_current_user
from app.schemas.core import JobCreate, JobUpdate, JobInDB

router = APIRouter()

@router.post("/", response_model=JobInDB)
def create_job(
    job_in: JobCreate, 
    db: Client = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    job_data = job_in.model_dump()
    job_data["user_id"] = current_user.get("id")
    
    res = db.table("jobs").insert(job_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create job")
    return res.data[0]

@router.get("/", response_model=List[JobInDB])
def read_jobs(
    skip: int = 0, limit: int = 100, 
    db: Client = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    end_idx = skip + limit - 1
    res = db.table("jobs").select("*").eq("user_id", current_user.get("id")).range(skip, end_idx).execute()
    return res.data

@router.get("/{job_id}", response_model=JobInDB)
def read_job(
    job_id: int, 
    db: Client = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    res = db.table("jobs").select("*").eq("id", job_id).eq("user_id", current_user.get("id")).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return res.data[0]

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int, 
    db: Client = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    res = db.table("jobs").delete().eq("id", job_id).eq("user_id", current_user.get("id")).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return None
