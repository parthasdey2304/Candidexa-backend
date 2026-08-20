"""Storage service for file operations.

Handles uploads to Supabase Storage with signed URLs, validation,
and security measures.
"""

import logging
import mimetypes
import uuid
from datetime import timedelta
from typing import BinaryIO, Optional, Tuple

from supabase import Client

from app.core.config import settings

logger = logging.getLogger("candidexa.services.storage")


class StorageService:
    """Service for file storage operations using Supabase Storage."""

    # Allowed MIME types for resume uploads
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    # Allowed file extensions
    ALLOWED_EXTENSIONS = {".pdf", ".docx"}

    # Maximum file size (bytes)
    MAX_FILE_SIZE = settings.MAX_RESUME_SIZE_MB * 1024 * 1024

    def __init__(self, db: Client, bucket: str = "resumes"):
        self.db = db
        self.bucket = bucket
        self.storage = db.storage.from_(bucket)

    def validate_file(self, file_content: bytes, filename: str, content_type: str) -> Tuple[bool, Optional[str]]:
        """Validate file type, size, and content."""
        # Check file size
        if len(file_content) > self.MAX_FILE_SIZE:
            return False, f"File size exceeds {settings.MAX_RESUME_SIZE_MB} MB limit"

        # Check MIME type
        if content_type not in self.ALLOWED_MIME_TYPES:
            return False, f"File type {content_type} not allowed. Use PDF or DOCX."

        # Check extension
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in self.ALLOWED_EXTENSIONS:
            return False, f"File extension {ext} not allowed. Use .pdf or .docx"

        # Validate MIME type matches extension
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type and guessed_type != content_type:
            # Allow some mismatches (e.g., browser might send generic type)
            pass

        # TODO: Add magic byte validation for extra security
        # For PDF: file_content[:4] == b'%PDF'
        # For DOCX: file_content[:4] == b'PK\x03\x04' (ZIP-based)

        return True, None

    def generate_object_name(self, user_id: int, original_filename: str) -> str:
        """Generate a secure, random object name for storage."""
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "pdf"
        unique_id = uuid.uuid4().hex[:16]
        return f"user_{user_id}/{unique_id}.{ext}"

    def upload_file(
        self,
        user_id: int,
        file_content: bytes,
        original_filename: str,
        content_type: str,
    ) -> Tuple[str, str]:
        """Upload file to Supabase Storage and return (object_path, signed_url)."""
        # Validate
        valid, error = self.validate_file(file_content, original_filename, content_type)
        if not valid:
            raise ValueError(error)

        # Generate secure object name
        object_name = self.generate_object_name(user_id, original_filename)

        # Upload to Supabase Storage
        try:
            self.storage.upload(
                object_name,
                file_content,
                file_options={"content-type": content_type, "upsert": "false"},
            )
        except Exception as e:
            logger.error(
                "Storage upload failed",
                extra={"user_id": user_id, "object": object_name, "error": str(e)},
            )
            raise ValueError(f"Failed to upload file: {e}")

        # Generate signed URL (valid for 1 hour)
        signed_url = self.get_signed_url(object_name, expires_in=3600)

        logger.info(
            "File uploaded to storage",
            extra={"user_id": user_id, "object": object_name, "size": len(file_content)},
        )

        return object_name, signed_url

    def get_signed_url(self, object_name: str, expires_in: int = 3600) -> str:
        """Generate a signed URL for private file access."""
        try:
            response = self.storage.create_signed_url(object_name, expires_in)
            return response["signedURL"]
        except Exception as e:
            logger.error(
                "Failed to create signed URL",
                extra={"object": object_name, "error": str(e)},
            )
            raise ValueError(f"Failed to generate download URL: {e}")

    def download_file(self, object_name: str) -> bytes:
        """Download file from storage (server-side only)."""
        try:
            return self.storage.download(object_name)
        except Exception as e:
            logger.error(
                "Storage download failed",
                extra={"object": object_name, "error": str(e)},
            )
            raise ValueError(f"Failed to download file: {e}")

    def delete_file(self, object_name: str) -> bool:
        """Delete file from storage."""
        try:
            self.storage.remove([object_name])
            logger.info("File deleted from storage", extra={"object": object_name})
            return True
        except Exception as e:
            logger.error(
                "Storage delete failed",
                extra={"object": object_name, "error": str(e)},
            )
            return False

    def list_user_files(self, user_id: int) -> list:
        """List all files for a user."""
        try:
            prefix = f"user_{user_id}/"
            response = self.storage.list(prefix)
            return response
        except Exception as e:
            logger.error(
                "Storage list failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    def cleanup_abandoned_uploads(self, older_than_hours: int = 24) -> int:
        """Clean up abandoned uploads older than specified hours."""
        # This would require tracking upload timestamps
        # For now, return 0
        logger.info("Cleanup abandoned uploads not yet implemented")
        return 0


def get_storage_service(db: Client, bucket: str = "resumes") -> StorageService:
    """Dependency injection helper."""
    return StorageService(db, bucket)