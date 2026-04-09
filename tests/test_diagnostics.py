"""Tests for SpendCube data quality diagnostics."""
import sys
from pathlib import Path

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.diagnostics.quality import DataQualityDiagnostics

_EXPECTED_CHECKS = {
    "missing_supplier_name",
    "uncategorised_spend",
    "unresolved_suppliers",
    "missing_payment_terms",
    "duplicate_invoice_risk",
    "negative_reversal_lines",
    "weak_descriptions",
    "missing_contract_linkage",
    "missing_bu_cost_centre",
}

# ---------------------------------------------------------------------------
# Helper DataFrames
# ---------------------------------------------------------------------------

def _clean_df() -> pd.DataFrame:
    """10-row DataFrame with no data quality issues."""
    return pd.DataFrame({
        "transaction_id": [f"TX-{i}" for i in range(10)],
        "invoice_number": [f"INV-{i}" for i in range(10)],
        "raw_supplier_name": [f"Supplier {i}" for i in range(10)],
        "canonical_supplier_id": [f"sid_{i}" for i in range(10)],
        "raw_line_description": [
            f"Professional consulting services and detailed advisory work item {i}"
            for i in range(10)
        ],
        "base_amount": [1000.0 * (i + 1) for i in range(10)],
        "category_l1": ["IT"] * 10,
        "payment_terms_days": [30] * 10,
        "po_number": [f"PO-{i}" for i in range(10)],
        "business_unit": ["Corporate"] * 10,
        "cost_centre": ["CC-01"] * 10,
    })


def _dirty_df() -> pd.DataFrame:
    """20-row DataFrame with many data quality issues."""
    return pd.DataFrame({
        "transaction_id": [f"TX-{i}" for i in range(20)],
        "invoice_number": ["INV-DUP"] * 10 + [f"INV-U{i}" for i in range(10)],
        "raw_supplier_name": [None] * 10 + [f"Supplier {i}" for i in range(10)],
        "canonical_supplier_id": [None] * 5 + [f"sid_{i}" for i in range(15)],
        "raw_line_description": ["misc"] * 10 + [None] * 10,
        "base_amount": [1000.0] * 20,
        "category_l1": [None] * 15 + ["IT"] * 5,
        "payment_terms_days": [None] * 15 + [30] * 5,
        "po_number": [None] * 20,
        "business_unit": [None] * 20,
        "cost_centre": [None] * 20,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_missing_supplier_returns_correct_pct(config):
    """50% missing raw_supplier_name → RED status."""
    df = pd.DataFrame({
        "transaction_id": ["TX-1", "TX-2", "TX-3", "TX-4"],
        "invoice_number": ["INV-1", "INV-2", "INV-3", "INV-4"],
        "raw_supplier_name": ["Supplier A", None, "Supplier B", None],
        "canonical_supplier_id": ["s1", None, "s2", None],
        "raw_line_description": ["office supplies quarterly order"] * 4,
        "base_amount": [100.0] * 4,
        "category_l1": ["IT"] * 4,
        "payment_terms_days": [30] * 4,
        "po_number": ["PO-1"] * 4,
        "business_unit": ["Corp"] * 4,
        "cost_centre": ["CC-01"] * 4,
    })
    diag = DataQualityDiagnostics(df, config)
    result = diag.check_missing_supplier_name()
    assert result["value"] == 2
    assert abs(result["pct"] - 50.0) < 0.01
    assert result["status"] == "RED"  # 50% >> 5% amber threshold


def test_duplicate_invoice_detects_duplicates(config):
    """Two rows sharing (invoice_number, base_amount) are flagged as duplicates."""
    df = pd.DataFrame({
        "transaction_id": ["TX-1", "TX-2", "TX-3"],
        "invoice_number": ["INV-DUP", "INV-DUP", "INV-UNIQ"],
        "raw_supplier_name": ["S1", "S1", "S2"],
        "canonical_supplier_id": ["s1", "s1", "s2"],
        "raw_line_description": ["services ordered quarterly"] * 3,
        "base_amount": [500.0, 500.0, 200.0],
        "category_l1": ["IT"] * 3,
        "payment_terms_days": [30] * 3,
        "po_number": ["PO-1", "PO-1", "PO-2"],
        "business_unit": ["Corp"] * 3,
        "cost_centre": ["CC-01"] * 3,
    })
    diag = DataQualityDiagnostics(df, config)
    result = diag.check_duplicate_invoice_risk()
    # INV-DUP + 500.0 appears twice → both rows are duplicates (value=2)
    assert result["value"] == 2
    assert result["pct"] > 0
    # 2/3 = 66.7% >> 2% amber threshold → RED
    assert result["status"] == "RED"


def test_weak_description_flags_misc(config):
    """Rows with 'misc' or 'services' (generic terms) are counted as weak."""
    df = pd.DataFrame({
        "transaction_id": ["TX-1", "TX-2", "TX-3"],
        "invoice_number": ["INV-1", "INV-2", "INV-3"],
        "raw_supplier_name": ["S1", "S2", "S3"],
        "canonical_supplier_id": ["s1", "s2", "s3"],
        "raw_line_description": ["misc", "services", "Professional consulting services for Q1 project"],
        "base_amount": [100.0, 200.0, 300.0],
        "category_l1": ["IT"] * 3,
        "payment_terms_days": [30] * 3,
        "po_number": ["PO-1"] * 3,
        "business_unit": ["Corp"] * 3,
        "cost_centre": ["CC-01"] * 3,
    })
    diag = DataQualityDiagnostics(df, config)
    result = diag.check_weak_descriptions()
    # "misc" and "services" are in generic terms set → 2 weak rows
    assert result["value"] == 2
    assert result["status"] in ("AMBER", "RED")


def test_scorecard_generates_without_error(config):
    """generate_scorecard() returns a non-empty string containing check names."""
    df = _clean_df()
    diag = DataQualityDiagnostics(df, config)
    diag.run_all()
    scorecard = diag.generate_scorecard()
    assert isinstance(scorecard, str)
    assert len(scorecard) > 100
    assert "Missing Supplier Name" in scorecard
    assert "Overall Data Quality Score" in scorecard


def test_all_9_checks_present_in_run_all(config):
    """run_all() must return exactly the 9 expected diagnostic checks."""
    df = _clean_df()
    diag = DataQualityDiagnostics(df, config)
    results = diag.run_all()
    assert len(results) == 9
    assert set(results.keys()) == _EXPECTED_CHECKS


def test_green_status_on_clean_data(config):
    """Checks that can be GREEN on clean data are GREEN."""
    df = _clean_df()
    diag = DataQualityDiagnostics(df, config)
    results = diag.run_all()
    assert results["missing_supplier_name"]["status"] == "GREEN"
    assert results["missing_payment_terms"]["status"] == "GREEN"
    assert results["missing_bu_cost_centre"]["status"] == "GREEN"
    assert results["duplicate_invoice_risk"]["status"] == "GREEN"


def test_red_status_on_dirty_data(config):
    """Dirty data must produce RED for missing supplier, uncategorised spend, and contract linkage."""
    df = _dirty_df()
    diag = DataQualityDiagnostics(df, config)
    results = diag.run_all()
    # 50% missing supplier names → RED (threshold 5%)
    assert results["missing_supplier_name"]["status"] == "RED"
    # 75% uncategorised spend → RED (threshold 15%)
    assert results["uncategorised_spend"]["status"] == "RED"
    # 100% spend with no PO and no contract_id → RED (threshold 60%)
    assert results["missing_contract_linkage"]["status"] == "RED"


def test_to_dataframe_returns_9_rows(config):
    """to_dataframe() returns a DataFrame with 9 rows, one per check."""
    df = _clean_df()
    diag = DataQualityDiagnostics(df, config)
    result_df = diag.to_dataframe()
    assert isinstance(result_df, pd.DataFrame)
    assert len(result_df) == 9
    assert "check" in result_df.columns
    assert "status" in result_df.columns
    assert "pct" in result_df.columns
    assert set(result_df["check"].tolist()) == _EXPECTED_CHECKS


def test_each_check_has_required_fields(config):
    """Every check result must contain value, pct, status, green_threshold, amber_threshold."""
    df = _clean_df()
    diag = DataQualityDiagnostics(df, config)
    results = diag.run_all()
    required_fields = {"value", "pct", "status", "green_threshold", "amber_threshold", "description", "remediation"}
    for name, result in results.items():
        missing = required_fields - set(result.keys())
        assert not missing, f"Check '{name}' is missing fields: {missing}"
        assert result["status"] in ("GREEN", "AMBER", "RED", "INFO", "WARN", "ALERT")
