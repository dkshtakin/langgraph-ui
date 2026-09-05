"""Tests for the demo entrypoint in ``backend/main.py``.

Verifies the FastAPI app mounts the API router (so every endpoint is
reachable) and serves Swagger UI at ``/docs``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_app_is_fastapi_instance():
    assert isinstance(app, FastAPI)


def test_router_mounted(client):
    """The router is mounted — GET /api/graphs resolves."""
    resp = client.get("/api/graphs")
    assert resp.status_code == 200
    data = resp.json()
    assert "book_planner" in data["graphs"]


def test_swagger_ui_served_at_docs(client):
    """Swagger UI is available at /docs for manual testing."""
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "Swagger UI" in resp.text


def test_openapi_lists_all_endpoints(client):
    """Every router endpoint is exposed in the OpenAPI schema."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for expected in [
        "/api/graphs",
        "/api/sessions",
        "/api/resume/{session_id}",
        "/api/sessions/{session_id}",
        "/api/stream",
    ]:
        assert expected in paths
