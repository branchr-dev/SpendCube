"""SpendCube pytest configuration and shared fixtures."""

import sys
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

# Ensure project root is on sys.path so src.* imports work from tests/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import load_config
from src.models.database import init_db


@pytest.fixture
def config():
    """Load config from config.yaml at the project root."""
    return load_config(str(_PROJECT_ROOT / "config.yaml"))


@pytest.fixture
def sample_df():
    """Return the 10-row messy sample dataset as a DataFrame.

    Column names match data/input/sample.csv exactly (raw source names).
    """
    return pd.read_csv(str(_PROJECT_ROOT / "data" / "input" / "sample.csv"))


@pytest.fixture
def in_memory_engine():
    """Return an in-memory SQLite engine with all tables initialised via init_db()."""
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


@pytest.fixture
def cube_df(in_memory_engine, config):
    """Return the full spend cube dict built from synthetic canonical transactions.

    Populates the in-memory engine with 10 transaction rows covering all
    Phase 4 scenarios (intercompany, tax, maverick, tail spend) then runs
    SpendCubeBuilder.build() to produce the cube dict.
    """
    from src.cube.builder import SpendCubeBuilder
    from src.models.database import insert_transactions

    rows = [
        {
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
        }
        for i in range(10)
    ]
    insert_transactions(in_memory_engine, rows)
    builder = SpendCubeBuilder(config, in_memory_engine)
    return builder.build()
