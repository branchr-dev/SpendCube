"""SpendCube payment terms analysis dashboard page."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.app import load_cube_data
from dashboard.client_config import get_currency_label
from dashboard.components.charts import scatter_bubble
from dashboard.components.filters import render_filters

_STANDARD_TERMS = {14, 30, 45, 60, 90}
_TERMS_BUCKETS = ["0-14", "15-30", "31-45", "46-60", "60+"]


def _assign_bucket(days: float) -> str:
    if days <= 14:
        return "0-14"
    elif days <= 30:
        return "15-30"
    elif days <= 45:
        return "31-45"
    elif days <= 60:
        return "46-60"
    else:
        return "60+"


def _kpi_row(
    df: pd.DataFrame,
    target_days: float,
    wacc: float,
) -> None:
    has_terms = df["payment_terms_days"].notna() if "payment_terms_days" in df.columns else pd.Series(False, index=df.index)
    terms_df = df[has_terms].copy()

    # Weighted average payment terms (weighted by base_amount)
    if not terms_df.empty and "base_amount" in terms_df.columns:
        total_weighted = (terms_df["payment_terms_days"] * terms_df["base_amount"].abs()).sum()
        total_weight = terms_df["base_amount"].abs().sum()
        weighted_avg = total_weighted / total_weight if total_weight > 0 else 0.0
    else:
        weighted_avg = 0.0

    # % Transactions with Terms
    total_txn = len(df)
    pct_with_terms = (has_terms.sum() / total_txn * 100) if total_txn > 0 else 0.0

    # Working Capital Opportunity
    wacc_rate = wacc / 100.0
    if not terms_df.empty and "canonical_supplier_name" in terms_df.columns:
        sup_terms = (
            terms_df.groupby("canonical_supplier_name")
            .agg(
                current_terms=("payment_terms_days", "mean"),
                annual_spend=("base_amount", "sum"),
            )
            .reset_index()
        )
        sup_terms = sup_terms[sup_terms["current_terms"] < target_days]
        sup_terms["wc_opportunity"] = (
            (target_days - sup_terms["current_terms"]) / 365.0
            * sup_terms["annual_spend"].abs()
            * wacc_rate
        )
        total_wc = sup_terms["wc_opportunity"].sum()
    else:
        total_wc = 0.0

    # Suppliers on short terms (<30 days)
    if not terms_df.empty and "canonical_supplier_name" in terms_df.columns:
        short_terms_count = (
            terms_df[terms_df["payment_terms_days"] < 30]["canonical_supplier_name"]
            .nunique()
        )
    else:
        short_terms_count = 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Weighted Avg Payment Terms", f"{weighted_avg:.1f} days")
    c2.metric("% Transactions with Terms", f"{pct_with_terms:.1f}%")
    c3.metric("Working Capital Opportunity", f"{get_currency_label()} {total_wc:,.0f}")
    c4.metric("Suppliers on Short Terms (<30d)", f"{short_terms_count:,}")


def _terms_histogram(df: pd.DataFrame) -> None:
    if "payment_terms_days" not in df.columns or df.empty:
        st.info("No payment terms data available.")
        return

    terms_data = df["payment_terms_days"].dropna()
    if terms_data.empty:
        st.info("No payment terms data available.")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=terms_data,
            xbins=dict(start=0, end=terms_data.max() + 5, size=5),
            name="Transactions",
            marker_color="#1f77b4",
        )
    )
    fig.update_layout(
        title="Payment Terms Distribution (bin size = 5 days)",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        xaxis=dict(title="Payment Terms (days)"),
        yaxis=dict(showgrid=False, title="Transaction Count"),
        bargap=0.05,
    )
    st.plotly_chart(fig, use_container_width=True)


def _supplier_terms_heatmap(df: pd.DataFrame) -> None:
    if "payment_terms_days" not in df.columns or "canonical_supplier_name" not in df.columns or df.empty:
        st.info("No data available for heatmap.")
        return

    terms_df = df[df["payment_terms_days"].notna()].copy()
    if terms_df.empty:
        st.info("No payment terms data for heatmap.")
        return

    terms_df["terms_bucket"] = terms_df["payment_terms_days"].apply(_assign_bucket)

    # Top 15 suppliers by total spend
    top15 = (
        terms_df.groupby("canonical_supplier_name")["base_amount"]
        .sum()
        .abs()
        .nlargest(15)
        .index.tolist()
    )
    heat_df = terms_df[terms_df["canonical_supplier_name"].isin(top15)]

    pivot = heat_df.pivot_table(
        index="canonical_supplier_name",
        columns="terms_bucket",
        values="base_amount",
        aggfunc="sum",
        fill_value=0,
    ).abs()

    # Ensure all buckets appear in order
    for bucket in _TERMS_BUCKETS:
        if bucket not in pivot.columns:
            pivot[bucket] = 0
    pivot = pivot[_TERMS_BUCKETS]

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale="Blues",
            colorbar=dict(title=f"Spend ({get_currency_label()})"),
        )
    )
    fig.update_layout(
        title=f"Top 15 Suppliers × Payment Terms Bucket (Spend {get_currency_label()})",
        paper_bgcolor="white",
        font=dict(size=12),
        xaxis=dict(title="Payment Terms Bucket"),
        yaxis=dict(title="Supplier"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _working_capital_table(df: pd.DataFrame, target_days: float, wacc: float) -> None:
    st.subheader("Working Capital Opportunity by Supplier")

    if "payment_terms_days" not in df.columns or "canonical_supplier_name" not in df.columns or df.empty:
        st.info("No data available for working capital analysis.")
        return

    terms_df = df[df["payment_terms_days"].notna()].copy()
    if terms_df.empty:
        st.info("No payment terms data available.")
        return

    wacc_rate = wacc / 100.0

    sup_agg = (
        terms_df.groupby("canonical_supplier_name")
        .agg(
            current_terms=("payment_terms_days", "mean"),
            annual_spend=("base_amount", "sum"),
        )
        .reset_index()
    )
    sup_agg["annual_spend"] = sup_agg["annual_spend"].abs()
    sup_agg = sup_agg[sup_agg["current_terms"] < target_days].copy()

    if sup_agg.empty:
        st.info(f"No suppliers with payment terms below target ({target_days:.0f} days).")
        return

    sup_agg["target_terms"] = target_days
    sup_agg["wc_opportunity"] = (
        (sup_agg["target_terms"] - sup_agg["current_terms"]) / 365.0
        * sup_agg["annual_spend"]
        * wacc_rate
    )
    sup_agg = sup_agg.sort_values("wc_opportunity", ascending=False).reset_index(drop=True)

    currency = get_currency_label()
    annual_spend_col = f"Annual Spend ({currency})"
    wc_opp_col = f"WC Opportunity ({currency})"
    display = sup_agg.rename(columns={
        "canonical_supplier_name": "Supplier",
        "current_terms": "Current Terms (days)",
        "target_terms": "Target Terms (days)",
        "annual_spend": annual_spend_col,
        "wc_opportunity": wc_opp_col,
    })
    display["Current Terms (days)"] = display["Current Terms (days)"].map("{:.0f}".format)
    display["Target Terms (days)"] = display["Target Terms (days)"].map("{:.0f}".format)
    display[annual_spend_col] = display[annual_spend_col].map("{:,.0f}".format)
    display[wc_opp_col] = display[wc_opp_col].map("{:,.0f}".format)

    st.dataframe(display, use_container_width=True, hide_index=True)


def _non_standard_terms(df: pd.DataFrame) -> None:
    st.subheader("Non-Standard Payment Terms")
    st.caption(f"Standard terms: {sorted(_STANDARD_TERMS)} days. Suppliers below have terms outside these values.")

    if "payment_terms_days" not in df.columns or "canonical_supplier_name" not in df.columns or df.empty:
        st.info("No data available.")
        return

    terms_df = df[df["payment_terms_days"].notna()].copy()
    if terms_df.empty:
        st.info("No payment terms data available.")
        return

    # Flag non-standard: terms not in standard set (rounded to nearest integer)
    terms_df["terms_rounded"] = terms_df["payment_terms_days"].round().astype(int)
    non_std = terms_df[~terms_df["terms_rounded"].isin(_STANDARD_TERMS)]

    if non_std.empty:
        st.success("All suppliers are on standard payment terms.")
        return

    anomaly = (
        non_std.groupby("canonical_supplier_name")
        .agg(
            avg_terms=("payment_terms_days", "mean"),
            spend=("base_amount", "sum"),
            txn_count=("payment_terms_days", "count"),
        )
        .reset_index()
        .sort_values("spend", ascending=False)
        .reset_index(drop=True)
    )
    anomaly["spend"] = anomaly["spend"].abs()

    spend_col = f"Spend ({get_currency_label()})"
    display = anomaly.rename(columns={
        "canonical_supplier_name": "Supplier",
        "avg_terms": "Avg Terms (days)",
        "spend": spend_col,
        "txn_count": "Transaction Count",
    })
    display["Avg Terms (days)"] = display["Avg Terms (days)"].map("{:.1f}".format)
    display[spend_col] = display[spend_col].map("{:,.0f}".format)

    st.dataframe(display, use_container_width=True, hide_index=True)


def _spend_terms_scatter(df: pd.DataFrame) -> list[str]:
    if df.empty or "payment_terms_days" not in df.columns:
        st.info("No data.")
        return []

    has_terms = df[df["payment_terms_days"].notna() & (df["base_amount"] > 0)]
    if has_terms.empty:
        return []

    agg = has_terms.groupby("canonical_supplier_name").agg(
        annual_spend=("base_amount", "sum"),
        avg_terms=("payment_terms_days", "mean"),
        txn_count=("transaction_id", "count"),
        primary_cat=("category_l1", lambda x: x.mode().iloc[0] if not x.dropna().empty else "Other"),
    ).reset_index()

    annual_spend_col = f"Annual Spend ({get_currency_label()})"
    agg.rename(columns={
        "canonical_supplier_name": "Supplier",
        "annual_spend": annual_spend_col,
        "avg_terms": "Avg Payment Terms (days)",
        "txn_count": "Transaction Count",
        "primary_cat": "Category",
    }, inplace=True)

    fig = scatter_bubble(
        agg,
        x=annual_spend_col,
        y="Avg Payment Terms (days)",
        size="Transaction Count",
        color="Category",
        label="Supplier",
        title="Supplier Spend vs Payment Terms",
        hover_name="Supplier",
    )
    fig.add_hline(y=30, line_dash="dash", line_color="grey", annotation_text="30d", annotation_position="right")
    fig.add_hline(y=45, line_dash="dash", line_color="orange", annotation_text="45d target", annotation_position="right")

    event = st.plotly_chart(fig, on_select="rerun", key="pt_spend_scatter", use_container_width=True)
    points = (event or {}).get("selection", {}).get("points", [])
    selected = [p.get("text") for p in points if p.get("text")]
    if selected:
        st.caption(f"Cross-filter active: {', '.join(selected[:3])} — click chart background to clear")
    return selected


def main() -> None:
    st.title("Payment Terms")

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

    if filtered.empty:
        st.info("No data matches the current filters.")
        return

    # --- Configuration inputs ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Working Capital Parameters")
    target_days = st.sidebar.number_input(
        "Target Payment Days",
        min_value=1,
        max_value=365,
        value=45,
        step=1,
        key="pt_target_days",
    )
    wacc_pct = st.sidebar.number_input(
        "WACC (%)",
        min_value=0.1,
        max_value=50.0,
        value=8.0,
        step=0.1,
        format="%.1f",
        key="pt_wacc",
    )

    # --- KPI row ---
    _kpi_row(filtered, float(target_days), float(wacc_pct))

    st.markdown("---")
    st.subheader("Supplier Spend vs Payment Terms")
    selected_suppliers = _spend_terms_scatter(filtered)
    cf = filtered[filtered["canonical_supplier_name"].isin(selected_suppliers)] if selected_suppliers else filtered

    st.markdown("---")

    # --- Distribution histogram ---
    _terms_histogram(filtered)

    st.markdown("---")

    # --- Supplier × terms bucket heatmap ---
    _supplier_terms_heatmap(filtered)

    st.markdown("---")

    # --- Working capital table ---
    _working_capital_table(cf, float(target_days), float(wacc_pct))

    st.markdown("---")

    # --- Non-standard terms anomaly list ---
    _non_standard_terms(cf)


if __name__ == "__main__":
    main()
