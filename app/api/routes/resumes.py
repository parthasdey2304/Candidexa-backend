from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.db.models import Resume, User
from app.api.deps import get_db, get_current_user
from app.schemas.core import ResumeCreate, ResumeUpdate, ResumeInDB

router = APIRouter()

@router.post("/", response_model=ResumeInDB)
def create_resume(
    resume_in: ResumeCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    resume = Resume(**resume_in.model_dump(), user_id=current_user.id)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume

@router.get("/", response_model=List[ResumeInDB])
def read_resumes(
    skip: int = 0, limit: int = 100, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    resumes = db.query(Resume).filter(Resume.user_id == current_user.id).offset(skip).limit(limit).all()
    return resumes

@router.get("/{resume_id}", response_model=ResumeInDB)
def read_resume(
    resume_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume

@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    db.delete(resume)
    db.commit()
    return None
