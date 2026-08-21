"""Storage service for private object storage (e.g., Supabase Storage or S3-compatible)."""

from __future__ import annotations

from supabase import create_client

from app.core.config import settings


class StorageService:
    def __init__(self):
        # Use Supabase storage
        self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        self.bucket = "resumes"

    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload bytes to private storage. Returns the storage key."""
        # Ensure bucket exists
        try:
            self.client.storage.get_bucket(self.bucket)
        except Exception:
            self.client.storage.create_bucket(self.bucket, options={"public": False})

        # Upload with random key to prevent enumeration
        self.client.storage.from_(self.bucket).upload(
            key, data, {"content-type": content_type, "upsert": "false"}
        )
        return key

    async def download(self, key: str) -> bytes:
        """Download bytes from private storage."""
        return self.client.storage.from_(self.bucket).download(key)

    async def delete(self, key: str) -> bool:
        """Delete object from storage."""
        try:
            self.client.storage.from_(self.bucket).remove([key])
            return True
        except Exception:
            return False

    async def create_signed_url(self, key: str, expires_in: int = 3600) -> str:
        """Create a signed URL for temporary access."""
        resp = self.client.storage.from_(self.bucket).create_signed_url(key, expires_in)
        return resp["signedURL"]


# Singleton instance
_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service


async def save_private_object(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Convenience function to save a private object."""
    service = get_storage_service()
    return await service.upload(key, data, content_type)


async def get_private_object(key: str) -> bytes:
    service = get_storage_service()
    return await service.download(key)


async def delete_private_object(key: str) -> bool:
    service = get_storage_service()
    return await service.delete(key)


async def get_signed_url(key: str, expires_in: int = 3600) -> str:
    service = get_storage_service()
    return await service.create_signed_url(key, expires_in)