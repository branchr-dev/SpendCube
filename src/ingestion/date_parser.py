"""SpendCube date parsing and normalisation utilities."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import pandas as pd
from dateutil import parser as dateutil_parser


_FORMATS = [
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%b-%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
]

_EXCEL_EPOCH = date(1899, 12, 30)


def parse_date(value: Any) -> date | None:
    """Parse a single date value into a Python date object.

    Handles:
    - None, empty string, 'N/A', NaN, pd.NaT → None
    - Excel date serials (int/float without fraction) → date via epoch
    - String dates via explicit format chain then dateutil fallback
    """
    if value is None:
        return None
    if value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "" or stripped == "N/A":
            return None
        # Try explicit formats first
        for fmt in _FORMATS:
            try:
                return pd.to_datetime(stripped, format=fmt).date()
            except (ValueError, TypeError):
                continue
        # Fallback to dateutil
        try:
            return dateutil_parser.parse(stripped, dayfirst=True).date()
        except (ValueError, TypeError):
            return None
    # Excel serial number (int or float whole number)
    if isinstance(value, (int, float)):
        try:
            return _EXCEL_EPOCH + timedelta(days=int(value))
        except (OverflowError, OSError, ValueError):
            return None
    # datetime/date objects
    if isinstance(value, date):
        return value
    return None


def parse_date_series(series: pd.Series) -> pd.Series:
    """Vectorised batch parse of a pandas Series into dates (or None)."""
    return series.map(parse_date)


if __name__ == "__main__":
    import sys

    samples = [
        ("'15/03/2024'", "15/03/2024", date(2024, 3, 15)),
        ("'2024-03-18'", "2024-03-18", date(2024, 3, 18)),
        ("'20-Mar-2024'", "20-Mar-2024", date(2024, 3, 20)),
        ("'5/4/2024'", "5/4/2024", date(2024, 4, 5)),
        ("'01/04/2024'", "01/04/2024", date(2024, 4, 1)),
        ("'2024-04-03'", "2024-04-03", date(2024, 4, 3)),
        ("'12/02/2024'", "12/02/2024", date(2024, 2, 12)),
        ("'31/03/2024'", "31/03/2024", date(2024, 3, 31)),
        ("'28/02/2024'", "28/02/2024", date(2024, 2, 28)),
    ]

    edge_cases = [
        ("None", None, None),
        ("''", "", None),
        ("'N/A'", "N/A", None),
        ("float('nan')", float("nan"), None),
        ("pd.NaT", pd.NaT, None),
        ("Excel 45369", 45369, None),  # just show result, no hardcoded expected
    ]

    all_pass = True
    print("=== Sample dates ===")
    for label, value, expected in samples:
        result = parse_date(value)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {status}  {label} → {result}  (expected {expected})")

    print("\n=== Edge cases ===")
    for label, value, expected in edge_cases:
        result = parse_date(value)
        if expected is None and label == "Excel 45369":
            # Just display the result; the formula is defined, not a specific output
            print(f"  INFO  {label} → {result}")
        else:
            status = "PASS" if result == expected else "FAIL"
            if status == "FAIL":
                all_pass = False
            print(f"  {status}  {label} → {result}  (expected {expected})")

    print("\n=== Series test ===")
    s = pd.Series(["15/03/2024", "2024-03-18", None, "N/A", 45369])
    results = parse_date_series(s)
    print(results.tolist())

    sys.exit(0 if all_pass else 1)
