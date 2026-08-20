"""Job service layer.

Encapsulates business logic for job operations.
"""

import logging
from typing import Any, Dict, List, Optional

from supabase import Client

from app.schemas.core import JobCreate, JobUpdate, JobInDB

logger = logging.getLogger("candidexa.services.job")


class JobService:
    """Service for job operations."""

    def __init__(self, db: Client):
        self.db = db

    def create_job(self, user_id: int, job_in: JobCreate) -> JobInDB:
        """Create a new job for the user."""
        job_data = job_in.model_dump()
        job_data["user_id"] = user_id

        res = self.db.table("jobs").insert(job_data).execute()
        if not res.data:
            raise ValueError("Failed to create job")

        logger.info("Job created", extra={"user_id": user_id, "job_id": res.data[0]["id"]})
        return JobInDB(**res.data[0])

    def get_jobs(self, user_id: int, skip: int = 0, limit: int = 100) -> List[JobInDB]:
        """Get all jobs for a user with pagination."""
        end_idx = skip + limit - 1
        res = (
            self.db.table("jobs")
            .select("*")
            .eq("user_id", user_id)
            .range(skip, end_idx)
            .execute()
        )
        return [JobInDB(**item) for item in (res.data or [])]

    def get_job(self, user_id: int, job_id: int) -> Optional[JobInDB]:
        """Get a specific job by ID, ensuring ownership."""
        res = (
            self.db.table("jobs")
            .select("*")
            .eq("id", job_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            return None
        return JobInDB(**res.data[0])

    def update_job(
        self, user_id: int, job_id: int, job_in: JobUpdate
    ) -> Optional[JobInDB]:
        """Update a job, ensuring ownership."""
        update_data = job_in.model_dump(exclude_unset=True, exclude_none=True)
        if not update_data:
            return self.get_job(user_id, job_id)

        res = (
            self.db.table("jobs")
            .update(update_data)
            .eq("id", job_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            return None

        logger.info("Job updated", extra={"user_id": user_id, "job_id": job_id})
        return JobInDB(**res.data[0])

    def delete_job(self, user_id: int, job_id: int) -> bool:
        """Delete a job, ensuring ownership."""
        res = (
            self.db.table("jobs")
            .delete()
            .eq("id", job_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            return False

        logger.info("Job deleted", extra={"user_id": user_id, "job_id": job_id})
        return True

    def search_jobs(
        self,
        user_id: int,
        query: Optional[str] = None,
        company: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[JobInDB]:
        """Search jobs with optional filters."""
        query_builder = self.db.table("jobs").select("*").eq("user_id", user_id)

        if query:
            # Supabase text search - using ilike for simplicity
            query_builder = query_builder.ilike("title", f"%{query}%")

        if company:
            query_builder = query_builder.ilike("company", f"%{company}%")

        end_idx = skip + limit - 1
        res = query_builder.range(skip, end_idx).execute()
        return [JobInDB(**item) for item in (res.data or [])]

    def deduplicate_jobs(self, user_id: int) -> int:
        """Remove duplicate jobs (same title + company for user)."""
        # Get all jobs
        res = self.db.table("jobs").select("*").eq("user_id", user_id).execute()
        jobs = res.data or []

        seen = set()
        deleted = 0
        for job in jobs:
            key = (job["title"].lower().strip(), job["company"].lower().strip())
            if key in seen:
                self.db.table("jobs").delete().eq("id", job["id"]).execute()
                deleted += 1
            else:
                seen.add(key)

        if deleted:
            logger.info("Duplicate jobs removed", extra={"user_id": user_id, "count": deleted})

        return deleted


def get_job_service(db: Client) -> JobService:
    """Dependency injection helper."""
    return JobService(db)