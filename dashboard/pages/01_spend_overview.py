"""SpendCube spend overview dashboard page."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.app import load_cube_data, load_quality_scorecard
from dashboard.components.charts import horizontal_bar, donut_chart
from dashboard.components.filters import render_filters


_STATUS_ICON = {
    "GREEN": "🟢",
    "AMBER": "🟡",
    "ALERT": "🟠",
    "RED": "🔴",
}


def _kpi_cards(filtered: pd.DataFrame) -> None:
    total_spend = filtered["base_amount"].sum() if "base_amount" in filtered.columns else 0.0
    supplier_count = (
        filtered["canonical_supplier_id"].nunique()
        if "canonical_supplier_id" in filtered.columns
        else 0
    )
    invoice_count = (
        filtered["invoice_number"].nunique()
        if "invoice_number" in filtered.columns
        else len(filtered)
    )
    avg_txn = total_spend / invoice_count if invoice_count else 0.0

    if "po_number" in filtered.columns and total_spend > 0:
        po_spend = filtered.loc[filtered["po_number"].notna(), "base_amount"].sum()
        contract_pct = po_spend / total_spend * 100
    else:
        contract_pct = 0.0

    if "is_tail_spend" in filtered.columns and total_spend > 0:
        tail_spend = filtered.loc[filtered["is_tail_spend"] == True, "base_amount"].sum()
        tail_pct = tail_spend / total_spend * 100
    else:
        tail_pct = 0.0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Spend (AUD)", f"{total_spend:,.0f}")
    c2.metric("Supplier Count", f"{supplier_count:,}")
    c3.metric("Invoice Count", f"{invoice_count:,}")
    c4.metric("Avg Transaction Size", f"{avg_txn:,.0f}")
    c5.metric("Contract Coverage", f"{contract_pct:.1f}%")
    c6.metric("Tail Spend", f"{tail_pct:.1f}%")


def _spend_by_month(filtered: pd.DataFrame) -> None:
    if "invoice_month" not in filtered.columns or filtered.empty:
        st.info("No monthly data available.")
        return

    monthly = (
        filtered.groupby("invoice_month")["base_amount"]
        .sum()
        .reset_index()
        .sort_values("invoice_month")
    )
    monthly["rolling_avg"] = monthly["base_amount"].rolling(3, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=monthly["invoice_month"], y=monthly["base_amount"], name="Monthly Spend")
    )
    fig.add_trace(
        go.Scatter(
            x=monthly["invoice_month"],
            y=monthly["rolling_avg"],
            name="3-Month Rolling Avg",
            mode="lines+markers",
            line=dict(color="crimson", width=2),
        )
    )
    fig.update_layout(
        title="Spend by Month",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        yaxis=dict(showgrid=False, title="Spend (AUD)"),
        xaxis=dict(title="Month"),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _category_and_bu(filtered: pd.DataFrame) -> None:
    col_left, col_right = st.columns(2)

    with col_left:
        if "category_l1" in filtered.columns and not filtered.empty:
            cat_data = (
                filtered.groupby("category_l1")["base_amount"]
                .sum()
                .reset_index()
                .rename(columns={"base_amount": "Spend", "category_l1": "Category L1"})
                .dropna(subset=["Category L1"])
                .sort_values("Spend", ascending=False)
                .head(10)
            )
            if cat_data.empty:
                st.info("No category data available.")
            else:
                fig = horizontal_bar(cat_data, x="Spend", y="Category L1", title="Spend by Category L1 (Top 10)")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No category data available.")

    with col_right:
        if "business_unit" in filtered.columns and not filtered.empty:
            bu_data = (
                filtered.groupby("business_unit")["base_amount"]
                .sum()
                .reset_index()
                .rename(columns={"base_amount": "Spend", "business_unit": "Business Unit"})
                .dropna(subset=["Business Unit"])
                .sort_values("Spend", ascending=False)
            )
            if bu_data.empty:
                st.info("No business unit data available.")
            else:
                fig = horizontal_bar(bu_data, x="Spend", y="Business Unit", title="Spend by Business Unit")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No business unit data available.")


def _top_suppliers(filtered: pd.DataFrame) -> None:
    if "canonical_supplier_name" not in filtered.columns or filtered.empty:
        st.info("No supplier data available.")
        return

    sup_data = (
        filtered.groupby("canonical_supplier_name")["base_amount"]
        .sum()
        .reset_index()
        .sort_values("base_amount", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )
    total = sup_data["base_amount"].sum()
    sup_data["cumulative_pct"] = sup_data["base_amount"].cumsum() / total * 100 if total else 0.0

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=sup_data["canonical_supplier_name"],
            x=sup_data["base_amount"],
            name="Spend (AUD)",
            orientation="h",
        )
    )
    fig.add_trace(
        go.Scatter(
            y=sup_data["canonical_supplier_name"],
            x=sup_data["cumulative_pct"],
            name="Cumulative %",
            mode="lines+markers",
            xaxis="x2",
            line=dict(color="crimson", width=2),
        )
    )
    fig.update_layout(
        title="Top 20 Suppliers by Spend",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        yaxis=dict(showgrid=False, autorange="reversed"),
        xaxis=dict(title="Spend (AUD)"),
        xaxis2=dict(
            title="Cumulative %",
            overlaying="x",
            side="top",
            range=[0, 105],
            showgrid=False,
        ),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _pareto_and_donut(filtered: pd.DataFrame) -> None:
    col_left, col_right = st.columns(2)

    with col_left:
        if "canonical_supplier_name" not in filtered.columns or filtered.empty:
            st.info("No supplier data for Pareto curve.")
        else:
            sup_data = (
                filtered.groupby("canonical_supplier_name")["base_amount"]
                .sum()
                .reset_index()
                .sort_values("base_amount", ascending=False)
                .reset_index(drop=True)
            )
            total = sup_data["base_amount"].sum()
            sup_data["rank"] = range(1, len(sup_data) + 1)
            sup_data["cumulative_pct"] = (
                sup_data["base_amount"].cumsum() / total * 100 if total else 0.0
            )
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=sup_data["rank"],
                    y=sup_data["cumulative_pct"],
                    mode="lines",
                    name="Cumulative Spend %",
                    line=dict(width=2),
                    fill="tozeroy",
                )
            )
            fig.update_layout(
                title="Pareto Curve — Supplier Concentration",
                paper_bgcolor="white",
                plot_bgcolor="white",
                font=dict(size=12),
                xaxis=dict(title="Supplier Rank"),
                yaxis=dict(
                    title="Cumulative Spend %", showgrid=False, range=[0, 100]
                ),
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        spend_type_count = (
            filtered["spend_type"].notna().sum()
            if "spend_type" in filtered.columns
            else 0
        )
        managed_count = (
            filtered["managed_status"].notna().sum()
            if "managed_status" in filtered.columns
            else 0
        )

        if spend_type_count >= managed_count and spend_type_count > 0:
            donut_col, donut_title = "spend_type", "Direct vs Indirect"
        elif managed_count > 0:
            donut_col, donut_title = "managed_status", "Managed vs Unmanaged"
        else:
            donut_col, donut_title = None, None

        if donut_col:
            donut_data = (
                filtered.groupby(donut_col)["base_amount"]
                .sum()
                .reset_index()
                .rename(columns={donut_col: "Category", "base_amount": "Spend"})
            )
            fig = donut_chart(donut_data, names="Category", values="Spend", title=donut_title)
            st.plotly_chart(fig, use_container_width=True)
        elif "po_number" in filtered.columns and not filtered.empty:
            po_data = pd.DataFrame(
                {
                    "Category": ["With PO", "Without PO"],
                    "Spend": [
                        filtered.loc[
                            filtered["po_number"].notna(), "base_amount"
                        ].sum(),
                        filtered.loc[
                            filtered["po_number"].isna(), "base_amount"
                        ].sum(),
                    ],
                }
            )
            fig = donut_chart(po_data, names="Category", values="Spend", title="PO Coverage")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No spend type or managed status data available.")


def _quality_scorecard(scorecard: dict) -> None:
    if not scorecard:
        st.info("No quality scorecard available. Run `make build-cube` to generate.")
        return

    st.subheader("Data Quality Scorecard")
    cols = st.columns(3)
    for i, (check_name, check_data) in enumerate(scorecard.items()):
        status = check_data.get("status", "UNKNOWN")
        icon = _STATUS_ICON.get(status, "⚪")
        label = check_name.replace("_", " ").title()
        raw_val = check_data.get("pct", check_data.get("value", "—"))
        val_str = f"{raw_val:.1f}%" if isinstance(raw_val, float) else str(raw_val)
        cols[i % 3].markdown(f"{icon} **{label}** — {val_str} ({status})")


def main() -> None:
    st.title("Spend Overview")

    cube = load_cube_data()
    if not cube:
        st.error("No spend data found. Run `make build-cube` first.")
        return

    txn = cube.get("transactions", pd.DataFrame())
    if txn.empty:
        st.info("No transactions loaded.")
        return

    filtered = render_filters(txn)

    if filtered.empty:
        st.info("No data matches the current filters.")
        return

    _kpi_cards(filtered)

    st.markdown("---")

    _spend_by_month(filtered)

    st.markdown("---")

    _category_and_bu(filtered)

    st.markdown("---")

    _top_suppliers(filtered)

    st.markdown("---")

    _pareto_and_donut(filtered)

    st.markdown("---")

    _quality_scorecard(load_quality_scorecard())


if __name__ == "__main__":
    main()
