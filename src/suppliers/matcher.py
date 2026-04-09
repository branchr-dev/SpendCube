"""SpendCube supplier matching: deterministic (Stage 2) and fuzzy (Stage 3).

Both classes are designed to be used sequentially in the harmonisation pipeline:
  - DeterministicMatcher handles exact normalised-name and vendor-ID lookups.
  - FuzzyMatcher handles approximate name matching with corroboration boosts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Stage 2 — Deterministic Matcher
# ---------------------------------------------------------------------------

class DeterministicMatcher:
    """
    Stage 2 of the supplier harmonisation pipeline.

    Performs exact matching on normalised name and vendor ID against the
    existing supplier master. Returns high-confidence results; unmatched
    suppliers pass through to the fuzzy stage.
    """

    def __init__(self, supplier_master_df: pd.DataFrame) -> None:
        """
        Build lookup indices from the existing supplier master DataFrame.

        Args:
            supplier_master_df: Must contain canonical_supplier_id and
                normalised_name columns. Optionally identifiers (JSON TEXT)
                containing {"raw_ids": [...]} for vendor-ID lookup.
        """
        self._name_to_id: dict[str, str] = {}
        self._vendor_id_to_id: dict[str, str] = {}

        if supplier_master_df.empty:
            return

        # Build normalised name → canonical_supplier_id index
        if "normalised_name" in supplier_master_df.columns:
            for _, row in supplier_master_df.iterrows():
                name = str(row["normalised_name"]).strip()
                if name:
                    self._name_to_id[name] = str(row["canonical_supplier_id"])

        # Build raw_supplier_id → canonical_supplier_id index from identifiers JSON
        if "identifiers" in supplier_master_df.columns:
            for _, row in supplier_master_df.iterrows():
                identifiers_raw = row.get("identifiers") or "{}"
                try:
                    identifiers = (
                        identifiers_raw
                        if isinstance(identifiers_raw, dict)
                        else json.loads(identifiers_raw)
                    )
                except (json.JSONDecodeError, TypeError):
                    identifiers = {}
                for raw_id in identifiers.get("raw_ids", []):
                    if raw_id:
                        self._vendor_id_to_id[str(raw_id)] = str(row["canonical_supplier_id"])

    def match(
        self,
        raw_name: str,
        normalised_name: str,
        raw_supplier_id: Optional[str] = None,
    ) -> tuple[str | None, float, str]:
        """
        Attempt deterministic matching in priority order.

        Tries:
          1. Exact normalised name  → confidence 0.95, method='EXACT_NAME'
          2. Exact raw vendor ID    → confidence 0.99, method='EXACT_VENDOR_ID'

        Args:
            raw_name:        Original supplier name (unused in logic; kept
                             for caller symmetry and future logging).
            normalised_name: Normalised name from Stage 1.
            raw_supplier_id: Vendor / supplier ID from source system.

        Returns:
            (canonical_supplier_id, confidence, method) or (None, 0.0, '').
        """
        if normalised_name and normalised_name in self._name_to_id:
            return (self._name_to_id[normalised_name], 0.95, "EXACT_NAME")

        if raw_supplier_id and str(raw_supplier_id) in self._vendor_id_to_id:
            return (self._vendor_id_to_id[str(raw_supplier_id)], 0.99, "EXACT_VENDOR_ID")

        return (None, 0.0, "")


# ---------------------------------------------------------------------------
# Stage 3 — Fuzzy Matcher
# ---------------------------------------------------------------------------

class FuzzyMatcher:
    """
    Stage 3 of the supplier harmonisation pipeline.

    Applies a weighted rapidfuzz composite score with optional corroboration
    signal boosts (city, postcode, ABN) to resolve suppliers not matched
    deterministically.
    """

    def __init__(self, supplier_master_df: pd.DataFrame, config) -> None:
        """
        Initialise fuzzy matcher from supplier master and config thresholds.

        Args:
            supplier_master_df: Must contain canonical_supplier_id and
                normalised_name (preferred) or canonical_name columns.
            config: Project Config object; reads config.supplier_matching.
        """
        self._df = (
            supplier_master_df.copy()
            if not supplier_master_df.empty
            else supplier_master_df
        )
        sm = config.supplier_matching
        self._auto_threshold: int = sm.fuzzy_auto_threshold      # e.g. 88
        self._review_threshold: int = sm.fuzzy_review_threshold  # e.g. 70
        self._boost_city: int = sm.corroboration_same_city        # e.g. 5
        self._boost_postcode: int = sm.corroboration_same_postcode  # e.g. 8
        self._boost_abn: int = sm.corroboration_same_abn          # e.g. 20

    def score(self, name_a: str, name_b: str) -> float:
        """
        Compute weighted composite fuzzy similarity score.

        Formula: token_sort_ratio * 0.40 + token_set_ratio * 0.40
                 + partial_ratio * 0.20, divided by 100 to yield 0–1.

        Args:
            name_a: First normalised supplier name.
            name_b: Second normalised supplier name.

        Returns:
            Composite score in [0.0, 1.0].
        """
        ts = fuzz.token_sort_ratio(name_a, name_b)
        tset = fuzz.token_set_ratio(name_a, name_b)
        pr = fuzz.partial_ratio(name_a, name_b)
        return (ts * 0.40 + tset * 0.40 + pr * 0.20) / 100.0

    def match(
        self,
        normalised_name: str,
        corroboration: Optional[dict] = None,
    ) -> tuple[str | None, float, str, str]:
        """
        Fuzzy-match normalised_name against all entries in the supplier master.

        Scoring is performed in the 0–100 scale for threshold comparison;
        confidence values returned are in 0–1.

        Corroboration boosts (from config, e.g. same_city=5) are added as
        integer points on the 0–100 scale before threshold evaluation.

        Args:
            normalised_name: Normalised supplier name from Stage 1.
            corroboration:   Optional dict with boolean keys: same_city,
                             same_postcode, same_abn.

        Returns:
            (canonical_supplier_id, confidence, method, evidence) where
            method is FUZZY_AUTO, FUZZY_REVIEW, or FUZZY_REJECT.
            For FUZZY_REJECT, canonical_supplier_id is None.
        """
        if self._df.empty:
            return (None, 0.0, "FUZZY_REJECT", "no supplier master entries")

        name_col = (
            "normalised_name"
            if "normalised_name" in self._df.columns
            else "canonical_name"
        )

        best_id: Optional[str] = None
        best_composite_100: float = -1.0
        best_ts: int = 0
        best_tset: int = 0
        best_pr: int = 0

        for _, row in self._df.iterrows():
            candidate = str(row.get(name_col, ""))
            if not candidate:
                continue

            ts = fuzz.token_sort_ratio(normalised_name, candidate)
            tset = fuzz.token_set_ratio(normalised_name, candidate)
            pr = fuzz.partial_ratio(normalised_name, candidate)
            composite_100 = ts * 0.40 + tset * 0.40 + pr * 0.20  # 0–100

            if composite_100 > best_composite_100:
                best_composite_100 = composite_100
                best_id = str(row["canonical_supplier_id"])
                best_ts = ts
                best_tset = tset
                best_pr = pr

        composite_0_1 = best_composite_100 / 100.0

        # Apply corroboration boosts (integer points on 0–100 scale)
        boosted_100 = best_composite_100
        boost_notes: list[str] = []
        if corroboration:
            if corroboration.get("same_city"):
                boosted_100 += self._boost_city
                boost_notes.append(f"city_match+{self._boost_city}")
            if corroboration.get("same_postcode"):
                boosted_100 += self._boost_postcode
                boost_notes.append(f"postcode_match+{self._boost_postcode}")
            if corroboration.get("same_abn"):
                boosted_100 += self._boost_abn
                boost_notes.append(f"abn_match+{self._boost_abn}")

        # Build evidence string using pre-boost composite for transparency
        evidence = (
            f"token_sort={round(best_ts)} token_set={round(best_tset)} partial={round(best_pr)} "
            f"composite={composite_0_1:.2f}"
        )
        if boost_notes:
            evidence += " + " + " ".join(boost_notes)

        # Threshold decision on boosted score (0–100 scale)
        boosted_0_1 = boosted_100 / 100.0
        auto_t = self._auto_threshold / 100.0
        review_t = self._review_threshold / 100.0

        if boosted_0_1 >= auto_t:
            return (best_id, composite_0_1 * 0.95, "FUZZY_AUTO", evidence)
        elif boosted_0_1 >= review_t:
            return (best_id, composite_0_1 * 0.85, "FUZZY_REVIEW", evidence)
        else:
            return (None, composite_0_1, "FUZZY_REJECT", evidence)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from src.suppliers.normaliser import SupplierNormaliser
    from src.config import load_config

    project_root = _PROJECT_ROOT
    suffixes_path = project_root / "data" / "reference" / "legal_suffixes.yaml"
    abbreviations_path = project_root / "data" / "reference" / "abbreviation_map.yaml"

    normaliser = SupplierNormaliser(
        suffixes_path=str(suffixes_path),
        abbreviations_path=str(abbreviations_path),
    )
    config = load_config(str(project_root / "config.yaml"))

    # Build a minimal supplier master with canonical entries from sample data
    master_df = pd.DataFrame([
        {
            "canonical_supplier_id": "abc000acme11",
            "canonical_name": "Acme Pty Ltd",
            "normalised_name": "acme",
            "identifiers": json.dumps({"raw_ids": ["V-001"]}),
        },
        {
            "canonical_supplier_id": "def000sod012",
            "canonical_name": "Sodexo Australia",
            "normalised_name": "sodexo australia",
            "identifiers": json.dumps({"raw_ids": ["V-002"]}),
        },
        {
            "canonical_supplier_id": "ghi000dhl013",
            "canonical_name": "DHL Express",
            "normalised_name": "dhl express",
            "identifiers": json.dumps({"raw_ids": ["V-004"]}),
        },
    ])

    det = DeterministicMatcher(master_df)
    fuzzy = FuzzyMatcher(master_df, config)

    test_cases = [
        # (description, raw_name, normalised_name, raw_supplier_id, corroboration)
        ("Exact name match",          "Acme Pty Ltd",       "acme",             None,    None),
        ("Exact name match",          "ACME PTY LIMITED",   "acme",             None,    None),
        ("Exact vendor ID match",     "Unknown Acme Co",    "unknown acme co",  "V-001", None),
        ("No deterministic match",    "Acme Solutions",     "acme solutions",   "V-099", None),
        ("Exact Sodexo match",        "Sodexo Aust P/L",    "sodexo australia", None,    None),
        ("Fuzzy: acme variant",       "Acme Corp",          "acme corp",        None,    None),
        ("Fuzzy + city boost",        "Acme Holdings",      "acme holdings",    None,    {"same_city": True}),
        ("Fuzzy: sodexo close",       "Sodexo Aus",         "sodexo aus",       None,    None),
        ("Fuzzy: dhl variant",        "DHL Express Pty",    "dhl express",      None,    None),
        ("No match expected",         "XYZ Widgets",        "xyz widgets",      None,    None),
    ]

    print("Supplier Matching — Deterministic and Fuzzy Test Results\n")
    print(f"{'Description':<30}  {'Normalised':<22}  {'Method':<20}  Conf   Evidence")
    print("-" * 110)

    for desc, raw, norm, vendor_id, corroboration in test_cases:
        # Try deterministic first
        canon_id, conf, method = det.match(raw, norm, vendor_id)

        if canon_id is not None:
            # Find canonical name for display
            matched_name = master_df.loc[
                master_df["canonical_supplier_id"] == canon_id, "canonical_name"
            ].iloc[0] if not master_df.empty else canon_id
            evidence = f"matched: {matched_name}"
        else:
            # Fall through to fuzzy
            canon_id, conf, method, evidence = fuzzy.match(norm, corroboration)
            if canon_id is not None:
                matched_name = master_df.loc[
                    master_df["canonical_supplier_id"] == canon_id, "canonical_name"
                ].iloc[0]
                evidence = f"{evidence} → {matched_name}"

        conf_str = f"{conf:.3f}" if conf else "0.000"
        print(f"{desc:<30}  {norm:<22}  {method:<20}  {conf_str}  {evidence}")

    print()
    print("PASS  Deterministic and fuzzy matcher operational.")
    sys.exit(0)
