"""SpendCube category deep dive dashboard page."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.app import load_cube_data
from dashboard.client_config import get_currency_label
from dashboard.components.charts import horizontal_bar, boxplot
from dashboard.components.filters import render_filters


def _category_selectors(txn: pd.DataFrame) -> pd.DataFrame:
    """Render L1 → L2 → L3 category selectors in the sidebar and return filtered df."""
    with st.sidebar:
        st.markdown("---")
        st.subheader("Category Drill-Down")

        # L1
        l1_options = ["All"] + sorted(txn["category_l1"].dropna().unique().tolist())
        selected_l1 = st.selectbox("Category L1", options=l1_options, key="cat_l1")

        cat_filtered = txn.copy()
        if selected_l1 != "All":
            cat_filtered = cat_filtered[cat_filtered["category_l1"] == selected_l1]

        # L2 (filtered by L1)
        l2_options = ["All"] + sorted(cat_filtered["category_l2"].dropna().unique().tolist())
        selected_l2 = st.selectbox("Category L2", options=l2_options, key="cat_l2")

        if selected_l2 != "All":
            cat_filtered = cat_filtered[cat_filtered["category_l2"] == selected_l2]

        # L3 (filtered by L2)
        l3_options = ["All"] + sorted(cat_filtered["category_l3"].dropna().unique().tolist())
        selected_l3 = st.selectbox("Category L3", options=l3_options, key="cat_l3")

        if selected_l3 != "All":
            cat_filtered = cat_filtered[cat_filtered["category_l3"] == selected_l3]

    return cat_filtered


def _kpi_row(df: pd.DataFrame) -> None:
    total_spend = df["base_amount"].sum() if "base_amount" in df.columns else 0.0

    supplier_count = (
        df["canonical_supplier_id"].nunique()
        if "canonical_supplier_id" in df.columns
        else 0
    )

    invoice_count = (
        df["invoice_number"].nunique()
        if "invoice_number" in df.columns
        else len(df)
    )

    if "po_number" in df.columns and total_spend > 0:
        po_spend = df.loc[df["po_number"].notna(), "base_amount"].sum()
        contract_pct = po_spend / total_spend * 100
    else:
        contract_pct = 0.0

    if "po_number" in df.columns and total_spend > 0:
        maverick_spend = df.loc[df["po_number"].isna(), "base_amount"].sum()
        maverick_pct = maverick_spend / total_spend * 100
    else:
        maverick_pct = 0.0

    avg_terms = (
        df["payment_terms_days"].dropna().mean()
        if "payment_terms_days" in df.columns
        else 0.0
    )
    if pd.isna(avg_terms):
        avg_terms = 0.0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric(f"Total Spend ({get_currency_label()})", f"{total_spend:,.0f}")
    c2.metric("Supplier Count", f"{supplier_count:,}")
    c3.metric("Invoice Count", f"{invoice_count:,}")
    c4.metric("Contract Coverage", f"{contract_pct:.1f}%")
    c5.metric("Maverick Spend", f"{maverick_pct:.1f}%")
    c6.metric("Avg Payment Terms", f"{avg_terms:.0f} days")


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


def _transaction_boxplot(df: pd.DataFrame) -> None:
    if df.empty or "base_amount" not in df.columns:
        st.info("No data.")
        return
    pos_df = df[df["base_amount"] > 0].copy()
    if pos_df.empty:
        st.info("No positive-value transactions for boxplot.")
        return
    fig = boxplot(pos_df, x="category_l1", y="base_amount", title=f"Transaction Value Distribution by Category ({get_currency_label()})")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Distribution of individual transaction values (positive spend only). Wide spread indicates purchasing inconsistency or multiple item types within the category.")


def _top_suppliers(df: pd.DataFrame) -> list[str]:
    if "canonical_supplier_name" not in df.columns or df.empty:
        st.info("No supplier data available.")
        return []

    sup_data = (
        df.groupby("canonical_supplier_name")["base_amount"]
        .sum()
        .reset_index()
        .rename(columns={"base_amount": "Spend", "canonical_supplier_name": "Supplier"})
        .dropna(subset=["Supplier"])
        .sort_values("Spend", ascending=False)
        .head(10)
    )

    if sup_data.empty:
        st.info("No supplier data for selected category.")
        return []

    fig = horizontal_bar(sup_data, x="Spend", y="Supplier", title="Top 10 Suppliers by Spend")
    event = st.plotly_chart(fig, on_select="rerun", key="cat_top_suppliers", use_container_width=True)
    points = (event or {}).get("selection", {}).get("points", [])
    selected = [p["y"] for p in points if "y" in p]
    if selected:
        st.caption(f"Cross-filter active: {', '.join(selected[:3])} — click chart background to clear")
    return selected


def _supplier_fragmentation(df: pd.DataFrame) -> None:
    if "canonical_supplier_name" not in df.columns or df.empty:
        st.info("No supplier data for fragmentation analysis.")
        return

    sup_spend = (
        df.groupby("canonical_supplier_name")["base_amount"]
        .sum()
        .reset_index()
    )

    total = sup_spend["base_amount"].sum()
    supplier_count = len(sup_spend)

    if total == 0 or supplier_count == 0:
        st.info("Insufficient data for fragmentation analysis.")
        return

    sup_spend["share_pct"] = sup_spend["base_amount"] / total * 100
    hhi = (sup_spend["share_pct"] ** 2).sum()
    top1_share = sup_spend["share_pct"].max()

    c1, c2, c3 = st.columns(3)
    c1.metric("Supplier Count", f"{supplier_count:,}")
    c2.metric("HHI (Market Concentration)", f"{hhi:,.0f}")
    c3.metric("Top Supplier Share", f"{top1_share:.1f}%")

    if hhi > 2500:
        st.warning("High market concentration (HHI > 2500) — potential single-source risk.")
    elif hhi > 1500:
        st.warning("Moderate market concentration (HHI 1500–2500).")


def _payment_terms_histogram(df: pd.DataFrame) -> None:
    if "payment_terms_days" not in df.columns or df.empty:
        st.info("No payment terms data available.")
        return

    terms = df["payment_terms_days"].dropna()
    if terms.empty:
        st.info("No payment terms recorded for this category.")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Histogram(x=terms, nbinsx=20, name="Payment Terms Distribution")
    )
    fig.update_layout(
        title="Payment Terms Distribution (days)",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        xaxis=dict(title="Payment Terms (days)"),
        yaxis=dict(showgrid=False, title="Transaction Count"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _savings_lever_flags(df: pd.DataFrame) -> None:
    st.subheader("Savings Lever Flags")

    flags_shown = False

    if "canonical_supplier_id" in df.columns:
        supplier_count = df["canonical_supplier_id"].nunique()
        if supplier_count > 5:
            st.info(f"Consolidation opportunity: {supplier_count} suppliers in this category — review for rationalisation.")
            flags_shown = True

    total_spend = df["base_amount"].sum() if "base_amount" in df.columns else 0.0
    if "po_number" in df.columns and total_spend > 0:
        maverick_spend = df.loc[df["po_number"].isna(), "base_amount"].sum()
        maverick_pct = maverick_spend / total_spend * 100
        if maverick_pct > 15:
            st.info(f"High maverick spend ({maverick_pct:.1f}%) — consider PO mandate or contract coverage improvement.")
            flags_shown = True

    if "payment_terms_days" in df.columns:
        avg_terms = df["payment_terms_days"].dropna().mean()
        if not pd.isna(avg_terms) and avg_terms < 30:
            st.info(f"Short payment terms opportunity: average {avg_terms:.0f} days — renegotiate to 45+ days to improve working capital.")
            flags_shown = True

    if "canonical_supplier_name" in df.columns and total_spend > 0:
        sup_spend = df.groupby("canonical_supplier_name")["base_amount"].sum()
        if len(sup_spend) > 0:
            top1_share = sup_spend.max() / total_spend * 100
            if top1_share > 60:
                top_supplier = sup_spend.idxmax()
                st.info(f"High supplier concentration: '{top_supplier}' accounts for {top1_share:.1f}% of category spend.")
                flags_shown = True

    if not flags_shown:
        st.success("No savings lever flags identified for this category selection.")


def main() -> None:
    st.title("Category Deep Dive")
    st.caption('Drill down from L1 to L3 category. Select a category in the sidebar to filter all charts. Click a supplier bar to cross-filter to that supplier.')

    cube = load_cube_data()
    if not cube:
        st.error("No spend data found. Please contact your analyst.")
        return

    txn = cube.get("transactions", pd.DataFrame())
    if txn.empty:
        st.info("No transactions loaded.")
        return

    # Apply global filters first
    filtered = render_filters(txn)

    # Then apply category drill-down selectors (within sidebar)
    cat_filtered = _category_selectors(filtered)

    if cat_filtered.empty:
        st.info("No data matches the current filters and category selection.")
        return

    _kpi_row(cat_filtered)

    st.markdown("---")

    sup_sel = _top_suppliers(cat_filtered)
    cf = cat_filtered[cat_filtered["canonical_supplier_name"].isin(sup_sel)] if sup_sel else cat_filtered

    st.markdown("---")

    _spend_trend(cf)

    st.markdown("---")
    st.subheader("Transaction Value Distribution")
    _transaction_boxplot(cat_filtered)

    st.markdown("---")

    _payment_terms_histogram(cf)

    st.markdown("---")

    st.subheader("Supplier Fragmentation")
    _supplier_fragmentation(cat_filtered)

    st.markdown("---")

    _savings_lever_flags(cat_filtered)


if __name__ == "__main__":
    main()
