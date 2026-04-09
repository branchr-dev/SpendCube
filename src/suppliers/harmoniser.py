"""SpendCube supplier harmonisation pipeline entry point."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import Engine, insert, select

from src.models.database import supplier_master_table


def build_supplier_master(
    raw_suppliers: pd.DataFrame,
    engine: Engine,
    config: dict,
) -> pd.DataFrame:
    """Build the canonical supplier_master table from raw supplier data.

    For each unique normalised_name in raw_suppliers, generates a canonical
    supplier entry and inserts it into supplier_master if not already present.
    Idempotent: existing entries are skipped, not updated.

    Args:
        raw_suppliers: DataFrame with columns:
            - raw_supplier_name: str
            - raw_supplier_id: str | None
            - normalised_name: str (pre-computed)
        engine: SQLAlchemy engine (SQLite in Phase 2)
        config: Pipeline config dict (not used in this function but kept for
                interface consistency with the orchestrator)

    Returns:
        DataFrame with columns: canonical_supplier_id, canonical_name,
        normalised_name — covering both newly inserted and pre-existing entries.
    """
    if raw_suppliers.empty:
        return pd.DataFrame(columns=["canonical_supplier_id", "canonical_name", "normalised_name"])

    # ------------------------------------------------------------------
    # Step 1: Fetch existing supplier_master entries
    # ------------------------------------------------------------------
    with engine.connect() as conn:
        existing_rows = conn.execute(
            select(
                supplier_master_table.c.canonical_supplier_id,
                supplier_master_table.c.canonical_name,
            )
        ).fetchall()

    existing_ids: set[str] = {row[0] for row in existing_rows}
    existing_records: list[dict] = [
        {"canonical_supplier_id": row[0], "canonical_name": row[1]}
        for row in existing_rows
    ]

    # ------------------------------------------------------------------
    # Step 2: Group by normalised_name to build canonical entries
    # ------------------------------------------------------------------
    now = datetime.now(tz=timezone.utc).isoformat()
    new_records: list[dict] = []
    output_rows: list[dict] = []

    for normalised_name, group in raw_suppliers.groupby("normalised_name", sort=False):
        canonical_supplier_id = hashlib.sha256(
            normalised_name.encode()
        ).hexdigest()[:12]

        # Most-common raw_supplier_name (title-cased) as canonical_name
        canonical_name = (
            group["raw_supplier_name"]
            .value_counts()
            .idxmax()
            .strip()
            .title()
        )

        output_rows.append({
            "canonical_supplier_id": canonical_supplier_id,
            "canonical_name": canonical_name,
            "normalised_name": normalised_name,
        })

        if canonical_supplier_id in existing_ids:
            continue  # idempotent: skip existing entries

        # Collect unique raw_supplier_ids (exclude None / NaN)
        raw_ids = sorted(
            {
                str(v)
                for v in group["raw_supplier_id"].dropna().unique()
                if str(v).strip()
            }
        )

        new_records.append({
            "canonical_supplier_id": canonical_supplier_id,
            "canonical_name": canonical_name,
            "parent_company_id": None,
            "parent_name": None,
            "country": None,
            "identifiers": json.dumps({"raw_ids": raw_ids}),
            "created_at": now,
            "updated_at": now,
        })

    # ------------------------------------------------------------------
    # Step 3: Bulk insert new entries
    # ------------------------------------------------------------------
    if new_records:
        with engine.begin() as conn:
            conn.execute(insert(supplier_master_table), new_records)

    return pd.DataFrame(output_rows, columns=["canonical_supplier_id", "canonical_name", "normalised_name"])
