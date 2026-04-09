"""SpendCube data quality diagnostics and scoring."""

from __future__ import annotations

import argparse
import json
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

_WEAK_DESCRIPTION_TERMS = frozenset(
    {"misc", "miscellaneous", "services", "payment", "invoice", "charges"}
)

_STATUS_EMOJI = {
    "GREEN": "✅",
    "AMBER": "⚠️",
    "RED": "🔴",
    "INFO": "✅",
    "WARN": "⚠️",
    "ALERT": "🔴",
}


def _get_status(pct: float, green_threshold: float, amber_threshold: float) -> str:
    """Return GREEN/AMBER/RED based on percentage and thresholds (lower is better)."""
    if pct < green_threshold:
        return "GREEN"
    if pct < amber_threshold:
        return "AMBER"
    return "RED"


def _get_info_status(pct: float, info_threshold: float, warn_threshold: float) -> str:
    """Return INFO/WARN/ALERT based on percentage and thresholds (lower is better)."""
    if pct < info_threshold:
        return "INFO"
    if pct < warn_threshold:
        return "WARN"
    return "ALERT"


class DataQualityDiagnostics:
    """Run all data quality diagnostic checks on a transactions DataFrame.

    Args:
        transactions_df: DataFrame loaded from the transactions table.
        config: SpendCube config object.
    """

    def __init__(self, transactions_df: pd.DataFrame, config) -> None:
        self.df = transactions_df.copy()
        self.config = config
        self._results: dict[str, dict] | None = None

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_missing_supplier_name(self) -> dict:
        """Pct rows where raw_supplier_name is null. GREEN<1%, AMBER 1-5%, RED>5%."""
        total = len(self.df)
        missing = self.df["raw_supplier_name"].isna().sum() if total else 0
        pct = (missing / total * 100) if total else 0.0
        green, amber = 1.0, 5.0
        return {
            "value": int(missing),
            "pct": round(pct, 2),
            "status": _get_status(pct, green, amber),
            "green_threshold": green,
            "amber_threshold": amber,
            "description": "Rows missing raw_supplier_name",
            "remediation": "Enrich source data or add supplier name fallback from vendor ID.",
        }

    def check_uncategorised_spend(self) -> dict:
        """Pct spend (base_amount) where category_l1 is null. GREEN<5%, AMBER 5-15%, RED>15%."""
        col = "category_l1" if "category_l1" in self.df.columns else "internal_category_l1"
        total_spend = self.df["base_amount"].abs().sum()
        if col in self.df.columns:
            uncategorised_mask = self.df[col].isna()
        else:
            uncategorised_mask = pd.Series(True, index=self.df.index)
        uncategorised_spend = self.df.loc[uncategorised_mask, "base_amount"].abs().sum()
        pct = (uncategorised_spend / total_spend * 100) if total_spend else 0.0
        green, amber = 5.0, 15.0
        return {
            "value": round(float(uncategorised_spend), 2),
            "pct": round(pct, 2),
            "status": _get_status(pct, green, amber),
            "green_threshold": green,
            "amber_threshold": amber,
            "description": "Spend (base_amount) with no category assignment",
            "remediation": "Run categorisation pipeline; add keyword rules or GL mappings for uncategorised GL codes.",
        }

    def check_unresolved_suppliers(self) -> dict:
        """Pct unique raw_supplier_names where canonical_supplier_id is null. GREEN<10%, AMBER 10-25%, RED>25%."""
        if "raw_supplier_name" not in self.df.columns:
            return self._empty_check("check_unresolved_suppliers", 10.0, 25.0)
        unique_suppliers = self.df.groupby("raw_supplier_name")["canonical_supplier_id"].first()
        total_unique = len(unique_suppliers)
        unresolved = unique_suppliers.isna().sum()
        pct = (unresolved / total_unique * 100) if total_unique else 0.0
        green, amber = 10.0, 25.0
        return {
            "value": int(unresolved),
            "pct": round(pct, 2),
            "status": _get_status(pct, green, amber),
            "green_threshold": green,
            "amber_threshold": amber,
            "description": "Unique raw supplier names with no canonical ID resolved",
            "remediation": "Review supplier match log (PENDING status); lower fuzzy threshold or add manual overrides.",
        }

    def check_missing_payment_terms(self) -> dict:
        """Pct spend where payment_terms_days is null. GREEN<10%, AMBER 10-30%, RED>30%."""
        total_spend = self.df["base_amount"].abs().sum()
        missing_mask = self.df["payment_terms_days"].isna()
        missing_spend = self.df.loc[missing_mask, "base_amount"].abs().sum()
        pct = (missing_spend / total_spend * 100) if total_spend else 0.0
        green, amber = 10.0, 30.0
        return {
            "value": round(float(missing_spend), 2),
            "pct": round(pct, 2),
            "status": _get_status(pct, green, amber),
            "green_threshold": green,
            "amber_threshold": amber,
            "description": "Spend with no payment terms days populated",
            "remediation": "Parse raw_payment_terms field; enrich from supplier master or contract data.",
        }

    def check_duplicate_invoice_risk(self) -> dict:
        """Pct rows where (invoice_number, base_amount) appears >1 time. GREEN<0.5%, AMBER 0.5-2%, RED>2%."""
        total = len(self.df)
        if total == 0:
            pct = 0.0
            duplicate_count = 0
        else:
            counts = self.df.groupby(["invoice_number", "base_amount"])["transaction_id"].transform("count")
            duplicate_count = int((counts > 1).sum())
            pct = duplicate_count / total * 100
        green, amber = 0.5, 2.0
        return {
            "value": duplicate_count,
            "pct": round(pct, 2),
            "status": _get_status(pct, green, amber),
            "green_threshold": green,
            "amber_threshold": amber,
            "description": "Rows sharing an (invoice_number, base_amount) key — potential duplicate payments",
            "remediation": "Review is_duplicate flag; investigate AP process for duplicate invoice controls.",
        }

    def check_negative_reversal_lines(self) -> dict:
        """Pct rows where base_amount < 0. INFO<3%, WARN 3-8%, ALERT>8%."""
        total = len(self.df)
        negative_count = int((self.df["base_amount"] < 0).sum()) if total else 0
        pct = (negative_count / total * 100) if total else 0.0
        info_thresh, warn_thresh = 3.0, 8.0
        return {
            "value": negative_count,
            "pct": round(pct, 2),
            "status": _get_info_status(pct, info_thresh, warn_thresh),
            "green_threshold": info_thresh,
            "amber_threshold": warn_thresh,
            "description": "Rows with negative base_amount (credit notes / reversals)",
            "remediation": "High reversal rates may indicate AP process issues or over-accruals; investigate with finance.",
        }

    def check_weak_descriptions(self) -> dict:
        """Pct rows with null, short (<5 words), or generic raw_line_description. GREEN<15%, AMBER 15-30%, RED>30%."""
        total = len(self.df)
        if total == 0:
            pct = 0.0
            weak_count = 0
        else:
            col = self.df["raw_line_description"]
            is_null = col.isna()
            is_generic = col.str.lower().isin(_WEAK_DESCRIPTION_TERMS).fillna(False)
            is_short = (~is_null & ~is_generic) & (col.str.split().str.len().fillna(0) < 5)
            weak_mask = is_null | is_generic | is_short
            weak_count = int(weak_mask.sum())
            pct = weak_count / total * 100
        green, amber = 15.0, 30.0
        return {
            "value": weak_count,
            "pct": round(pct, 2),
            "status": _get_status(pct, green, amber),
            "green_threshold": green,
            "amber_threshold": amber,
            "description": "Rows with null, <5-word, or generic line description",
            "remediation": "Enrich descriptions from PO/contract data; add description enrichment rules.",
        }

    def check_missing_contract_linkage(self) -> dict:
        """Pct spend where po_number is null AND contract_id is null. GREEN<30%, AMBER 30-60%, RED>60%."""
        total_spend = self.df["base_amount"].abs().sum()
        po_null = self.df["po_number"].isna()
        if "contract_id" in self.df.columns:
            contract_null = self.df["contract_id"].isna()
        else:
            contract_null = pd.Series(True, index=self.df.index)
        no_linkage_mask = po_null & contract_null
        no_linkage_spend = self.df.loc[no_linkage_mask, "base_amount"].abs().sum()
        pct = (no_linkage_spend / total_spend * 100) if total_spend else 0.0
        green, amber = 30.0, 60.0
        return {
            "value": round(float(no_linkage_spend), 2),
            "pct": round(pct, 2),
            "status": _get_status(pct, green, amber),
            "green_threshold": green,
            "amber_threshold": amber,
            "description": "Spend with neither a PO number nor a contract ID (uncontrolled spend)",
            "remediation": "Mandate PO creation for categories above threshold; implement contract catalogue.",
        }

    def check_missing_bu_cost_centre(self) -> dict:
        """Pct rows where business_unit is null AND cost_centre is null. GREEN<5%, AMBER 5-15%, RED>15%."""
        total = len(self.df)
        bu_null = self.df["business_unit"].isna() if "business_unit" in self.df.columns else pd.Series(True, index=self.df.index)
        cc_null = self.df["cost_centre"].isna() if "cost_centre" in self.df.columns else pd.Series(True, index=self.df.index)
        missing_both = int((bu_null & cc_null).sum()) if total else 0
        pct = (missing_both / total * 100) if total else 0.0
        green, amber = 5.0, 15.0
        return {
            "value": missing_both,
            "pct": round(pct, 2),
            "status": _get_status(pct, green, amber),
            "green_threshold": green,
            "amber_threshold": amber,
            "description": "Rows with no business unit and no cost centre",
            "remediation": "Enrich from GL account hierarchy; mandate BU/CC in AP data entry.",
        }

    # ------------------------------------------------------------------
    # Aggregate runner
    # ------------------------------------------------------------------

    def run_all(self) -> dict[str, dict]:
        """Run all 9 diagnostic checks and return structured results.

        Returns:
            dict mapping check name → {value, pct, status, green_threshold,
            amber_threshold, description, remediation}
        """
        self._results = {
            "missing_supplier_name": self.check_missing_supplier_name(),
            "uncategorised_spend": self.check_uncategorised_spend(),
            "unresolved_suppliers": self.check_unresolved_suppliers(),
            "missing_payment_terms": self.check_missing_payment_terms(),
            "duplicate_invoice_risk": self.check_duplicate_invoice_risk(),
            "negative_reversal_lines": self.check_negative_reversal_lines(),
            "weak_descriptions": self.check_weak_descriptions(),
            "missing_contract_linkage": self.check_missing_contract_linkage(),
            "missing_bu_cost_centre": self.check_missing_bu_cost_centre(),
        }
        return self._results

    # ------------------------------------------------------------------
    # Output methods
    # ------------------------------------------------------------------

    def generate_scorecard(self) -> str:
        """Return a formatted text scorecard with emoji status indicators."""
        if self._results is None:
            self.run_all()
        results = self._results

        lines = [
            "=" * 72,
            "  SpendCube Data Quality Scorecard",
            "=" * 72,
            f"  {'Check':<35} {'Pct':>7}  {'Status':<8}",
            "-" * 72,
        ]

        score_total = 0
        score_count = 0

        for name, r in results.items():
            status = r["status"]
            emoji = _STATUS_EMOJI.get(status, "  ")
            label = name.replace("_", " ").title()
            pct_str = f"{r['pct']:.1f}%"
            lines.append(f"  {label:<35} {pct_str:>7}  {emoji} {status}")

            # Numeric score for each check (GREEN=100, AMBER=50, RED=0; INFO=100, WARN=50, ALERT=0)
            if status in ("GREEN", "INFO"):
                score_total += 100
            elif status in ("AMBER", "WARN"):
                score_total += 50
            score_count += 1

        overall = score_total / score_count if score_count else 0
        lines += [
            "-" * 72,
            f"  Overall Data Quality Score: {overall:.0f}/100",
            "=" * 72,
            "",
            "  Remediation Guidance:",
        ]
        for name, r in results.items():
            if r["status"] not in ("GREEN", "INFO"):
                label = name.replace("_", " ").title()
                lines.append(f"  • {label}: {r['remediation']}")

        lines.append("=" * 72)
        return "\n".join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        """Return diagnostics as a DataFrame for dashboard use."""
        if self._results is None:
            self.run_all()
        rows = []
        for name, r in self._results.items():
            rows.append(
                {
                    "check": name,
                    "description": r["description"],
                    "value": r["value"],
                    "pct": r["pct"],
                    "status": r["status"],
                    "green_threshold": r["green_threshold"],
                    "amber_threshold": r["amber_threshold"],
                    "remediation": r["remediation"],
                }
            )
        return pd.DataFrame(rows)

    def export_json(self, path: str = "data/output/quality_scorecard.json") -> str:
        """Save scorecard to JSON and return the file path."""
        if self._results is None:
            self.run_all()
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(self._results, fh, indent=2, default=str)
        return str(output_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _empty_check(self, name: str, green: float, amber: float) -> dict:
        return {
            "value": 0,
            "pct": 0.0,
            "status": "GREEN",
            "green_threshold": green,
            "amber_threshold": amber,
            "description": f"{name} (column not available)",
            "remediation": "No action required.",
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SpendCube data quality diagnostics")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument(
        "--export",
        default="data/output/quality_scorecard.json",
        help="Path to export JSON scorecard (default: data/output/quality_scorecard.json)",
    )
    args = parser.parse_args()

    config = load_config()
    engine = get_engine(args.db)
    transactions_df = get_transactions(engine)

    diagnostics = DataQualityDiagnostics(transactions_df, config)
    diagnostics.run_all()

    print(diagnostics.generate_scorecard())

    json_path = diagnostics.export_json(args.export)
    print(f"\nScorecard exported to: {json_path}")
