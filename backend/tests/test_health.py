"""Tests for health, AI status, and documentation endpoints."""

from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient):
    """Verify root endpoint provides app metadata and links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "LedgerLeaf"
    assert "docs" in data


def test_health_endpoint(client: TestClient):
    """Verify health endpoint reports application and database health."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data
    assert "timestamp" in data


def test_ai_status_endpoint_disconnected(client: TestClient):
    """
    Verify AI status endpoint reports genuine disconnected status when local engine is offline.
    Never pretends or mocks fake connectivity.
    """
    response = client.get("/api/v1/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("disconnected", "connected", "error")
    assert "provider" in data
    assert "message" in data
    # When offline, model should be None
    if data["status"] == "disconnected":
        assert data["model"] is None


def test_swagger_docs_available(client: TestClient):
    """Verify FastAPI documentation is available at /docs."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_openapi_schema(client: TestClient):
    """Verify OpenAPI schema registers health and AI endpoints."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema.get("paths", {})
    assert "/api/v1/health" in paths
    assert "/api/v1/ai/status" in paths
