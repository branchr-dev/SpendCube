"""Tests for /api/engagements/{engagement_id}/cube/* endpoints."""

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
    return mock_engine, mock_conn


def _execute_result(rows=None, row=None):
    """Build a mock execute() return value with .mappings().all() or .mappings().first()."""
    result = MagicMock()
    if rows is not None:
        result.mappings.return_value.all.return_value = rows
    if row is not None:
        result.mappings.return_value.first.return_value = row
    return result


# ---------------------------------------------------------------------------
# GET /overview
# ---------------------------------------------------------------------------

class TestOverview:
    def test_overview_returns_expected_keys(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()

        agg_row = {
            "total_spend": 100000.0,
            "invoice_count": 500,
            "supplier_count": 50,
            "category_count": 10,
            "data_freshness": "2025-12-31",
            "maverick_spend": 10000.0,
        }
        supplier_rows = [{"total_spend": 80000.0}, {"total_spend": 20000.0}]

        mock_conn.execute.side_effect = [
            _execute_result(row=agg_row),
            _execute_result(rows=supplier_rows),
        ]

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/overview",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        expected_keys = {
            "total_spend",
            "invoice_count",
            "supplier_count",
            "category_count",
            "currency_label",
            "maverick_spend_pct",
            "tail_spend_pct",
            "data_freshness",
        }
        assert expected_keys.issubset(data.keys())
        assert data["currency_label"] == "AUD"
        assert isinstance(data["total_spend"], float)
        assert isinstance(data["invoice_count"], int)
        assert isinstance(data["supplier_count"], int)
        assert 0.0 <= data["maverick_spend_pct"] <= 1.0
        assert 0.0 <= data["tail_spend_pct"] <= 1.0

    def test_overview_handles_zero_spend(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()

        agg_row = {
            "total_spend": 0.0,
            "invoice_count": 0,
            "supplier_count": 0,
            "category_count": 0,
            "data_freshness": None,
            "maverick_spend": 0.0,
        }
        mock_conn.execute.side_effect = [
            _execute_result(row=agg_row),
            _execute_result(rows=[]),
        ]

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/overview",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["maverick_spend_pct"] == 0.0
        assert data["tail_spend_pct"] == 0.0


# ---------------------------------------------------------------------------
# GET /by-month
# ---------------------------------------------------------------------------

class TestByMonth:
    def test_by_month_returns_sorted_list_with_rolling_avg(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()

        month_rows = [
            {"month": "2025-01", "total_spend": 10000.0, "transaction_count": 50},
            {"month": "2025-02", "total_spend": 12000.0, "transaction_count": 60},
            {"month": "2025-03", "total_spend": 11000.0, "transaction_count": 55},
            {"month": "2025-04", "total_spend": 13000.0, "transaction_count": 65},
        ]
        mock_conn.execute.return_value.mappings.return_value.all.return_value = month_rows

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/by-month",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 4

        # Sorted ascending by month (data returned from DB in order; check keys)
        months = [item["month"] for item in data]
        assert months == sorted(months)

        for item in data:
            assert "month" in item
            assert "total_spend" in item
            assert "transaction_count" in item
            assert "rolling_3m_avg" in item

        # First two have no rolling avg (need 3 periods)
        assert data[0]["rolling_3m_avg"] is None
        assert data[1]["rolling_3m_avg"] is None
        # Third onwards have rolling avg
        assert data[2]["rolling_3m_avg"] is not None
        assert data[3]["rolling_3m_avg"] is not None

    def test_by_month_returns_empty_list_when_no_data(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        mock_conn.execute.return_value.mappings.return_value.all.return_value = []

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/by-month",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /by-supplier
# ---------------------------------------------------------------------------

class TestBySupplier:
    def _make_supplier_rows(self, n: int):
        return [
            {
                "canonical_supplier_id": f"supplier_{i:03d}",
                "canonical_supplier_name": f"Supplier {i}",
                "parent_company_name": None,
                "transaction_count": 10,
                "total_spend": float(1000 * (n - i)),
                "avg_payment_days": 30.0,
                "abc_segment": None,
            }
            for i in range(n)
        ]

    def test_by_supplier_respects_limit_param(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        supplier_rows = self._make_supplier_rows(5)

        mock_conn.execute.side_effect = [
            _execute_result(rows=supplier_rows),
            _execute_result(row={"total_count": 100}),
        ]

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/by-supplier?limit=5",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "total_count" in data
        assert len(data["data"]) == 5
        assert data["total_count"] == 100

    def test_by_supplier_returns_expected_row_shape(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        supplier_rows = self._make_supplier_rows(2)

        mock_conn.execute.side_effect = [
            _execute_result(rows=supplier_rows),
            _execute_result(row={"total_count": 2}),
        ]

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/by-supplier",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        row = resp.json()["data"][0]
        assert "canonical_supplier_id" in row
        assert "canonical_supplier_name" in row
        assert "transaction_count" in row
        assert "total_spend" in row
        assert "avg_payment_days" in row


# ---------------------------------------------------------------------------
# GET /by-category
# ---------------------------------------------------------------------------

class TestByCategory:
    def test_by_category_returns_list_sorted_by_spend(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        category_rows = [
            {
                "category_l1": "IT",
                "category_l2": "Software",
                "category_l3": "SaaS",
                "unspsc_code": "43230000",
                "transaction_count": 100,
                "total_spend": 50000.0,
                "supplier_count": 5,
            },
            {
                "category_l1": "HR",
                "category_l2": "Training",
                "category_l3": None,
                "unspsc_code": None,
                "transaction_count": 20,
                "total_spend": 10000.0,
                "supplier_count": 2,
            },
        ]
        mock_conn.execute.return_value.mappings.return_value.all.return_value = category_rows

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/by-category",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["category_l1"] == "IT"
        assert data[0]["total_spend"] == 50000.0


# ---------------------------------------------------------------------------
# GET /by-bu
# ---------------------------------------------------------------------------

class TestByBu:
    def test_by_bu_returns_list(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        bu_rows = [
            {"business_unit": "Finance", "cost_centre": "CC001", "total_spend": 30000.0, "transaction_count": 100},
            {"business_unit": "IT", "cost_centre": "CC002", "total_spend": 20000.0, "transaction_count": 50},
        ]
        mock_conn.execute.return_value.mappings.return_value.all.return_value = bu_rows

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/by-bu",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["business_unit"] == "Finance"
        assert "total_spend" in data[0]
        assert "transaction_count" in data[0]


# ---------------------------------------------------------------------------
# GET /by-payment-terms
# ---------------------------------------------------------------------------

class TestByPaymentTerms:
    def test_by_payment_terms_returns_wc_opportunity(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _JWT_SECRET)

        mock_engine, mock_conn = _make_mock_engine()
        pt_rows = [
            {"bucket": "0-30", "transaction_count": 200, "total_spend": 50000.0},
            {"bucket": "31-60", "transaction_count": 100, "total_spend": 30000.0},
            {"bucket": "61-90", "transaction_count": 50, "total_spend": 15000.0},
            {"bucket": "90+", "transaction_count": 10, "total_spend": 5000.0},
        ]
        mock_conn.execute.return_value.mappings.return_value.all.return_value = pt_rows

        with patch("app.middleware.auth.pyjwt.decode", return_value={"email": TEST_EMAIL}), \
             patch("app.routers.cube.get_engine", return_value=mock_engine), \
             patch("app.routers.cube._load_config", return_value=None), \
             patch(
                 "app.routers.cube.verify_engagement_ownership",
                 new_callable=AsyncMock,
                 return_value=_MOCK_ENGAGEMENT,
             ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                f"/api/engagements/{ENGAGEMENT_ID}/cube/by-payment-terms",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 4

        for item in data:
            assert "bucket" in item
            assert "transaction_count" in item
            assert "total_spend" in item
            assert "spend_pct" in item
            assert "wc_opportunity_aud" in item
            assert item["wc_opportunity_aud"] >= 0

        total_pct = sum(item["spend_pct"] for item in data)
        assert abs(total_pct - 1.0) < 0.01

        # 0-30 bucket has midpoint 15 < target 45, so WC opportunity > 0
        zero_thirty = next(item for item in data if item["bucket"] == "0-30")
        assert zero_thirty["wc_opportunity_aud"] > 0
