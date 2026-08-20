"""Workers package for background task processing."""

from app.workers.celery_app import celery_app
from app.workers.tasks import (
    process_resume_upload,
    generate_tailored_resumes,
    generate_code,
    push_to_github,
    deploy_project,
    generate_video,
    cleanup_expired_jobs,
    cleanup_abandoned_uploads,
    get_task_status,
    cancel_task,
)

__all__ = [
    "celery_app",
    "process_resume_upload",
    "generate_tailored_resumes",
    "generate_code",
    "push_to_github",
    "deploy_project",
    "generate_video",
    "cleanup_expired_jobs",
    "cleanup_abandoned_uploads",
    "get_task_status",
    "cancel_task",
]