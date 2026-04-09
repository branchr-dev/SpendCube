"""SpendCube ingestion pipeline orchestrator.

Ties together column mapping, date parsing, currency conversion,
and data cleaning into a single Ingestor class.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

# Ensure project root is on sys.path so imports work when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ingestion.cleaner import DataCleaner
from src.ingestion.column_mapper import ColumnMapper
from src.ingestion.currency_converter import CurrencyConverter
from src.ingestion.date_parser import parse_date_series

# Columns accepted by the transactions DB table (from src/models/database.py).
_DB_COLUMNS = {
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
    "review_date", "raw_data",
}


def _safe_json(d: dict) -> str:
    """Serialize a dict to JSON, converting NaN/non-serialisable values to strings."""
    clean = {}
    for k, v in d.items():
        if isinstance(v, float) and np.isnan(v):
            clean[k] = None
        elif isinstance(v, (np.integer,)):
            clean[k] = int(v)
        elif isinstance(v, (np.floating,)):
            clean[k] = float(v)
        elif isinstance(v, (np.bool_,)):
            clean[k] = bool(v)
        else:
            clean[k] = v
    return json.dumps(clean, default=str)


class Ingestor:
    """Orchestrates the full ingestion pipeline for CSV and Excel files."""

    def __init__(self, config) -> None:
        """Initialise pipeline components from config.

        Args:
            config: Loaded Config object from src.config.load_config().
        """
        self.config = config
        self.mapper = ColumnMapper(config.column_mappings)
        fx_path = str(Path(config.paths.reference_dir) / "fx_rates.csv")
        self.converter = CurrencyConverter(fx_path, config.spend_cube.base_currency)
        self.cleaner = DataCleaner()

    def ingest_file(self, file_path: str, source_system: str = None) -> pd.DataFrame:
        """Read a CSV or Excel file and run it through the full ingestion pipeline.

        Steps:
        1. Read file into raw DataFrame.
        2. Capture original columns as JSON in raw_data.
        3. Auto-detect source system from column names if not provided.
        4. Apply column mapping (renames source columns to canonical names).
        5. Set source_row_number to original row index.
        6. Parse invoice_date using multi-format date parser.
        7. Convert amounts to base currency (AUD) via CurrencyConverter.
        8. Apply DataCleaner (flags, payment terms, null normalisation).
        9. Generate UUID transaction_id for each row.
        10. Set ingested_at and last_modified_at to current UTC datetime.

        Args:
            file_path: Path to CSV or Excel file.
            source_system: Column mapping key (e.g. 'DEFAULT'). Auto-detected if None.

        Returns:
            DataFrame with canonical column names and all derived fields.
        """
        path = Path(file_path)
        if path.suffix.lower() in (".xlsx", ".xls"):
            df_raw = pd.read_excel(path)
        else:
            df_raw = pd.read_csv(path)

        # Capture raw source data before any transformation
        raw_data_series = df_raw.apply(lambda row: _safe_json(row.to_dict()), axis=1)

        # Auto-detect source system from column overlap
        if source_system is None:
            source_system = self.mapper.detect_source_system(df_raw.columns.tolist())

        # Rename columns to canonical names
        df = self.mapper.map_dataframe(df_raw, source_system)

        # Metadata columns
        df["source_row_number"] = df_raw.index
        df["raw_data"] = raw_data_series
        df["source_system"] = source_system
        df["base_currency"] = self.config.spend_cube.base_currency

        # Parse invoice_date
        if "invoice_date" in df.columns:
            df["invoice_date"] = parse_date_series(df["invoice_date"])

        # Currency conversion
        if all(c in df.columns for c in ("original_amount", "original_currency", "invoice_date")):
            df = self.converter.convert_dataframe(
                df, "original_amount", "original_currency", "invoice_date"
            )
            # Rename to match DB column name
            df = df.rename(columns={"fx_rate_used": "fx_rate"})

        # Data cleaning and flag detection
        df = self.cleaner.clean(df)

        # Generate unique transaction IDs
        df["transaction_id"] = [str(uuid4()) for _ in range(len(df))]

        # Timestamps (ISO string — stored as TEXT in SQLite)
        now = datetime.utcnow().isoformat()
        df["ingested_at"] = now
        df["last_modified_at"] = now

        return df

    def ingest_to_db(self, file_path: str, engine, source_system: str = None) -> int:
        """Ingest a file and write the resulting rows to the database.

        Args:
            file_path: Path to CSV or Excel file.
            engine: SQLAlchemy engine (from src.models.database.get_engine).
            source_system: Column mapping key. Auto-detected if None.

        Returns:
            Number of rows inserted.
        """
        from src.models.database import insert_transactions

        df = self.ingest_file(file_path, source_system)
        records = self._df_to_records(df)
        return insert_transactions(engine, records)

    def _df_to_records(self, df: pd.DataFrame) -> list[dict]:
        """Convert DataFrame to list of dicts for DB insertion.

        Filters to only DB columns, and coerces types (Decimal→float,
        bool→int, date→ISO string, numpy types→Python types).
        """
        records = []
        for _, row in df.iterrows():
            rec: dict = {}
            for col, val in row.items():
                if col not in _DB_COLUMNS:
                    continue
                # Type coercion for SQLAlchemy compatibility
                if isinstance(val, Decimal):
                    val = float(val)
                elif isinstance(val, (np.bool_,)):
                    val = int(val)
                elif isinstance(val, bool):
                    val = int(val)
                elif isinstance(val, float) and np.isnan(val):
                    val = None
                elif isinstance(val, (np.integer,)):
                    val = int(val)
                elif isinstance(val, (np.floating,)):
                    val = None if np.isnan(val) else float(val)
                elif hasattr(val, "isoformat"):
                    val = val.isoformat()
                elif val is pd.NaT:
                    val = None
                rec[col] = val
            # Ensure boolean flag columns are stored as int
            for bool_col in ("is_credit_note", "is_intercompany", "is_tax_line", "is_duplicate"):
                if bool_col in rec and rec[bool_col] is not None:
                    rec[bool_col] = int(rec[bool_col])
            records.append(rec)
        return records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_summary(df: pd.DataFrame, file_path: str) -> None:  # pragma: no cover
    """Print ingestion summary to stdout."""
    total = len(df)
    print(f"\nIngested {total} rows from {file_path}")

    source = df["source_system"].iloc[0] if "source_system" in df.columns else "UNKNOWN"
    print(f"Source system: {source}")

    # Document type counts
    if "document_type" in df.columns:
        print("\nDocument types:")
        for dtype, count in df["document_type"].value_counts().items():
            print(f"  {dtype}: {count}")

    # Flag counts
    print("\nFlags:")
    for flag in ("is_credit_note", "is_intercompany", "is_tax_line", "is_freight_line"):
        if flag in df.columns:
            count = int(df[flag].sum())
            print(f"  {flag}: {count}")

    # Currency conversion
    if "original_currency" in df.columns:
        base_ccy = df["base_currency"].iloc[0] if "base_currency" in df.columns else "AUD"
        foreign = df[df["original_currency"] != base_ccy]
        if len(foreign) > 0:
            print(f"\nCurrency conversion:")
            for ccy, grp in foreign.groupby("original_currency"):
                print(f"  {len(grp)} {ccy} transaction(s) converted to {base_ccy}")

    # FX warnings
    if "fx_warning" in df.columns:
        warnings = df["fx_warning"].dropna()
        print(f"\nCurrency conversion warnings: {len(warnings)}")
        for w in warnings:
            print(f"  {w}")
    else:
        print("\nCurrency conversion warnings: 0")

    # Parse failures (rows where invoice_date is None)
    if "invoice_date" in df.columns:
        failures = int(df["invoice_date"].isna().sum())
        print(f"Parse failures (invoice_date): {failures}")

    print(f"\n{total} rows processed")


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="SpendCube ingestion pipeline — ingest a CSV or Excel file"
    )
    parser.add_argument("--file", required=True, help="Path to input CSV or Excel file")
    parser.add_argument(
        "--source", default=None,
        help="Source system name for column mapping (e.g. DEFAULT). Auto-detected if omitted."
    )
    parser.add_argument(
        "--db", default=None,
        help="SQLite DB path. If provided, ingested rows are written to the database."
    )
    parser.add_argument(
        "--config", default=str(_PROJECT_ROOT / "config.yaml"),
        help="Path to config.yaml (default: <project_root>/config.yaml)"
    )
    args = parser.parse_args()

    from src.config import load_config
    config = load_config(args.config)
    ingestor = Ingestor(config)

    if args.db:
        from src.models.database import get_engine, init_db
        engine = get_engine(args.db)
        init_db(engine)
        count = ingestor.ingest_to_db(args.file, engine, args.source)
        # Re-ingest for summary (no DB write)
        df = ingestor.ingest_file(args.file, args.source)
        _print_summary(df, args.file)
        print(f"\nDB: {count} rows written to {args.db}")
    else:
        df = ingestor.ingest_file(args.file, args.source)
        _print_summary(df, args.file)


if __name__ == "__main__":  # pragma: no cover
    main()
