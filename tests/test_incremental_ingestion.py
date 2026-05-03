"""Tests for incremental ingestion — dedup, batch tracking, queued rows."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import select

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ingestion.ingest import Ingestor
from src.models.database import ingestion_batches_table, transactions_raw_table


_CSV_CONTENT = (
    "VENDOR_NAME,VENDOR_NUM,INV_NO,INV_DATE,LINE_DESC,AMT,CCY,GL_CODE,COST_CTR,PAY_TERMS,PO_NUM,BUS_UNIT,SITE\n"
    "Acme Corp,V-001,INV-001,15/03/2024,Office supplies,100.00,AUD,6421,CC-01,Net 30,PO-001,Corporate,Sydney\n"
    "Bravo Ltd,V-002,INV-002,16/03/2024,IT equipment,200.00,AUD,6444,CC-02,Net 30,PO-002,Corporate,Melbourne\n"
    "Charlie Pty,V-003,INV-003,17/03/2024,Catering services,300.00,AUD,6512,CC-03,Net 30,PO-003,Operations,Brisbane\n"
    "Delta Inc,V-004,INV-004,18/03/2024,Freight charges,400.00,AUD,6301,CC-04,Net 14,PO-004,Operations,Perth\n"
    "Echo Group,V-005,INV-005,19/03/2024,Software license,500.00,AUD,6444,CC-05,Net 30,PO-005,Corporate,Sydney\n"
)

_ENGAGEMENT_ID = "test-engagement-001"


@pytest.fixture
def synthetic_csv(tmp_path):
    csv_file = tmp_path / "test_5_rows.csv"
    csv_file.write_text(_CSV_CONTENT)
    return str(csv_file)


@pytest.fixture
def ingestor(config):
    return Ingestor(config)


# ---------------------------------------------------------------------------
# Hash tests
# ---------------------------------------------------------------------------

def test_source_row_hash_stability():
    row = {"a": 1, "b": "x"}
    h1 = Ingestor.compute_source_row_hash(row)
    h2 = Ingestor.compute_source_row_hash(row)
    assert h1 == h2
    assert len(h1) == 64


def test_source_row_hash_uniqueness():
    h1 = Ingestor.compute_source_row_hash({"a": 1, "b": "x"})
    h2 = Ingestor.compute_source_row_hash({"a": 2, "b": "x"})
    assert h1 != h2


# ---------------------------------------------------------------------------
# Incremental ingestion tests
# ---------------------------------------------------------------------------

def test_ingest_to_raw_new_rows(ingestor, in_memory_engine, synthetic_csv):
    result = ingestor.ingest_to_raw(synthetic_csv, in_memory_engine, _ENGAGEMENT_ID)

    assert result["new_rows"] == 5
    assert result["duplicate_rows"] == 0

    with in_memory_engine.connect() as conn:
        rows = conn.execute(
            select(transactions_raw_table).where(
                transactions_raw_table.c.engagement_id == _ENGAGEMENT_ID
            )
        ).fetchall()

    assert len(rows) == 5
    assert all(r.pipeline_status == "queued" for r in rows)


def test_ingest_to_raw_dedup(ingestor, in_memory_engine, synthetic_csv):
    ingestor.ingest_to_raw(synthetic_csv, in_memory_engine, _ENGAGEMENT_ID)
    result = ingestor.ingest_to_raw(synthetic_csv, in_memory_engine, _ENGAGEMENT_ID)

    assert result["new_rows"] == 0
    assert result["duplicate_rows"] == 5

    with in_memory_engine.connect() as conn:
        rows = conn.execute(select(transactions_raw_table)).fetchall()

    assert len(rows) == 5


def test_batch_tracking(ingestor, in_memory_engine, synthetic_csv):
    result = ingestor.ingest_to_raw(synthetic_csv, in_memory_engine, _ENGAGEMENT_ID)
    batch_id = result["batch_id"]

    with in_memory_engine.connect() as conn:
        batch = conn.execute(
            select(ingestion_batches_table).where(
                ingestion_batches_table.c.id == batch_id
            )
        ).fetchone()

    assert batch is not None
    assert batch.status == "done"
    assert batch.new_rows == 5
    assert batch.duplicate_rows == 0
