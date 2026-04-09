"""SpendCube reusable Streamlit table components."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def format_monetary(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Return a copy of df with monetary columns formatted as '{:,.0f}'."""
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: f"{v:,.0f}" if pd.notna(v) else ""
            )
    return df


def styled_dataframe(df: pd.DataFrame, format_cols: dict = None) -> None:
    """Render a styled st.dataframe.

    Args:
        df: DataFrame to display.
        format_cols: Optional dict mapping column name → format string,
                     e.g. {"amount": "{:,.0f}", "pct": "{:.1f}%"}.
    """
    if format_cols:
        fmt = {col: fmt for col, fmt in format_cols.items() if col in df.columns}
        styler = df.style.format(fmt)
        st.dataframe(styler, use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)


def kpi_row(metrics: dict) -> None:
    """Render a row of st.metric() cards.

    Args:
        metrics: Dict of {label: value} or {label: (value, delta)}.
                 delta is optional; pass None or omit for no delta arrow.
    """
    cols = st.columns(len(metrics))
    for col, (label, payload) in zip(cols, metrics.items()):
        if isinstance(payload, tuple):
            value, delta = payload[0], payload[1] if len(payload) > 1 else None
        else:
            value, delta = payload, None
        with col:
            st.metric(label=label, value=value, delta=delta)
