"""SpendCube recommendations dashboard page."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.client_config import get_currency_label
from dashboard.components.charts import heatmap

_RECS_PATH = Path(__file__).parent.parent.parent / "data" / "output" / "recommendations.json"

_CONFIDENCE_COLOURS = {
    "HIGH": "background-color: #d4edda; color: #155724; font-weight: bold",
    "MEDIUM": "background-color: #fff3cd; color: #856404; font-weight: bold",
    "LOW": "background-color: #f8d7da; color: #721c24; font-weight: bold",
}


@st.cache_data
def _load_recommendations() -> list[dict]:
    """Load recommendations from JSON. Returns empty list if not found.

    Handles both the legacy bare-list format and the new dict format
    ``{'recommendations': [...], 'portfolio_summary': {...}}``.
    """
    if not _RECS_PATH.exists():
        return []
    with _RECS_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "recommendations" in data:
        return data["recommendations"]
    return data


@st.cache_data
def _load_portfolio_summary() -> dict:
    """Load portfolio summary from JSON. Returns empty dict if not found."""
    if not _RECS_PATH.exists():
        return {}
    with _RECS_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        return data.get("portfolio_summary", {})
    return {}


def _colour_confidence(val: str) -> str:
    return _CONFIDENCE_COLOURS.get(val, "")


def _kpi_row(recs: list[dict]) -> None:
    total_savings = sum(r.get("estimated_impact_aud", 0.0) for r in recs)
    total_count = len(recs)
    high_count = sum(1 for r in recs if r.get("confidence") == "HIGH")
    medium_count = sum(1 for r in recs if r.get("confidence") == "MEDIUM")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Total Identified Savings ({get_currency_label()})", f"{total_savings:,.0f}")
    c2.metric("Recommendation Count", str(total_count))
    c3.metric("HIGH Confidence", str(high_count))
    c4.metric("MEDIUM Confidence", str(medium_count))


def _build_display_df(recs: list[dict]) -> pd.DataFrame:
    impact_col = f"Estimated Impact ({get_currency_label()})"
    rows = []
    for i, r in enumerate(recs, 1):
        rows.append(
            {
                "Rank": i,
                "Type": r.get("type", ""),
                "Context": r.get("context", ""),
                "Evidence": r.get("evidence", ""),
                impact_col: r.get("estimated_impact_aud", 0.0),
                "Confidence": r.get("confidence", ""),
                "Lever": r.get("lever", ""),
            }
        )
    return pd.DataFrame(rows)


def _recommendations_table(recs: list[dict]) -> None:
    st.subheader("Recommendations Table")
    df = _build_display_df(recs)
    if df.empty:
        st.info("No recommendations to display.")
        return

    impact_col = f"Estimated Impact ({get_currency_label()})"
    styled = df.style.format({impact_col: "{:,.0f}"}).map(
        _colour_confidence, subset=["Confidence"]
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)


def _savings_heatmap(recs: list[dict]) -> tuple[str | None, str | None]:
    st.subheader("Savings Heatmap — Type × Lever (click a cell to filter recommendations below)")
    if not recs:
        st.info("No data for heatmap.")
        return None, None

    df = pd.DataFrame(
        [
            {
                "type": r.get("type", ""),
                "lever": r.get("lever", ""),
                "estimated_impact_aud": r.get("estimated_impact_aud", 0.0),
            }
            for r in recs
        ]
    )

    if df["type"].nunique() < 1 or df["lever"].nunique() < 1:
        st.info("Not enough variety in recommendation types/levers for a heatmap.")
        return None, None

    fig = heatmap(
        df,
        x="lever",
        y="type",
        values="estimated_impact_aud",
        title=f"Estimated Impact ({get_currency_label()}) by Recommendation Type and Lever",
    )
    event = st.plotly_chart(fig, on_select="rerun", key="recs_heatmap", use_container_width=True)
    points = (event or {}).get("selection", {}).get("points", [])
    if points:
        sel_lever = points[0].get("x")
        sel_type = points[0].get("y")
        parts = [p for p in [sel_type, sel_lever] if p]
        if parts:
            st.caption(f"Cross-filter active: {' × '.join(parts)} — click chart background to clear")
            return sel_type, sel_lever
    return None, None


def _detail_cards(recs: list[dict]) -> None:
    st.subheader("Recommendation Detail")
    for i, r in enumerate(recs, 1):
        label = (
            f"#{i:02d} [{r.get('type', '')}] {r.get('context', '')} "
            f"— {get_currency_label()} {r.get('estimated_impact_aud', 0.0):,.0f} "
            f"({r.get('confidence', '')})"
        )
        with st.expander(label):
            col_left, col_right = st.columns(2)
            with col_left:
                st.markdown(f"**Evidence:** {r.get('evidence', '—')}")
                st.markdown(f"**Action:** {r.get('action', '—')}")
                st.markdown(f"**Lever:** {r.get('lever', '—')}")
                st.markdown(f"**Confidence:** {r.get('confidence', '—')}")
            with col_right:
                narrative = r.get("narrative")
                if narrative:
                    st.markdown("**Narrative:**")
                    st.markdown(narrative)
                else:
                    st.caption("Narrative not available for this recommendation.")

                assumptions = r.get("assumptions")
                if assumptions:
                    st.markdown("**Assumptions:**")
                    if isinstance(assumptions, list):
                        for a in assumptions:
                            st.markdown(f"- {a}")
                    else:
                        st.markdown(str(assumptions))


def _excel_download(recs: list[dict]) -> None:
    df = _build_display_df(recs)
    if df.empty:
        return

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Recommendations")
    buffer.seek(0)

    st.download_button(
        label="Download Recommendations as Excel",
        data=buffer,
        file_name="recommendations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def main() -> None:
    st.title("Recommendations")

    recs = _load_recommendations()

    if not recs:
        st.warning("No recommendations available. Please contact your analyst.")
        return

    # --- Confidence filter ---
    selected_confidence = st.multiselect(
        "Filter by Confidence",
        options=["HIGH", "MEDIUM", "LOW"],
        default=["HIGH", "MEDIUM", "LOW"],
    )
    if selected_confidence:
        recs = [r for r in recs if r.get("confidence") in selected_confidence]

    if not recs:
        st.info("No recommendations match the selected confidence filters.")
        return

    # Sort by impact descending
    recs = sorted(recs, key=lambda r: r.get("estimated_impact_aud", 0.0), reverse=True)

    # --- KPI row ---
    _kpi_row(recs)

    st.markdown("---")

    # --- Recommendations table ---
    _recommendations_table(recs)

    st.markdown("---")

    # --- Savings heatmap (click to filter detail cards) ---
    sel_type, sel_lever = _savings_heatmap(recs)

    # Apply heatmap selection to filter detail cards
    recs_detail = recs
    if sel_type:
        recs_detail = [r for r in recs_detail if r.get("type") == sel_type]
    if sel_lever:
        recs_detail = [r for r in recs_detail if r.get("lever") == sel_lever]
    if (sel_type or sel_lever) and len(recs_detail) < len(recs):
        st.caption(f"Showing {len(recs_detail)} of {len(recs)} recommendations.")

    st.markdown("---")

    # --- Download button ---
    _excel_download(recs)

    st.markdown("---")

    # --- Detail cards ---
    _detail_cards(recs_detail)


if __name__ == "__main__":
    main()
