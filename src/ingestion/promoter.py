"""IncrementalPromoter: promotes queued rows from transactions_raw to transactions."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from src.categorisation.categoriser import SpendCategoriser
from src.models.database import (
    get_queued_raw_rows,
    insert_transactions,
    mark_raw_rows_processed,
    supplier_master_table,
)
from src.suppliers.harmoniser import SupplierHarmoniser
from src.suppliers.normaliser import SupplierNormaliser


_CONFIDENCE_MEDIUM = 0.60

# Columns accepted by the transactions table (subset of schema — all others are skipped).
_TX_COLUMNS = frozenset({
    "transaction_id", "source_system", "source_row_number", "ingested_at",
    "last_modified_at", "invoice_number", "document_type", "invoice_date",
    "raw_supplier_name", "raw_supplier_id", "raw_line_description",
    "original_amount", "original_currency", "base_amount", "base_currency",
    "fx_rate", "gl_account", "cost_centre", "raw_payment_terms",
    "payment_terms_days", "po_number", "business_unit", "plant_site",
    "canonical_supplier_id", "canonical_supplier_name",
    "canonical_supplier_confidence", "parent_company_id", "parent_company_name",
    "category_l1", "category_l2", "category_l3", "unspsc_code",
    "category_confidence", "category_method", "spend_type", "addressability",
    "managed_status", "is_credit_note", "is_intercompany", "is_tax_line",
    "is_duplicate", "review_status", "reviewer", "review_notes",
    "review_date", "raw_data", "engagement_id", "source_raw_id",
})


class IncrementalPromoter:
    """Promotes a batch of queued transactions_raw rows through supplier harmonisation
    and categorisation, then writes enriched rows to the transactions table.

    LLM categorisation is never called — rows below 0.60 confidence go to
    review_required status.
    """

    def __init__(self, engine, config) -> None:
        self.engine = engine
        self.config = config

    def promote(self, engagement_id: str, batch_id: str) -> dict:
        """Promote all queued rows for a batch.

        Returns:
            dict with keys: promoted_count, review_required_count, failed_count
        """
        # Step 1: Get queued raw rows — early return if none
        df_queued = get_queued_raw_rows(self.engine, engagement_id, batch_id)
        if df_queued.empty:
            return {"promoted_count": 0, "review_required_count": 0, "failed_count": 0}

        # Step 2: Resolve suppliers — harmonise only names not already in supplier_master
        supplier_map = self._resolve_suppliers(df_queued)

        # Step 3: Enrich queued rows with canonical supplier columns
        df_enriched = self._enrich_with_supplier(df_queued, supplier_map)

        # Step 4: Categorise — force dry_run=True so no LLM calls are made
        config_dry = self.config.model_copy(deep=True)
        config_dry.llm.dry_run = True
        categoriser = SpendCategoriser(config_dry, self.engine)
        df_categorised = categoriser.categorise(df_enriched)

        # Step 5: Split into promoted (confidence >= 0.60) and review_required
        confidence = df_categorised["category_confidence"].fillna(0.0)
        promoted_mask = confidence >= _CONFIDENCE_MEDIUM
        df_promoted = df_categorised[promoted_mask].copy()
        df_review = df_categorised[~promoted_mask].copy()

        promoted_raw_ids = df_queued.loc[df_promoted.index, "id"].tolist()
        review_raw_ids = df_queued.loc[df_review.index, "id"].tolist()

        # Step 6: Insert promoted rows into transactions table
        if not df_promoted.empty:
            raw_id_by_idx = df_queued["id"].to_dict()
            records = self._build_records(df_promoted, raw_id_by_idx)
            insert_transactions(self.engine, records, engagement_id)

        # Step 7: Mark raw rows with final pipeline_status
        mark_raw_rows_processed(self.engine, promoted_raw_ids, "processed")
        mark_raw_rows_processed(self.engine, review_raw_ids, "review_required")

        # Step 8: Return counts
        return {
            "promoted_count": len(promoted_raw_ids),
            "review_required_count": len(review_raw_ids),
            "failed_count": 0,
        }

    # ── Private helpers ────────────────────────────────────────────────────

    def _resolve_suppliers(self, df_queued: pd.DataFrame) -> dict:
        """Return dict: raw_supplier_name -> {canonical_supplier_id, canonical_supplier_name, confidence}.

        Names whose canonical_supplier_id is already in supplier_master are
        resolved via a direct lookup. Only truly new names are passed through
        SupplierHarmoniser, which inserts them into supplier_master.
        """
        project_root = Path(__file__).resolve().parents[2]
        normaliser = SupplierNormaliser(
            str(project_root / "data" / "reference" / "legal_suffixes.yaml"),
            str(project_root / "data" / "reference" / "abbreviation_map.yaml"),
        )

        unique_names = [
            n for n in df_queued["raw_supplier_name"].dropna().unique().tolist()
            if str(n).strip()
        ]
        if not unique_names:
            return {}

        # Normalise and compute deterministic canonical_supplier_id for each name
        norm_series = normaliser.normalise_series(pd.Series(unique_names))
        normalised = dict(zip(unique_names, norm_series.tolist()))
        canonical_ids = {
            name: hashlib.sha256(norm.encode()).hexdigest()[:12]
            for name, norm in normalised.items()
        }

        # Query supplier_master for any already-known canonical IDs
        all_expected = list(set(canonical_ids.values()))
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(
                    supplier_master_table.c.canonical_supplier_id,
                    supplier_master_table.c.canonical_name,
                ).where(
                    supplier_master_table.c.canonical_supplier_id.in_(all_expected)
                )
            ).fetchall()

        known_master = {r[0]: r[1] for r in rows}

        result: dict = {}
        unknown_names: list[str] = []

        for name in unique_names:
            cid = canonical_ids[name]
            if cid in known_master:
                result[name] = {
                    "canonical_supplier_id": cid,
                    "canonical_supplier_name": known_master[cid],
                    "confidence": 0.95,
                }
            else:
                unknown_names.append(name)

        # Run SupplierHarmoniser only for names not already in supplier_master
        if unknown_names:
            harmoniser = SupplierHarmoniser(self.config, self.engine)
            unknown_df = pd.DataFrame({"raw_supplier_name": unknown_names})
            _, match_log_df = harmoniser.harmonise(unknown_df)

            if not match_log_df.empty:
                # Refresh supplier_master to get canonical_name for newly inserted entries
                new_cids = match_log_df["canonical_supplier_id"].dropna().unique().tolist()
                new_master: dict = {}
                if new_cids:
                    with self.engine.connect() as conn:
                        new_rows = conn.execute(
                            select(
                                supplier_master_table.c.canonical_supplier_id,
                                supplier_master_table.c.canonical_name,
                            ).where(
                                supplier_master_table.c.canonical_supplier_id.in_(new_cids)
                            )
                        ).fetchall()
                    new_master = {r[0]: r[1] for r in new_rows}

                unknown_set = set(unknown_names)
                for _, log_row in match_log_df.iterrows():
                    raw_name = log_row["raw_supplier_name"]
                    if raw_name not in unknown_set:
                        continue
                    cid = log_row.get("canonical_supplier_id")
                    conf = float(log_row.get("confidence", 0.0))
                    canonical_name = new_master.get(cid, raw_name) if cid else raw_name
                    result[raw_name] = {
                        "canonical_supplier_id": cid,
                        "canonical_supplier_name": canonical_name,
                        "confidence": conf,
                    }

        return result

    def _enrich_with_supplier(self, df_queued: pd.DataFrame, supplier_map: dict) -> pd.DataFrame:
        """Add canonical_supplier_id/name/confidence columns to the queued rows DataFrame."""
        df = df_queued.copy()

        def _lookup(name, key):
            if pd.isna(name) or not str(name).strip():
                return None
            return supplier_map.get(str(name), {}).get(key)

        df["canonical_supplier_id"] = df["raw_supplier_name"].apply(
            lambda n: _lookup(n, "canonical_supplier_id")
        )
        df["canonical_supplier_name"] = df["raw_supplier_name"].apply(
            lambda n: _lookup(n, "canonical_supplier_name")
        )
        df["canonical_supplier_confidence"] = df["raw_supplier_name"].apply(
            lambda n: _lookup(n, "confidence")
        )
        return df

    def _build_records(self, df_promoted: pd.DataFrame, raw_id_by_idx: dict) -> list[dict]:
        """Convert promoted rows into transaction record dicts for insert_transactions."""
        now = datetime.now(timezone.utc).isoformat()
        records = []
        for idx, row in df_promoted.iterrows():
            rec: dict = {
                "transaction_id": str(uuid.uuid4()),
                "ingested_at": now,
                "last_modified_at": now,
                "source_raw_id": raw_id_by_idx.get(idx),
            }
            for col in df_promoted.columns:
                if col not in _TX_COLUMNS or col in rec:
                    continue
                val = row[col]
                if isinstance(val, float) and pd.isna(val):
                    val = None
                elif val is pd.NaT:
                    val = None
                rec[col] = val
            records.append(rec)
        return records
