"""SpendCube supplier harmonisation pipeline entry point."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
from sqlalchemy import Engine, insert, select

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.database import (
    supplier_master_table,
    supplier_match_log_table,
    transactions_table,
)
from src.models.schema import ReviewStatus
from src.suppliers.embeddings import EmbeddingMatcher
from src.suppliers.matcher import DeterministicMatcher, FuzzyMatcher
from src.suppliers.normaliser import SupplierNormaliser
from src.suppliers.parent_mapper import ParentMapper
from src.utils.logging import get_logger_from_config


# ---------------------------------------------------------------------------
# build_supplier_master — Stage 4 helper (US-005)
# ---------------------------------------------------------------------------

def build_supplier_master(
    raw_suppliers: pd.DataFrame,
    engine: Engine,
    config,
) -> pd.DataFrame:
    """Build the canonical supplier_master table from raw supplier data.

    For each unique normalised_name in raw_suppliers, generates a canonical
    supplier entry and inserts it into supplier_master if not already present.
    Idempotent: existing entries are skipped, not updated.

    Args:
        raw_suppliers: DataFrame with columns:
            - raw_supplier_name: str
            - raw_supplier_id: str | None
            - normalised_name: str (pre-computed)
        engine: SQLAlchemy engine (SQLite in Phase 2)
        config: Pipeline config dict (not used in this function but kept for
                interface consistency with the orchestrator)

    Returns:
        DataFrame with columns: canonical_supplier_id, canonical_name,
        normalised_name — covering both newly inserted and pre-existing entries.
    """
    if raw_suppliers.empty:
        return pd.DataFrame(columns=["canonical_supplier_id", "canonical_name", "normalised_name"])

    # ------------------------------------------------------------------
    # Step 1: Fetch existing supplier_master entries
    # ------------------------------------------------------------------
    with engine.connect() as conn:
        existing_rows = conn.execute(
            select(
                supplier_master_table.c.canonical_supplier_id,
                supplier_master_table.c.canonical_name,
            )
        ).fetchall()

    existing_ids: set[str] = {row[0] for row in existing_rows}
    existing_records: list[dict] = [
        {"canonical_supplier_id": row[0], "canonical_name": row[1]}
        for row in existing_rows
    ]

    # ------------------------------------------------------------------
    # Step 2: Group by normalised_name to build canonical entries
    # ------------------------------------------------------------------
    now = datetime.now(tz=timezone.utc).isoformat()
    new_records: list[dict] = []
    output_rows: list[dict] = []

    for normalised_name, group in raw_suppliers.groupby("normalised_name", sort=False):
        canonical_supplier_id = hashlib.sha256(
            normalised_name.encode()
        ).hexdigest()[:12]

        # Most-common raw_supplier_name (title-cased) as canonical_name
        canonical_name = (
            group["raw_supplier_name"]
            .value_counts()
            .idxmax()
            .strip()
            .title()
        )

        output_rows.append({
            "canonical_supplier_id": canonical_supplier_id,
            "canonical_name": canonical_name,
            "normalised_name": normalised_name,
        })

        if canonical_supplier_id in existing_ids:
            continue  # idempotent: skip existing entries

        # Collect unique raw_supplier_ids (exclude None / NaN)
        raw_ids = sorted(
            {
                str(v)
                for v in group["raw_supplier_id"].dropna().unique()
                if str(v).strip()
            }
        )

        new_records.append({
            "canonical_supplier_id": canonical_supplier_id,
            "canonical_name": canonical_name,
            "parent_company_id": None,
            "parent_name": None,
            "country": None,
            "identifiers": json.dumps({"raw_ids": raw_ids}),
            "created_at": now,
            "updated_at": now,
        })

    # ------------------------------------------------------------------
    # Step 3: Bulk insert new entries
    # ------------------------------------------------------------------
    if new_records:
        with engine.begin() as conn:
            conn.execute(insert(supplier_master_table), new_records)

    return pd.DataFrame(output_rows, columns=["canonical_supplier_id", "canonical_name", "normalised_name"])


# ---------------------------------------------------------------------------
# SupplierHarmoniser — full orchestrator (US-006)
# ---------------------------------------------------------------------------

class SupplierHarmoniser:
    """Full 5-stage supplier harmonisation orchestrator.

    Stages:
      1. Normalise raw supplier names (SupplierNormaliser)
      2. Group by normalised_name (intra-batch dedup)
      3. DeterministicMatcher — exact normalised name / vendor ID
      4. FuzzyMatcher — rapidfuzz composite score
      5. EmbeddingMatcher — sentence-transformer cosine similarity
      + ParentMapper — LLM parent company enrichment (dry-run aware)
    """

    def __init__(self, config, engine: Engine) -> None:
        self.config = config
        self.engine = engine
        self.logger = get_logger_from_config(__name__, config)

        project_root = Path(__file__).resolve().parents[2]
        suffixes_path = project_root / "data" / "reference" / "legal_suffixes.yaml"
        abbreviations_path = project_root / "data" / "reference" / "abbreviation_map.yaml"

        self.normaliser = SupplierNormaliser(str(suffixes_path), str(abbreviations_path))
        self.parent_mapper = ParentMapper(config)
        self._review_threshold: float = config.categorisation.confidence_medium  # 0.60

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def harmonise(
        self, transactions_df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Run the full harmonisation pipeline.

        Args:
            transactions_df: Transactions DataFrame from ingestion (must have
                raw_supplier_name; raw_supplier_id is optional).

        Returns:
            (supplier_master_df, match_log_df) — both DataFrames reflect the
            current state of the DB after this run.
        """
        now = datetime.now(tz=timezone.utc).isoformat()

        # ------------------------------------------------------------------
        # Step 1: Extract unique (raw_supplier_name, raw_supplier_id) pairs
        # ------------------------------------------------------------------
        cols = ["raw_supplier_name"] + (
            ["raw_supplier_id"] if "raw_supplier_id" in transactions_df.columns else []
        )
        raw_pairs = (
            transactions_df[cols]
            .copy()
            .dropna(subset=["raw_supplier_name"])
            .drop_duplicates(subset=["raw_supplier_name"])
            .reset_index(drop=True)
        )
        if "raw_supplier_id" not in raw_pairs.columns:
            raw_pairs["raw_supplier_id"] = None

        self.logger.info("Step 1: %d unique raw supplier names", len(raw_pairs))

        if raw_pairs.empty:
            empty_master = pd.DataFrame(
                columns=["canonical_supplier_id", "canonical_name", "normalised_name"]
            )
            empty_log = pd.DataFrame(
                columns=[
                    "id", "raw_supplier_name", "raw_supplier_id",
                    "canonical_supplier_id", "match_method", "confidence",
                    "evidence", "review_status", "created_at",
                ]
            )
            return empty_master, empty_log

        # ------------------------------------------------------------------
        # Step 2: Normalise all names
        # ------------------------------------------------------------------
        raw_pairs["normalised_name"] = self.normaliser.normalise_series(
            raw_pairs["raw_supplier_name"]
        )
        self.logger.info(
            "Step 2: %d unique normalised names",
            raw_pairs["normalised_name"].nunique(),
        )

        # ------------------------------------------------------------------
        # Step 3: Count intra-batch normalised_name occurrences
        # ------------------------------------------------------------------
        normalised_counts: dict[str, int] = (
            raw_pairs["normalised_name"].value_counts().to_dict()
        )

        # ------------------------------------------------------------------
        # Step 4: Build initial supplier_master via build_supplier_master()
        # Load pre-existing master BEFORE insert (for matching in steps 5–7)
        # ------------------------------------------------------------------
        pre_existing_df = self._load_master_from_db()
        pre_existing_norm_names: set[str] = set()
        if not pre_existing_df.empty and "normalised_name" in pre_existing_df.columns:
            pre_existing_norm_names = set(
                pre_existing_df["normalised_name"].dropna().tolist()
            )

        supplier_master_df = build_supplier_master(raw_pairs, self.engine, self.config)
        self.logger.info("Step 4: %d canonical suppliers in master", len(supplier_master_df))

        # ------------------------------------------------------------------
        # Steps 5–7: Initialise matchers against pre-existing master
        # ------------------------------------------------------------------
        det_matcher = DeterministicMatcher(pre_existing_df)
        fuzzy_matcher = FuzzyMatcher(pre_existing_df, self.config)
        embedding_matcher = EmbeddingMatcher()

        candidate_names: list[str] = []
        candidate_ids: list[str] = []
        if not pre_existing_df.empty and "normalised_name" in pre_existing_df.columns:
            valid = pre_existing_df.dropna(subset=["normalised_name", "canonical_supplier_id"])
            candidate_names = valid["normalised_name"].tolist()
            candidate_ids = valid["canonical_supplier_id"].tolist()

        # ------------------------------------------------------------------
        # Check existing match_log entries for idempotency
        # ------------------------------------------------------------------
        with self.engine.connect() as conn:
            existing_logged_rows = conn.execute(
                select(supplier_match_log_table.c.raw_supplier_name).distinct()
            ).fetchall()
        existing_logged_names: set[str] = {row[0] for row in existing_logged_rows}

        # ------------------------------------------------------------------
        # Build match_log entry for each unique raw supplier
        # ------------------------------------------------------------------
        match_log_entries: list[dict] = []

        for _, raw_row in raw_pairs.iterrows():
            raw_name = str(raw_row["raw_supplier_name"])
            raw_id_val = raw_row.get("raw_supplier_id")
            raw_id = (
                str(raw_id_val)
                if pd.notna(raw_id_val) and str(raw_id_val).strip()
                else None
            )
            normalised = str(raw_row["normalised_name"])
            intra_count = normalised_counts.get(normalised, 1)
            default_canonical_id = hashlib.sha256(normalised.encode()).hexdigest()[:12]

            if intra_count > 1:
                # Multiple raw suppliers in this batch share the same normalised_name
                canonical_id = default_canonical_id
                confidence = 1.0
                method = "NORMALISED_NAME_GROUP"
                evidence = json.dumps(
                    {"normalised_name": normalised, "group_size": intra_count}
                )

            elif normalised in pre_existing_norm_names:
                # Normalised name already exists in the DB master
                canonical_id = default_canonical_id  # SHA256 is deterministic
                confidence = 0.95
                method = "EXACT_NORMALISED_NAME"
                evidence = json.dumps({"normalised_name": normalised})

            else:
                # Step 5: DeterministicMatcher — vendor ID lookup
                det_id, det_conf, det_method = det_matcher.match(
                    raw_name, normalised, raw_id
                )

                if det_id is not None:
                    canonical_id = det_id
                    confidence = det_conf
                    method = det_method
                    evidence = json.dumps({"raw_supplier_id": raw_id})

                else:
                    # Step 6: FuzzyMatcher
                    fz_id, fz_conf, fz_method, fz_ev = fuzzy_matcher.match(normalised)

                    if fz_id is not None and fz_method != "FUZZY_REJECT":
                        canonical_id = fz_id
                        confidence = fz_conf
                        method = fz_method
                        evidence = json.dumps({"fuzzy": fz_ev})

                    else:
                        # Step 7: EmbeddingMatcher
                        if candidate_names:
                            em_id, em_conf, em_method, em_ev = embedding_matcher.match(
                                normalised, candidate_names, candidate_ids, self.config
                            )
                            if em_id is not None and em_method not in (
                                "EMBEDDING_REJECT", "EMBEDDING_UNAVAILABLE"
                            ):
                                canonical_id = em_id
                                confidence = em_conf
                                method = em_method
                                evidence = json.dumps({"embedding": em_ev})
                            else:
                                canonical_id = default_canonical_id
                                confidence = 1.0
                                method = "NEW_CANONICAL"
                                evidence = json.dumps({"normalised_name": normalised})
                        else:
                            canonical_id = default_canonical_id
                            confidence = 1.0
                            method = "NEW_CANONICAL"
                            evidence = json.dumps({"normalised_name": normalised})

            review_status = (
                ReviewStatus.PENDING.value
                if confidence < self._review_threshold
                else ReviewStatus.APPROVED.value
            )

            match_log_entries.append({
                "id": str(uuid4()),
                "raw_supplier_name": raw_name,
                "raw_supplier_id": raw_id,
                "canonical_supplier_id": canonical_id,
                "match_method": method,
                "confidence": confidence,
                "evidence": evidence,
                "review_status": review_status,
                "created_at": now,
            })

        # ------------------------------------------------------------------
        # Step 8: ParentMapper — enrich canonical suppliers without a parent
        # ------------------------------------------------------------------
        if not supplier_master_df.empty:
            parent_results = self.parent_mapper.enrich(
                supplier_master_df["canonical_name"].tolist()
            )
            for result in parent_results:
                if result.get("parent_company_name"):
                    parent_id = hashlib.sha256(
                        result["parent_company_name"].lower().encode()
                    ).hexdigest()[:12]
                    with self.engine.begin() as conn:
                        conn.execute(
                            supplier_master_table.update()
                            .where(
                                supplier_master_table.c.canonical_name
                                == result["supplier_name"]
                            )
                            .values(
                                parent_company_id=parent_id,
                                parent_name=result["parent_company_name"],
                                updated_at=now,
                            )
                        )

        # ------------------------------------------------------------------
        # Step 9: supplier_master already persisted by build_supplier_master
        # Step 10: Write match_log entries (skip already-logged names)
        # ------------------------------------------------------------------
        new_log_entries = [
            e for e in match_log_entries
            if e["raw_supplier_name"] not in existing_logged_names
        ]
        if new_log_entries:
            with self.engine.begin() as conn:
                conn.execute(insert(supplier_match_log_table), new_log_entries)
            self.logger.info("Step 10: wrote %d match_log entries", len(new_log_entries))

        match_log_df = pd.DataFrame(match_log_entries)

        # Refresh master from DB to include any parent updates
        supplier_master_df = self._load_master_from_db()

        # ------------------------------------------------------------------
        # Step 11: Return
        # ------------------------------------------------------------------
        return supplier_master_df, match_log_df

    def update_transactions(
        self,
        transactions_df: pd.DataFrame,
        match_log_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Join match_log onto transactions to populate canonical supplier columns.

        Args:
            transactions_df: Raw transactions DataFrame.
            match_log_df:    Match log returned by harmonise().

        Returns:
            Copy of transactions_df with canonical_supplier_id,
            canonical_supplier_name, canonical_supplier_confidence,
            parent_company_id, parent_company_name,
            supplier_match_confidence, supplier_match_method populated.
        """
        if match_log_df.empty:
            return transactions_df.copy()

        master_df = self._load_master_from_db()

        # One enrichment row per raw_supplier_name (highest confidence wins)
        lookup = (
            match_log_df[
                ["raw_supplier_name", "canonical_supplier_id", "confidence", "match_method"]
            ]
            .sort_values("confidence", ascending=False)
            .drop_duplicates(subset=["raw_supplier_name"], keep="first")
            .copy()
        )

        if not master_df.empty:
            master_slim = master_df[
                ["canonical_supplier_id", "canonical_name", "parent_company_id", "parent_name"]
            ].copy()
            lookup = lookup.merge(master_slim, on="canonical_supplier_id", how="left")
        else:
            lookup["canonical_name"] = None
            lookup["parent_company_id"] = None
            lookup["parent_name"] = None

        # Rename to target column names before merge
        lookup = lookup.rename(
            columns={
                "canonical_name": "canonical_supplier_name",
                "parent_name": "parent_company_name",
                "confidence": "supplier_match_confidence",
                "match_method": "supplier_match_method",
            }
        )

        # Drop existing canonical columns from transactions to avoid suffix conflicts
        drop_cols = [
            c for c in [
                "canonical_supplier_id", "canonical_supplier_name",
                "canonical_supplier_confidence", "parent_company_id",
                "parent_company_name", "supplier_match_confidence",
                "supplier_match_method",
            ]
            if c in transactions_df.columns
        ]
        result = transactions_df.drop(columns=drop_cols).copy()
        result = result.merge(lookup, on="raw_supplier_name", how="left")

        # canonical_supplier_confidence mirrors supplier_match_confidence
        result["canonical_supplier_confidence"] = result.get("supplier_match_confidence")

        return result

    def get_review_queue(self, match_log_df: pd.DataFrame) -> pd.DataFrame:
        """Return match_log rows with confidence below the review threshold.

        Rows are sorted by total supplier spend descending (joins transactions
        from DB). Falls back to sorting by confidence ascending if the join
        cannot be computed.

        Args:
            match_log_df: Match log DataFrame returned by harmonise().

        Returns:
            Filtered DataFrame of low-confidence rows, with total_spend column
            when the join succeeds.
        """
        if match_log_df.empty or "confidence" not in match_log_df.columns:
            return pd.DataFrame()

        review_df = match_log_df[
            match_log_df["confidence"] < self._review_threshold
        ].copy()

        if review_df.empty:
            return review_df

        try:
            txn_df = pd.read_sql(
                select(
                    transactions_table.c.raw_supplier_name,
                    transactions_table.c.base_amount,
                ).where(transactions_table.c.base_amount.isnot(None)),
                self.engine,
            )
            if not txn_df.empty:
                spend = (
                    txn_df.groupby("raw_supplier_name")["base_amount"]
                    .sum()
                    .reset_index()
                    .rename(columns={"base_amount": "total_spend"})
                )
                review_df = review_df.merge(spend, on="raw_supplier_name", how="left")
                review_df["total_spend"] = review_df["total_spend"].fillna(0.0)
                review_df = review_df.sort_values("total_spend", ascending=False)
            else:
                review_df = review_df.sort_values("confidence", ascending=True)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Could not join transactions for spend sort: %s", exc)
            review_df = review_df.sort_values("confidence", ascending=True)

        return review_df.reset_index(drop=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_master_from_db(self) -> pd.DataFrame:
        """Load supplier_master from DB, adding computed normalised_name column."""
        with self.engine.connect() as conn:
            rows = conn.execute(select(supplier_master_table)).fetchall()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "canonical_supplier_id", "canonical_name", "normalised_name",
                    "parent_company_id", "parent_name", "country", "identifiers",
                    "created_at", "updated_at",
                ]
            )

        df = pd.DataFrame([dict(r._mapping) for r in rows])
        # normalised_name is not stored in DB; derive it from canonical_name
        df["normalised_name"] = self.normaliser.normalise_series(df["canonical_name"])
        return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SpendCube Supplier Harmoniser — runs full harmonisation pipeline"
    )
    parser.add_argument(
        "--db",
        default="data/db/spend_cube.db",
        help="Path to SQLite database (default: data/db/spend_cube.db)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Optional CSV/Excel path — if provided, ingests first then harmonises",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    args = parser.parse_args()

    from src.config import load_config
    from src.models.database import get_engine, get_transactions, init_db

    config = load_config(args.config)
    engine = get_engine(args.db)
    init_db(engine)

    if args.input:
        from src.ingestion.ingest import Ingestor
        print(f"Ingesting {args.input} into {args.db} ...")
        ingestor = Ingestor(config)
        count = ingestor.ingest_to_db(args.input, engine)
        print(f"  {count} rows written\n")

    transactions_df = get_transactions(engine)

    if transactions_df.empty:
        print("No transactions found in database. Run ingestion first.")
        print("  make ingest  (or)  python src/ingestion/ingest.py --file data/input/sample.csv")
        sys.exit(0)

    print(f"Loaded {len(transactions_df)} transactions from {args.db}\n")

    harmoniser = SupplierHarmoniser(config, engine)
    supplier_master_df, match_log_df = harmoniser.harmonise(transactions_df)

    # Update canonical supplier columns on transactions in DB
    if not match_log_df.empty:
        enriched_df = harmoniser.update_transactions(transactions_df, match_log_df)
        # Map enriched DataFrame columns → transactions table columns
        col_map = {
            "canonical_supplier_id": "canonical_supplier_id",
            "canonical_supplier_name": "canonical_supplier_name",
            "supplier_match_confidence": "canonical_supplier_confidence",
            "parent_company_id": "parent_company_id",
            "parent_company_name": "parent_company_name",
        }
        db_col_names = [c.name for c in transactions_table.columns]
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

    # Summary
    unique_raw = len(match_log_df) if not match_log_df.empty else 0
    canonical_count = len(supplier_master_df) if not supplier_master_df.empty else 0

    print("Harmonisation Summary")
    print(f"  Unique raw suppliers : {unique_raw}")
    print(f"  Canonical suppliers  : {canonical_count}")

    if not match_log_df.empty and "match_method" in match_log_df.columns:
        print("\n  Match method breakdown:")
        for method, count in match_log_df["match_method"].value_counts().items():
            print(f"    {method:<30} {count}")

    review_queue = harmoniser.get_review_queue(match_log_df)
    print(f"\n  Review queue size    : {len(review_queue)}")

    sys.exit(0)
