"""SpendCube data cleaning and validation pipeline."""

from __future__ import annotations

import re
import sys
import os
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Null representations to normalise to np.nan
# ---------------------------------------------------------------------------
_NULL_VALUES = {"", "N/A", "n/a", "NULL", "null", "None", "-", "#N/A", "nan"}


def detect_document_type(row: pd.Series) -> str:
    """Return 'CREDIT_NOTE' or 'INVOICE' based on amount sign and invoice prefix.

    Args:
        row: A DataFrame row with 'original_amount' and 'invoice_number' fields.

    Returns:
        'CREDIT_NOTE' if amount < 0 or invoice_number starts with 'CN-' or 'CR-';
        'INVOICE' otherwise.
    """
    amount = row.get("original_amount")
    invoice_number = row.get("invoice_number")

    try:
        if amount is not None and not (isinstance(amount, float) and np.isnan(amount)):
            if float(amount) < 0:
                return "CREDIT_NOTE"
    except (ValueError, TypeError):
        pass

    if invoice_number is not None and not (isinstance(invoice_number, float) and np.isnan(invoice_number)):
        inv_str = str(invoice_number).upper()
        if inv_str.startswith("CN-") or inv_str.startswith("CR-"):
            return "CREDIT_NOTE"

    return "INVOICE"


def parse_payment_terms(raw: Optional[str]) -> Optional[int]:
    """Parse a raw payment terms string into an integer number of days.

    Handles: 'Net 30', 'NET30', 'net30', 'Net30', 'n30', '30 days', '30'.
    Extracts the first integer found using r'\\b(\\d+)\\b'.

    Args:
        raw: Raw payment terms string or None.

    Returns:
        Integer days (e.g. 30, 14, 45, 60) or None if unparseable.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw or raw in _NULL_VALUES:
        return None

    # Use r'(\d+)' to handle both spaced ('Net 30') and compact ('NET30', 'n30') forms.
    # The spec regex r'\b(\d+)\b' only matches when digits have word boundaries on both
    # sides, which fails for 'NET30' (letter before digit is still \w). Using (\d+)
    # extracts the first run of digits in all listed cases.
    match = re.search(r"(\d+)", raw)
    if match:
        return int(match.group(1))
    return None


def detect_intercompany(supplier_name: str) -> bool:
    """Return True if supplier_name is an intercompany entity.

    Checks (case-insensitive) for: 'INTERCOMPANY', 'INTER-COMPANY',
    'INTRA-COMPANY', 'INTERNAL -', 'IC - ', or starts with 'IC-'.

    Args:
        supplier_name: Raw supplier name string.

    Returns:
        True if intercompany, False otherwise.
    """
    if not supplier_name or not isinstance(supplier_name, str):
        return False

    upper = supplier_name.upper()

    if upper.startswith("IC-"):
        return True

    _INTERCO_KEYWORDS = [
        "INTERCOMPANY",
        "INTER-COMPANY",
        "INTRA-COMPANY",
        "INTERNAL -",
        "IC - ",
    ]
    return any(kw in upper for kw in _INTERCO_KEYWORDS)


def detect_tax_line(description: str, gl_account: Optional[str]) -> bool:
    """Return True if this line item is a tax adjustment.

    Checks description (lowercased) for tax keywords, or gl_account starting
    with '2' (balance sheet GL range).

    Args:
        description: Line item description string.
        gl_account: GL account code string or None.

    Returns:
        True if tax line, False otherwise.
    """
    _TAX_KEYWORDS = ["gst", "vat", "tax adj", "tax adjustment", "withholding tax"]

    if description and isinstance(description, str):
        lower = description.lower()
        if any(kw in lower for kw in _TAX_KEYWORDS):
            return True

    if gl_account and isinstance(gl_account, str):
        if gl_account.strip().startswith("2"):
            return True

    return False


def detect_freight_line(description: str) -> bool:
    """Return True if this line item is a freight/shipping charge.

    Checks description (lowercased) for freight keywords.

    Args:
        description: Line item description string.

    Returns:
        True if freight line, False otherwise.
    """
    _FREIGHT_KEYWORDS = ["freight", "shipping charge", "delivery charge", "courier fee"]

    if not description or not isinstance(description, str):
        return False

    lower = description.lower()
    return any(kw in lower for kw in _FREIGHT_KEYWORDS)


class DataCleaner:
    """Cleans raw ingested DataFrames: whitespace, null normalisation, and flag detection."""

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all cleaning, type coercion, and flag detection to a raw DataFrame.

        Steps:
        1. Strip leading/trailing whitespace from all object/string columns.
        2. Normalise null representations to np.nan.
        3. Detect document_type (CREDIT_NOTE / INVOICE).
        4. Parse payment_terms_days from raw_payment_terms.
        5. Set boolean flags: is_credit_note, is_intercompany, is_tax_line, is_freight_line.

        Args:
            df: Raw input DataFrame (canonical column names expected).

        Returns:
            Cleaned DataFrame with additional columns added.
        """
        df = df.copy()

        # 1. Strip whitespace from all string/object columns
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].apply(
                lambda v: v.strip() if isinstance(v, str) else v
            )

        # 2. Normalise null representations
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].apply(
                lambda v: np.nan if (isinstance(v, str) and v in _NULL_VALUES) else v
            )

        # 3. Detect document type
        df["document_type"] = df.apply(detect_document_type, axis=1)

        # 4. Parse payment terms
        raw_terms_col = "raw_payment_terms" if "raw_payment_terms" in df.columns else None
        if raw_terms_col:
            df["payment_terms_days"] = df[raw_terms_col].apply(
                lambda v: parse_payment_terms(v if isinstance(v, str) else None)
            )
        else:
            df["payment_terms_days"] = None

        # 5. Boolean flags
        df["is_credit_note"] = df["document_type"] == "CREDIT_NOTE"

        supplier_col = "raw_supplier_name" if "raw_supplier_name" in df.columns else None
        if supplier_col:
            df["is_intercompany"] = df[supplier_col].apply(
                lambda v: detect_intercompany(v if isinstance(v, str) else "")
            )
        else:
            df["is_intercompany"] = False

        desc_col = "raw_line_description" if "raw_line_description" in df.columns else None
        gl_col = "gl_account" if "gl_account" in df.columns else None

        if desc_col:
            df["is_tax_line"] = df.apply(
                lambda row: detect_tax_line(
                    row[desc_col] if isinstance(row.get(desc_col), str) else "",
                    row[gl_col] if gl_col and isinstance(row.get(gl_col), str) else None,
                ),
                axis=1,
            )
            df["is_freight_line"] = df[desc_col].apply(
                lambda v: detect_freight_line(v if isinstance(v, str) else "")
            )
        else:
            df["is_tax_line"] = False
            df["is_freight_line"] = False

        return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    # Build a small sample DataFrame that exercises all detection paths.
    sample_data = {
        "invoice_number": ["INV-001", "CN-2024-001", "INV-002", "INV-003", "INV-004"],
        "original_amount": [1250.00, -500.00, 300.00, 0.00, 850.00],
        "raw_supplier_name": [
            "Acme Pty Ltd",
            "INTERCOMPANY - LEGAL",
            "  Sodexo Australia  ",
            "IC-AU-FINANCE",
            "DHL Express",
        ],
        "raw_line_description": [
            "Office supplies",
            "Legal services adjustment",
            "Catering services",
            "GST adjustment",
            "Freight and delivery charge",
        ],
        "gl_account": ["6420100", "2100100", "6500200", "2100100", "7100100"],
        "raw_payment_terms": ["Net 30", "net30", "30 days", "N/A", "NET 45"],
    }

    df_raw = pd.DataFrame(sample_data)

    print("=== BEFORE CLEANING ===")
    print(df_raw[["invoice_number", "raw_supplier_name", "raw_payment_terms"]].to_string())
    print()

    cleaner = DataCleaner()
    df_clean = cleaner.clean(df_raw)

    print("=== AFTER CLEANING ===")
    key_cols = [
        "invoice_number",
        "raw_supplier_name",
        "document_type",
        "payment_terms_days",
        "is_credit_note",
        "is_intercompany",
        "is_tax_line",
        "is_freight_line",
    ]
    print(df_clean[key_cols].to_string())
