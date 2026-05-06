"""Tests for review workstation and recommendations API endpoints."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_EMAIL = "test@example.com"
_JWT_SECRET = "test-secret"
VALID_TOKEN = _jwt.encode({"email": TEST_EMAIL}, _JWT_SECRET, algorithm="HS256")
ENGAGEMENT_ID = str(uuid.uuid4())

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


def _auth_headers():
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _make_mock_engine():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    mock_engine.begin.return_value = mock_conn
    return mock_engine, mock_conn


def _execute_result(rows=None, row=None, rowcount=1):
    result = MagicMock()
    result.rowcount = rowcount
    if rows is not None:
        result.mappings.return_value.all.return_value = rows
    if row is not None:
        result.mappings.return_value.first.return_value = row
    return result


# ---------------------------------------------------------------------------
# GET /supplier-queue
# ---------------------------------------------------------------------------

class TestSupplierQueue:
    def test_supplier_queue_returns_list(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()

        supplier_rows = [
            {
                "id": "match_001",
                "raw_supplier_name": "ACME CORP PTY LTD",
                "raw_supplier_id": None,
                "canonical_supplier_id": "abc123",
                "match_method": "FUZZY",
                "confidence": 0.45,
                "evidence": json.dumps({"token_sort_ratio": 0.45}),
                "review_status": "PENDING",
                "created_at": "2026-05-03T00:00:00+00:00",
            },
            {
                "id": "match_002",
                "raw_supplier_name": "TechCo Solutions",
                "raw_supplier_id": None,
                "canonical_supplier_id": "def456",
                "match_method": "EMBEDDING",
                "confidence": 0.55,
                "evidence": None,
                "review_status": "PENDING",
                "created_at": "2026-05-03T00:00:00+00:00",
            },
        ]
        mock_conn.execute.return_value.mappings.return_value.all.return_value = supplier_rows

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/review/supplier-queue",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == "match_001"
        assert data[0]["review_status"] == "PENDING"
        # evidence JSON string should be parsed to dict
        assert isinstance(data[0]["evidence"], dict)
        # None evidence stays None
        assert data[1]["evidence"] is None

    def test_supplier_queue_returns_empty_list_when_no_pending(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        mock_conn.execute.return_value.mappings.return_value.all.return_value = []

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/review/supplier-queue",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /supplier/{match_id}/approve
# ---------------------------------------------------------------------------

class TestApproveSupplier:
    def test_approve_updates_review_status(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        mock_conn.execute.return_value = _execute_result(rowcount=1)

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                f"/api/engagements/{ENGAGEMENT_ID}/review/supplier/match_001/approve",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"

        # Verify two execute calls: UPDATE + INSERT audit
        assert mock_conn.execute.call_count == 2

        # First call should be the UPDATE
        first_call_sql = str(mock_conn.execute.call_args_list[0][0][0])
        assert "UPDATE" in first_call_sql or "update" in first_call_sql.lower()

    def test_approve_returns_404_for_unknown_match(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        mock_conn.execute.return_value = _execute_result(rowcount=0)

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                f"/api/engagements/{ENGAGEMENT_ID}/review/supplier/nonexistent/approve",
                headers=_auth_headers(),
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /supplier/{match_id}/reject
# ---------------------------------------------------------------------------

class TestRejectSupplier:
    def test_reject_returns_rejected_status(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        mock_conn.execute.return_value = _execute_result(rowcount=1)

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                f"/api/engagements/{ENGAGEMENT_ID}/review/supplier/match_001/reject",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# POST /category-override
# ---------------------------------------------------------------------------

class TestCategoryOverride:
    def test_category_override_inserts_row_and_audit_entry(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()

        created_row = {
            "id": "override_001",
            "engagement_id": ENGAGEMENT_ID,
            "canonical_supplier_id": "supplier_abc",
            "gl_account": None,
            "override_l1": "Information Technology",
            "override_l2": "Software",
            "override_l3": "SaaS",
            "unspsc_code": "43230000",
            "reviewer": TEST_EMAIL,
            "reason": "Manual correction based on contract review",
            "created_at": "2026-05-03T00:00:00+00:00",
        }

        # Three execute calls: INSERT override, INSERT audit, SELECT to return row
        mock_conn.execute.side_effect = [
            _execute_result(rowcount=1),
            _execute_result(rowcount=1),
            _execute_result(row=created_row),
        ]

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                f"/api/engagements/{ENGAGEMENT_ID}/review/category-override",
                headers=_auth_headers(),
                json={
                    "canonical_supplier_id": "supplier_abc",
                    "override_l1": "Information Technology",
                    "override_l2": "Software",
                    "override_l3": "SaaS",
                    "unspsc_code": "43230000",
                    "reason": "Manual correction based on contract review",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "override_001"
        assert data["override_l1"] == "Information Technology"
        assert data["reviewer"] == TEST_EMAIL

        # Three execute calls: INSERT override, INSERT audit, SELECT
        assert mock_conn.execute.call_count == 3

    def test_category_override_requires_supplier_or_gl(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, _ = _make_mock_engine()

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                f"/api/engagements/{ENGAGEMENT_ID}/review/category-override",
                headers=_auth_headers(),
                json={
                    "override_l1": "IT",
                    "override_l2": "Software",
                    "override_l3": "SaaS",
                    "reason": "Test",
                },
            )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /category-queue
# ---------------------------------------------------------------------------

class TestCategoryQueue:
    def test_category_queue_returns_list(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()

        txn_rows = [
            {
                "transaction_id": "txn_001",
                "raw_supplier_name": "Mystery Vendor",
                "raw_line_description": "Misc services",
                "base_amount": 5000.0,
                "category_l1": None,
                "category_l2": None,
                "category_l3": None,
                "category_confidence": 0.30,
            },
        ]
        mock_conn.execute.return_value.mappings.return_value.all.return_value = txn_rows

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/review/category-queue",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["transaction_id"] == "txn_001"
        assert data[0]["category_confidence"] == 0.30


# ---------------------------------------------------------------------------
# GET /audit-log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_audit_log_returns_list(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()

        audit_rows = [
            {
                "id": "audit_001",
                "engagement_id": ENGAGEMENT_ID,
                "table_name": "supplier_match_log",
                "record_id": "match_001",
                "field_name": "review_status",
                "old_value": "PENDING",
                "new_value": "APPROVED",
                "changed_by": TEST_EMAIL,
                "changed_at": "2026-05-03T00:00:00+00:00",
            },
        ]
        mock_conn.execute.return_value.mappings.return_value.all.return_value = audit_rows

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.review.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.review.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/review/audit-log",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["new_value"] == "APPROVED"


# ---------------------------------------------------------------------------
# GET /recommendations (root)
# ---------------------------------------------------------------------------

class TestGetRecommendations:
    def test_get_recommendations_returns_404_when_null(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        mock_conn.execute.return_value.mappings.return_value.first.return_value = {
            "recommendations_json": None,
        }

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.recommendations.get_engine", return_value=mock_engine):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/recommendations",
                headers=_auth_headers(),
            )

        assert resp.status_code == 404
        assert "not yet generated" in resp.json()["detail"].lower()

    def test_get_recommendations_returns_parsed_json(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()

        payload = {
            "recommendations": [{"type": "SUPPLIER_CONSOLIDATION", "estimated_impact_aud": 10000.0}],
            "portfolio_summary": {"total_spend": 100000.0, "recommendation_count": 1},
        }
        mock_conn.execute.return_value.mappings.return_value.first.return_value = {
            "recommendations_json": json.dumps(payload),
        }

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.recommendations.get_engine", return_value=mock_engine):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/recommendations",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
        assert "portfolio_summary" in data
        assert len(data["recommendations"]) == 1
