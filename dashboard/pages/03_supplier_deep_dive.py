"""SpendCube supplier deep dive dashboard page."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.app import load_cube_data
from dashboard.client_config import get_currency_label
from dashboard.components.charts import horizontal_bar, dumbbell
from dashboard.components.filters import render_filters

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "spend_cube.db"


@st.cache_data
def _load_supplier_match_log() -> pd.DataFrame:
    """Load supplier_match_log from SQLite. Returns empty DataFrame if unavailable."""
    if not _DB_PATH.exists():
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(_DB_PATH)
        df = pd.read_sql_query("SELECT * FROM supplier_match_log", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def _build_supplier_options(txn: pd.DataFrame) -> list[str]:
    """Return supplier labels sorted by spend desc: 'Name (AUD 22,500)'."""
    sup_spend = (
        txn.groupby("canonical_supplier_name")["base_amount"]
        .sum()
        .reset_index()
        .sort_values("base_amount", ascending=False)
    )
    currency = get_currency_label()
    return [
        f"{row['canonical_supplier_name']} ({currency} {row['base_amount']:,.0f})"
        for _, row in sup_spend.iterrows()
    ]


def _extract_supplier_name(label: str) -> str:
    """Strip the spend suffix to get the canonical name."""
    currency = get_currency_label()
    idx = label.rfind(f" ({currency} ")
    return label[:idx] if idx != -1 else label


def _kpi_row(df: pd.DataFrame) -> None:
    total_spend = df["base_amount"].sum() if "base_amount" in df.columns else 0.0

    invoice_count = (
        df["invoice_number"].nunique()
        if "invoice_number" in df.columns
        else len(df)
    )

    avg_transaction = total_spend / invoice_count if invoice_count > 0 else 0.0

    avg_terms = (
        df["payment_terms_days"].dropna().mean()
        if "payment_terms_days" in df.columns
        else float("nan")
    )
    if pd.isna(avg_terms):
        avg_terms = 0.0

    if "po_number" in df.columns and total_spend > 0:
        po_spend = df.loc[df["po_number"].notna(), "base_amount"].sum()
        contract_pct = po_spend / total_spend * 100
    else:
        contract_pct = 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(f"Total Spend ({get_currency_label()})", f"{total_spend:,.0f}")
    c2.metric("Invoice Count", f"{invoice_count:,}")
    c3.metric(f"Avg Transaction Size ({get_currency_label()})", f"{avg_transaction:,.0f}")
    c4.metric("Payment Terms (days)", f"{avg_terms:.0f}")
    c5.metric("Contract Coverage", f"{contract_pct:.1f}%")


def _spend_trend(df: pd.DataFrame) -> None:
    if "invoice_month" not in df.columns or df.empty:
        st.info("No monthly data available.")
        return

    monthly = (
        df.groupby("invoice_month")["base_amount"]
        .sum()
        .reset_index()
        .sort_values("invoice_month")
    )

    if monthly.empty:
        st.info("No monthly trend data.")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=monthly["invoice_month"], y=monthly["base_amount"], name="Monthly Spend")
    )
    fig.update_layout(
        title="Monthly Spend Trend",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        xaxis=dict(title="Month"),
        yaxis=dict(showgrid=False, title=f"Spend ({get_currency_label()})"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _spend_by_category(df: pd.DataFrame) -> list[str]:
    if "category_l1" not in df.columns or df.empty:
        st.info("No category data available.")
        return []

    cat_data = (
        df.groupby("category_l1")["base_amount"]
        .sum()
        .reset_index()
        .rename(columns={"base_amount": "Spend", "category_l1": "Category"})
        .dropna(subset=["Category"])
        .sort_values("Spend", ascending=False)
    )

    if cat_data.empty:
        st.info("No category spend data.")
        return []

    fig = horizontal_bar(cat_data, x="Spend", y="Category", title="Spend by Category (L1)")
    event = st.plotly_chart(fig, on_select="rerun", key="supplier_spend_by_cat", use_container_width=True)
    points = (event or {}).get("selection", {}).get("points", [])
    selected = [p["y"] for p in points if "y" in p]
    if selected:
        st.caption(f'Cross-filter active: {", ".join(selected[:3])} — click chart background to clear')
    return selected


def _spend_by_bu(df: pd.DataFrame) -> None:
    bu_col = None
    for candidate in ("business_unit", "plant_site", "cost_centre"):
        if candidate in df.columns and df[candidate].notna().any():
            bu_col = candidate
            break

    if bu_col is None or df.empty:
        st.info("No business unit / site data available.")
        return

    bu_data = (
        df.groupby(bu_col)["base_amount"]
        .sum()
        .reset_index()
        .rename(columns={"base_amount": "Spend", bu_col: "Business Unit / Site"})
        .dropna(subset=["Business Unit / Site"])
        .sort_values("Spend", ascending=False)
    )

    if bu_data.empty:
        st.info("No business unit spend data.")
        return

    fig = horizontal_bar(
        bu_data,
        x="Spend",
        y="Business Unit / Site",
        title="Spend by Business Unit / Site",
    )
    st.plotly_chart(fig, use_container_width=True)


def _related_entities(
    txn: pd.DataFrame,
    supplier_name: str,
    canonical_supplier_id: str | None,
    match_log: pd.DataFrame,
) -> None:
    st.subheader("Related Entities")

    # --- Same parent company ---
    parent = None
    if "parent_company_name" in txn.columns:
        supplier_rows = txn[txn["canonical_supplier_name"] == supplier_name]
        parents = supplier_rows["parent_company_name"].dropna().unique()
        if len(parents) > 0:
            parent = parents[0]

    if parent:
        siblings = txn[
            (txn["parent_company_name"] == parent)
            & (txn["canonical_supplier_name"] != supplier_name)
        ]["canonical_supplier_name"].dropna().unique()

        if len(siblings) > 0:
            spend_col = f"Spend ({get_currency_label()})"
            sib_spend = (
                txn[txn["canonical_supplier_name"].isin(siblings)]
                .groupby("canonical_supplier_name")["base_amount"]
                .sum()
                .reset_index()
                .rename(columns={"canonical_supplier_name": "Supplier", "base_amount": spend_col})
                .sort_values(spend_col, ascending=False)
            )
            st.markdown(f"**Same parent company ({parent}):**")
            st.dataframe(
                sib_spend.assign(**{spend_col: sib_spend[spend_col].map("{:,.0f}".format)}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.markdown(f"**Parent company:** {parent} — no other related suppliers found.")
    else:
        st.markdown("No parent company information available for this supplier.")

    # --- Fuzzy / similar name matches (PENDING review) ---
    if not match_log.empty and "review_status" in match_log.columns:
        pending = match_log[match_log["review_status"] == "PENDING"]

        if canonical_supplier_id and "canonical_supplier_id" in match_log.columns:
            similar = pending[pending["canonical_supplier_id"] == canonical_supplier_id]
        else:
            similar = pd.DataFrame()

        if not similar.empty:
            st.markdown("**Similar supplier names (pending review):**")
            cols_to_show = [c for c in ["raw_supplier_name", "match_method", "confidence"] if c in similar.columns]
            st.dataframe(similar[cols_to_show], use_container_width=True, hide_index=True)
        else:
            st.markdown("No pending fuzzy-match variants for this supplier.")
    else:
        st.markdown("No supplier match log data available.")


def _risk_flags(df: pd.DataFrame, txn_all: pd.DataFrame, supplier_name: str) -> None:
    st.subheader("Risk Flags")

    flags_shown = False

    supplier_spend = df["base_amount"].sum() if "base_amount" in df.columns else 0.0
    total_spend = txn_all["base_amount"].sum() if "base_amount" in txn_all.columns else 0.0

    if total_spend > 0:
        concentration = supplier_spend / total_spend
        if concentration > 0.20:
            pct = concentration * 100
            st.warning(f"High concentration: {pct:.1f}% of total spend")
            flags_shown = True

    if "category_l1" in df.columns and not df.empty:
        unique_cats = df["category_l1"].dropna().nunique()
        if unique_cats == 1:
            st.warning("Single source risk: all spend concentrated in one L1 category.")
            flags_shown = True

    if "po_number" in df.columns and supplier_spend > 0:
        po_spend = df.loc[df["po_number"].notna(), "base_amount"].sum()
        contract_coverage = po_spend / supplier_spend
        if contract_coverage < 0.5:
            st.warning(f"Low contract coverage: {contract_coverage * 100:.1f}% of spend has a PO.")
            flags_shown = True

    if not flags_shown:
        st.success("No risk flags identified for this supplier.")


def _payment_terms_dumbbell(sup_df: pd.DataFrame, all_txn: pd.DataFrame) -> None:
    if sup_df.empty or "payment_terms_days" not in sup_df.columns:
        st.info("No payment terms data.")
        return
    has_terms = sup_df[sup_df["payment_terms_days"].notna()]
    if has_terms.empty:
        st.info("No payment terms recorded for this supplier.")
        return
    sup_avg = float(has_terms["payment_terms_days"].mean())
    primary_cat = (
        has_terms["category_l1"].mode().iloc[0]
        if "category_l1" in has_terms.columns and not has_terms["category_l1"].dropna().empty
        else None
    )
    if primary_cat and "payment_terms_days" in all_txn.columns:
        cat_median = float(
            all_txn[all_txn["category_l1"] == primary_cat]["payment_terms_days"].dropna().median()
        )
    elif "payment_terms_days" in all_txn.columns:
        cat_median = float(all_txn["payment_terms_days"].dropna().median())
    else:
        cat_median = None
    if cat_median is None:
        st.info("Category benchmark unavailable.")
        return
    supplier_label = (
        sup_df["canonical_supplier_name"].iloc[0]
        if "canonical_supplier_name" in sup_df.columns
        else "Selected Supplier"
    )
    row_df = pd.DataFrame({
        "Supplier": [supplier_label],
        "Avg Terms (days)": [sup_avg],
        "Category Median (days)": [cat_median],
    })
    fig = dumbbell(
        row_df,
        label_col="Supplier",
        left_col="Avg Terms (days)",
        right_col="Category Median (days)",
        left_name="Supplier Avg",
        right_name="Category Median",
        title=f"Payment Terms vs Category Median ({primary_cat or 'All Categories'})",
    )
    st.plotly_chart(fig, use_container_width=True)
    supplier_below = sup_avg < cat_median
    msg = (
        f"This supplier is on {'shorter' if supplier_below else 'longer'} terms "
        f"({sup_avg:.0f}d) than the {primary_cat or 'overall'} category median ({cat_median:.0f}d). "
        f"{'Working capital opportunity: negotiate extension.' if supplier_below else 'Terms are favourable.'}"
    )
    st.caption(msg)


def main() -> None:
    st.title("Supplier Deep Dive")

    cube = load_cube_data()
    if not cube:
        st.error("No spend data found. Please contact your analyst.")
        return

    txn = cube.get("transactions", pd.DataFrame())
    if txn.empty:
        st.info("No transactions loaded.")
        return

    # Apply global filters
    filtered = render_filters(txn)

    if filtered.empty or "canonical_supplier_name" not in filtered.columns:
        st.info("No data matches the current filters.")
        return

    # --- Supplier selector ---
    options = _build_supplier_options(filtered)
    if not options:
        st.info("No suppliers in filtered dataset.")
        return

    selected_label = st.selectbox("Select Supplier", options=options, key="supplier_select")
    selected_name = _extract_supplier_name(selected_label)

    sup_txn = filtered[filtered["canonical_supplier_name"] == selected_name]

    if sup_txn.empty:
        st.info(f"No transactions found for '{selected_name}'.")
        return

    # Resolve canonical_supplier_id for related entities lookup
    canonical_supplier_id = None
    if "canonical_supplier_id" in sup_txn.columns:
        ids = sup_txn["canonical_supplier_id"].dropna().unique()
        if len(ids) > 0:
            canonical_supplier_id = str(ids[0])

    st.markdown("---")

    # --- KPI row ---
    _kpi_row(sup_txn)

    st.markdown("---")

    # --- Spend by category + by BU side by side ---
    col_left, col_right = st.columns(2)
    with col_left:
        cat_sel = _spend_by_category(sup_txn)
    with col_right:
        _spend_by_bu(sup_txn)

    cf_sup = sup_txn[sup_txn["category_l1"].isin(cat_sel)] if cat_sel else sup_txn

    st.markdown("---")

    # --- Spend trend (cross-filtered by category selection if active) ---
    _spend_trend(cf_sup)

    st.markdown("---")

    # --- Related entities ---
    match_log = _load_supplier_match_log()
    _related_entities(filtered, selected_name, canonical_supplier_id, match_log)

    st.markdown("---")

    # --- Risk flags ---
    _risk_flags(sup_txn, filtered, selected_name)

    st.markdown("---")
    st.subheader("Payment Terms Benchmark")
    _payment_terms_dumbbell(sup_txn, filtered)


if __name__ == "__main__":
    main()
