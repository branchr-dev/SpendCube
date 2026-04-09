"""SpendCube OLAP cube construction entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import load_config
from src.models.database import get_engine, get_transactions
from src.utils.logging import get_logger_from_config


_PAYMENT_BUCKETS = [
    (0, 14, "0-14"),
    (15, 30, "15-30"),
    (31, 45, "31-45"),
    (46, 60, "46-60"),
    (61, None, "60+"),
]

_CUBE_KEYS = ("transactions", "by_supplier", "by_category", "by_bu", "by_month", "by_payment_terms")


def _payment_terms_bucket(days) -> str:
    if pd.isna(days):
        return "Unknown"
    d = int(days)
    for lo, hi, label in _PAYMENT_BUCKETS:
        if hi is None:
            if d >= lo:
                return label
        elif lo <= d <= hi:
            return label
    return "Unknown"


class SpendCubeBuilder:
    """Build the dimensional spend cube from canonical transactions.

    Args:
        config: SpendCube Config object.
        engine: SQLAlchemy engine connected to the SpendCube database.
    """

    def __init__(self, config, engine):
        self.config = config
        self.engine = engine
        self.logger = get_logger_from_config(__name__, config)
        sc = config.spend_cube
        # tail_spend_value_pct = fraction of total spend that the TAIL contributes (default 0.20)
        # => top suppliers account for (1 - 0.20) = 0.80 of spend
        self._non_tail_threshold = 1.0 - sc.tail_spend_value_pct
        self.spend_concentration: dict = {}

    def build(self) -> dict[str, pd.DataFrame]:
        """Load transactions and materialise all cube views.

        Returns:
            Dict with keys: 'transactions', 'by_supplier', 'by_category',
            'by_bu', 'by_month', 'by_payment_terms'.
        """
        self.logger.info("Loading transactions from database")
        df = get_transactions(self.engine)

        if df.empty:
            self.logger.warning("No transactions found — returning empty cube")
            return {k: pd.DataFrame() for k in _CUBE_KEYS}

        # Time dimensions
        df = self._add_time_dimensions(df)

        # Tail spend flag
        df = self._add_tail_spend_flag(df)

        # Addressable spend: exclude intercompany and tax lines
        addr = df[(df["is_intercompany"] != 1) & (df["is_tax_line"] != 1)].copy()

        # Standard aggregation measures
        agg = {
            "base_amount": "sum",
            "invoice_number": "count",
            "po_number": "count",
            "payment_terms_days": "mean",
        }

        by_supplier = (
            addr.groupby(["canonical_supplier_name", "parent_company_name"], dropna=False)
            .agg(agg)
            .reset_index()
        )

        by_category = (
            addr.groupby(["category_l1", "category_l2", "category_l3"], dropna=False)
            .agg(agg)
            .reset_index()
        )

        by_bu = (
            addr.groupby(["business_unit", "cost_centre"], dropna=False)
            .agg(agg)
            .reset_index()
        )

        by_month = (
            addr.groupby("invoice_month", dropna=False)
            .agg(agg)
            .reset_index()
        )

        addr["payment_terms_bucket"] = addr["payment_terms_days"].apply(_payment_terms_bucket)
        by_payment_terms = (
            addr.groupby("payment_terms_bucket", dropna=False)
            .agg(agg)
            .reset_index()
        )

        # Concentration metrics as attribute (available after build)
        self.spend_concentration = self._compute_concentration(addr)

        self.logger.info(
            "Cube built: %d transactions, %d unique suppliers, %d categories, %d business units",
            len(df),
            addr["canonical_supplier_id"].nunique(),
            addr["category_l1"].nunique(),
            addr["business_unit"].nunique(),
        )

        return {
            "transactions": df,
            "by_supplier": by_supplier,
            "by_category": by_category,
            "by_bu": by_bu,
            "by_month": by_month,
            "by_payment_terms": by_payment_terms,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _add_time_dimensions(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        dates = pd.to_datetime(df["invoice_date"], errors="coerce")
        df["invoice_year"] = dates.dt.year.where(dates.notna()).astype("Int64")
        df["invoice_month"] = dates.dt.strftime("%Y-%m").where(dates.notna())
        df["invoice_quarter"] = (
            dates.dt.year.astype(str) + "-Q" + dates.dt.quarter.astype(str)
        ).where(dates.notna())
        return df

    def _add_tail_spend_flag(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        addr = df[(df["is_intercompany"] != 1) & (df["is_tax_line"] != 1)]

        if addr.empty or addr["canonical_supplier_id"].isna().all():
            df["is_tail_spend"] = False
            return df

        supplier_spend = (
            addr.groupby("canonical_supplier_id")["base_amount"]
            .sum()
            .sort_values(ascending=False)
        )
        total_spend = supplier_spend.sum()

        if total_spend == 0:
            df["is_tail_spend"] = False
            return df

        n_suppliers = len(supplier_spend)

        if n_suppliers < 10:
            # Small dataset fallback: tail = suppliers below median spend
            median_spend = supplier_spend.median()
            tail_suppliers = set(supplier_spend[supplier_spend < median_spend].index)
        else:
            # Standard: find top suppliers that account for (1 - tail_value_pct) of spend.
            # A supplier is tail if the cumulative spend BEFORE adding it already meets threshold.
            cumulative_pct = supplier_spend.cumsum() / total_spend
            shifted = cumulative_pct.shift(1, fill_value=0.0)
            tail_suppliers = set(supplier_spend.index[shifted >= self._non_tail_threshold])

        df["is_tail_spend"] = df["canonical_supplier_id"].isin(tail_suppliers)
        return df

    def _compute_concentration(self, addr: pd.DataFrame) -> dict:
        total = addr["base_amount"].sum()
        if total == 0:
            return {
                "top_10_supplier_pct": 0.0,
                "top_20_supplier_pct": 0.0,
                "top_50_supplier_pct": 0.0,
            }
        supplier_spend = (
            addr.groupby("canonical_supplier_id")["base_amount"]
            .sum()
            .sort_values(ascending=False)
        )
        return {
            "top_10_supplier_pct": round(supplier_spend.head(10).sum() / total, 4),
            "top_20_supplier_pct": round(supplier_spend.head(20).sum() / total, 4),
            "top_50_supplier_pct": round(supplier_spend.head(50).sum() / total, 4),
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build SpendCube dimensional cube")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--output", default=None, help="Output directory (optional)")
    args = parser.parse_args()

    config = load_config(args.config)
    engine = get_engine(args.db)

    builder = SpendCubeBuilder(config, engine)
    cube = builder.build()

    df = cube["transactions"]
    addr = df[(df.get("is_intercompany", 0) != 1) & (df.get("is_tax_line", 0) != 1)]

    print(
        f"{len(df)} transactions, "
        f"{addr['canonical_supplier_id'].nunique()} canonical suppliers, "
        f"{addr['category_l1'].nunique()} categories, "
        f"{addr['business_unit'].nunique()} business units"
    )

    conc = builder.spend_concentration
    if conc:
        print(
            f"Concentration: top-10={conc['top_10_supplier_pct']:.1%}, "
            f"top-20={conc['top_20_supplier_pct']:.1%}, "
            f"top-50={conc['top_50_supplier_pct']:.1%}"
        )

    if args.output:
        from src.cube.exporter import CubeExporter  # noqa: PLC0415
        exporter = CubeExporter(args.output)
        paths = exporter.export_parquet(cube)
        for key, path in paths.items():
            print(f"  {key}: {path}")
