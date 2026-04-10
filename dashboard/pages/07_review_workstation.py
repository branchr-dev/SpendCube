"""SpendCube analyst review workstation dashboard page."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, select, update
from sqlalchemy import insert as sa_insert

from src.models.database import (
    audit_log_table,
    supplier_master_table,
    supplier_match_log_table,
    transactions_table,
)

_DB_PATH = "data/db/spend_cube.db"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_engine():
    db_path = Path(_DB_PATH)
    if not db_path.exists():
        return None
    return create_engine(
        f"sqlite:///{_DB_PATH}",
        connect_args={"check_same_thread": False},
    )


def _insert_audit_log(
    engine,
    table_name: str,
    record_id: str,
    field_name: str,
    old_value: str,
    new_value: str,
    changed_by: str = "reviewer",
) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            sa_insert(audit_log_table),
            [
                {
                    "id": str(uuid4()),
                    "table_name": table_name,
                    "record_id": record_id,
                    "field_name": field_name,
                    "old_value": old_value,
                    "new_value": new_value,
                    "changed_by": changed_by,
                    "changed_at": now,
                }
            ],
        )


# ---------------------------------------------------------------------------
# Data loading (cached — cleared after any DB mutation)
# ---------------------------------------------------------------------------

@st.cache_data
def _load_pending_supplier_matches() -> pd.DataFrame:
    """Load PENDING supplier match log rows with canonical name and total spend."""
    engine = _get_engine()
    if engine is None:
        return pd.DataFrame()

    match_df = pd.read_sql(
        select(supplier_match_log_table).where(
            supplier_match_log_table.c.review_status == "PENDING"
        ),
        engine,
    )

    if match_df.empty:
        return match_df

    # Join supplier_master for canonical_supplier_name
    master_df = pd.read_sql(
        select(
            supplier_master_table.c.canonical_supplier_id,
            supplier_master_table.c.canonical_name,
        ),
        engine,
    )
    if not master_df.empty:
        match_df = match_df.merge(master_df, on="canonical_supplier_id", how="left")
        match_df["canonical_supplier_name"] = match_df["canonical_name"].fillna(
            match_df["canonical_supplier_id"]
        )
    else:
        match_df["canonical_supplier_name"] = match_df["canonical_supplier_id"]

    # Join transactions for total spend per raw supplier name
    txn_df = pd.read_sql(
        select(
            transactions_table.c.raw_supplier_name,
            transactions_table.c.base_amount,
        ).where(transactions_table.c.base_amount.isnot(None)),
        engine,
    )
    if not txn_df.empty:
        spend_df = (
            txn_df.groupby("raw_supplier_name")["base_amount"]
            .sum()
            .reset_index()
            .rename(columns={"base_amount": "total_spend"})
        )
        match_df = match_df.merge(spend_df, on="raw_supplier_name", how="left")
    else:
        match_df["total_spend"] = 0.0

    match_df["total_spend"] = match_df["total_spend"].fillna(0.0)

    # Sort: confidence asc (lowest first), spend desc
    match_df = match_df.sort_values(
        ["confidence", "total_spend"], ascending=[True, False]
    ).reset_index(drop=True)

    return match_df


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _approve_match(
    match_id: str,
    raw_supplier_name: str,
    canonical_supplier_id: str,
    canonical_supplier_name: str,
) -> None:
    engine = _get_engine()
    if engine is None:
        return

    with engine.begin() as conn:
        conn.execute(
            update(supplier_match_log_table)
            .where(supplier_match_log_table.c.id == match_id)
            .values(review_status="APPROVED")
        )

    _insert_audit_log(
        engine, "supplier_match_log", match_id,
        "review_status", "PENDING", "APPROVED",
    )

    with engine.begin() as conn:
        conn.execute(
            update(transactions_table)
            .where(transactions_table.c.raw_supplier_name == raw_supplier_name)
            .values(
                canonical_supplier_id=canonical_supplier_id,
                canonical_supplier_name=canonical_supplier_name,
            )
        )

    _insert_audit_log(
        engine, "transactions", raw_supplier_name,
        "canonical_supplier_id", "", canonical_supplier_id,
    )

    st.cache_data.clear()


def _reject_match(match_id: str) -> None:
    engine = _get_engine()
    if engine is None:
        return

    with engine.begin() as conn:
        conn.execute(
            update(supplier_match_log_table)
            .where(supplier_match_log_table.c.id == match_id)
            .values(review_status="REJECTED")
        )

    _insert_audit_log(
        engine, "supplier_match_log", match_id,
        "review_status", "PENDING", "REJECTED",
    )

    st.cache_data.clear()


def _override_match(
    match_id: str,
    raw_supplier_name: str,
    override_name: str,
) -> None:
    engine = _get_engine()
    if engine is None:
        return

    canonical_name = override_name.strip().title()
    normalised = override_name.strip().lower()
    canonical_supplier_id = hashlib.sha256(normalised.encode()).hexdigest()[:12]
    now = datetime.now(tz=timezone.utc).isoformat()

    # Create supplier_master entry if it doesn't already exist
    with engine.connect() as conn:
        existing = conn.execute(
            select(supplier_master_table.c.canonical_supplier_id).where(
                supplier_master_table.c.canonical_supplier_id == canonical_supplier_id
            )
        ).fetchone()

    if not existing:
        with engine.begin() as conn:
            conn.execute(
                sa_insert(supplier_master_table),
                [
                    {
                        "canonical_supplier_id": canonical_supplier_id,
                        "canonical_name": canonical_name,
                        "parent_company_id": None,
                        "parent_name": None,
                        "country": None,
                        "identifiers": "{}",
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
            )

    with engine.begin() as conn:
        conn.execute(
            update(supplier_match_log_table)
            .where(supplier_match_log_table.c.id == match_id)
            .values(
                review_status="APPROVED",
                canonical_supplier_id=canonical_supplier_id,
            )
        )

    _insert_audit_log(
        engine, "supplier_match_log", match_id,
        "review_status", "PENDING", "APPROVED (OVERRIDE)",
    )

    with engine.begin() as conn:
        conn.execute(
            update(transactions_table)
            .where(transactions_table.c.raw_supplier_name == raw_supplier_name)
            .values(
                canonical_supplier_id=canonical_supplier_id,
                canonical_supplier_name=canonical_name,
            )
        )

    _insert_audit_log(
        engine, "transactions", raw_supplier_name,
        "canonical_supplier_id", "", canonical_supplier_id,
    )

    st.cache_data.clear()


# ---------------------------------------------------------------------------
# Supplier Match Review section
# ---------------------------------------------------------------------------

def _supplier_match_review_section() -> None:
    st.subheader("Supplier Match Review")

    matches_df = _load_pending_supplier_matches()
    pending_count = len(matches_df)

    st.metric("Matches Pending Review", str(pending_count))

    if matches_df.empty:
        st.success("No pending supplier matches — queue is clear.")
        return

    for _, row in matches_df.iterrows():
        match_id = str(row["id"])
        raw_name = str(row.get("raw_supplier_name", ""))
        raw_id = str(row.get("raw_supplier_id") or "")
        canonical_id = str(row.get("canonical_supplier_id", ""))
        canonical_name = str(row.get("canonical_supplier_name") or canonical_id)
        confidence = float(row.get("confidence", 0.0))
        match_method = str(row.get("match_method", ""))
        evidence = str(row.get("evidence", ""))
        total_spend = float(row.get("total_spend", 0.0))

        label = f"{raw_name} → {canonical_name} (conf: {confidence:.2f})"

        with st.expander(label):
            info_col, spend_col = st.columns([3, 1])
            with info_col:
                st.markdown(f"**Raw Supplier ID:** {raw_id or '—'}")
                st.markdown(f"**Match Method:** {match_method}")
                st.markdown(f"**Evidence:** `{evidence}`")
                st.markdown(f"**Proposed Canonical:** {canonical_name}")
            with spend_col:
                st.metric("Total Spend (AUD)", f"{total_spend:,.0f}")

            st.markdown("---")

            approve_col, reject_col, override_col = st.columns(3)

            with approve_col:
                if st.button("✅ Approve", key=f"approve_{match_id}"):
                    _approve_match(match_id, raw_name, canonical_id, canonical_name)
                    st.rerun()

            with reject_col:
                if st.button("❌ Reject", key=f"reject_{match_id}"):
                    _reject_match(match_id)
                    st.rerun()

            with override_col:
                with st.form(key=f"override_form_{match_id}"):
                    override_input = st.text_input(
                        "Manual canonical name",
                        value=canonical_name,
                        key=f"override_input_{match_id}",
                    )
                    if st.form_submit_button("✏️ Override"):
                        if override_input.strip():
                            _override_match(match_id, raw_name, override_input)
                            st.rerun()
                        else:
                            st.warning("Please enter a canonical name.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Review Workstation")

    engine = _get_engine()
    if engine is None:
        st.error(
            f"Database not found at `{_DB_PATH}`. "
            "Run the full pipeline first:\n\n"
            "```bash\nmake ingest && make harmonise && make categorise && make build-cube\n```"
        )
        return

    _supplier_match_review_section()

    # TODO: US-006 — category review queue and overrides sections


if __name__ == "__main__":
    main()
