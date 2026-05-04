"""SpendCube SQLAlchemy Core database setup — Postgres-compatible types only."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import (
    Column,
    Engine,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
    func,
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

metadata = MetaData()

transactions_table = Table(
    "transactions",
    metadata,
    Column("transaction_id", Text, primary_key=True),
    Column("source_system", Text),
    Column("source_row_number", Integer),
    Column("ingested_at", Text),
    Column("last_modified_at", Text),
    Column("invoice_number", Text),
    Column("document_type", Text),
    Column("invoice_date", Text),
    Column("raw_supplier_name", Text),
    Column("raw_supplier_id", Text),
    Column("raw_line_description", Text),
    Column("original_amount", Float),
    Column("original_currency", Text),
    Column("base_amount", Float),
    Column("base_currency", Text),
    Column("fx_rate", Float),
    Column("gl_account", Text),
    Column("cost_centre", Text),
    Column("raw_payment_terms", Text),
    Column("payment_terms_days", Integer),
    Column("po_number", Text),
    Column("business_unit", Text),
    Column("plant_site", Text),
    Column("canonical_supplier_id", Text),
    Column("canonical_supplier_name", Text),
    Column("canonical_supplier_confidence", Float),
    Column("parent_company_id", Text),
    Column("parent_company_name", Text),
    Column("category_l1", Text),
    Column("category_l2", Text),
    Column("category_l3", Text),
    Column("unspsc_code", Text),
    Column("category_confidence", Float),
    Column("category_method", Text),
    Column("spend_type", Text),
    Column("addressability", Text),
    Column("managed_status", Text),
    Column("is_credit_note", Integer),
    Column("is_intercompany", Integer),
    Column("is_tax_line", Integer),
    Column("is_duplicate", Integer),
    Column("review_status", Text),
    Column("reviewer", Text),
    Column("review_notes", Text),
    Column("review_date", Text),
    Column("raw_data", Text),
    Column("engagement_id", Text, nullable=True),
    Column("legal_entity", Text, nullable=True),
    Column("vendor_country", Text, nullable=True),
    Column("plant_country", Text, nullable=True),
    Column("categorisation_status", Text, nullable=True),
    Column("manual_override_flag", Integer, nullable=True),
    Column("ai_classification_flag", Integer, nullable=True),
    Column("harmonised_payment_term", Text, nullable=True),
    Column("discount_percent", Float, nullable=True),
    Column("discount_days", Integer, nullable=True),
    Column("has_early_payment_discount", Integer, nullable=True),
    Column("payment_term_confidence", Float, nullable=True),
    Column("abc_segment", Text, nullable=True),
    Column("source_raw_id", Text, nullable=True),
    Column("unit_price", Float, nullable=True),
    Column("unit_of_measure", Text, nullable=True),
)

supplier_master_table = Table(
    "supplier_master",
    metadata,
    Column("canonical_supplier_id", Text, primary_key=True),
    Column("canonical_name", Text),
    Column("parent_company_id", Text),
    Column("parent_name", Text),
    Column("country", Text),
    Column("identifiers", Text),
    Column("created_at", Text),
    Column("updated_at", Text),
    Column("engagement_id", Text, nullable=True),
)

supplier_match_log_table = Table(
    "supplier_match_log",
    metadata,
    Column("id", Text, primary_key=True),
    Column("raw_supplier_name", Text),
    Column("raw_supplier_id", Text),
    Column("canonical_supplier_id", Text),
    Column("match_method", Text),
    Column("confidence", Float),
    Column("evidence", Text),
    Column("review_status", Text),
    Column("created_at", Text),
    Column("engagement_id", Text, nullable=True),
)

category_overrides_table = Table(
    "category_overrides",
    metadata,
    Column("id", Text, primary_key=True),
    Column("canonical_supplier_id", Text),
    Column("gl_account", Text),
    Column("override_l1", Text),
    Column("override_l2", Text),
    Column("override_l3", Text),
    Column("unspsc_code", Text),
    Column("reviewer", Text),
    Column("reason", Text),
    Column("created_at", Text),
    Column("engagement_id", Text, nullable=True),
)

audit_log_table = Table(
    "audit_log",
    metadata,
    Column("id", Text, primary_key=True),
    Column("table_name", Text),
    Column("record_id", Text),
    Column("field_name", Text),
    Column("old_value", Text),
    Column("new_value", Text),
    Column("changed_by", Text),
    Column("changed_at", Text),
    Column("engagement_id", Text, nullable=True),
)

ingestion_batches_table = Table(
    "ingestion_batches",
    metadata,
    Column("id", Text, primary_key=True),
    Column("engagement_id", Text),
    Column("filename", Text),
    Column("row_count", Integer),
    Column("new_rows", Integer),
    Column("duplicate_rows", Integer),
    Column("status", Text),
    Column("uploaded_at", Text),
    Column("completed_at", Text),
)

transactions_raw_table = Table(
    "transactions_raw",
    metadata,
    Column("id", Text, primary_key=True),
    Column("engagement_id", Text),
    Column("batch_id", Text),
    Column("source_row_hash", Text, unique=True),
    Column("pipeline_status", Text),
    Column("invoice_number", Text),
    Column("invoice_date", Text),
    Column("raw_supplier_name", Text),
    Column("base_amount", Float),
    Column("raw_data", Text),
    Column("created_at", Text),
)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def get_engine(db_url: str) -> Engine:
    if db_url.startswith("postgresql://") or db_url.startswith("postgresql+psycopg2://"):
        return create_engine(db_url, pool_pre_ping=True)
    elif db_url.startswith("sqlite://"):
        return create_engine(db_url, connect_args={"check_same_thread": False})
    else:
        return create_engine(
            f"sqlite:///{db_url}",
            connect_args={"check_same_thread": False},
        )


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------

def insert_transactions(engine: Engine, records: list[dict], engagement_id: Optional[str] = None) -> int:
    if not records:
        return 0
    rows = []
    for rec in records:
        row = dict(rec)
        if isinstance(row.get("raw_data"), dict):
            row["raw_data"] = json.dumps(row["raw_data"])
        if engagement_id is not None:
            row["engagement_id"] = engagement_id
        rows.append(row)
    with engine.begin() as conn:
        result = conn.execute(insert(transactions_table), rows)
    return result.rowcount


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def get_transactions(engine: Engine, filters: Optional[dict] = None) -> pd.DataFrame:
    stmt = select(transactions_table)
    if filters:
        for col, val in filters.items():
            stmt = stmt.where(transactions_table.c[col] == val)
    return pd.read_sql(stmt, engine)


def get_db_stats(engine: Engine) -> dict:
    tables = [
        transactions_table,
        supplier_master_table,
        supplier_match_log_table,
        category_overrides_table,
        audit_log_table,
    ]
    stats = {}
    with engine.connect() as conn:
        for tbl in tables:
            count = conn.execute(select(func.count()).select_from(tbl)).scalar()
            stats[tbl.name] = count
    return stats


# ---------------------------------------------------------------------------
# Batch ingestion helpers
# ---------------------------------------------------------------------------

def create_batch(engine: Engine, engagement_id: str, filename: str, row_count: int) -> str:
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            insert(ingestion_batches_table),
            {
                "id": batch_id,
                "engagement_id": engagement_id,
                "filename": filename,
                "row_count": row_count,
                "new_rows": None,
                "duplicate_rows": None,
                "status": "processing",
                "uploaded_at": now,
                "completed_at": None,
            },
        )
    return batch_id


def insert_raw_transactions(
    engine: Engine,
    records: list[dict],
    batch_id: str,
    engagement_id: str,
) -> tuple[int, int]:
    if not records:
        return 0, 0

    is_postgres = "postgresql" in str(engine.url)
    chunk_size = 5000
    total_new = 0
    total_dup = 0
    now = datetime.now(timezone.utc).isoformat()

    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        rows = [
            {
                "id": str(uuid.uuid4()),
                "engagement_id": engagement_id,
                "batch_id": batch_id,
                "pipeline_status": "queued",
                "created_at": now,
                **r,
            }
            for r in chunk
        ]

        if is_postgres:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(transactions_raw_table)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["source_row_hash"])
            )
        else:
            from sqlalchemy import insert as sa_insert

            stmt = sa_insert(transactions_raw_table).prefix_with("OR IGNORE").values(rows)

        with engine.begin() as conn:
            result = conn.execute(stmt)

        new_rows = result.rowcount if result.rowcount >= 0 else len(chunk)
        total_new += new_rows
        total_dup += len(chunk) - new_rows

    return total_new, total_dup


def get_queued_raw_rows(engine: Engine, engagement_id: str, batch_id: str) -> pd.DataFrame:
    stmt = select(transactions_raw_table).where(
        transactions_raw_table.c.pipeline_status == "queued",
        transactions_raw_table.c.engagement_id == engagement_id,
        transactions_raw_table.c.batch_id == batch_id,
    )
    return pd.read_sql(stmt, engine)


def mark_raw_rows_processed(engine: Engine, row_ids: list[str], status: str) -> None:
    if not row_ids:
        return
    stmt = (
        update(transactions_raw_table)
        .where(transactions_raw_table.c.id.in_(row_ids))
        .values(pipeline_status=status)
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def update_batch_status(
    engine: Engine,
    batch_id: str,
    status: str,
    new_rows: int,
    duplicate_rows: int,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    stmt = (
        update(ingestion_batches_table)
        .where(ingestion_batches_table.c.id == batch_id)
        .values(status=status, new_rows=new_rows, duplicate_rows=duplicate_rows, completed_at=now)
    )
    with engine.begin() as conn:
        conn.execute(stmt)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialise SpendCube SQLite database")
    parser.add_argument("--db-path", required=True, help="Path to SQLite database file")
    args = parser.parse_args()

    engine = get_engine(args.db_path)
    init_db(engine)
    stats = get_db_stats(engine)
    print(f"{len(stats)} tables created")
    for name, count in stats.items():
        print(f"  {name}: {count} rows")
