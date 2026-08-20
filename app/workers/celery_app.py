"""Celery application for background task processing."""

import os
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# Celery configuration
broker_url = os.getenv("CELERY_BROKER_URL", settings.REDIS_URL or "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", settings.REDIS_URL or "redis://localhost:6379/0")

celery_app = Celery(
    "candidexa",
    broker=broker_url,
    backend=result_backend,
    include=["app.workers.tasks"],
)

# Celery settings
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    result_expires=86400,  # 24 hours
    beat_schedule={
        "cleanup-expired-jobs": {
            "task": "app.workers.tasks.cleanup_expired_jobs",
            "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM UTC
        },
        "cleanup-abandoned-uploads": {
            "task": "app.workers.tasks.cleanup_abandoned_uploads",
            "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM UTC
        },
    },
)

# Optional: configure task routes for different queues
celery_app.conf.task_routes = {
    "app.workers.tasks.process_resume_upload": {"queue": "resumes"},
    "app.workers.tasks.generate_tailored_resumes": {"queue": "ai-heavy"},
    "app.workers.tasks.generate_code": {"queue": "code-generation"},
    "app.workers.tasks.deploy_project": {"queue": "deployment"},
    "app.workers.tasks.generate_video": {"queue": "video-generation"},
}

if __name__ == "__main__":
    celery_app.start()