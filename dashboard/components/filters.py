"""SpendCube reusable Streamlit filter components."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Render global filter sidebar and return filtered DataFrame.

    Filters applied:
    - Date range on invoice_date
    - Business unit multiselect
    - Category L1 multiselect
    - Supplier name text search

    Filter state is persisted via st.session_state so values survive
    Streamlit re-runs.
    """
    filtered = df.copy()

    with st.sidebar:
        st.header("Filters")

        # --- Date range ---
        if "invoice_date" in df.columns:
            date_col = pd.to_datetime(df["invoice_date"], errors="coerce")
            min_date = date_col.min()
            max_date = date_col.max()

            if pd.isna(min_date) or pd.isna(max_date):
                min_date = max_date = pd.Timestamp.today()

            if "filter_date_start" not in st.session_state:
                st.session_state["filter_date_start"] = min_date.date()
            if "filter_date_end" not in st.session_state:
                st.session_state["filter_date_end"] = max_date.date()

            date_start = st.date_input(
                "Invoice date from",
                value=st.session_state["filter_date_start"],
                min_value=min_date.date(),
                max_value=max_date.date(),
                key="filter_date_start",
            )
            date_end = st.date_input(
                "Invoice date to",
                value=st.session_state["filter_date_end"],
                min_value=min_date.date(),
                max_value=max_date.date(),
                key="filter_date_end",
            )

            mask = (date_col.dt.date >= date_start) & (date_col.dt.date <= date_end)
            filtered = filtered[mask]

        # --- Business unit ---
        if "business_unit" in df.columns:
            all_bus = sorted(df["business_unit"].dropna().unique().tolist())
            if "filter_business_unit" not in st.session_state:
                st.session_state["filter_business_unit"] = []

            selected_bu = st.multiselect(
                "Business unit",
                options=all_bus,
                default=st.session_state["filter_business_unit"],
                key="filter_business_unit",
            )
            if selected_bu:
                filtered = filtered[filtered["business_unit"].isin(selected_bu)]

        # --- Category L1 ---
        cat_col = None
        for candidate in ("category_l1", "unspsc_l1", "l1_category"):
            if candidate in df.columns:
                cat_col = candidate
                break

        if cat_col:
            all_cats = sorted(df[cat_col].dropna().unique().tolist())
            if "filter_category_l1" not in st.session_state:
                st.session_state["filter_category_l1"] = []

            selected_cats = st.multiselect(
                "Category L1",
                options=all_cats,
                default=st.session_state["filter_category_l1"],
                key="filter_category_l1",
            )
            if selected_cats:
                filtered = filtered[filtered[cat_col].isin(selected_cats)]

        # --- Supplier search ---
        sup_col = None
        for candidate in ("canonical_supplier_name", "supplier_name", "raw_supplier_name"):
            if candidate in df.columns:
                sup_col = candidate
                break

        if sup_col:
            if "filter_supplier_search" not in st.session_state:
                st.session_state["filter_supplier_search"] = ""

            supplier_query = st.text_input(
                "Supplier search",
                value=st.session_state["filter_supplier_search"],
                key="filter_supplier_search",
                placeholder="Type to filter suppliers…",
            )
            if supplier_query:
                mask = filtered[sup_col].str.contains(
                    supplier_query, case=False, na=False
                )
                filtered = filtered[mask]

    return filtered
