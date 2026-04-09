"""SpendCube spend metrics and KPI calculations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import load_config
from src.models.database import get_engine, get_transactions
from src.utils.logging import get_logger_from_config

# Status → numeric score mapping for data quality
_STATUS_SCORES = {"GREEN": 100, "AMBER": 60, "RED": 20}


class CubeMetrics:
    """Compute all KPI and derived metrics from the spend cube DataFrames.

    Args:
        cube: Dict returned by SpendCubeBuilder.build().
        config: SpendCube config object.
    """

    def __init__(self, cube: dict[str, pd.DataFrame], config):
        self.cube = cube
        self.config = config
        self.logger = get_logger_from_config(__name__, config)

        txn = cube.get("transactions", pd.DataFrame())
        # Addressable: exclude intercompany and tax lines
        if txn.empty:
            self._addr = pd.DataFrame()
        else:
            self._addr = txn[
                (txn.get("is_intercompany", pd.Series([0] * len(txn))) != 1)
                & (txn.get("is_tax_line", pd.Series([0] * len(txn))) != 1)
            ].copy()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def compute_all(self) -> dict:
        """Compute and return all scalar KPIs as a flat dict."""
        kpis: dict = {}

        addr = self._addr
        txn = self.cube.get("transactions", pd.DataFrame())

        total_spend = float(addr["base_amount"].sum()) if not addr.empty else 0.0
        kpis["total_spend"] = total_spend

        if not addr.empty:
            kpis["total_suppliers"] = int(addr["canonical_supplier_id"].nunique())
            kpis["total_invoices"] = int(addr["invoice_number"].nunique())
        else:
            kpis["total_suppliers"] = 0
            kpis["total_invoices"] = 0

        kpis["avg_transaction_size"] = (
            total_spend / kpis["total_invoices"] if kpis["total_invoices"] > 0 else 0.0
        )

        # Contract coverage
        kpis["contract_coverage_pct"] = self._contract_coverage(addr, total_spend)

        # Maverick spend
        kpis["maverick_spend_pct"] = self._maverick_spend(addr, total_spend)

        # Tail spend (uses full transactions for total, tail flag already set)
        kpis["tail_spend_pct"], kpis["tail_supplier_count"] = self._tail_spend(txn)

        # Payment terms
        kpis["weighted_avg_payment_terms"], kpis["pct_missing_payment_terms"] = (
            self._payment_terms_metrics(addr)
        )

        # Concentration
        hhi, top10, pareto80 = self._concentration(addr, total_spend)
        kpis["hhi"] = hhi
        kpis["top_10_supplier_pct"] = top10
        kpis["pareto_80_supplier_count"] = pareto80

        # Working capital opportunity at default parameters
        kpis["working_capital_opportunity"] = self.working_capital_opportunity(
            addr=addr
        )

        # Data quality score
        kpis["data_quality_score"] = self._data_quality_score(txn)

        return kpis

    def working_capital_opportunity(
        self,
        target_days: int = 45,
        wacc: float = 0.08,
        addr: Optional[pd.DataFrame] = None,
    ) -> float:
        """Estimate working capital opportunity across top-50 suppliers.

        For each of the top 50 suppliers (by spend), computes:
            max(0, (target_days - supplier_avg_terms) / 365 * supplier_spend * wacc)

        Suppliers with no payment terms data are excluded.

        Args:
            target_days: Target payment terms in days (default 45).
            wacc: Weighted average cost of capital (default 0.08).
            addr: Addressable spend DataFrame; uses internal if not provided.

        Returns:
            Total working capital opportunity in base currency.
        """
        if addr is None:
            addr = self._addr

        if addr.empty or "payment_terms_days" not in addr.columns:
            return 0.0

        has_terms = addr.dropna(subset=["payment_terms_days"])
        if has_terms.empty:
            return 0.0

        supplier_stats = (
            has_terms.groupby("canonical_supplier_id")
            .agg(supplier_spend=("base_amount", "sum"), avg_terms=("payment_terms_days", "mean"))
            .sort_values("supplier_spend", ascending=False)
            .head(50)
        )

        opportunity = supplier_stats.apply(
            lambda row: max(
                0.0,
                (target_days - row["avg_terms"]) / 365.0 * row["supplier_spend"] * wacc,
            ),
            axis=1,
        ).sum()

        return float(opportunity)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _contract_coverage(self, addr: pd.DataFrame, total_spend: float) -> float:
        if addr.empty or total_spend == 0 or "is_on_contract" not in addr.columns:
            return 0.0
        on_contract_spend = float(addr[addr["is_on_contract"] == 1]["base_amount"].sum())
        return round(on_contract_spend / total_spend, 4)

    def _maverick_spend(self, addr: pd.DataFrame, total_spend: float) -> float:
        if addr.empty or total_spend == 0:
            return 0.0

        po_null = addr["po_number"].isna() if "po_number" in addr.columns else pd.Series([True] * len(addr))

        if "is_on_contract" in addr.columns:
            not_contracted = addr["is_on_contract"] != 1
        else:
            not_contracted = pd.Series([True] * len(addr), index=addr.index)

        maverick = addr[po_null & not_contracted]
        return round(float(maverick["base_amount"].sum()) / total_spend, 4)

    def _tail_spend(self, txn: pd.DataFrame) -> tuple[float, int]:
        if txn.empty or "is_tail_spend" not in txn.columns:
            return 0.0, 0

        total_spend = float(txn["base_amount"].sum())
        if total_spend == 0:
            return 0.0, 0

        tail_rows = txn[txn["is_tail_spend"] == True]  # noqa: E712
        tail_spend = float(tail_rows["base_amount"].sum())
        tail_supplier_count = int(tail_rows["canonical_supplier_id"].nunique())

        return round(tail_spend / total_spend, 4), tail_supplier_count

    def _payment_terms_metrics(self, addr: pd.DataFrame) -> tuple[float, float]:
        if addr.empty or "payment_terms_days" not in addr.columns:
            return 0.0, 1.0

        has_terms = addr.dropna(subset=["payment_terms_days"])
        total_rows = len(addr)
        missing_rows = total_rows - len(has_terms)

        pct_missing = round(missing_rows / total_rows, 4) if total_rows > 0 else 1.0

        if has_terms.empty:
            return 0.0, pct_missing

        numerator = (has_terms["base_amount"] * has_terms["payment_terms_days"]).sum()
        denominator = has_terms["base_amount"].sum()

        weighted_avg = float(numerator / denominator) if denominator != 0 else 0.0
        return round(weighted_avg, 2), pct_missing

    def _concentration(
        self, addr: pd.DataFrame, total_spend: float
    ) -> tuple[float, float, int]:
        """Returns (hhi, top_10_supplier_pct, pareto_80_supplier_count)."""
        if addr.empty or total_spend == 0 or "canonical_supplier_id" not in addr.columns:
            return 0.0, 0.0, 0

        supplier_spend = (
            addr.groupby("canonical_supplier_id")["base_amount"]
            .sum()
            .sort_values(ascending=False)
        )

        shares = supplier_spend / total_spend
        hhi = float((shares ** 2).sum() * 10_000)

        top10_pct = round(float(supplier_spend.head(10).sum() / total_spend), 4)

        cumulative = supplier_spend.cumsum() / total_spend
        pareto80 = int((cumulative < 0.80).sum()) + 1  # +1 for the one that crosses 80%
        pareto80 = min(pareto80, len(supplier_spend))

        return round(hhi, 2), top10_pct, pareto80

    def _data_quality_score(self, txn: pd.DataFrame) -> Optional[float]:
        """Compute data quality score (0-100) via the diagnostics module.

        Returns None if the diagnostics module is not yet implemented.
        """
        try:
            from src.diagnostics.quality import DataQualityDiagnostics  # noqa: PLC0415

            diag = DataQualityDiagnostics(txn, self.config)
            results = diag.run_all()
            if not results:
                return None
            scores = [
                _STATUS_SCORES.get(v.get("status", "RED"), 0) for v in results.values()
            ]
            return round(sum(scores) / len(scores), 1)
        except (ImportError, AttributeError, NotImplementedError):
            self.logger.debug("Diagnostics module not yet available; skipping data_quality_score")
            return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _format_table(kpis: dict) -> str:
    rows = []
    for key, value in kpis.items():
        if value is None:
            formatted = "N/A"
        elif isinstance(value, float):
            if key.endswith("_pct") or key.startswith("pct_"):
                formatted = f"{value:.1%}"
            elif key in ("hhi",):
                formatted = f"{value:,.1f}"
            elif key in ("weighted_avg_payment_terms",):
                formatted = f"{value:.1f} days"
            elif key in ("working_capital_opportunity", "total_spend", "avg_transaction_size"):
                formatted = f"${value:,.0f}"
            else:
                formatted = f"{value:.4f}"
        elif isinstance(value, int):
            formatted = f"{value:,}"
        else:
            formatted = str(value)
        rows.append((key.replace("_", " ").title(), formatted))

    col_width = max(len(r[0]) for r in rows)
    lines = [f"{'Metric':<{col_width}}  {'Value'}"]
    lines.append("-" * (col_width + 20))
    for label, val in rows:
        lines.append(f"{label:<{col_width}}  {val}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute SpendCube KPI metrics")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    engine = get_engine(args.db)

    from src.cube.builder import SpendCubeBuilder  # noqa: PLC0415

    builder = SpendCubeBuilder(config, engine)
    cube = builder.build()

    metrics = CubeMetrics(cube, config)
    kpis = metrics.compute_all()

    print("\nSpendCube KPI Report")
    print("=" * 50)
    print(_format_table(kpis))
