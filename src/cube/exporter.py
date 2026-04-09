"""SpendCube cube export to Parquet, Excel, and CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import load_config
from src.models.database import get_engine
from src.utils.logging import get_logger_from_config

_logger = None


def _get_logger(config=None):
    global _logger
    if _logger is None:
        if config is not None:
            _logger = get_logger_from_config(__name__, config)
        else:
            from src.utils.logging import get_logger
            _logger = get_logger(__name__)
    return _logger


class CubeExporter:
    """Persist spend cube DataFrames to Parquet, Excel, and CSV.

    Args:
        output_dir: Directory for output files (created if needed).
        config: Optional config object for logging.
    """

    def __init__(self, output_dir: str = "data/output", config=None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = _get_logger(config)

    # ------------------------------------------------------------------
    # Parquet
    # ------------------------------------------------------------------

    def export_parquet(self, cube: dict[str, pd.DataFrame]) -> dict[str, str]:
        """Write each DataFrame in *cube* to a .parquet file.

        Args:
            cube: Dict returned by SpendCubeBuilder.build().

        Returns:
            Dict of {key: absolute_file_path}.
        """
        paths: dict[str, str] = {}
        for key, df in cube.items():
            if df is None:
                continue
            dest = self.output_dir / f"{key}.parquet"
            # Cast object columns that may be Decimal to float64 for Parquet compatibility.
            df = _coerce_decimals(df)
            df.to_parquet(dest, engine="pyarrow", index=False)
            self.logger.info("Wrote %s (%d rows) → %s", key, len(df), dest)
            paths[key] = str(dest)
        return paths

    def load_parquet(self, key: str) -> pd.DataFrame:
        """Load a previously exported Parquet file by cube key.

        Args:
            key: Cube key, e.g. 'transactions', 'by_supplier'.

        Returns:
            DataFrame loaded from data/output/{key}.parquet.
        """
        path = self.output_dir / f"{key}.parquet"
        self.logger.info("Loading %s", path)
        return pd.read_parquet(path, engine="pyarrow")

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------

    def export_excel(
        self,
        cube: dict[str, pd.DataFrame],
        filename: str = "spend_cube.xlsx",
    ) -> str:
        """Write all cube DataFrames as separate sheets in a single workbook.

        Args:
            cube: Dict returned by SpendCubeBuilder.build().
            filename: Output filename (placed in output_dir).

        Returns:
            Absolute path to the written Excel file.
        """
        dest = self.output_dir / filename
        with pd.ExcelWriter(dest, engine="openpyxl") as writer:
            for key, df in cube.items():
                if df is None:
                    continue
                # Sheet names max 31 chars in Excel.
                sheet = key[:31]
                df = _coerce_decimals(df)
                df.to_excel(writer, sheet_name=sheet, index=False)
                self.logger.info("Wrote sheet '%s' (%d rows)", sheet, len(df))
        self.logger.info("Excel workbook written → %s", dest)
        return str(dest)

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def export_csv(
        self,
        cube: dict[str, pd.DataFrame],
        subdir: str = "csv",
    ) -> dict[str, str]:
        """Write each DataFrame as a CSV file under output_dir/csv/.

        Args:
            cube: Dict returned by SpendCubeBuilder.build().
            subdir: Subdirectory name within output_dir.

        Returns:
            Dict of {key: absolute_file_path}.
        """
        csv_dir = self.output_dir / subdir
        csv_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, str] = {}
        for key, df in cube.items():
            if df is None:
                continue
            dest = csv_dir / f"{key}.csv"
            df.to_csv(dest, index=False)
            self.logger.info("Wrote %s (%d rows) → %s", key, len(df), dest)
            paths[key] = str(dest)
        return paths


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_decimals(df: pd.DataFrame) -> pd.DataFrame:
    """Cast Decimal/object numeric columns to float64 for Parquet/Excel compat."""
    import decimal
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna()
            if not sample.empty and isinstance(sample.iloc[0], decimal.Decimal):
                df[col] = df[col].astype(float)
    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export SpendCube to Parquet/Excel/CSV")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument(
        "--format",
        choices=["parquet", "excel", "csv", "all"],
        default="parquet",
        help="Output format",
    )
    parser.add_argument("--output", default="data/output", help="Output directory")
    args = parser.parse_args()

    config = load_config(args.config)
    engine = get_engine(args.db)

    from src.cube.builder import SpendCubeBuilder  # noqa: PLC0415

    builder = SpendCubeBuilder(config, engine)
    cube = builder.build()

    exporter = CubeExporter(args.output, config=config)

    all_paths: dict[str, str] = {}

    if args.format in ("parquet", "all"):
        all_paths.update(exporter.export_parquet(cube))

    if args.format in ("excel", "all"):
        excel_path = exporter.export_excel(cube)
        all_paths["excel"] = excel_path

    if args.format in ("csv", "all"):
        all_paths.update(exporter.export_csv(cube))

    print(f"\nFiles created ({len(all_paths)}):")
    for key, path in all_paths.items():
        size = Path(path).stat().st_size
        print(f"  {key}: {path}  ({size:,} bytes)")
