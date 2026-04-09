"""SpendCube deterministic rule-based spend categorisation.

Implements three categorisation passes:
  Pass 0: category_overrides table (confidence=1.0, method=MANUAL)
  Pass 1: GL code mapping from category_seed_mappings.csv (method=DETERMINISTIC_GL)
  Pass 2: Supplier name mapping from category_seed_mappings.csv (method=DETERMINISTIC_SUPPLIER)

Each pass returns (classified_df, unclassified_df). Unclassified rows are
passed to the next pass.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.schema import CategoryMethod
from src.utils.logging import get_logger_from_config


class DeterministicCategoriser:
    """Passes 0–2 of the categorisation pipeline (overrides, GL, supplier).

    Args:
        seed_mappings_path: Path to category_seed_mappings.csv.
        engine: SQLAlchemy engine (used to read category_overrides table).
        config: SpendCube Config object with paths/logging sections.
    """

    def __init__(self, seed_mappings_path: str, engine, config) -> None:
        self.engine = engine
        self.config = config
        self.logger = get_logger_from_config(__name__, config)

        # ── Seed mappings ─────────────────────────────────────────────────
        self.seed_mappings = pd.read_csv(seed_mappings_path)
        self.logger.info(
            f"Loaded {len(self.seed_mappings)} seed mappings from {seed_mappings_path}"
        )

        # ── Category overrides from DB ────────────────────────────────────
        try:
            self.overrides = pd.read_sql("SELECT * FROM category_overrides", engine)
            self.logger.info(
                f"Loaded {len(self.overrides)} category overrides from DB"
            )
        except Exception as exc:
            self.logger.warning(f"Could not load category_overrides from DB: {exc}")
            self.overrides = pd.DataFrame(
                columns=[
                    "id", "canonical_supplier_id", "gl_account",
                    "override_l1", "override_l2", "override_l3", "unspsc_code",
                    "reviewer", "reason", "created_at",
                ]
            )

        # ── Internal category hierarchy ───────────────────────────────────
        reference_dir = Path(config.paths.reference_dir)
        hierarchy_path = reference_dir / "internal_category_hierarchy.csv"
        self.hierarchy = pd.read_csv(hierarchy_path)
        self.logger.info(
            f"Loaded {len(self.hierarchy)} hierarchy rows from {hierarchy_path}"
        )

        # ── Build GL lookup (normalised code → seed row dict) ─────────────
        gl_rows = self.seed_mappings[self.seed_mappings["mapping_type"] == "GL"].copy()
        self._gl_lookup: dict[str, dict] = {}
        for _, row in gl_rows.iterrows():
            sv = str(row["source_value"]).strip().lstrip("0") or "0"
            self._gl_lookup[sv] = row.to_dict()

        # ── Build supplier lookup (lowercase name → seed row dict) ─────────
        supplier_rows = self.seed_mappings[
            self.seed_mappings["mapping_type"] == "SUPPLIER"
        ].copy()
        self._supplier_lookup: dict[str, dict] = {
            str(row["source_value"]).strip().lower(): row.to_dict()
            for _, row in supplier_rows.iterrows()
        }

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _ensure_category_cols(df: pd.DataFrame) -> pd.DataFrame:
        """Add category output columns if not already present."""
        for col in (
            "category_l1", "category_l2", "category_l3",
            "unspsc_code", "category_confidence", "category_method",
        ):
            if col not in df.columns:
                df[col] = None
        return df

    def _apply_seed_to_row(self, df: pd.DataFrame, idx, seed: dict, method: str) -> None:
        """Write a single seed mapping result into a DataFrame row."""
        df.at[idx, "category_l1"] = seed.get("internal_category_l1") or ""
        df.at[idx, "category_l2"] = seed.get("internal_category_l2") or ""
        df.at[idx, "category_l3"] = seed.get("internal_category_l3") or ""
        df.at[idx, "unspsc_code"] = str(seed.get("unspsc_segment_code", ""))
        df.at[idx, "category_confidence"] = float(seed.get("confidence", 0.85))
        df.at[idx, "category_method"] = method

    def _gl_norm(self, gl_account) -> Optional[str]:
        """Normalise a GL account code: strip leading zeros."""
        if gl_account is None or (isinstance(gl_account, float) and pd.isna(gl_account)):
            return None
        normed = str(gl_account).strip().lstrip("0")
        return normed or "0"

    # ── Pass 0: Category overrides ────────────────────────────────────────

    def apply_overrides(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Pass 0 — highest-priority manual overrides from category_overrides table.

        Matches on canonical_supplier_id OR gl_account.  Confidence is always 1.0
        and method is MANUAL.

        Args:
            df: DataFrame of unclassified transactions.

        Returns:
            (classified_df, unclassified_df)
        """
        if df.empty or self.overrides.empty:
            return pd.DataFrame(columns=df.columns), df.copy()

        df = df.copy()
        df = self._ensure_category_cols(df)
        classified_mask = pd.Series(False, index=df.index)

        for _, override in self.overrides.iterrows():
            supplier_id = override.get("canonical_supplier_id")
            gl_account = override.get("gl_account")

            match = pd.Series(False, index=df.index)
            if supplier_id and pd.notna(supplier_id) and str(supplier_id).strip():
                if "canonical_supplier_id" in df.columns:
                    match |= df["canonical_supplier_id"] == str(supplier_id).strip()
            if gl_account and pd.notna(gl_account) and str(gl_account).strip():
                if "gl_account" in df.columns:
                    match |= df["gl_account"] == str(gl_account).strip()

            if not match.any():
                continue

            df.loc[match, "category_l1"] = override.get("override_l1")
            df.loc[match, "category_l2"] = override.get("override_l2")
            df.loc[match, "category_l3"] = override.get("override_l3")
            df.loc[match, "unspsc_code"] = override.get("unspsc_code")
            df.loc[match, "category_confidence"] = 1.0
            df.loc[match, "category_method"] = CategoryMethod.MANUAL.value
            classified_mask |= match

        classified = df[classified_mask].copy()
        unclassified = df[~classified_mask].copy()
        self.logger.info(
            f"Pass 0 (overrides): {len(classified)} classified, "
            f"{len(unclassified)} unclassified"
        )
        return classified, unclassified

    # ── Pass 1: GL code mapping ───────────────────────────────────────────

    def apply_gl_mapping(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Pass 1 — deterministic GL code lookup.

        Normalises GL codes by stripping leading zeros.  Tries exact match first,
        then falls back to a 4-digit prefix match (e.g. '6420100' → try '6420100',
        then '6420').

        Args:
            df: DataFrame of unclassified transactions.

        Returns:
            (classified_df, unclassified_df)
        """
        if df.empty:
            return pd.DataFrame(columns=df.columns), df.copy()

        df = df.copy()
        df = self._ensure_category_cols(df)
        classified_mask = pd.Series(False, index=df.index)

        for idx in df.index:
            gl_norm = self._gl_norm(df.at[idx, "gl_account"] if "gl_account" in df.columns else None)
            if gl_norm is None:
                continue

            # Exact match, then 4-digit prefix fallback
            seed = self._gl_lookup.get(gl_norm)
            if seed is None:
                prefix = gl_norm[:4]
                seed = self._gl_lookup.get(prefix)

            if seed is None:
                continue

            self._apply_seed_to_row(df, idx, seed, CategoryMethod.DETERMINISTIC_GL.value)
            classified_mask.at[idx] = True

        classified = df[classified_mask].copy()
        unclassified = df[~classified_mask].copy()
        self.logger.info(
            f"Pass 1 (GL mapping): {len(classified)} classified, "
            f"{len(unclassified)} unclassified"
        )
        return classified, unclassified

    # ── Pass 2: Supplier name mapping ────────────────────────────────────

    def apply_supplier_mapping(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Pass 2 — deterministic supplier name lookup (case-insensitive).

        Args:
            df: DataFrame of unclassified transactions.

        Returns:
            (classified_df, unclassified_df)
        """
        if df.empty:
            return pd.DataFrame(columns=df.columns), df.copy()

        df = df.copy()
        df = self._ensure_category_cols(df)
        classified_mask = pd.Series(False, index=df.index)

        for idx in df.index:
            supplier = (
                df.at[idx, "canonical_supplier_name"]
                if "canonical_supplier_name" in df.columns
                else None
            )
            if supplier is None or (isinstance(supplier, float) and pd.isna(supplier)):
                continue
            key = str(supplier).strip().lower()
            if not key:
                continue

            seed = self._supplier_lookup.get(key)
            if seed is None:
                continue

            self._apply_seed_to_row(
                df, idx, seed, CategoryMethod.DETERMINISTIC_SUPPLIER.value
            )
            classified_mask.at[idx] = True

        classified = df[classified_mask].copy()
        unclassified = df[~classified_mask].copy()
        self.logger.info(
            f"Pass 2 (supplier mapping): {len(classified)} classified, "
            f"{len(unclassified)} unclassified"
        )
        return classified, unclassified


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from src.config import load_config
    from src.models.database import get_engine, init_db

    config = load_config("config.yaml")
    engine = get_engine(config.paths.db_path)
    init_db(engine)

    seed_path = str(Path(config.paths.reference_dir) / "category_seed_mappings.csv")
    categoriser = DeterministicCategoriser(seed_path, engine, config)

    # Build sample transactions covering all three passes
    sample_data = [
        # Pass 1 — GL exact match
        {"transaction_id": "t01", "gl_account": "6420100", "canonical_supplier_id": None, "canonical_supplier_name": None, "raw_line_description": "Office stationery order"},
        {"transaction_id": "t02", "gl_account": "6441",    "canonical_supplier_id": None, "canonical_supplier_name": None, "raw_line_description": "Mobile phone fleet"},
        {"transaction_id": "t03", "gl_account": "6420999", "canonical_supplier_id": None, "canonical_supplier_name": None, "raw_line_description": "General office supplies (prefix match)"},
        # Pass 2 — Supplier match
        {"transaction_id": "t04", "gl_account": None, "canonical_supplier_id": None, "canonical_supplier_name": "Telstra",   "raw_line_description": "Monthly telecom invoice"},
        {"transaction_id": "t05", "gl_account": None, "canonical_supplier_id": None, "canonical_supplier_name": "Microsoft", "raw_line_description": "Azure subscription"},
        {"transaction_id": "t06", "gl_account": None, "canonical_supplier_id": None, "canonical_supplier_name": "DHL",       "raw_line_description": "International freight"},
        {"transaction_id": "t07", "gl_account": None, "canonical_supplier_id": None, "canonical_supplier_name": "KPMG",      "raw_line_description": "Audit fees Q1"},
        # Unmatched — will go to later passes
        {"transaction_id": "t08", "gl_account": "9999", "canonical_supplier_id": None, "canonical_supplier_name": "Unknown Vendor", "raw_line_description": "Miscellaneous services"},
        {"transaction_id": "t09", "gl_account": None,   "canonical_supplier_id": None, "canonical_supplier_name": "Random Corp",    "raw_line_description": "Ad hoc signage"},
        {"transaction_id": "t10", "gl_account": None,   "canonical_supplier_id": None, "canonical_supplier_name": None,             "raw_line_description": "Staff canteen March"},
    ]
    df = pd.DataFrame(sample_data)

    print(f"\nSample transactions: {len(df)} rows")
    print("=" * 60)

    # Pass 0: overrides
    classified_0, remaining = categoriser.apply_overrides(df)
    print(f"Pass 0 (MANUAL overrides): {len(classified_0)} classified")

    # Pass 1: GL mapping
    classified_1, remaining = categoriser.apply_gl_mapping(remaining)
    print(f"Pass 1 (DETERMINISTIC_GL): {len(classified_1)} classified")
    for _, row in classified_1.iterrows():
        print(
            f"  {row['transaction_id']} gl={row['gl_account']} → "
            f"{row['category_l1']}/{row['category_l2']} "
            f"(conf={row['category_confidence']:.2f})"
        )

    # Pass 2: supplier mapping
    classified_2, remaining = categoriser.apply_supplier_mapping(remaining)
    print(f"Pass 2 (DETERMINISTIC_SUPPLIER): {len(classified_2)} classified")
    for _, row in classified_2.iterrows():
        print(
            f"  {row['transaction_id']} supplier={row['canonical_supplier_name']} → "
            f"{row['category_l1']}/{row['category_l2']} "
            f"(conf={row['category_confidence']:.2f})"
        )

    total_classified = len(classified_0) + len(classified_1) + len(classified_2)
    print(f"\nTotal classified: {total_classified}/{len(df)} "
          f"({100*total_classified/len(df):.0f}%)")
    print(f"Unclassified (to pass to keyword/embedding/LLM): {len(remaining)}")
    for _, row in remaining.iterrows():
        print(f"  {row['transaction_id']} → {row['raw_line_description']}")
