#!/usr/bin/env python3
"""SpendCube pipeline evaluation harness.

Runs the full 6-phase pipeline against a temporary SQLite DB and prints a
structured 5-section quality report with PASS/WARN/FAIL verdicts.

Usage:
    python3 scripts/evaluate_pipeline.py              # 200-row synthetic data
    python3 scripts/evaluate_pipeline.py --csv file.csv
    python3 scripts/evaluate_pipeline.py --csv file.csv --db custom.db
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

# Add project root to sys.path before any src/ imports.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.yaml")


# ---------------------------------------------------------------------------
# Verdict helpers
# ---------------------------------------------------------------------------

def _pct_verdict(value: float, pass_thr: float, warn_thr: float) -> str:
    """PASS/WARN/FAIL where higher value is better (e.g. coverage_pct)."""
    if value >= pass_thr:
        return "PASS"
    if value >= warn_thr:
        return "WARN"
    return "FAIL"


def _count_verdict(value: int, pass_thr: int, warn_thr: int) -> str:
    """PASS/WARN/FAIL where higher count is better (e.g. recommendation count)."""
    if value >= pass_thr:
        return "PASS"
    if value >= warn_thr:
        return "WARN"
    return "FAIL"


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _run_eval(csv_path: str, db_path: str) -> dict:
    """Run all pipeline phases and return a structured results dict."""
    from src.config import load_config
    from src.models.database import (
        get_engine,
        get_transactions,
        init_db,
        transactions_table,
    )
    from src.ingestion.ingest import Ingestor
    from src.suppliers.harmoniser import SupplierHarmoniser
    from src.categorisation.categoriser import SpendCategoriser
    from src.cube.pipeline import run_pipeline
    from src.recommendations.engine import RecommendationEngine

    config = load_config(_CONFIG_PATH)
    engine = get_engine(db_path)
    init_db(engine)

    # ------------------------------------------------------------------
    # Phase 1: Ingestion
    # ------------------------------------------------------------------
    print("  [1/5] Ingesting data...")
    ingestor = Ingestor(config)
    row_count = ingestor.ingest_to_db(csv_path, engine)

    transactions_df = get_transactions(engine)
    credit_notes = int((transactions_df.get("is_credit_note", pd.Series(dtype=int)) == 1).sum())
    intercompany_filtered = int((transactions_df.get("is_intercompany", pd.Series(dtype=int)) == 1).sum())

    # ------------------------------------------------------------------
    # Phase 2: Supplier Harmonisation
    # ------------------------------------------------------------------
    print("  [2/5] Harmonising suppliers...")
    harmoniser = SupplierHarmoniser(config, engine)
    _supplier_master_df, match_log_df = harmoniser.harmonise(transactions_df)

    # Persist canonical supplier columns back to transactions table
    if not match_log_df.empty:
        enriched_df = harmoniser.update_transactions(transactions_df, match_log_df)
        col_map = {
            "canonical_supplier_id": "canonical_supplier_id",
            "canonical_supplier_name": "canonical_supplier_name",
            "supplier_match_confidence": "canonical_supplier_confidence",
            "parent_company_id": "parent_company_id",
            "parent_company_name": "parent_company_name",
        }
        db_col_names = {c.name for c in transactions_table.columns}
        update_cols = [
            (src, dst)
            for src, dst in col_map.items()
            if src in enriched_df.columns and dst in db_col_names
        ]
        if update_cols and "transaction_id" in enriched_df.columns:
            with engine.begin() as conn:
                for _, row in enriched_df.iterrows():
                    vals = {dst: row.get(src) for src, dst in update_cols}
                    conn.execute(
                        transactions_table.update()
                        .where(transactions_table.c.transaction_id == row["transaction_id"])
                        .values(**vals)
                    )

    # Compute supplier confidence stats
    canonical_suppliers = (
        match_log_df["canonical_supplier_id"].nunique() if not match_log_df.empty else 0
    )
    if not match_log_df.empty and "confidence" in match_log_df.columns:
        total_ml = len(match_log_df)
        conf_s = match_log_df["confidence"]
        s_high = int((conf_s >= 0.85).sum())
        s_medium = int(((conf_s >= 0.60) & (conf_s < 0.85)).sum())
        s_low = int((conf_s < 0.60).sum())
        s_high_pct = s_high / total_ml if total_ml else 0.0
        s_medium_pct = s_medium / total_ml if total_ml else 0.0
        s_low_pct = s_low / total_ml if total_ml else 0.0
        unmatched = s_low
    else:
        s_high_pct = s_medium_pct = s_low_pct = 0.0
        unmatched = 0

    # ------------------------------------------------------------------
    # Phase 3: Categorisation
    # ------------------------------------------------------------------
    print("  [3/5] Categorising spend...")
    transactions_df = get_transactions(engine)  # refresh post-harmonisation
    categoriser = SpendCategoriser(config, engine)
    result_df = categoriser.categorise(transactions_df)
    categoriser.update_transactions_in_db(result_df, engine)

    total_txn = len(result_df)
    if total_txn > 0 and "category_confidence" in result_df.columns:
        conf_c = result_df["category_confidence"].fillna(0.0)
        coverage_pct = float((conf_c >= 0.60).sum() / total_txn)
        c_high_pct = float((conf_c >= 0.85).sum() / total_txn)
        c_medium_pct = float(((conf_c >= 0.60) & (conf_c < 0.85)).sum() / total_txn)
        c_low_pct = float(((conf_c > 0.0) & (conf_c < 0.60)).sum() / total_txn)
        uncategorised = int((conf_c < 0.60).sum())
    else:
        coverage_pct = c_high_pct = c_medium_pct = c_low_pct = 0.0
        uncategorised = total_txn

    # ------------------------------------------------------------------
    # Phase 4: Cube + Diagnostics
    # ------------------------------------------------------------------
    print("  [4/5] Building spend cube and diagnostics...")
    temp_output = tempfile.mkdtemp(prefix="spendcube_eval_output_")
    try:
        pipeline_result = run_pipeline(db_path, _CONFIG_PATH, temp_output)
        diagnostics_results = pipeline_result.get("diagnostics_results", {})
    finally:
        shutil.rmtree(temp_output, ignore_errors=True)

    # ------------------------------------------------------------------
    # Phase 5 (Phase 6): Recommendations
    # ------------------------------------------------------------------
    print("  [5/5] Generating recommendations...")
    rec_engine = RecommendationEngine(config, get_engine(db_path))
    recommendations = rec_engine.run()
    portfolio = rec_engine._portfolio_summary

    return {
        "ingestion": {
            "row_count": row_count,
            "credit_notes": credit_notes,
            "intercompany_filtered": intercompany_filtered,
        },
        "harmonisation": {
            "canonical_suppliers": canonical_suppliers,
            "high_pct": s_high_pct,
            "medium_pct": s_medium_pct,
            "low_pct": s_low_pct,
            "unmatched": unmatched,
        },
        "categorisation": {
            "coverage_pct": coverage_pct,
            "high_pct": c_high_pct,
            "medium_pct": c_medium_pct,
            "low_pct": c_low_pct,
            "uncategorised": uncategorised,
        },
        "recommendations": {
            "count": len(recommendations),
            "types": sorted({r.get("type", "") for r in recommendations if r.get("type")}),
            "total_savings_aud": sum(r.get("estimated_impact_aud", 0.0) or 0.0 for r in recommendations),
            "sanity_check_passed": portfolio.get("sanity_check_passed", True),
        },
        "diagnostics": diagnostics_results,
    }


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def _print_report(results: dict) -> int:
    """Print 5-section report. Returns 0 if all verdicts pass, 1 if any FAIL."""
    SEP = "─" * 60

    def _pct_str(v: float) -> str:
        return f"{v * 100:.1f}%"

    def _aud_str(v: float) -> str:
        return f"${v:,.0f}"

    overall_fail = False

    print()
    print("=" * 60)
    print("  SpendCube Pipeline Evaluation Report")
    print("=" * 60)

    # ── Section 1: Ingestion ─────────────────────────────────────────
    s1 = results["ingestion"]
    print(f"\n{'─' * 60}")
    print("  Section 1 — Ingestion")
    print(f"{'─' * 60}")
    print(f"  row_count             : {s1['row_count']:,}")
    print(f"  credit_notes          : {s1['credit_notes']:,}")
    print(f"  intercompany_filtered : {s1['intercompany_filtered']:,}")

    # ── Section 2: Supplier Harmonisation ────────────────────────────
    s2 = results["harmonisation"]
    print(f"\n{SEP}")
    print("  Section 2 — Supplier Harmonisation")
    print(SEP)
    print(f"  canonical_suppliers   : {s2['canonical_suppliers']:,}")
    print(f"  high_pct (>= 0.85)    : {_pct_str(s2['high_pct'])}")
    print(f"  medium_pct (0.60–0.85): {_pct_str(s2['medium_pct'])}")
    print(f"  low_pct (< 0.60)      : {_pct_str(s2['low_pct'])}")
    print(f"  unmatched             : {s2['unmatched']:,}")

    # ── Section 3: Categorisation ─────────────────────────────────────
    s3 = results["categorisation"]
    cov_verdict = _pct_verdict(s3["coverage_pct"], 0.70, 0.50)
    if cov_verdict == "FAIL":
        overall_fail = True
    print(f"\n{SEP}")
    print("  Section 3 — Spend Categorisation")
    print(SEP)
    print(f"  coverage_pct          : {_pct_str(s3['coverage_pct'])}  [{cov_verdict}]")
    print(f"  high_pct (>= 0.85)    : {_pct_str(s3['high_pct'])}")
    print(f"  medium_pct (0.60–0.85): {_pct_str(s3['medium_pct'])}")
    print(f"  low_pct (< 0.60)      : {_pct_str(s3['low_pct'])}")
    print(f"  uncategorised         : {s3['uncategorised']:,}")

    # ── Section 4: Recommendations ───────────────────────────────────
    s4 = results["recommendations"]
    rec_verdict = _count_verdict(s4["count"], 3, 1)
    sanity_verdict = "PASS" if s4["sanity_check_passed"] else "FAIL"
    if rec_verdict == "FAIL" or sanity_verdict == "FAIL":
        overall_fail = True
    print(f"\n{SEP}")
    print("  Section 4 — Recommendations")
    print(SEP)
    print(f"  count                 : {s4['count']:,}  [{rec_verdict}]")
    print(f"  types                 : {', '.join(s4['types']) if s4['types'] else '—'}")
    print(f"  total_savings_aud     : {_aud_str(s4['total_savings_aud'])}")
    print(f"  sanity_check_passed   : {s4['sanity_check_passed']}  [{sanity_verdict}]")

    # ── Section 5: Data Quality ───────────────────────────────────────
    print(f"\n{SEP}")
    print("  Section 5 — Data Quality")
    print(SEP)
    diag = results["diagnostics"]
    if diag:
        for check_name, check in diag.items():
            status = check.get("status", "?")
            pct = check.get("pct", 0.0)
            print(f"  {check_name:<30}: {status:<5}  ({pct:.1f}%)")
    else:
        print("  (no diagnostics data)")

    # ── Overall ────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    overall = "FAIL" if overall_fail else "PASS"
    print(f"  Overall verdict: {overall}")
    print("=" * 60)
    print()

    return 1 if overall_fail else 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="SpendCube pipeline evaluation harness")
    parser.add_argument("--csv", default=None, metavar="PATH", help="Input CSV file (200-row synthetic data if omitted)")
    parser.add_argument("--db", default=None, metavar="PATH", help="SQLite DB path (temp file if omitted, deleted after run)")
    args = parser.parse_args()

    temp_csv_path: str | None = None
    temp_db_path: str | None = None

    try:
        # ── Generate synthetic data if no CSV provided ─────────────────
        if args.csv:
            csv_path = args.csv
        else:
            from src.utils.generate_test_data import generate_test_data

            fd, temp_csv_path = tempfile.mkstemp(suffix=".csv", prefix="spendcube_eval_")
            os.close(fd)
            csv_path = temp_csv_path

            print("Generating 200-row synthetic dataset...")
            df = generate_test_data(rows=200, seed=42)
            df.to_csv(csv_path, index=False)
            print(f"  Written to: {csv_path}")

        # ── Resolve DB path ─────────────────────────────────────────────
        if args.db:
            db_path = args.db
        else:
            fd, temp_db_path = tempfile.mkstemp(suffix=".db", prefix="spendcube_eval_")
            os.close(fd)
            db_path = temp_db_path

        print(f"\nRunning pipeline against: {db_path}")
        results = _run_eval(csv_path, db_path)
        exit_code = _print_report(results)

    finally:
        if temp_csv_path and os.path.exists(temp_csv_path):
            os.unlink(temp_csv_path)
        if temp_db_path and os.path.exists(temp_db_path):
            os.unlink(temp_db_path)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
