from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from supabase import Client

from app.api.deps import get_db, get_current_user
from app.schemas.core import ResumeCreate, ResumeUpdate, ResumeInDB

router = APIRouter()

@router.post("/", response_model=ResumeInDB)
def create_resume(
    resume_in: ResumeCreate, 
    db: Client = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    resume_data = resume_in.model_dump()
    resume_data["user_id"] = current_user.get("id")
    
    res = db.table("resumes").insert(resume_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create resume")
    return res.data[0]

@router.get("/", response_model=List[ResumeInDB])
def read_resumes(
    skip: int = 0, limit: int = 100, 
    db: Client = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    # offset and limit map to range in supabase
    # supabase range is inclusive, so range(0, 9) returns 10 items
    end_idx = skip + limit - 1
    res = db.table("resumes").select("*").eq("user_id", current_user.get("id")).range(skip, end_idx).execute()
    return res.data

@router.get("/{resume_id}", response_model=ResumeInDB)
def read_resume(
    resume_id: int, 
    db: Client = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    res = db.table("resumes").select("*").eq("id", resume_id).eq("user_id", current_user.get("id")).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Resume not found")
    return res.data[0]

@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: int, 
    db: Client = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    res = db.table("resumes").delete().eq("id", resume_id).eq("user_id", current_user.get("id")).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Resume not found")
    return None
