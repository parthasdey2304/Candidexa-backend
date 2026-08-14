from fastapi import APIRouter, Depends
from typing import Dict, Any
from supabase import Client

from app.api.deps import get_db, get_current_user
from app.schemas.core import DashboardSummary

router = APIRouter()

@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    db: Client = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user.get("id")

    # 1. Calculate Resume Readiness (Max ATS score among all resumes)
    # Supabase doesn't support max() aggregation out of the box in the JS client / REST API,
    # so we fetch and compute. For huge datasets, we'd use a postgres function.
    resumes_res = db.table("resumes").select("ats_score").eq("user_id", user_id).execute()
    resume_readiness = max([r.get("ats_score", 0) for r in resumes_res.data]) if resumes_res.data else 0

    # 2. Count Saved Jobs
    jobs_res = db.table("jobs").select("id", count="exact").eq("user_id", user_id).execute()
    saved_jobs_count = jobs_res.count if jobs_res.count else 0

    # 3. Count Active Applications (Not rejected or saved)
    # Supabase supports in_
    apps_res = db.table("applications").select("id", count="exact").eq("user_id", user_id).in_("status", ["Applied", "Interview", "Offer"]).execute()
    active_apps_count = apps_res.count if apps_res.count else 0

    # 4. Get 3 Recent Jobs with their best application match score
    recent_jobs_res = db.table("jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(3).execute()
    recent_jobs_db = recent_jobs_res.data
    
    recent_jobs = []
    for job in recent_jobs_db:
        # Check if there is an application to get the match score
        app_res = db.table("applications").select("match_score").eq("job_id", job["id"]).limit(1).execute()
        match_score = app_res.data[0]["match_score"] if app_res.data else 0
        
        status = "strong" if match_score >= 80 else "partial" if match_score >= 60 else "weak"
        
        recent_jobs.append({
            "title": job.get("title"),
            "company": job.get("company"),
            "match": match_score,
            "status": status
        })

    # 5. Get 3 Recent Applications
    recent_apps_res = db.table("applications").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(3).execute()
    recent_apps_db = recent_apps_res.data
    
    recent_apps = []
    for app in recent_apps_db:
        job_res = db.table("jobs").select("title,company").eq("id", app["job_id"]).execute()
        job = job_res.data[0] if job_res.data else None
        
        # Need to handle date formatting. In Postgres, it's ISO format string.
        # We can extract just month and day if we want, or rely on frontend.
        from datetime import datetime
        date_str = "Unknown Date"
        if app.get("created_at"):
            try:
                # Handle ISO format from Supabase (e.g., '2023-11-20T14:32:00+00:00')
                dt = datetime.fromisoformat(app["created_at"].replace('Z', '+00:00'))
                date_str = dt.strftime("%b %d")
            except Exception:
                date_str = str(app["created_at"])[:10]

        recent_apps.append({
            "role": job["title"] if job else "Unknown Role",
            "company": job["company"] if job else "Unknown Company",
            "status": app.get("status"),
            "date": date_str
        })

    return {
        "resume_readiness": resume_readiness,
        "saved_jobs_count": saved_jobs_count,
        "active_apps_count": active_apps_count,
        "recent_jobs": recent_jobs,
        "recent_apps": recent_apps
    }
