from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Resume, Job, Application, User
from app.api.deps import get_db, get_current_user
from app.schemas.core import DashboardSummary

router = APIRouter()

@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Calculate Resume Readiness (Max ATS score among all resumes)
    max_ats = db.query(func.max(Resume.ats_score)).filter(Resume.user_id == current_user.id).scalar()
    resume_readiness = max_ats if max_ats is not None else 0

    # 2. Count Saved Jobs
    saved_jobs_count = db.query(Job).filter(Job.user_id == current_user.id).count()

    # 3. Count Active Applications (Not rejected or saved)
    active_apps_count = db.query(Application).filter(
        Application.user_id == current_user.id,
        Application.status.in_(["Applied", "Interview", "Offer"])
    ).count()

    # 4. Get 3 Recent Jobs with their best application match score
    recent_jobs_db = db.query(Job).filter(Job.user_id == current_user.id).order_by(Job.created_at.desc()).limit(3).all()
    recent_jobs = []
    for job in recent_jobs_db:
        # Check if there is an application to get the match score
        app = db.query(Application).filter(Application.job_id == job.id).first()
        match_score = app.match_score if app else 0
        
        status = "strong" if match_score >= 80 else "partial" if match_score >= 60 else "weak"
        
        recent_jobs.append({
            "title": job.title,
            "company": job.company,
            "match": match_score,
            "status": status
        })

    # 5. Get 3 Recent Applications
    recent_apps_db = db.query(Application).filter(Application.user_id == current_user.id).order_by(Application.created_at.desc()).limit(3).all()
    recent_apps = []
    for app in recent_apps_db:
        job = db.query(Job).filter(Job.id == app.job_id).first()
        recent_apps.append({
            "role": job.title if job else "Unknown Role",
            "company": job.company if job else "Unknown Company",
            "status": app.status,
            "date": app.created_at.strftime("%b %d")
        })

    return {
        "resume_readiness": resume_readiness,
        "saved_jobs_count": saved_jobs_count,
        "active_apps_count": active_apps_count,
        "recent_jobs": recent_jobs,
        "recent_apps": recent_apps
    }
