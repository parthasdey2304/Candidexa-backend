"""Services package for Candidexa Backend."""

from app.services.ai_gateway import (
    ai_request,
    local_match_score,
    template_cover_letter,
)
from app.services.resume_service import ResumeService, get_resume_service
from app.services.job_service import JobService, get_job_service
from app.services.storage_service import StorageService, get_storage_service

__all__ = [
    "ai_request",
    "local_match_score",
    "template_cover_letter",
    "ResumeService",
    "get_resume_service",
    "JobService",
    "get_job_service",
    "StorageService",
    "get_storage_service",
]