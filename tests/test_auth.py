"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from main import app


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    def test_signup_endpoint_exists(self, client):
        """Signup endpoint should exist."""
        response = client.post("/api/auth/signup", json={
            "email": "test@example.com",
            "password": "TestPass123!",
            "full_name": "Test User"
        })
        # Should not return 404
        assert response.status_code != 404

    def test_login_endpoint_exists(self, client):
        """Login endpoint should exist."""
        response = client.post("/api/auth/login", data={
            "username": "test@example.com",
            "password": "TestPass123!"
        })
        # Should not return 404
        assert response.status_code != 404

    def test_google_auth_endpoint_exists(self, client):
        """Google auth endpoint should exist."""
        response = client.post("/api/auth/google", json={
            "credential": "fake-google-token"
        })
        # Should not return 404
        assert response.status_code != 404


class TestProtectedEndpoints:
    """Tests for protected endpoints requiring authentication."""

    async def test_protected_endpoint_requires_auth(self, client):
        """Protected endpoints should return 401 without auth."""
        response = await client.get("/api/resumes/")
        assert response.status_code == 401

    async def test_protected_endpoint_requires_auth_jobs(self, client):
        """Jobs endpoint should require auth."""
        response = await client.get("/api/jobs/")
        assert response.status_code == 401

    async def test_protected_endpoint_requires_auth_dashboard(self, client):
        """Dashboard endpoint should require auth."""
        response = await client.get("/api/dashboard/summary")
        assert response.status_code == 401

    async def test_invalid_token_rejected(self, client):
        """Invalid JWT should be rejected."""
        headers = {"Authorization": "Bearer invalid-token"}
        response = await client.get("/api/resumes/", headers=headers)
        assert response.status_code == 401

    async def test_malformed_token_rejected(self, client):
        """Malformed JWT should be rejected."""
        headers = {"Authorization": "Bearer not.a.valid.token"}
        response = await client.get("/api/resumes/", headers=headers)
        assert response.status_code == 401