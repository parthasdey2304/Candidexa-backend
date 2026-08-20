"""Resume service layer.

Encapsulates business logic for resume operations, separating it from
API route handlers for testability and reusability.
"""

import logging
from typing import Any, Dict, List, Optional

from supabase import Client

from app.core.config import settings
from app.core.ai_guard import redact_pii
from app.schemas.core import ResumeCreate, ResumeUpdate, ResumeInDB

logger = logging.getLogger("candidexa.services.resume")


class ResumeService:
    """Service for resume operations."""

    def __init__(self, db: Client):
        self.db = db

    def create_resume(self, user_id: int, resume_in: ResumeCreate) -> ResumeInDB:
        """Create a new resume for the user."""
        resume_data = resume_in.model_dump()
        resume_data["user_id"] = user_id

        res = self.db.table("resumes").insert(resume_data).execute()
        if not res.data:
            raise ValueError("Failed to create resume")

        logger.info("Resume created", extra={"user_id": user_id, "resume_id": res.data[0]["id"]})
        return ResumeInDB(**res.data[0])

    def get_resumes(self, user_id: int, skip: int = 0, limit: int = 100) -> List[ResumeInDB]:
        """Get all resumes for a user with pagination."""
        end_idx = skip + limit - 1
        res = (
            self.db.table("resumes")
            .select("*")
            .eq("user_id", user_id)
            .range(skip, end_idx)
            .execute()
        )
        return [ResumeInDB(**item) for item in (res.data or [])]

    def get_resume(self, user_id: int, resume_id: int) -> Optional[ResumeInDB]:
        """Get a specific resume by ID, ensuring ownership."""
        res = (
            self.db.table("resumes")
            .select("*")
            .eq("id", resume_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            return None
        return ResumeInDB(**res.data[0])

    def update_resume(
        self, user_id: int, resume_id: int, resume_in: ResumeUpdate
    ) -> Optional[ResumeInDB]:
        """Update a resume, ensuring ownership."""
        update_data = resume_in.model_dump(exclude_unset=True, exclude_none=True)
        if not update_data:
            return self.get_resume(user_id, resume_id)

        res = (
            self.db.table("resumes")
            .update(update_data)
            .eq("id", resume_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            return None

        logger.info("Resume updated", extra={"user_id": user_id, "resume_id": resume_id})
        return ResumeInDB(**res.data[0])

    def delete_resume(self, user_id: int, resume_id: int) -> bool:
        """Delete a resume, ensuring ownership."""
        res = (
            self.db.table("resumes")
            .delete()
            .eq("id", resume_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            return False

        logger.info("Resume deleted", extra={"user_id": user_id, "resume_id": resume_id})
        return True

    def analyze_resume_match(
        self,
        user_id: int,
        resume_id: int,
        job_description: str,
    ) -> Dict[str, Any]:
        """Analyze how well a resume matches a job description."""
        resume = self.get_resume(user_id, resume_id)
        if not resume:
            raise ValueError("Resume not found")

        # Redact PII before AI analysis
        safe_content = redact_pii(resume.content)

        # TODO: Call AI gateway for analysis
        # For now, use local fallback
        from app.core.ai_guard import local_match_score

        result = local_match_score(safe_content, job_description)

        # Update resume ATS score
        self.update_resume(user_id, resume_id, ResumeUpdate(ats_score=result.match_score))

        return {
            "match_score": result.match_score,
            "feedback": result.feedback,
            "provider": result.provider,
        }

    def generate_tailored_resume(
        self,
        user_id: int,
        master_resume_id: int,
        job_description: str,
        company_profile: Optional[Dict[str, Any]] = None,
    ) -> ResumeInDB:
        """Generate a tailored resume for a specific job."""
        master = self.get_resume(user_id, master_resume_id)
        if not master:
            raise ValueError("Master resume not found")

        # TODO: Call AI gateway for tailoring
        # For now, create a basic tailored version
        safe_content = redact_pii(master.content)
        tailored_content = f"TAILORED FOR: {job_description[:200]}\n\n{safe_content}"

        new_resume = self.create_resume(
            user_id,
            ResumeCreate(
                title=f"Tailored: {master.title}",
                content=tailored_content,
                is_master=False,
            ),
        )

        return new_resume

    def upload_resume_file(
        self,
        user_id: int,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> ResumeInDB:
        """Process uploaded resume file and create resume record."""
        # Validate file type
        allowed_types = {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        if content_type not in allowed_types:
            raise ValueError(f"File type {content_type} not allowed. Use PDF or DOCX.")

        # Validate file size
        max_size = settings.MAX_RESUME_SIZE_MB * 1024 * 1024
        if len(file_content) > max_size:
            raise ValueError(f"File size exceeds {settings.MAX_RESUME_SIZE_MB} MB limit")

        # TODO: Parse file content (PDF/DOCX)
        # For now, store as placeholder
        parsed_content = f"[Parsed from {filename}]\nFile size: {len(file_content)} bytes\nContent type: {content_type}"

        # TODO: Upload to Supabase Storage and get signed URL

        resume = self.create_resume(
            user_id,
            ResumeCreate(
                title=filename,
                content=parsed_content,
                is_master=False,
            ),
        )

        logger.info(
            "Resume file uploaded",
            extra={"user_id": user_id, "resume_id": resume.id, "filename": filename},
        )
        return resume


def get_resume_service(db: Client) -> ResumeService:
    """Dependency injection helper."""
    return ResumeService(db)