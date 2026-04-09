"""SpendCube Streamlit dashboard application entry point."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="SpendCube",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

_DATA_DIR = Path("data/output")
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
            f"Missing Parquet files: {', '.join(missing)}. "
            "Run `make build-cube` to generate the spend cube before launching the dashboard."
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


def main() -> None:
    st.title("SpendCube — Procurement Analytics")
    st.markdown(
        "Procurement spend analytics pipeline. "
        "Use the sidebar to navigate between dashboards."
    )

    cube = load_cube_data()

    if not cube:
        st.info(
            "No data found. Run the full pipeline first:\n\n"
            "```bash\nmake ingest && make harmonise && make categorise && make build-cube\n```"
        )
        return

    txn = cube.get("transactions", pd.DataFrame())
    suppliers = cube.get("by_supplier", pd.DataFrame())

    total_spend = float(txn["base_amount"].sum()) if "base_amount" in txn.columns else 0.0
    supplier_count = len(suppliers) if not suppliers.empty else 0
    invoice_count = len(txn)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Spend (AUD)", f"{total_spend:,.0f}")
    col2.metric("Suppliers", f"{supplier_count:,}")
    col3.metric("Invoices", f"{invoice_count:,}")

    st.markdown("---")
    st.markdown(
        "Navigate to a dashboard page using the sidebar on the left, "
        "or select from the pages listed below:\n\n"
        "- **Spend Overview** — KPIs, trends, category and supplier breakdown\n"
        "- **Category Deep Dive** — L1 → L2 → L3 drill-down with savings levers\n"
        "- **Supplier Deep Dive** — per-supplier spend, risk flags, related entities\n"
        "- **Payment Terms** — working capital opportunity analysis\n"
        "- **Data Quality** — 9-check scorecard with drill-down into issues\n"
    )


if __name__ == "__main__":
    main()
