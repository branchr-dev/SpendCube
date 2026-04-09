"""Tests for SpendCube ingestion pipeline."""

import math
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ingestion.cleaner import (
    DataCleaner,
    detect_document_type,
    detect_intercompany,
    detect_tax_line,
    parse_payment_terms,
)
from src.ingestion.column_mapper import ColumnMapper
from src.ingestion.currency_converter import CurrencyConverter
from src.ingestion.date_parser import parse_date
from src.ingestion.ingest import Ingestor

_FX_RATES_PATH = str(_PROJECT_ROOT / "data" / "reference" / "fx_rates.csv")
_SAMPLE_CSV_PATH = str(_PROJECT_ROOT / "data" / "input" / "sample.csv")
_EXCEL_EPOCH = date(1899, 12, 30)


# ---------------------------------------------------------------------------
# Date parser tests
# ---------------------------------------------------------------------------

def test_parse_date_ddmmyyyy():
    assert parse_date("15/03/2024") == date(2024, 3, 15)


def test_parse_date_iso():
    assert parse_date("2024-03-18") == date(2024, 3, 18)


def test_parse_date_dd_mon_yyyy():
    assert parse_date("20-Mar-2024") == date(2024, 3, 20)


def test_parse_date_ambiguous_slash():
    # "5/4/2024" — DD/MM/YYYY takes priority → 5th April 2024
    result = parse_date("5/4/2024")
    assert result == date(2024, 4, 5)


def test_parse_date_none_returns_none():
    assert parse_date(None) is None


def test_parse_date_empty_string_returns_none():
    assert parse_date("") is None


def test_parse_date_nan_returns_none():
    assert parse_date(float("nan")) is None


def test_parse_date_excel_serial():
    serial = 45369
    expected = _EXCEL_EPOCH + timedelta(days=serial)
    result = parse_date(serial)
    assert result == expected
    # Sanity check: serial 45369 maps to a plausible date in 2024
    assert result.year == 2024


def test_parse_date_nat_returns_none():
    assert parse_date(pd.NaT) is None


def test_parse_date_dateutil_fallback():
    # "March 15 2024" doesn't match any explicit format — dateutil should parse it
    result = parse_date("March 15 2024")
    assert result == date(2024, 3, 15)


def test_parse_date_date_object_passthrough():
    d = date(2024, 6, 1)
    assert parse_date(d) == d


# ---------------------------------------------------------------------------
# Currency converter tests
# ---------------------------------------------------------------------------

@pytest.fixture
def converter():
    return CurrencyConverter(_FX_RATES_PATH, base_currency="AUD")


def test_same_currency_returns_original(converter):
    amount = Decimal("1000.00")
    converted, rate, warning = converter.convert(amount, "AUD", date(2024, 3, 15))
    assert converted == amount
    assert rate == 1.0
    assert warning is None


def test_usd_to_aud_returns_reasonable_amount(converter):
    # DHL row: USD 8750 → should be 12 000–15 000 AUD based on 2024 rates
    converted, rate, warning = converter.convert(
        Decimal("8750.00"), "USD", date(2024, 2, 12)
    )
    assert 12_000 <= float(converted) <= 15_000
    assert rate is not None
    assert warning is None


def test_unknown_currency_returns_warning(converter):
    converted, rate, warning = converter.convert(
        Decimal("500.00"), "XYZ", date(2024, 2, 1)
    )
    # Amount unchanged, no rate, warning set
    assert converted == Decimal("500.00")
    assert rate is None
    assert warning is not None
    assert "UNKNOWN_CURRENCY_PAIR" in warning


def test_missing_month_uses_nearest(converter):
    # A date far in the future has no exact rate — nearest should be used and warning issued
    converted, rate, warning = converter.convert(
        Decimal("1000.00"), "USD", date(2030, 6, 1)
    )
    assert rate is not None
    assert warning is not None
    assert "RATE_ESTIMATE" in warning


# ---------------------------------------------------------------------------
# Data cleaner tests
# ---------------------------------------------------------------------------

def test_whitespace_stripped():
    df = pd.DataFrame({
        "invoice_number": ["  INV-001  "],
        "original_amount": [100.0],
    })
    cleaner = DataCleaner()
    result = cleaner.clean(df)
    assert result["invoice_number"].iloc[0] == "INV-001"


def test_null_variants_normalised():
    df = pd.DataFrame({
        "invoice_number": ["INV-001"],
        "original_amount": [100.0],
        "raw_supplier_name": ["N/A"],
        "raw_line_description": ["NULL"],
    })
    cleaner = DataCleaner()
    result = cleaner.clean(df)
    assert result["raw_supplier_name"].iloc[0] is np.nan or (
        isinstance(result["raw_supplier_name"].iloc[0], float)
        and math.isnan(result["raw_supplier_name"].iloc[0])
    )


def test_payment_terms_net30():
    assert parse_payment_terms("Net 30") == 30


def test_payment_terms_NET30_no_space():
    assert parse_payment_terms("NET30") == 30


def test_payment_terms_none():
    assert parse_payment_terms(None) is None


def test_detect_credit_note_negative_amount():
    row = pd.Series({"original_amount": -850.00, "invoice_number": "INV-2024-001"})
    assert detect_document_type(row) == "CREDIT_NOTE"


def test_detect_credit_note_cn_prefix():
    row = pd.Series({"original_amount": 100.00, "invoice_number": "CN-2024-001"})
    assert detect_document_type(row) == "CREDIT_NOTE"


def test_detect_intercompany():
    assert detect_intercompany("INTERCOMPANY - LEGAL") is True
    assert detect_intercompany("IC-AU-FINANCE") is True
    assert detect_intercompany("Acme Pty Ltd") is False


def test_detect_tax_line_gst():
    assert detect_tax_line("Tax adjustment - GST", None) is True
    assert detect_tax_line("GST charge", None) is True


def test_detect_tax_line_gl_balance_sheet():
    # GL starting with '2' indicates balance sheet → tax line
    assert detect_tax_line("Office supplies", "2100100") is True
    assert detect_tax_line("Office supplies", "6420100") is False


# ---------------------------------------------------------------------------
# Ingestion pipeline tests
# ---------------------------------------------------------------------------

@pytest.fixture
def ingestor(config):
    return Ingestor(config)


def test_ingest_sample_csv_returns_10_rows(ingestor):
    df = ingestor.ingest_file(_SAMPLE_CSV_PATH)
    assert len(df) == 10


def test_ingest_cn_row_is_credit_note(ingestor):
    df = ingestor.ingest_file(_SAMPLE_CSV_PATH)
    # CN-2024-001 row (Sodexo, -850.00) should be a credit note
    cn_rows = df[df["invoice_number"] == "CN-2024-001"]
    assert len(cn_rows) == 1
    assert cn_rows.iloc[0]["is_credit_note"] is True or cn_rows.iloc[0]["is_credit_note"] == 1


def test_ingest_intercompany_row_flagged(ingestor):
    df = ingestor.ingest_file(_SAMPLE_CSV_PATH)
    # INTERCOMPANY - LEGAL row
    ic_rows = df[df["invoice_number"] == "INV-2024-006"]
    assert len(ic_rows) == 1
    assert ic_rows.iloc[0]["is_intercompany"] is True or ic_rows.iloc[0]["is_intercompany"] == 1


def test_ingest_tax_row_flagged(ingestor):
    df = ingestor.ingest_file(_SAMPLE_CSV_PATH)
    # TAX-ADJ-001 row with GL 2100100
    tax_rows = df[df["invoice_number"] == "TAX-ADJ-001"]
    assert len(tax_rows) == 1
    assert tax_rows.iloc[0]["is_tax_line"] is True or tax_rows.iloc[0]["is_tax_line"] == 1


def test_ingest_usd_row_converted_to_aud(ingestor):
    df = ingestor.ingest_file(_SAMPLE_CSV_PATH)
    # DHL Express row: original USD, base_amount should be > original_amount
    dhl_rows = df[df["invoice_number"] == "INV-2024-007"]
    assert len(dhl_rows) == 1
    row = dhl_rows.iloc[0]
    assert str(row["original_currency"]) == "USD"
    base_amount = float(row["base_amount"])
    assert 12_000 <= base_amount <= 15_000


def test_ingest_all_rows_have_transaction_id(ingestor):
    df = ingestor.ingest_file(_SAMPLE_CSV_PATH)
    assert df["transaction_id"].notna().all()
    assert df["transaction_id"].nunique() == 10


def test_ingest_to_db_inserts_10_rows(ingestor, in_memory_engine):
    count = ingestor.ingest_to_db(_SAMPLE_CSV_PATH, in_memory_engine)
    assert count == 10


# ---------------------------------------------------------------------------
# Column mapper tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mapper(config):
    return ColumnMapper(config.column_mappings)


def test_column_mapper_detect_source_system(mapper, sample_df):
    detected = mapper.detect_source_system(sample_df.columns.tolist())
    assert detected == "DEFAULT"


def test_column_mapper_get_unmapped_fields(mapper, sample_df):
    unmapped = mapper.get_unmapped_required_fields(sample_df.columns.tolist(), "DEFAULT")
    assert unmapped == []


def test_column_mapper_unknown_system_fallback(mapper, sample_df):
    # Unknown source system falls back to DEFAULT mapping
    mapped = mapper.map_dataframe(sample_df, "UNKNOWN_SYSTEM")
    assert "raw_supplier_name" in mapped.columns
