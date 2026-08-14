from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# --- Resume Schemas ---

class ResumeBase(BaseModel):
    title: str
    content: str
    is_master: Optional[bool] = False
    ats_score: Optional[int] = 0

class ResumeCreate(ResumeBase):
    pass

class ResumeUpdate(ResumeBase):
    title: Optional[str] = None
    content: Optional[str] = None

class ResumeInDB(ResumeBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Job Schemas ---

class JobBase(BaseModel):
    title: str
    company: str
    description: Optional[str] = None
    url: Optional[str] = None

class JobCreate(JobBase):
    pass

class JobUpdate(JobBase):
    title: Optional[str] = None
    company: Optional[str] = None

class JobInDB(JobBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Application Schemas ---

class ApplicationBase(BaseModel):
    job_id: int
    resume_id: Optional[int] = None
    status: Optional[str] = "Saved"
    match_score: Optional[int] = 0
    applied_date: Optional[datetime] = None

class ApplicationCreate(ApplicationBase):
    pass

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    resume_id: Optional[int] = None
    match_score: Optional[int] = None
    applied_date: Optional[datetime] = None

class ApplicationInDB(ApplicationBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Dashboard Schemas ---

class RecentJob(BaseModel):
    title: str
    company: str
    match: int
    status: str

class RecentApp(BaseModel):
    role: str
    company: str
    status: str
    date: str

class DashboardSummary(BaseModel):
    resume_readiness: int
    saved_jobs_count: int
    active_apps_count: int
    recent_jobs: List[RecentJob]
    recent_apps: List[RecentApp]
