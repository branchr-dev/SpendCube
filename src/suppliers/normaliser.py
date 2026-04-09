"""SpendCube supplier name normalisation.

Stage 1 of the 5-stage supplier harmonisation pipeline. Always runs first,
on every supplier name, producing a normalised form for downstream matching.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Legal entity designator set
# ---------------------------------------------------------------------------
# Only these suffixes from legal_suffixes.yaml are stripped during normalisation.
# Geographic and organisational qualifiers (Australia, Group, International, etc.)
# are intentionally excluded — they may be meaningful identifiers that distinguish
# regional entities (e.g. "Sodexo Australia" from "Sodexo UK") and should be
# preserved.  The full yaml list remains the authoritative reference for future
# phases; this code simply filters to strippable entries.
_LEGAL_ENTITY_SET: frozenset[str] = frozenset({
    # Compound Australian designators
    "pty ltd", "pty. ltd.", "pty. ltd",
    # Slash / dot variants
    "p/l", "p.l.",
    # US / international
    "llc", "l.l.c.",
    "inc", "inc.", "incorporated",
    # Generic limited / ltd
    "ltd", "ltd.", "limited",
    # European
    "gmbh", "ag", "s.a.", "s.a.s.", "b.v.", "n.v.",
    # UK
    "plc",
    # Corporation / company
    "corp", "corp.", "corporation",
    "co", "co.", "company",
    # Other
    "trust", "pty",
})

# Regex for Trading-As prefix variants (applied before suffix stripping)
_TA_PATTERN = re.compile(
    r"^\s*(?:t/a|t\.a\.|trading\s+as)\s+",
    re.IGNORECASE,
)


class SupplierNormaliser:
    """
    Stage 1 of the supplier harmonisation pipeline.

    Produces a normalised form of a raw supplier name suitable for exact-match
    deduplication and as input to downstream fuzzy / embedding matching stages.
    """

    def __init__(self, suffixes_path: str, abbreviations_path: str) -> None:
        """
        Load reference data for normalisation.

        Args:
            suffixes_path:      Path to data/reference/legal_suffixes.yaml
            abbreviations_path: Path to data/reference/abbreviation_map.yaml
        """
        with open(suffixes_path) as fh:
            raw = yaml.safe_load(fh)
        all_suffixes = [s.lower() for s in raw.get("suffixes", [])]
        # Filter to true legal entity designators; sort longest first for
        # greedy (longest-match) stripping.
        self._suffixes: list[str] = sorted(
            (s for s in all_suffixes if s in _LEGAL_ENTITY_SET),
            key=len,
            reverse=True,
        )

        with open(abbreviations_path) as fh:
            abbrev_raw = yaml.safe_load(fh)
        # Lowercase keys and values; sort by key length descending for
        # longest-abbreviation-first expansion.
        self._abbrev_items: list[tuple[str, str]] = sorted(
            ((k.lower(), v.lower()) for k, v in abbrev_raw.items()),
            key=lambda kv: -len(kv[0]),
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def normalise(self, name: Optional[str]) -> str:
        """
        Normalise a single supplier name.

        Processing pipeline (in order):
          1. Return '' for None / blank input.
          2. Lowercase.
          3. Strip leading/trailing whitespace.
          4. Remove T/A, T.A., Trading As prefix.
          5. Iteratively strip legal entity suffixes (longest first).
          6. Expand abbreviations (whole-word match, longest abbreviation first).
          7. Remove punctuation except hyphens between word characters.
          8. Collapse multiple spaces to a single space.
          9. Strip again.

        Args:
            name: Raw supplier name (may be None, NaN, or blank).

        Returns:
            Normalised string; empty string for None / blank input.
        """
        # Step 1 — guard
        if name is None:
            return ""
        s = str(name).strip()
        if not s:
            return ""

        # Step 2 — lowercase
        s = s.lower()

        # Step 3 — strip (already stripped above; reapply after lower in case of
        # leading/trailing chars revealed by casing)
        s = s.strip()

        # Step 4 — remove T/A / Trading As prefix
        s = _TA_PATTERN.sub("", s).strip()

        # Step 5 — iteratively strip legal entity suffixes (longest first)
        changed = True
        while changed:
            changed = False
            for suffix in self._suffixes:
                # Word-boundary: suffix must not be part of a larger word.
                pattern = r"(?<!\w)" + re.escape(suffix) + r"\s*$"
                new_s = re.sub(pattern, "", s).rstrip()
                if new_s != s:
                    s = new_s
                    changed = True
                    break  # restart from longest after each successful strip

        # Over-strip protection: if all content was stripped, fall back to
        # the lowercased original (prevents e.g. "Pty Ltd Pty Ltd" → "").
        if not s.strip():
            s = str(name).lower().strip()

        # Step 6 — expand abbreviations (whole-word, longest abbreviation first)
        for abbr, expansion in self._abbrev_items:
            pattern = r"\b" + re.escape(abbr) + r"\b"
            s = re.sub(pattern, expansion, s)

        # Step 7 — remove punctuation except hyphens within words
        # Pass A: remove all non-alphanumeric, non-space, non-hyphen characters.
        s = re.sub(r"[^\w\s-]", " ", s)
        # Pass B: remove hyphens that are NOT between two word characters
        #         (i.e. keep "co-op" but strip "intercompany - legal").
        s = re.sub(r"(?<!\w)-|-(?!\w)", " ", s)

        # Step 8 — collapse multiple spaces
        s = re.sub(r"\s+", " ", s)

        # Step 9 — final strip
        return s.strip()

    def normalise_series(self, series: pd.Series) -> pd.Series:
        """
        Normalise a pandas Series of supplier names.

        Args:
            series: Series of raw supplier name strings (may contain NaN / None).

        Returns:
            Series of normalised strings (same index as input).
        """
        return series.map(self.normalise)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    suffixes_path = project_root / "data" / "reference" / "legal_suffixes.yaml"
    abbreviations_path = project_root / "data" / "reference" / "abbreviation_map.yaml"
    sample_path = project_root / "data" / "input" / "sample.csv"

    normaliser = SupplierNormaliser(
        suffixes_path=str(suffixes_path),
        abbreviations_path=str(abbreviations_path),
    )

    print("Supplier Name Normalisation — Sample Data\n")
    print(f"{'Raw Name':<40}  Normalised")
    print("-" * 70)

    acme_normalised: set[str] = set()
    sodexo_normalised: set[str] = set()

    with open(sample_path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw = row.get("VENDOR_NAME", "") or ""
            normalised = normaliser.normalise(raw if raw.strip() else None)
            print(f"{raw!r:<40}  {normalised!r}")

            raw_lower = raw.strip().lower()
            if "acme" in raw_lower:
                acme_normalised.add(normalised)
            elif "sodexo" in raw_lower:
                sodexo_normalised.add(normalised)

    print()
    errors: list[str] = []

    if len(acme_normalised) == 1:
        print(f"PASS  Acme variants all normalise to: {next(iter(acme_normalised))!r}")
    else:
        msg = f"FAIL  Acme variants produced multiple results: {acme_normalised}"
        print(msg)
        errors.append(msg)

    if len(sodexo_normalised) == 1:
        print(f"PASS  Sodexo variants all normalise to: {next(iter(sodexo_normalised))!r}")
    else:
        msg = f"FAIL  Sodexo variants produced multiple results: {sodexo_normalised}"
        print(msg)
        errors.append(msg)

    sys.exit(1 if errors else 0)
