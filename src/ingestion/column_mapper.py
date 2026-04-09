"""SpendCube column mapping and header normalisation."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


# Canonical fields that must be supplied by source data for a valid ingestion
REQUIRED_CANONICAL_FIELDS = [
    "invoice_number",
    "original_amount",
    "original_currency",
    "invoice_date",
    "raw_supplier_name",
]


class ColumnMapper:
    """Maps source DataFrame columns to canonical field names using YAML-driven config."""

    def __init__(self, mappings: dict) -> None:
        """
        Args:
            mappings: dict from config.column_mappings section.
                      Keys are source system names (e.g. 'DEFAULT', 'SAP'),
                      values are dicts mapping source column names to canonical names.
        """
        self.mappings = mappings

    def get_mapping(self, source_system: str = "DEFAULT") -> dict:
        """Return the column mapping dict for the given source system, falling back to DEFAULT."""
        if source_system in self.mappings:
            return self.mappings[source_system]
        return self.mappings.get("DEFAULT", {})

    def map_dataframe(self, df: pd.DataFrame, source_system: str = "DEFAULT") -> pd.DataFrame:
        """
        Rename DataFrame columns using the mapping for source_system.
        Falls back to DEFAULT if source_system not found.
        Columns not in the mapping are preserved with original names.
        """
        mapping = self.get_mapping(source_system)
        rename_map = {src: canon for src, canon in mapping.items() if src in df.columns}
        return df.rename(columns=rename_map)

    def detect_source_system(self, columns: list[str]) -> str:
        """
        Detect the best-matching source system for the given column list.
        Returns the source_system whose mapping has the highest column overlap.
        Returns 'DEFAULT' if no mapping has a meaningful match.
        """
        columns_set = set(columns)
        best_system = "DEFAULT"
        best_overlap = 0

        for system, mapping in self.mappings.items():
            source_cols = set(mapping.keys())
            overlap = len(columns_set & source_cols)
            if overlap > best_overlap:
                best_overlap = overlap
                best_system = system

        return best_system

    def get_unmapped_required_fields(
        self, df_columns: list[str], source_system: str = "DEFAULT"
    ) -> list[str]:
        """
        Return canonical required fields not covered by the current mapping
        for the given source system and DataFrame columns.
        """
        mapping = self.get_mapping(source_system)
        covered = {canon for src, canon in mapping.items() if src in df_columns}
        return [field for field in REQUIRED_CANONICAL_FIELDS if field not in covered]


if __name__ == "__main__":
    # Add project root to path so src.config is importable regardless of cwd
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))

    from src.config import load_config

    config = load_config(str(project_root / "config.yaml"))
    mapper = ColumnMapper(config.column_mappings)

    # Test dataframe with DEFAULT source column names
    test_data = {
        "VENDOR_NAME": ["Acme Pty Ltd"],
        "VENDOR_NUM": ["V-001"],
        "INV_NO": ["INV-2024-001"],
        "INV_DATE": ["15/03/2024"],
        "LINE_DESC": ["Professional services"],
        "AMT": [1250.00],
        "CCY": ["AUD"],
        "GL_CODE": ["6420100"],
        "COST_CTR": ["CC-MKT-01"],
        "PAY_TERMS": ["NET30"],
        "PO_NUM": ["PO-9001"],
        "BUS_UNIT": ["Corporate"],
        "SITE": ["Sydney"],
    }
    df = pd.DataFrame(test_data)

    print("Original columns:")
    print("  " + ", ".join(df.columns.tolist()))

    mapped_df = mapper.map_dataframe(df, "DEFAULT")

    print("\nRenamed columns (DEFAULT mapping):")
    print("  " + ", ".join(mapped_df.columns.tolist()))

    print("\nColumn mapping applied:")
    mapping = mapper.get_mapping("DEFAULT")
    for src, canon in mapping.items():
        if src in df.columns:
            print(f"  {src} -> {canon}")

    detected = mapper.detect_source_system(df.columns.tolist())
    print(f"\nDetected source system: {detected}")

    unmapped = mapper.get_unmapped_required_fields(df.columns.tolist(), "DEFAULT")
    if unmapped:
        print(f"\nUnmapped required fields: {unmapped}")
    else:
        print("\nAll required canonical fields are covered by DEFAULT mapping.")
