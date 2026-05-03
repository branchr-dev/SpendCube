"""SpendCube Phase 4 pipeline orchestrator.

Runs builder → metrics → exporter → diagnostics in sequence and prints
a final summary of key KPIs and the data quality scorecard.

Usage:
    python src/cube/pipeline.py --db data/db/spend_cube.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
from sqlalchemy import update as sa_update

from src.config import load_config
from src.cube.builder import SpendCubeBuilder
from src.cube.exporter import CubeExporter
from src.cube.metrics import CubeMetrics
from src.diagnostics.quality import DataQualityDiagnostics
from src.models.database import get_engine, transactions_table
from src.utils.logging import get_logger_from_config


def _compute_abc_segments(engine, df: pd.DataFrame) -> None:
    """Compute ABC segment per supplier and write back to the transactions table.

    Pareto convention: A = top 80% of spend, B = next 15%, C = bottom 5%.
    Computed per engagement_id when the column is present.
    """
    addr = df[(df["is_intercompany"] != 1) & (df["is_tax_line"] != 1)].copy()
    if addr.empty or addr["canonical_supplier_id"].isna().all():
        return

    has_engagement = "engagement_id" in addr.columns

    group_cols = (
        ["engagement_id", "canonical_supplier_id"]
        if has_engagement
        else ["canonical_supplier_id"]
    )

    supplier_spend = (
        addr.groupby(group_cols, dropna=False)["base_amount"]
        .sum()
        .reset_index()
        .rename(columns={"base_amount": "total_spend"})
    )

    abc_rows: list[pd.DataFrame] = []
    if has_engagement:
        engagement_groups = supplier_spend.groupby("engagement_id", dropna=False)
    else:
        engagement_groups = [("_all", supplier_spend)]

    for _eng_id, group in engagement_groups:
        group = group.sort_values("total_spend", ascending=False).copy()
        total = group["total_spend"].sum()
        if total == 0:
            continue
        group["cumulative_pct"] = group["total_spend"].cumsum() / total
        group["abc_segment"] = group["cumulative_pct"].apply(
            lambda x: "A" if x <= 0.80 else ("B" if x <= 0.95 else "C")
        )
        abc_rows.append(group)

    if not abc_rows:
        return

    abc_df = pd.concat(abc_rows, ignore_index=True)

    with engine.begin() as conn:
        for _, row in abc_df.iterrows():
            sid = row["canonical_supplier_id"]
            segment = row["abc_segment"]
            if pd.isna(sid):
                continue
            stmt = (
                sa_update(transactions_table)
                .where(transactions_table.c.canonical_supplier_id == sid)
                .values(abc_segment=segment)
            )
            if has_engagement and not pd.isna(row.get("engagement_id")):
                stmt = stmt.where(
                    transactions_table.c.engagement_id == row["engagement_id"]
                )
            conn.execute(stmt)


def run_pipeline(db_path: str, config_path: str = "config.yaml", output_dir: str = "data/output") -> dict:
    """Run the full Phase 4 pipeline and return a summary dict.

    Steps:
        1. Build spend cube (builder)
        2. Compute KPI metrics (metrics)
        3. Export to Parquet (exporter)
        4. Run data quality diagnostics (diagnostics)

    Args:
        db_path: Path to the SQLite database file.
        config_path: Path to config.yaml.
        output_dir: Directory to write output files.

    Returns:
        Dict with keys: kpis, export_paths, diagnostics_results, scorecard_path.
    """
    config = load_config(config_path)
    logger = get_logger_from_config(__name__, config)
    engine = get_engine(db_path)

    # Step 1: Build cube
    logger.info("Step 1/4 — Building spend cube")
    builder = SpendCubeBuilder(config, engine)
    cube = builder.build()

    # Step 1b: Compute and write ABC segments
    logger.info("Step 1b — Computing ABC supplier segments")
    _compute_abc_segments(engine, cube.get("transactions", pd.DataFrame()))

    # Step 2: Compute metrics
    logger.info("Step 2/4 — Computing KPI metrics")
    metrics = CubeMetrics(cube, config)
    kpis = metrics.compute_all()

    # Step 3: Export to Parquet
    logger.info("Step 3/4 — Exporting cube to Parquet")
    exporter = CubeExporter(output_dir, config=config)
    export_paths = exporter.export_parquet(cube)

    # Step 4: Run diagnostics
    logger.info("Step 4/4 — Running data quality diagnostics")
    txn_df = cube.get("transactions")
    diag = DataQualityDiagnostics(txn_df, config)
    diagnostics_results = diag.run_all()
    scorecard_path = diag.export_json(str(Path(output_dir) / "quality_scorecard.json"))
    scorecard_text = diag.generate_scorecard()

    return {
        "kpis": kpis,
        "export_paths": export_paths,
        "diagnostics_results": diagnostics_results,
        "scorecard_path": scorecard_path,
        "scorecard_text": scorecard_text,
    }


def _print_summary(result: dict) -> None:
    kpis = result["kpis"]

    print("\n" + "=" * 60)
    print("SpendCube Phase 4 Pipeline — Summary")
    print("=" * 60)

    def _fmt_currency(v):
        return f"${v:,.0f}" if v is not None else "N/A"

    def _fmt_pct(v):
        return f"{v:.1%}" if v is not None else "N/A"

    def _fmt_int(v):
        return f"{v:,}" if v is not None else "N/A"

    print(f"\n  Total Spend:              {_fmt_currency(kpis.get('total_spend'))}")
    print(f"  Unique Suppliers:         {_fmt_int(kpis.get('total_suppliers'))}")
    print(f"  Invoice Count:            {_fmt_int(kpis.get('total_invoices'))}")
    print(f"  Avg Transaction Size:     {_fmt_currency(kpis.get('avg_transaction_size'))}")
    print(f"  Contract Coverage:        {_fmt_pct(kpis.get('contract_coverage_pct'))}")
    print(f"  Maverick Spend:           {_fmt_pct(kpis.get('maverick_spend_pct'))}")
    print(f"  Tail Spend:               {_fmt_pct(kpis.get('tail_spend_pct'))}")
    print(f"  Tail Supplier Count:      {_fmt_int(kpis.get('tail_supplier_count'))}")
    dqs = kpis.get("data_quality_score")
    print(f"  Data Quality Score:       {f'{dqs:.1f}/100' if dqs is not None else 'N/A'}")

    print("\nExported files:")
    for key, path in result["export_paths"].items():
        size = Path(path).stat().st_size if Path(path).exists() else 0
        print(f"  {key}: {path}  ({size:,} bytes)")

    print(f"\nQuality scorecard: {result['scorecard_path']}")
    print("\n" + result["scorecard_text"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SpendCube Phase 4 pipeline end-to-end")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--output", default="data/output", help="Output directory")
    args = parser.parse_args()

    result = run_pipeline(args.db, args.config, args.output)
    _print_summary(result)
