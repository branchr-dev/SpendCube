"""SpendCube analyst review workstation dashboard page."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy import insert as sa_insert

from src.models.database import (
    audit_log_table,
    category_overrides_table,
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
# Data loading — category review
# ---------------------------------------------------------------------------

_UNSPSC_PATH = "data/reference/unspsc_v24.csv"


@st.cache_data
def _load_low_confidence_transactions(limit: int = 50) -> pd.DataFrame:
    """Load transactions where category_confidence < 0.60, sorted by abs(base_amount) desc."""
    engine = _get_engine()
    if engine is None:
        return pd.DataFrame()
    df = pd.read_sql(
        select(transactions_table).where(
            (transactions_table.c.category_confidence < 0.60)
            | transactions_table.c.category_confidence.is_(None)
        ),
        engine,
    )
    if df.empty:
        return df
    df["abs_amount"] = df["base_amount"].abs().fillna(0.0)
    df = df.sort_values("abs_amount", ascending=False).head(limit).reset_index(drop=True)
    return df


@st.cache_data
def _load_category_options() -> tuple[list[str], dict[str, list[str]]]:
    """Return (l1_list, {l1: [l2, ...]}) derived from UNSPSC reference CSV."""
    try:
        unspsc = pd.read_csv(_UNSPSC_PATH)
        l1_list = sorted(unspsc["segment_name"].dropna().unique().tolist())
        l1_to_l2: dict[str, list[str]] = {}
        for l1, grp in unspsc.groupby("segment_name"):
            l1_to_l2[l1] = sorted(grp["family_name"].dropna().unique().tolist())
        return l1_list, l1_to_l2
    except Exception:
        return [], {}


@st.cache_data
def _load_category_overrides() -> pd.DataFrame:
    engine = _get_engine()
    if engine is None:
        return pd.DataFrame()
    return pd.read_sql(select(category_overrides_table), engine)


@st.cache_data
def _load_audit_log(limit: int = 50) -> pd.DataFrame:
    engine = _get_engine()
    if engine is None:
        return pd.DataFrame()
    df = pd.read_sql(select(audit_log_table), engine)
    if df.empty:
        return df
    df = df.sort_values("changed_at", ascending=False).head(limit).reset_index(drop=True)
    return df[["table_name", "field_name", "old_value", "new_value", "changed_by", "changed_at"]]


# ---------------------------------------------------------------------------
# Actions — category review
# ---------------------------------------------------------------------------

def _override_category(
    transaction_id: str,
    canonical_supplier_id: str,
    gl_account: str | None,
    old_l1: str | None,
    new_l1: str,
    new_l2: str,
) -> None:
    engine = _get_engine()
    if engine is None:
        return

    now = datetime.now(tz=timezone.utc).isoformat()
    override_id = str(uuid4())

    # Insert category_overrides row
    with engine.begin() as conn:
        conn.execute(
            sa_insert(category_overrides_table),
            [
                {
                    "id": override_id,
                    "canonical_supplier_id": canonical_supplier_id or None,
                    "gl_account": gl_account or None,
                    "override_l1": new_l1,
                    "override_l2": new_l2,
                    "override_l3": None,
                    "unspsc_code": None,
                    "reviewer": "manual",
                    "reason": "reviewer override",
                    "created_at": now,
                }
            ],
        )

    # Update the transaction row
    with engine.begin() as conn:
        conn.execute(
            update(transactions_table)
            .where(transactions_table.c.transaction_id == transaction_id)
            .values(
                category_l1=new_l1,
                category_l2=new_l2,
                category_method="MANUAL",
                category_confidence=1.0,
            )
        )

    _insert_audit_log(
        engine, "transactions", transaction_id,
        "category_l1", old_l1 or "", new_l1,
    )

    st.cache_data.clear()


def _delete_category_override(override_id: str) -> None:
    engine = _get_engine()
    if engine is None:
        return

    with engine.begin() as conn:
        conn.execute(
            delete(category_overrides_table).where(
                category_overrides_table.c.id == override_id
            )
        )

    _insert_audit_log(
        engine, "category_overrides", override_id,
        "id", override_id, "(deleted)",
    )

    st.cache_data.clear()


def _add_category_override_rule(
    canonical_supplier_id: str | None,
    gl_account: str | None,
    override_l1: str,
    override_l2: str,
    reason: str,
) -> None:
    engine = _get_engine()
    if engine is None:
        return

    now = datetime.now(tz=timezone.utc).isoformat()
    override_id = str(uuid4())

    with engine.begin() as conn:
        conn.execute(
            sa_insert(category_overrides_table),
            [
                {
                    "id": override_id,
                    "canonical_supplier_id": canonical_supplier_id or None,
                    "gl_account": gl_account or None,
                    "override_l1": override_l1,
                    "override_l2": override_l2,
                    "override_l3": None,
                    "unspsc_code": None,
                    "reviewer": "manual",
                    "reason": reason or "manual rule",
                    "created_at": now,
                }
            ],
        )

    _insert_audit_log(
        engine, "category_overrides", override_id,
        "id", "", override_id,
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
# Category Review Queue section
# ---------------------------------------------------------------------------

def _category_review_section() -> None:
    st.subheader("Category Review Queue")

    txns = _load_low_confidence_transactions(limit=50)
    l1_list, l1_to_l2 = _load_category_options()

    if txns.empty:
        st.success("No transactions below confidence threshold — category queue is clear.")
        return

    st.caption(f"Showing top {len(txns)} transactions with category confidence < 0.60, sorted by absolute spend.")

    for _, row in txns.iterrows():
        txn_id = str(row["transaction_id"])
        raw_supplier = str(row.get("raw_supplier_name") or "")
        raw_desc = str(row.get("raw_line_description") or "")
        base_amount = float(row.get("base_amount") or 0.0)
        cat_conf = row.get("category_confidence")
        cat_conf_str = f"{cat_conf:.2f}" if cat_conf is not None else "—"
        current_l1 = str(row.get("category_l1") or "")
        current_l2 = str(row.get("category_l2") or "")
        cat_method = str(row.get("category_method") or "—")
        canonical_supplier_id = str(row.get("canonical_supplier_id") or "")
        gl_account = str(row.get("gl_account") or "")

        desc_short = raw_desc[:50] if len(raw_desc) > 50 else raw_desc
        label = f"{raw_supplier} | {desc_short} | AUD {base_amount:,.0f} | conf: {cat_conf_str}"

        with st.expander(label):
            info_col, action_col = st.columns([2, 3])

            with info_col:
                st.markdown(f"**Current L1:** {current_l1 or '—'}")
                st.markdown(f"**Current L2:** {current_l2 or '—'}")
                st.markdown(f"**Category Method:** {cat_method}")
                st.markdown(f"**Transaction ID:** `{txn_id}`")

            with action_col:
                default_l1_idx = l1_list.index(current_l1) if current_l1 in l1_list else 0
                sel_l1 = st.selectbox(
                    "L1 Category",
                    options=l1_list,
                    index=default_l1_idx,
                    key=f"cat_l1_{txn_id}",
                )
                l2_options = l1_to_l2.get(sel_l1, [])
                default_l2_idx = l2_options.index(current_l2) if current_l2 in l2_options else 0
                sel_l2 = st.selectbox(
                    "L2 Category",
                    options=l2_options if l2_options else ["—"],
                    index=default_l2_idx,
                    key=f"cat_l2_{txn_id}",
                )

                if st.button("Override Category", key=f"override_cat_{txn_id}"):
                    if sel_l1 and sel_l2 and sel_l2 != "—":
                        _override_category(
                            transaction_id=txn_id,
                            canonical_supplier_id=canonical_supplier_id,
                            gl_account=gl_account or None,
                            old_l1=current_l1 or None,
                            new_l1=sel_l1,
                            new_l2=sel_l2,
                        )
                        st.success(f"Category overridden to {sel_l1} / {sel_l2}")
                        st.rerun()
                    else:
                        st.warning("Select a valid L1 and L2 category before overriding.")


# ---------------------------------------------------------------------------
# Category Override Rules section
# ---------------------------------------------------------------------------

def _category_override_rules_section() -> None:
    st.subheader("Category Override Rules")

    overrides_df = _load_category_overrides()
    l1_list, l1_to_l2 = _load_category_options()

    if overrides_df.empty:
        st.info("No category override rules defined yet.")
    else:
        display_cols = [c for c in ["id", "canonical_supplier_id", "gl_account",
                                     "override_l1", "override_l2", "reviewer",
                                     "reason", "created_at"] if c in overrides_df.columns]
        st.dataframe(overrides_df[display_cols], use_container_width=True)

        st.markdown("**Delete a rule:**")
        for _, ov_row in overrides_df.iterrows():
            ov_id = str(ov_row["id"])
            ov_label = (
                f"{ov_row.get('override_l1', '')} / {ov_row.get('override_l2', '')} "
                f"— supplier: {ov_row.get('canonical_supplier_id') or '—'} "
                f"| GL: {ov_row.get('gl_account') or '—'}"
            )
            if st.button(f"Delete: {ov_label}", key=f"del_override_{ov_id}"):
                _delete_category_override(ov_id)
                st.rerun()

    st.markdown("---")
    st.markdown("**Add a new override rule:**")

    with st.form("add_override_rule_form"):
        form_supplier_id = st.text_input("Canonical Supplier ID (optional)")
        form_gl_account = st.text_input("GL Account (optional)")
        form_l1 = st.selectbox("L1 Category", options=[""] + l1_list, key="form_l1")
        l2_options_form = l1_to_l2.get(form_l1, []) if form_l1 else []
        form_l2 = st.selectbox(
            "L2 Category",
            options=[""] + l2_options_form,
            key="form_l2",
        )
        form_reason = st.text_input("Reason", value="manual rule")

        submitted = st.form_submit_button("Add Override Rule")
        if submitted:
            if not form_l1 or not form_l2:
                st.warning("Please select both L1 and L2 categories.")
            elif not form_supplier_id.strip() and not form_gl_account.strip():
                st.warning("Provide at least a Canonical Supplier ID or GL Account.")
            else:
                _add_category_override_rule(
                    canonical_supplier_id=form_supplier_id.strip() or None,
                    gl_account=form_gl_account.strip() or None,
                    override_l1=form_l1,
                    override_l2=form_l2,
                    reason=form_reason.strip(),
                )
                st.success("Override rule added.")
                st.rerun()


# ---------------------------------------------------------------------------
# Audit Trail section
# ---------------------------------------------------------------------------

def _audit_trail_section() -> None:
    st.subheader("Audit Trail")

    audit_df = _load_audit_log(limit=50)
    if audit_df.empty:
        st.info("No audit log entries yet.")
    else:
        st.caption("Last 50 review workstation actions.")
        st.dataframe(audit_df, use_container_width=True)


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
    st.divider()
    _category_review_section()
    st.divider()
    _category_override_rules_section()
    st.divider()
    _audit_trail_section()


if __name__ == "__main__":
    main()
