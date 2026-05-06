"""Tests for SupabaseAuthMiddleware and /api/engagements endpoints."""

import uuid
from unittest.mock import MagicMock, patch

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_EMAIL = "test@example.com"
_JWT_SECRET = "test-secret"
VALID_TOKEN = _jwt.encode({"email": TEST_EMAIL}, _JWT_SECRET, algorithm="HS256")
ENGAGEMENT_ID = str(uuid.uuid4())


def _mock_engagement(engagement_id=ENGAGEMENT_ID, owner_email=TEST_EMAIL):
    return {
        "id": engagement_id,
        "name": "Test Engagement",
        "client_name": "Acme Corp",
        "currency_label": "AUD",
        "engagement_title": "Procurement Spend Diagnostic",
        "owner_email": owner_email,
        "is_admin": False,
        "llm_dry_run": True,
        "created_at": "2026-05-03T00:00:00+00:00",
        "recommendations_json": None,
    }


def _make_client(monkeypatch):
    """Return TestClient with JWT validation bypassed to inject TEST_EMAIL."""
    monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)
    with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}):
        client = TestClient(app, raise_server_exceptions=True)
        return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_headers():
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAuth:
    def test_unauthenticated_request_returns_401(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/engagements")
        assert resp.status_code == 401

    def test_health_skips_auth(self):
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/health")
        assert resp.status_code == 200


class TestEngagementsCRUD:
    def test_post_creates_engagement_and_returns_id(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        created = _mock_engagement()

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.mappings.return_value.first.return_value = created

        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.engagements.get_engine", return_value=mock_engine):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/engagements",
                json={"name": "Test Engagement", "client_name": "Acme Corp"},
                headers=_auth_headers(),
            )

        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["owner_email"] == TEST_EMAIL

    def test_get_lists_only_own_engagements(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        engagements = [_mock_engagement()]

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.mappings.return_value.all.return_value = engagements

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.engagements.get_engine", return_value=mock_engine):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/engagements", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert all(e["owner_email"] == TEST_EMAIL for e in data)

    def test_get_unknown_engagement_returns_403(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        # No row found
        mock_conn.execute.return_value.mappings.return_value.first.return_value = None

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.engagements.get_engine", return_value=mock_engine):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{uuid.uuid4()}",
                headers=_auth_headers(),
            )

        assert resp.status_code == 403
