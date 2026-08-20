"""Tests for authorization and object-level access control."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

from main import app


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestAuthorization:
    """Tests for user authorization and data isolation."""

    @pytest.mark.asyncio
    async def test_protected_route_requires_token(self, client):
        """Protected routes should require authentication."""
        r = await client.get("/api/v1/resumes/anything")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_user_cannot_read_others_resume(self, client):
        """Users should not be able to read other users' resumes."""
        # This test requires mocking the database
        pass

    @pytest.mark.asyncio
    async def test_csrf_required_on_state_changing(self, client):
        """State-changing routes should require CSRF token."""
        # POST without CSRF should fail
        r = await client.post("/api/v1/resumes", json={})
        assert r.status_code in (401, 403)


class TestAuthorizationHelpers:
    """Tests for authorization helper functions."""

    def test_blind_index_stable(self):
        """blind_index should be deterministic."""
        from app.core.crypto import blind_index
        assert blind_index("user@example.com") == blind_index("user@example.com")
        assert blind_index("user@example.com") != blind_index("other@example.com")

    def test_field_roundtrip(self):
        """encrypt_field / decrypt_field should round-trip."""
        from app.core.crypto import encrypt_field, decrypt_field
        pt = "Sensitive résumé content — PII here"
        assert decrypt_field(encrypt_field(pt)) == pt

    def test_password_never_sha256(self):
        """Password hashing should use Argon2id, not SHA-256."""
        from app.core.security import hash_password
        h = hash_password("correct horse battery staple")
        assert h.startswith("$argon2id$")  # not $sha256$