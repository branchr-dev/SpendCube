"""SpendCube Streamlit dashboard application entry point."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.client_config import (
    get_client_name,
    get_currency_label,
    get_data_freshness,
    get_engagement_title,
)

title = get_engagement_title()
if get_client_name():
    title = f"{get_client_name()} — {title}"

st.set_page_config(
    page_title=title,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

_DATA_DIR = Path(__file__).parent.parent / "data" / "output"
_PAGES_DIR = Path(__file__).parent / "pages"
_PARQUET_FILES = {
    "transactions": "transactions.parquet",
    "by_supplier": "by_supplier.parquet",
    "by_category": "by_category.parquet",
    "by_month": "by_month.parquet",
}


@st.cache_data
def load_cube_data() -> dict[str, pd.DataFrame]:
    """Load all spend cube Parquet files. Returns dict keyed by table name."""
    missing = [
        name
        for name, fname in _PARQUET_FILES.items()
        if not (_DATA_DIR / fname).exists()
    ]
    if missing:
        st.error(
            "Spend data not yet loaded. Please contact your analyst to refresh the dataset."
        )
        return {}

    return {
        name: pd.read_parquet(_DATA_DIR / fname)
        for name, fname in _PARQUET_FILES.items()
    }


@st.cache_data
def load_quality_scorecard() -> dict:
    """Load data quality scorecard JSON. Returns empty dict if not found."""
    path = _DATA_DIR / "quality_scorecard.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _cover() -> None:
    client = get_client_name()
    engagement = get_engagement_title()
    if client:
        st.title(client)
        st.subheader(engagement)
    else:
        st.title(engagement)

    freshness = get_data_freshness()
    st.caption(f"Data last refreshed: {freshness}")

    cube = load_cube_data()

    if not cube:
        st.info("No spend data found. Please contact your analyst to load a dataset.")
        return

    txn = cube.get("transactions", pd.DataFrame())
    suppliers = cube.get("by_supplier", pd.DataFrame())

    currency = get_currency_label()
    total_spend = float(txn["base_amount"].sum()) if "base_amount" in txn.columns else 0.0
    supplier_count = len(suppliers) if not suppliers.empty else 0
    invoice_count = len(txn)

    col1, col2, col3 = st.columns(3)
    col1.metric(f"Total Spend ({currency})", f"{total_spend:,.0f}")
    col2.metric("Suppliers", f"{supplier_count:,}")
    col3.metric("Invoices", f"{invoice_count:,}")

    st.markdown("---")
    st.markdown("Use the sidebar to navigate between analysis views.")
    st.markdown(
        "- **Spend Overview** — KPIs, monthly trend, category and supplier breakdown\n"
        "- **Category Deep Dive** — Category drill-down from L1 to L3, supplier fragmentation, savings signals\n"
        "- **Supplier Deep Dive** — Per-supplier spend profile, payment terms benchmark, risk flags\n"
        "- **Payment Terms** — Working capital opportunity, terms distribution, supplier benchmark\n"
    )


pg = st.navigation([
    st.Page(_cover, title="Cover", icon="📊", default=True),
    st.Page(str(_PAGES_DIR / "01_spend_overview.py"), title="Spend Overview"),
    st.Page(str(_PAGES_DIR / "02_category_deep_dive.py"), title="Category Deep Dive"),
    st.Page(str(_PAGES_DIR / "03_supplier_deep_dive.py"), title="Supplier Deep Dive"),
    st.Page(str(_PAGES_DIR / "04_payment_terms.py"), title="Payment Terms"),
    st.Page(str(_PAGES_DIR / "05_data_quality.py"), title="Data Quality"),
    st.Page(str(_PAGES_DIR / "06_recommendations.py"), title="Recommendations"),
    st.Page(str(_PAGES_DIR / "99_admin_review_workstation.py"), title="Review Workstation"),
])
pg.run()
