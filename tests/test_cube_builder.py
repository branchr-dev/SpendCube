"""Tests for SpendCube OLAP cube builder, metrics, and exporter."""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.cube.builder import SpendCubeBuilder, _payment_terms_bucket
from src.cube.exporter import CubeExporter
from src.cube.metrics import CubeMetrics
from src.models.database import init_db, insert_transactions

_EXPECTED_KEYS = {"transactions", "by_supplier", "by_category", "by_bu", "by_month", "by_payment_terms"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transactions(n=10):
    """Return n synthetic canonical transaction dicts covering all test scenarios.

    Rows:
      i % 3 == 0 → supplier_a
      i % 3 == 1 → supplier_b
      i % 3 == 2 → supplier_c
      i == 8     → is_tax_line = 1  (excluded from addressable)
      i == 9     → is_intercompany = 1 (excluded from addressable)
      i % 2 == 0 → has PO (not maverick)
      i % 2 == 1 → no PO (maverick candidate)
    """
    rows = []
    for i in range(n):
        rows.append({
            "transaction_id": f"TX-{i:03d}",
            "source_system": "TEST",
            "source_row_number": i,
            "ingested_at": "2024-04-01T00:00:00",
            "last_modified_at": "2024-04-01T00:00:00",
            "invoice_number": f"INV-{i:03d}",
            "document_type": "INVOICE",
            "invoice_date": "2024-03-15" if i < 5 else "2024-04-10",
            "raw_supplier_name": f"Supplier {chr(65 + i % 3)}",
            "raw_supplier_id": f"V-{i:03d}",
            "raw_line_description": f"Consulting and professional services item {i}",
            "original_amount": 1000.0 * (i + 1),
            "original_currency": "AUD",
            "base_amount": 1000.0 * (i + 1),
            "base_currency": "AUD",
            "fx_rate": 1.0,
            "gl_account": "6421",
            "cost_centre": "CC-01",
            "raw_payment_terms": "Net 30",
            "payment_terms_days": 30,
            "po_number": "PO-001" if i % 2 == 0 else None,
            "business_unit": "Corporate",
            "plant_site": "Sydney",
            "canonical_supplier_id": f"supplier_{chr(97 + i % 3)}",
            "canonical_supplier_name": f"Supplier {chr(65 + i % 3)}",
            "canonical_supplier_confidence": 0.95,
            "parent_company_id": None,
            "parent_company_name": None,
            "category_l1": "IT" if i % 2 == 0 else "Facilities",
            "category_l2": "Software",
            "category_l3": None,
            "unspsc_code": None,
            "category_confidence": 0.9,
            "category_method": "KEYWORD",
            "spend_type": None,
            "addressability": None,
            "managed_status": None,
            "is_credit_note": 0,
            "is_intercompany": 1 if i == 9 else 0,
            "is_tax_line": 1 if i == 8 else 0,
            "is_duplicate": 0,
            "review_status": None,
            "reviewer": None,
            "review_notes": None,
            "review_date": None,
            "raw_data": "{}",
        })
    return rows


@pytest.fixture
def engine_with_data():
    """In-memory SQLite engine with 10 synthetic transactions."""
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    insert_transactions(engine, _make_transactions())
    return engine


@pytest.fixture
def cube(engine_with_data, config):
    """Built spend cube dict from synthetic transactions."""
    builder = SpendCubeBuilder(config, engine_with_data)
    return builder.build()


# ---------------------------------------------------------------------------
# Builder tests
# ---------------------------------------------------------------------------

def test_build_returns_expected_keys(cube):
    assert set(cube.keys()) == _EXPECTED_KEYS


def test_by_supplier_aggregates_correctly(cube):
    by_sup = cube["by_supplier"]
    assert not by_sup.empty
    assert "canonical_supplier_name" in by_sup.columns
    assert "base_amount" in by_sup.columns
    # Addressable excludes i=8 (tax) and i=9 (intercompany) → 3 suppliers remain
    assert len(by_sup) <= 3
    # Total addressable spend should equal sum of rows 0-7 (i=8,9 excluded)
    expected_addr_spend = sum(1000.0 * (i + 1) for i in range(8))
    assert abs(by_sup["base_amount"].sum() - expected_addr_spend) < 0.01


def test_by_month_has_invoice_date_as_yyyy_mm(cube):
    by_month = cube["by_month"]
    assert not by_month.empty
    assert "invoice_month" in by_month.columns
    for val in by_month["invoice_month"].dropna():
        assert re.match(r"^\d{4}-\d{2}$", val), f"Unexpected format: {val}"
    months = set(by_month["invoice_month"].dropna().tolist())
    assert "2024-03" in months
    assert "2024-04" in months


def test_tail_spend_flag_computed(cube):
    txn = cube["transactions"]
    assert "is_tail_spend" in txn.columns
    # With 3 suppliers and small dataset fallback, at least one should be tail
    assert txn["is_tail_spend"].sum() > 0


def test_spend_concentration_top10_pct_between_0_and_1(engine_with_data, config):
    builder = SpendCubeBuilder(config, engine_with_data)
    builder.build()
    conc = builder.spend_concentration
    assert 0.0 <= conc["top_10_supplier_pct"] <= 1.0
    assert 0.0 <= conc["top_20_supplier_pct"] <= 1.0
    assert 0.0 <= conc["top_50_supplier_pct"] <= 1.0


def test_maverick_spend_excludes_po_rows(cube, config):
    """Maverick spend pct should be >0 because half of rows have no PO."""
    metrics = CubeMetrics(cube, config)
    kpis = metrics.compute_all()
    # i=1,3,5,7 have no PO → non-zero maverick spend
    assert kpis["maverick_spend_pct"] > 0.0
    assert kpis["maverick_spend_pct"] <= 1.0


def test_cube_excludes_intercompany_from_addressable(cube):
    """by_supplier total spend must be less than full transactions total (intercompany+tax excluded)."""
    txn = cube["transactions"]
    by_sup = cube["by_supplier"]
    txn_total = txn["base_amount"].sum()
    addr_total = by_sup["base_amount"].sum()
    # Row 8 (tax, 9000) and row 9 (intercompany, 10000) are excluded
    assert addr_total < txn_total


def test_build_with_empty_db_returns_empty_cube(config):
    """Builder on empty DB returns dict of empty DataFrames, one per key."""
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    builder = SpendCubeBuilder(config, engine)
    cube = builder.build()
    assert set(cube.keys()) == _EXPECTED_KEYS
    for df in cube.values():
        assert isinstance(df, pd.DataFrame)
        assert df.empty


def test_time_dimensions_added_to_transactions(cube):
    txn = cube["transactions"]
    assert "invoice_year" in txn.columns
    assert "invoice_month" in txn.columns
    assert "invoice_quarter" in txn.columns
    assert (txn["invoice_year"] == 2024).all()
    # Quarter should match YYYY-Q1/Q2/Q3/Q4 pattern
    for val in txn["invoice_quarter"].dropna():
        assert re.match(r"^\d{4}-Q[1-4]$", val), f"Unexpected quarter format: {val}"


def test_by_category_groups_by_category_l1(cube):
    by_cat = cube["by_category"]
    assert "category_l1" in by_cat.columns
    assert not by_cat.empty
    categories = set(by_cat["category_l1"].tolist())
    # IT (even rows) and Facilities (odd rows) both appear
    assert "IT" in categories
    assert "Facilities" in categories


def test_metrics_compute_all_returns_positive_totals(cube, config):
    metrics = CubeMetrics(cube, config)
    kpis = metrics.compute_all()
    assert kpis["total_spend"] > 0
    assert kpis["total_suppliers"] > 0
    assert kpis["total_invoices"] > 0
    assert kpis["avg_transaction_size"] > 0


def test_metrics_hhi_is_valid_range(cube, config):
    """HHI must be between 0 and 10000 (monopoly = 10000)."""
    metrics = CubeMetrics(cube, config)
    kpis = metrics.compute_all()
    assert 0 <= kpis["hhi"] <= 10_000


def test_payment_terms_bucket_boundaries():
    """_payment_terms_bucket maps day counts to the correct string labels."""
    assert _payment_terms_bucket(0) == "0-14"
    assert _payment_terms_bucket(14) == "0-14"
    assert _payment_terms_bucket(15) == "15-30"
    assert _payment_terms_bucket(30) == "15-30"
    assert _payment_terms_bucket(31) == "31-45"
    assert _payment_terms_bucket(46) == "46-60"
    assert _payment_terms_bucket(61) == "60+"
    assert _payment_terms_bucket(None) == "Unknown"


def test_standard_tail_spend_with_many_suppliers(config):
    """With 10+ suppliers the standard cumulative algorithm is used (not median fallback)."""
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    # Create 12 unique suppliers with very unequal spend so tail spend is non-trivial.
    rows = []
    for i in range(12):
        rows.append({
            "transaction_id": f"TX-{i:03d}",
            "source_system": "TEST", "source_row_number": i,
            "ingested_at": "2024-04-01T00:00:00", "last_modified_at": "2024-04-01T00:00:00",
            "invoice_number": f"INV-{i:03d}", "document_type": "INVOICE",
            "invoice_date": "2024-03-15",
            "raw_supplier_name": f"Supplier {i}",
            "raw_supplier_id": f"V-{i:03d}",
            "raw_line_description": f"Services item {i}",
            "original_amount": float(10_000 * (12 - i)),  # Supplier 0 has most spend
            "original_currency": "AUD",
            "base_amount": float(10_000 * (12 - i)),
            "base_currency": "AUD", "fx_rate": 1.0,
            "gl_account": "6421", "cost_centre": "CC-01",
            "raw_payment_terms": "Net 30", "payment_terms_days": 30,
            "po_number": "PO-001", "business_unit": "Corporate", "plant_site": "Sydney",
            "canonical_supplier_id": f"supplier_{i:02d}",
            "canonical_supplier_name": f"Supplier {i}",
            "canonical_supplier_confidence": 0.95,
            "parent_company_id": None, "parent_company_name": None,
            "category_l1": "IT", "category_l2": None, "category_l3": None,
            "unspsc_code": None, "category_confidence": 0.9, "category_method": "KEYWORD",
            "spend_type": None, "addressability": None, "managed_status": None,
            "is_credit_note": 0, "is_intercompany": 0, "is_tax_line": 0, "is_duplicate": 0,
            "review_status": None, "reviewer": None, "review_notes": None, "review_date": None,
            "raw_data": "{}",
        })
    insert_transactions(engine, rows)
    builder = SpendCubeBuilder(config, engine)
    cube = builder.build()
    txn = cube["transactions"]
    assert "is_tail_spend" in txn.columns
    # With 12 suppliers, some should be tail (bottom suppliers by spend)
    assert txn["is_tail_spend"].sum() > 0


# ---------------------------------------------------------------------------
# CubeExporter tests
# ---------------------------------------------------------------------------

def test_exporter_export_parquet_writes_all_keys(cube, config, tmp_path):
    """export_parquet() writes one .parquet file per cube key."""
    exporter = CubeExporter(str(tmp_path), config=config)
    paths = exporter.export_parquet(cube)
    assert set(paths.keys()) == _EXPECTED_KEYS
    for key, path in paths.items():
        assert Path(path).exists(), f"{key}.parquet not found"
        assert Path(path).stat().st_size > 0


def test_exporter_load_parquet_roundtrip(cube, config, tmp_path):
    """load_parquet() returns the same number of rows as the original DataFrame."""
    exporter = CubeExporter(str(tmp_path), config=config)
    exporter.export_parquet(cube)
    loaded = exporter.load_parquet("transactions")
    assert isinstance(loaded, pd.DataFrame)
    assert len(loaded) == len(cube["transactions"])


def test_exporter_export_csv_writes_files(cube, config, tmp_path):
    """export_csv() writes one .csv file per cube key under output_dir/csv/."""
    exporter = CubeExporter(str(tmp_path), config=config)
    paths = exporter.export_csv(cube)
    for key, path in paths.items():
        assert Path(path).exists(), f"{key}.csv not found"
    assert set(paths.keys()) == _EXPECTED_KEYS


def test_exporter_creates_nested_output_dir(cube, config, tmp_path):
    """CubeExporter creates the output directory if it does not exist."""
    new_dir = tmp_path / "nested" / "output"
    exporter = CubeExporter(str(new_dir), config=config)
    paths = exporter.export_parquet(cube)
    assert new_dir.exists()
    assert len(paths) == len(_EXPECTED_KEYS)


def test_exporter_export_excel_writes_workbook(cube, config, tmp_path):
    """export_excel() writes a single .xlsx file containing all cube sheets."""
    exporter = CubeExporter(str(tmp_path), config=config)
    excel_path = exporter.export_excel(cube, filename="test_cube.xlsx")
    assert Path(excel_path).exists()
    assert Path(excel_path).stat().st_size > 0
    # Verify all keys appear as sheets in the workbook
    import openpyxl
    wb = openpyxl.load_workbook(excel_path)
    sheet_names = set(wb.sheetnames)
    for key in _EXPECTED_KEYS:
        assert key[:31] in sheet_names, f"Sheet '{key}' not found in workbook"


# ---------------------------------------------------------------------------
# Metrics edge cases
# ---------------------------------------------------------------------------

def test_working_capital_opportunity_non_negative(cube, config):
    """working_capital_opportunity() must return a non-negative float."""
    metrics = CubeMetrics(cube, config)
    opp = metrics.working_capital_opportunity(target_days=45, wacc=0.08)
    assert isinstance(opp, float)
    assert opp >= 0.0


def test_metrics_tail_spend_and_supplier_count(cube, config):
    """tail_spend_pct must be in [0,1] and tail_supplier_count >= 0."""
    metrics = CubeMetrics(cube, config)
    kpis = metrics.compute_all()
    assert 0.0 <= kpis["tail_spend_pct"] <= 1.0
    assert kpis["tail_supplier_count"] >= 0


def test_metrics_addressable_excludes_intercompany(cube, config):
    """total_spend in metrics (addressable) must be less than full transactions sum."""
    metrics = CubeMetrics(cube, config)
    kpis = metrics.compute_all()
    txn_total = cube["transactions"]["base_amount"].sum()
    # Rows 8 (tax) and 9 (intercompany) are excluded from addressable spend
    assert kpis["total_spend"] < txn_total


# ---------------------------------------------------------------------------
# Pipeline integration test
# ---------------------------------------------------------------------------

def test_pipeline_runs_end_to_end(tmp_path):
    """run_pipeline() returns a result dict with kpis and export_paths."""
    from sqlalchemy import create_engine as _engine
    from src.cube.pipeline import run_pipeline
    from src.models.database import init_db as _init
    from src.models.database import insert_transactions as _insert

    db_path = str(tmp_path / "pipe_test.db")
    engine = _engine(f"sqlite:///{db_path}")
    _init(engine)

    rows = [
        {
            "transaction_id": f"TX-{i}", "source_system": "TEST",
            "source_row_number": i, "ingested_at": "2024-04-01T00:00:00",
            "last_modified_at": "2024-04-01T00:00:00",
            "invoice_number": f"INV-{i}", "document_type": "INVOICE",
            "invoice_date": "2024-03-15",
            "raw_supplier_name": f"Supplier {i}", "raw_supplier_id": f"V-{i}",
            "raw_line_description": f"Services item {i}",
            "original_amount": 500.0, "original_currency": "AUD",
            "base_amount": 500.0, "base_currency": "AUD", "fx_rate": 1.0,
            "gl_account": "6421", "cost_centre": "CC-01",
            "raw_payment_terms": "Net 30", "payment_terms_days": 30,
            "po_number": "PO-1", "business_unit": "Corp", "plant_site": "SYD",
            "canonical_supplier_id": f"s_{i}", "canonical_supplier_name": f"Supplier {i}",
            "canonical_supplier_confidence": 0.95,
            "parent_company_id": None, "parent_company_name": None,
            "category_l1": "IT", "category_l2": None, "category_l3": None,
            "unspsc_code": None, "category_confidence": 0.9, "category_method": "KEYWORD",
            "spend_type": None, "addressability": None, "managed_status": None,
            "is_credit_note": 0, "is_intercompany": 0, "is_tax_line": 0, "is_duplicate": 0,
            "review_status": None, "reviewer": None, "review_notes": None,
            "review_date": None, "raw_data": "{}",
        }
        for i in range(5)
    ]
    _insert(engine, rows)

    output_dir = str(tmp_path / "output")
    result = run_pipeline(
        db_path,
        config_path=str(_PROJECT_ROOT / "config.yaml"),
        output_dir=output_dir,
    )

    assert "kpis" in result
    assert "export_paths" in result
    assert "diagnostics_results" in result
    assert result["kpis"]["total_spend"] > 0
    assert len(result["export_paths"]) == len(_EXPECTED_KEYS)
