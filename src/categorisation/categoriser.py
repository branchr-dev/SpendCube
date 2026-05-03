"""SpendCube categorisation pipeline entry point.

Orchestrates the full 6-pass spend categorisation pipeline in strict order:

  Pass 0: Category overrides (DB table) — confidence 1.0, method=MANUAL
  Pass 1: GL code mapping              — method=DETERMINISTIC_GL
  Pass 2: Supplier name mapping        — method=DETERMINISTIC_SUPPLIER
  Pass 3: Keyword/regex rules          — method=KEYWORD
  Pass 4: Embedding similarity         — method=EMBEDDING
  Pass 5: LLM fallback (Claude API)    — confidence capped 0.70, method=LLM

Rows still below confidence_medium (0.60) after all passes → review queue.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import insert as sa_insert, update

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.categorisation.deterministic import DeterministicCategoriser
from src.categorisation.embedding_classifier import EmbeddingCategoriser
from src.categorisation.llm_classifier import LLMCategoriser
from src.models.database import (
    category_overrides_table,
    get_engine,
    get_transactions,
    init_db,
    transactions_table,
)
from src.utils.logging import get_logger_from_config


class SpendCategoriser:
    """Orchestrates the full 6-pass spend categorisation pipeline.

    Args:
        config: SpendCube Config object.
        engine: SQLAlchemy engine connected to the SpendCube database.
    """

    def __init__(self, config, engine) -> None:
        self.config = config
        self.engine = engine
        self.logger = get_logger_from_config(__name__, config)

        reference_dir = Path(config.paths.reference_dir)
        seed_mappings_path = str(reference_dir / "category_seed_mappings.csv")
        hierarchy_path = str(reference_dir / "internal_category_hierarchy.csv")
        cache_path = str(Path(config.paths.data_dir) / "cache" / "category_embeddings.pkl")

        self.deterministic = DeterministicCategoriser(
            seed_mappings_path=seed_mappings_path,
            engine=engine,
            config=config,
        )
        self.embedding = EmbeddingCategoriser(
            hierarchy_path=hierarchy_path,
            cache_path=cache_path,
            config=config,
        )
        self.llm = LLMCategoriser(
            config=config,
            hierarchy_path=hierarchy_path,
        )

    # ── Main orchestrator ─────────────────────────────────────────────────

    def categorise(self, transactions_df: pd.DataFrame) -> pd.DataFrame:
        """Run all 6 categorisation passes in strict order.

        Each pass processes only rows not yet classified at or above
        confidence_medium (0.60). Rows classified by an earlier pass are
        not re-processed.

        Args:
            transactions_df: DataFrame of transactions to categorise.

        Returns:
            Full transactions_df with category_l1, category_l2, category_l3,
            unspsc_code, category_confidence, category_method populated.
            Rows that could not be classified get category_confidence=0.0
            and category_method=None.
        """
        if transactions_df.empty:
            return transactions_df.copy()

        # Ensure output columns exist on working copy
        df = transactions_df.copy()
        for col in (
            "category_l1", "category_l2", "category_l3",
            "unspsc_code", "category_confidence", "category_method",
        ):
            if col not in df.columns:
                df[col] = None

        total = len(df)
        classified_parts: list[pd.DataFrame] = []
        remaining = df.copy()

        # ── Pass 0: Overrides ──────────────────────────────────────────────
        classified_0, remaining = self.deterministic.apply_overrides(remaining)
        n0 = len(classified_0)
        if not classified_0.empty:
            classified_parts.append(classified_0)
        self.logger.info(
            f"Pass 0 (Overrides): {n0} classified, {len(remaining)} remaining"
        )

        # ── Pass 1: GL mapping ─────────────────────────────────────────────
        classified_1, remaining = self.deterministic.apply_gl_mapping(remaining)
        n1 = len(classified_1)
        if not classified_1.empty:
            classified_parts.append(classified_1)
        self.logger.info(
            f"Pass 1 (GL): {n1} classified, {len(remaining)} remaining"
        )

        # ── Pass 2: Supplier mapping ───────────────────────────────────────
        classified_2, remaining = self.deterministic.apply_supplier_mapping(remaining)
        n2 = len(classified_2)
        if not classified_2.empty:
            classified_parts.append(classified_2)
        self.logger.info(
            f"Pass 2 (Supplier): {n2} classified, {len(remaining)} remaining"
        )

        # ── Pass 3: Keyword rules ──────────────────────────────────────────
        classified_3, remaining = self.deterministic.apply_keyword_rules(remaining)
        n3 = len(classified_3)
        if not classified_3.empty:
            classified_parts.append(classified_3)
        self.logger.info(
            f"Pass 3 (Keyword): {n3} classified, {len(remaining)} remaining"
        )

        # ── Pass 4: Embedding similarity ───────────────────────────────────
        classified_4, remaining = self.embedding.classify_batch(remaining, self.config)
        n4 = len(classified_4)
        if not classified_4.empty:
            classified_parts.append(classified_4)
        self.logger.info(
            f"Pass 4 (Embedding): {n4} classified, {len(remaining)} remaining"
        )

        # ── Pass 5: LLM fallback ───────────────────────────────────────────
        # Only items still below llm_fallback_threshold (0.60) after pass 4.
        # `remaining` is exactly those items since classify_batch only marks
        # rows with confidence >= confidence_medium as classified.
        classified_5, remaining_final = self.llm.classify_dataframe(remaining, self.config)
        n5 = len(classified_5)
        if not classified_5.empty:
            classified_parts.append(classified_5)
        self.logger.info(
            f"Pass 5 (LLM): {n5} classified, {len(remaining_final)} remaining"
        )

        # ── Unclassified ───────────────────────────────────────────────────
        n_unclassified = len(remaining_final)
        if not remaining_final.empty:
            remaining_final = remaining_final.copy()
            remaining_final["category_confidence"] = 0.0
            remaining_final["category_method"] = None
            classified_parts.append(remaining_final)
        self.logger.info(f"Unclassified: {n_unclassified} rows → review queue")

        # ── Reassemble in original order ───────────────────────────────────
        if classified_parts:
            result = pd.concat(classified_parts, ignore_index=False)
            result = result.loc[df.index]
        else:
            result = df.copy()
            result["category_confidence"] = 0.0
            result["category_method"] = None

        # ── Pass-by-pass summary ───────────────────────────────────────────
        self.logger.info("=" * 60)
        self.logger.info(f"Categorisation complete — {total} total rows")
        self.logger.info(f"  Pass 0 (Overrides):  {n0}")
        self.logger.info(f"  Pass 1 (GL):         {n1}")
        self.logger.info(f"  Pass 2 (Supplier):   {n2}")
        self.logger.info(f"  Pass 3 (Keyword):    {n3}")
        self.logger.info(f"  Pass 4 (Embedding):  {n4}")
        self.logger.info(f"  Pass 5 (LLM):        {n5}")
        self.logger.info(f"  Unclassified:        {n_unclassified}")

        return result

    # ── Review queue ──────────────────────────────────────────────────────

    def get_review_queue(self, transactions_df: pd.DataFrame) -> pd.DataFrame:
        """Return rows requiring human review (confidence below MEDIUM threshold).

        Sorted by absolute spend descending so highest-value items are reviewed first.

        Args:
            transactions_df: Categorised transactions DataFrame.

        Returns:
            DataFrame of rows where category_confidence < confidence_medium (0.60),
            sorted by abs(base_amount) descending.
        """
        confidence_medium = getattr(
            getattr(self.config, "categorisation", None), "confidence_medium", 0.60
        )
        if "category_confidence" not in transactions_df.columns:
            return transactions_df.copy()

        mask = (
            transactions_df["category_confidence"].isna()
            | (transactions_df["category_confidence"] < confidence_medium)
        )
        review = transactions_df[mask].copy()

        if "base_amount" in review.columns:
            review = review.assign(
                _abs_amount=review["base_amount"].abs()
            ).sort_values("_abs_amount", ascending=False).drop(columns=["_abs_amount"])

        return review

    # ── DB update ─────────────────────────────────────────────────────────

    def update_transactions_in_db(self, transactions_df: pd.DataFrame, engine) -> int:
        """Update the transactions table with new category field values.

        Executes one UPDATE per row (WHERE transaction_id=?).

        Args:
            transactions_df: DataFrame with category fields populated.
            engine: SQLAlchemy engine.

        Returns:
            Count of rows updated.
        """
        category_cols = [
            "category_l1", "category_l2", "category_l3",
            "unspsc_code", "category_confidence", "category_method",
        ]
        if "transaction_id" not in transactions_df.columns:
            self.logger.warning(
                "transactions_df has no transaction_id column — skipping DB update"
            )
            return 0

        updated = 0
        with engine.begin() as conn:
            for _, row in transactions_df.iterrows():
                tid = row.get("transaction_id")
                if tid is None or (isinstance(tid, float) and pd.isna(tid)):
                    continue
                values = {}
                for col in category_cols:
                    if col in transactions_df.columns:
                        val = row.get(col)
                        if isinstance(val, float) and pd.isna(val):
                            val = None
                        values[col] = val
                if not values:
                    continue

                # Populate analytics status fields from categorisation results
                confidence = values.get("category_confidence")
                method = values.get("category_method")
                values["categorisation_status"] = (
                    "categorised" if (confidence is not None and confidence >= 0.60)
                    else "uncategorised"
                )
                values["ai_classification_flag"] = 1 if method == "LLM" else 0
                values["manual_override_flag"] = 1 if method == "MANUAL" else 0

                stmt = (
                    update(transactions_table)
                    .where(transactions_table.c.transaction_id == str(tid))
                    .values(**values)
                )
                conn.execute(stmt)
                updated += 1

        self.logger.info(f"Updated {updated} rows in transactions table")
        return updated

    # ── Feedback / overrides ──────────────────────────────────────────────

    def apply_feedback(self, overrides: list[dict], engine) -> None:
        """Insert new manual category overrides into the category_overrides table.

        Each override dict must contain at least one of canonical_supplier_id or
        gl_account, plus l1, l2 (optional), l3 (optional), and optionally
        unspsc_code, reviewer, reason.

        Args:
            overrides: List of override dicts.
            engine: SQLAlchemy engine.
        """
        if not overrides:
            return

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for override in overrides:
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "canonical_supplier_id": override.get("canonical_supplier_id"),
                    "gl_account": override.get("gl_account"),
                    "override_l1": override.get("l1"),
                    "override_l2": override.get("l2"),
                    "override_l3": override.get("l3"),
                    "unspsc_code": override.get("unspsc_code"),
                    "reviewer": override.get("reviewer"),
                    "reason": override.get("reason"),
                    "created_at": now,
                }
            )

        with engine.begin() as conn:
            conn.execute(sa_insert(category_overrides_table), rows)

        self.logger.info(f"Inserted {len(rows)} category overrides")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SpendCube categorisation pipeline"
    )
    parser.add_argument(
        "--db", default="data/db/spend_cube.db", help="Path to SQLite database"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config.yaml"
    )
    args = parser.parse_args()

    from src.config import load_config

    config = load_config(args.config)
    engine = get_engine(args.db)
    init_db(engine)

    # Load all transactions
    transactions_df = get_transactions(engine)
    total = len(transactions_df)
    print(f"\nLoaded {total} transactions from {args.db}")

    if total == 0:
        print("No transactions to categorise.")
        sys.exit(0)

    # Run categorisation
    categoriser = SpendCategoriser(config=config, engine=engine)
    result_df = categoriser.categorise(transactions_df)

    # Persist to DB
    updated = categoriser.update_transactions_in_db(result_df, engine)
    print(f"Updated {updated} rows in database")

    # ── Pass-by-pass breakdown ─────────────────────────────────────────────
    print("\nClassified by pass:")
    method_col = result_df["category_method"].fillna("")
    counts = {
        "Pass 0 (Overrides)": int((method_col == "MANUAL").sum()),
        "Pass 1 (GL)":        int((method_col == "DETERMINISTIC_GL").sum()),
        "Pass 2 (Supplier)":  int((method_col == "DETERMINISTIC_SUPPLIER").sum()),
        "Pass 3 (Keyword)":   int((method_col == "KEYWORD").sum()),
        "Pass 4 (Embedding)": int(method_col.isin(["EMBEDDING", "EMBEDDING_REJECT"]).sum()),
        "Pass 5 (LLM)":       int((method_col == "LLM").sum()),
    }
    for label, count in counts.items():
        print(f"  {label}: {count}")

    unclassified_count = int(
        result_df["category_method"].isna().sum()
        + (method_col == "DRY_RUN").sum()
    )
    print(f"  Unclassified: {unclassified_count}")

    # ── Review queue ───────────────────────────────────────────────────────
    review_queue = categoriser.get_review_queue(result_df)
    print(f"\nReview queue: {len(review_queue)} rows (confidence < 0.60)")

    # ── Confidence band breakdown ──────────────────────────────────────────
    confidence_high = getattr(config.categorisation, "confidence_high", 0.85)
    confidence_medium = getattr(config.categorisation, "confidence_medium", 0.60)

    conf = result_df["category_confidence"].fillna(0.0)
    n_high = int((conf >= confidence_high).sum())
    n_medium = int(((conf >= confidence_medium) & (conf < confidence_high)).sum())
    n_low = int((conf < confidence_medium).sum())

    print(f"\nConfidence breakdown (total={total}):")
    print(f"  HIGH   (>= {confidence_high}):                {n_high:4d}  ({100 * n_high / total:.0f}%)")
    print(f"  MEDIUM ({confidence_medium}–{confidence_high}): {n_medium:4d}  ({100 * n_medium / total:.0f}%)")
    print(f"  LOW    (< {confidence_medium}):                {n_low:4d}  ({100 * n_low / total:.0f}%)")

    medium_high_pct = (n_high + n_medium) / total * 100
    print(f"\nTotal MEDIUM+ confidence: {n_high + n_medium}/{total} ({medium_high_pct:.0f}%)")
