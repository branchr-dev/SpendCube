"""SpendCube SQLAlchemy Core database setup — Postgres-compatible types only."""

from __future__ import annotations

import argparse
import json
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
)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def get_engine(db_path: str) -> Engine:
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------

def insert_transactions(engine: Engine, records: list[dict]) -> int:
    if not records:
        return 0
    # Serialise dict fields to JSON strings
    rows = []
    for rec in records:
        row = dict(rec)
        if isinstance(row.get("raw_data"), dict):
            row["raw_data"] = json.dumps(row["raw_data"])
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
