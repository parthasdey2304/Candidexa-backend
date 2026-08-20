from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api.deps import get_current_user, get_db
from app.schemas.core import ApplicationCreate, ApplicationInDB, ApplicationUpdate

router = APIRouter()

ALLOWED_STATUSES = {"Saved", "Applied", "Screening", "Interview", "Offer", "Rejected"}


def _owned_job_or_404(db: Client, user_id: int, job_id: int) -> Dict[str, Any]:
    res = (
        db.table("jobs")
        .select("id")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return res.data[0]


@router.post("/", response_model=ApplicationInDB, status_code=status.HTTP_201_CREATED)
def create_application(
    application_in: ApplicationCreate,
    db: Client = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = current_user["id"]
    _owned_job_or_404(db, user_id, application_in.job_id)

    if application_in.status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(ALLOWED_STATUSES)}",
        )

    if application_in.resume_id is not None:
        resume_res = (
            db.table("resumes")
            .select("id")
            .eq("id", application_in.resume_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not resume_res.data:
            raise HTTPException(status_code=404, detail="Resume not found")

    duplicate = (
        db.table("applications")
        .select("id")
        .eq("user_id", user_id)
        .eq("job_id", application_in.job_id)
        .execute()
    )
    if duplicate.data:
        raise HTTPException(
            status_code=409,
            detail="An application for this job already exists.",
        )

    data = application_in.model_dump(exclude_unset=True)
    data["user_id"] = user_id
    res = db.table("applications").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create application")
    return res.data[0]


@router.get("/", response_model=List[ApplicationInDB])
def read_applications(
    status_filter: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Client = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    limit = min(max(1, limit), 100)
    query = db.table("applications").select("*").eq("user_id", current_user["id"])
    if status_filter:
        if status_filter not in ALLOWED_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"status_filter must be one of {sorted(ALLOWED_STATUSES)}",
            )
        query = query.eq("status", status_filter)
    res = query.range(skip, skip + limit - 1).order("created_at", desc=True).execute()
    return res.data


@router.get("/{application_id}", response_model=ApplicationInDB)
def read_application(
    application_id: int,
    db: Client = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    res = (
        db.table("applications")
        .select("*")
        .eq("id", application_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Application not found")
    return res.data[0]


@router.patch("/{application_id}", response_model=ApplicationInDB)
def update_application(
    application_id: int,
    application_in: ApplicationUpdate,
    db: Client = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if application_in.status is not None and application_in.status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(ALLOWED_STATUSES)}",
        )

    existing = (
        db.table("applications")
        .select("id")
        .eq("id", application_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Application not found")

    res = (
        db.table("applications")
        .update(application_in.model_dump(exclude_unset=True, exclude_none=True))
        .eq("id", application_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to update application")
    return res.data[0]


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: int,
    db: Client = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    res = (
        db.table("applications")
        .delete()
        .eq("id", application_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Application not found")
    return None
