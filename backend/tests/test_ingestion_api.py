"""Tests for /api/engagements/{engagement_id}/ingest/* endpoints."""

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_EMAIL = "test@example.com"
VALID_TOKEN = "valid.jwt.token"
ENGAGEMENT_ID = str(uuid.uuid4())
JOB_ID = str(uuid.uuid4())

_MOCK_ENGAGEMENT = {
    "id": ENGAGEMENT_ID,
    "name": "Test Engagement",
    "client_name": "Acme Corp",
    "currency_label": "AUD",
    "engagement_title": "Procurement Spend Diagnostic",
    "owner_email": TEST_EMAIL,
    "is_admin": False,
    "llm_dry_run": True,
    "created_at": "2026-05-03T00:00:00+00:00",
    "recommendations_json": None,
}

_MOCK_JOB = {
    "id": JOB_ID,
    "status": "queued",
    "stage": None,
    "started_at": "2026-05-03T00:00:00+00:00",
    "completed_at": None,
    "error_message": None,
    "batch_id": None,
}


def _auth_headers():
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _make_mock_engine(row_for_select=_MOCK_ENGAGEMENT):
    """Return a MagicMock engine where connect() returns row_for_select."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.mappings.return_value.first.return_value = row_for_select

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_engine.begin.return_value = mock_conn
    return mock_engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_auth_and_engine(monkeypatch, engine):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret")
    return patch("app.middleware.auth.jwt.decode", return_value={"email": TEST_EMAIL}), \
           patch("app.routers.ingestion.get_engine", return_value=engine)


# ---------------------------------------------------------------------------
# POST /upload — valid CSV returns columns list
# ---------------------------------------------------------------------------

class TestUpload:
    def test_upload_valid_csv_returns_columns(self, monkeypatch, tmp_path):
        csv_content = b"invoice_date,raw_supplier_name,base_amount\n2024-01-01,Acme,100.0\n"
        csv_file = tmp_path / "test.csv"
        csv_file.write_bytes(csv_content)

        engine = _make_mock_engine(_MOCK_ENGAGEMENT)
        monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret")

        with patch("app.middleware.auth.jwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.ingestion.get_engine", return_value=engine):
            client = TestClient(app, raise_server_exceptions=True)
            with open(csv_file, "rb") as f:
                resp = client.post(
                    f"/api/engagements/{ENGAGEMENT_ID}/ingest/upload",
                    files={"file": ("test.csv", f, "text/csv")},
                    headers=_auth_headers(),
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "columns" in data
        assert isinstance(data["columns"], list)
        assert "invoice_date" in data["columns"]
        assert "job_id" in data
        assert "file_path" in data
        assert "row_count_estimate" in data

    def test_upload_invalid_extension_returns_400(self, monkeypatch):
        engine = _make_mock_engine(_MOCK_ENGAGEMENT)
        monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret")

        with patch("app.middleware.auth.jwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.ingestion.get_engine", return_value=engine):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                f"/api/engagements/{ENGAGEMENT_ID}/ingest/upload",
                files={"file": ("test.txt", b"some content", "text/plain")},
                headers=_auth_headers(),
            )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /run — creates pipeline_jobs row with status=queued
# ---------------------------------------------------------------------------

class TestRun:
    def test_run_creates_job_with_status_queued(self, monkeypatch):
        engine = _make_mock_engine(_MOCK_ENGAGEMENT)
        monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret")

        with patch("app.middleware.auth.jwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.ingestion.get_engine", return_value=engine), \
             patch("app.routers.ingestion._run_pipeline"):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                f"/api/engagements/{ENGAGEMENT_ID}/ingest/run",
                json={
                    "job_id": JOB_ID,
                    "file_path": "/tmp/test.csv",
                    "column_mapping": {"Invoice Date": "invoice_date"},
                },
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == JOB_ID
        assert data["status"] == "queued"

        # Verify INSERT was called on the engine
        mock_conn = engine.begin.return_value
        mock_conn.execute.assert_called()


# ---------------------------------------------------------------------------
# GET /status/{job_id} — returns job row
# ---------------------------------------------------------------------------

class TestStatus:
    def _engine_with_job(self, engagement_row=_MOCK_ENGAGEMENT, job_row=_MOCK_JOB):
        """Engine that returns engagement on first connect, job on second connect."""
        mock_conn_engagement = MagicMock()
        mock_conn_engagement.__enter__ = MagicMock(return_value=mock_conn_engagement)
        mock_conn_engagement.__exit__ = MagicMock(return_value=False)
        mock_conn_engagement.execute.return_value.mappings.return_value.first.return_value = engagement_row

        mock_conn_job = MagicMock()
        mock_conn_job.__enter__ = MagicMock(return_value=mock_conn_job)
        mock_conn_job.__exit__ = MagicMock(return_value=False)
        mock_conn_job.execute.return_value.mappings.return_value.first.return_value = job_row

        mock_engine = MagicMock()
        mock_engine.connect.side_effect = [mock_conn_engagement, mock_conn_job]
        mock_engine.begin.return_value = mock_conn_engagement
        return mock_engine

    def test_get_status_known_job_returns_row(self, monkeypatch):
        engine = self._engine_with_job()
        monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret")

        with patch("app.middleware.auth.jwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.ingestion.get_engine", return_value=engine):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/ingest/status/{JOB_ID}",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == JOB_ID
        assert data["status"] == "queued"
        assert "stage" in data
        assert "started_at" in data
        assert "completed_at" in data
        assert "error_message" in data

    def test_get_status_unknown_job_returns_404(self, monkeypatch):
        # Engine returns engagement OK but no job row
        mock_conn_engagement = MagicMock()
        mock_conn_engagement.__enter__ = MagicMock(return_value=mock_conn_engagement)
        mock_conn_engagement.__exit__ = MagicMock(return_value=False)
        mock_conn_engagement.execute.return_value.mappings.return_value.first.return_value = _MOCK_ENGAGEMENT

        mock_conn_job = MagicMock()
        mock_conn_job.__enter__ = MagicMock(return_value=mock_conn_job)
        mock_conn_job.__exit__ = MagicMock(return_value=False)
        mock_conn_job.execute.return_value.mappings.return_value.first.return_value = None

        mock_engine = MagicMock()
        mock_engine.connect.side_effect = [mock_conn_engagement, mock_conn_job]

        monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret")

        with patch("app.middleware.auth.jwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.ingestion.get_engine", return_value=mock_engine):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/ingest/status/{str(uuid.uuid4())}",
                headers=_auth_headers(),
            )

        assert resp.status_code == 404
