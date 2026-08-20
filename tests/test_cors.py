"""Tests for CORS configuration."""

import pytest
from httpx import AsyncClient, ASGITransport

from main import app


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestCORS:
    """Tests for CORS headers and behavior."""

    async def test_cors_allows_configured_origin(self, client):
        """CORS should allow configured frontend origin."""
        headers = {"Origin": "http://localhost:3000"}
        response = await client.options("/health", headers=headers)
        assert response.status_code == 200
        # Check CORS headers
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    async def test_cors_allows_credentials(self, client):
        """CORS should allow credentials for configured origins."""
        headers = {"Origin": "http://localhost:3000"}
        response = await client.options("/health", headers=headers)
        assert response.headers.get("access-control-allow-credentials") == "true"

    async def test_cors_rejects_unconfigured_origin(self, client):
        """CORS should not allow unconfigured origins with credentials."""
        headers = {"Origin": "http://evil.com"}
        response = await client.options("/health", headers=headers)
        # Should not echo back the evil origin with credentials
        if "access-control-allow-origin" in response.headers:
            assert response.headers["access-control-allow-origin"] != "http://evil.com"

    async def test_cors_preflight_includes_methods(self, client):
        """CORS preflight should include allowed methods."""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        }
        response = await client.options("/api/resumes/", headers=headers)
        assert response.status_code == 200
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        assert "POST" in allowed_methods
        assert "GET" in allowed_methods

    async def test_cors_preflight_includes_headers(self, client):
        """CORS preflight should include allowed headers."""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        }
        response = await client.options("/api/resumes/", headers=headers)
        assert response.status_code == 200
        allowed_headers = response.headers.get("access-control-allow-headers", "")
        assert "Authorization" in allowed_headers
        assert "Content-Type" in allowed_headers

    async def test_no_wildcard_cors_with_credentials(self, client):
        """CORS should not use wildcard with credentials."""
        headers = {"Origin": "http://localhost:3000"}
        response = await client.options("/health", headers=headers)
        allow_origin = response.headers.get("access-control-allow-origin", "")
        assert allow_origin != "*"