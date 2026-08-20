"""Tests for health and readiness endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from main import app


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    async def test_health_returns_200(self, client):
        """Health endpoint should return HTTP 200."""
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_returns_correct_structure(self, client):
        """Health endpoint should return expected JSON structure."""
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "candidexa-backend"
        assert "version" in data

    async def test_health_no_auth_required(self, client):
        """Health endpoint should not require authentication."""
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_not_rate_limited(self, client):
        """Health endpoint should not be rate limited."""
        # Make multiple requests
        for _ in range(10):
            response = await client.get("/health")
            assert response.status_code == 200


class TestReadinessEndpoint:
    """Tests for /ready endpoint."""

    async def test_ready_returns_200(self, client):
        """Readiness endpoint should return HTTP 200."""
        response = await client.get("/ready")
        assert response.status_code == 200

    async def test_ready_returns_correct_structure(self, client):
        """Readiness endpoint should return expected JSON structure."""
        response = await client.get("/ready")
        data = response.json()
        assert data["status"] == "ready"
        assert "database" in data