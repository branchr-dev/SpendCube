"""SpendCube synthetic test data generator."""

from __future__ import annotations

import os
import sys

# Remove this script's directory from sys.path so that src/utils/logging.py
# does not shadow the standard library logging module.
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir in sys.path:
    sys.path.remove(_script_dir)

import argparse
import random
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from faker import Faker


# ---------------------------------------------------------------------------
# GL code ranges by category
# ---------------------------------------------------------------------------

GL_RANGES = [
    (6420000, 6429999, "Office"),
    (6510000, 6519999, "Facilities"),
    (6300000, 6309999, "Logistics"),
    (6440000, 6449999, "IT"),
]

# ---------------------------------------------------------------------------
# Legal suffix variants for duplicate supplier generation
# ---------------------------------------------------------------------------

LEGAL_SUFFIX_VARIANTS = [
    ["Pty Ltd", "PTY LIMITED", "P/L", "Pty. Ltd.", "PTY LTD"],
    ["Ltd", "LIMITED", "LTD"],
    ["Inc", "INC", "Incorporated", "INCORPORATED"],
    ["Corp", "CORP", "Corporation", "CORPORATION"],
    ["Pty Ltd", "P/L", "Aust P/L", "Australia Pty Ltd", "AUSTRALIA"],
]

DEPARTMENTS = [
    "LEGAL", "FINANCE", "HR", "MARKETING", "IT", "OPERATIONS",
    "PROCUREMENT", "LOGISTICS", "ENGINEERING", "COMPLIANCE",
]

CURRENCIES = ["AUD", "USD", "EUR", "GBP", "JPY", "NZD", "SGD", "CAD"]
CURRENCY_WEIGHTS = [0.90, 0.05, 0.03, 0.005, 0.005, 0.003, 0.004, 0.003]

PAY_TERMS_VARIANTS = {
    "Net 14": ["Net 14", "NET14", "N14", "14 days"],
    "Net 30": ["Net 30", "NET30", "N30", "30 days", "net-30"],
    "Net 45": ["Net 45", "NET45", "N45", "45 days"],
    "Net 60": ["Net 60", "NET60", "N60", "60 days"],
    "Net 7":  ["Net 7",  "NET7",  "N7",  "7 days"],
    "EOM":    ["EOM", "End of Month", "end of month"],
}

BUSINESS_UNITS = ["Corporate", "Operations", "Mining", "Energy", "Finance", "Technology", "Retail"]
SITES = ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Darwin", "Canberra"]

LINE_DESCS = [
    "Professional services", "Office supplies", "IT equipment", "Catering services",
    "Freight charges", "Consulting fees", "Maintenance services", "Software licences",
    "Facility management", "Logistics - domestic", "IT support", "Travel expenses",
    "Marketing materials", "Legal services", "Training services", "Equipment hire",
    "Cleaning services", "Security services", "Telecommunications", "Cloud services",
    "Printing services", "Office furniture", "Staff catering", "Conference facilities",
    "Engineering services", "Data services", "Subscription - annual", "Courier services",
]


def _make_date_string(d: date, messiness: float, rng: random.Random) -> str:
    """Return a date string in a format driven by messiness level."""
    if messiness == 0.0:
        return d.strftime("%Y-%m-%d")

    formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"]
    if messiness < 0.5:
        # Bias toward ISO
        weights = [1 - messiness, messiness * 0.6, messiness * 0.4]
    else:
        weights = [0.33, 0.34, 0.33]

    fmt = rng.choices(formats, weights=weights, k=1)[0]
    return d.strftime(fmt)


def _make_gl_code(messiness: float, rng: random.Random) -> str:
    """Pick a GL code from realistic ranges, optionally stripping leading zero."""
    gl_min, gl_max, _ = rng.choice(GL_RANGES)
    code = rng.randint(gl_min, gl_max)
    code_str = str(code)
    # At messiness > 0.3, strip leading digit occasionally (simulates export artifact)
    if messiness > 0.3 and rng.random() < (messiness - 0.3) * 0.5:
        code_str = code_str[1:]  # strip first digit (leading zero effect)
    return code_str


def _make_pay_terms(messiness: float, rng: random.Random) -> str:
    """Return a payment terms string, possibly in a variant form."""
    base = rng.choice(list(PAY_TERMS_VARIANTS.keys()))
    variants = PAY_TERMS_VARIANTS[base]
    if messiness == 0.0:
        return base
    return rng.choice(variants)


def _make_vendor_num(index: int) -> str:
    return f"V-{index + 1:04d}"


def _make_po_num(rng: random.Random) -> str:
    return f"PO-{rng.randint(10000, 99999)}"


def _make_cost_centre(rng: random.Random, messiness: float) -> str:
    dept = rng.choice(["MKT", "OPS", "LEG", "FIN", "IT", "LOG", "MIN", "ENG"])
    num = rng.randint(1, 5)
    if messiness > 0.0 and rng.random() < messiness * 0.3:
        # Variant: drop "CC-" prefix
        return f"{dept}{num:02d}"
    return f"CC-{dept}-{num:02d}"


def _apply_missing(value: str, rate: float, rng: random.Random) -> str:
    """Return empty string at the given rate."""
    if rng.random() < rate:
        return ""
    return value


def _capitalise_variant(name: str, messiness: float, rng: random.Random) -> str:
    """Apply capitalisation variants driven by messiness."""
    if messiness == 0.0:
        return name
    r = rng.random()
    if r < messiness * 0.2:
        return name.upper()
    if r < messiness * 0.35:
        return name.lower()
    return name


def generate_test_data(
    rows: int = 10000,
    suppliers: int = 500,
    categories: int = 50,
    messiness: float = 0.3,
    duplicate_supplier_rate: float = 0.15,
    credit_note_rate: float = 0.05,
    intercompany_rate: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a realistic messy procurement CSV as a DataFrame.

    Parameters
    ----------
    rows:                   Total number of invoice rows to generate.
    suppliers:              Number of distinct base supplier names.
    categories:             Not used directly (reserved for future GL diversity).
    messiness:              0.0 = clean; 1.0 = maximally messy.
    duplicate_supplier_rate: Fraction of rows using a name variant instead of base.
    credit_note_rate:       Fraction of rows that are credit notes (negative AMT).
    intercompany_rate:      Fraction of rows with INTERCOMPANY vendor.
    seed:                   Random seed for reproducibility.
    """
    rng = random.Random(seed)
    fake = Faker("en_AU")
    fake.seed_instance(seed)

    # ------------------------------------------------------------------
    # 1. Build supplier pool
    # ------------------------------------------------------------------
    base_suppliers: list[str] = []
    supplier_nums: dict[str, str] = {}
    for i in range(suppliers):
        name = fake.company()
        # Strip any trailing suffix that faker adds — we'll manage these
        base_suppliers.append(name)
        supplier_nums[name] = _make_vendor_num(i)

    # Suffix variant pool (for duplicate supplier names)
    suffix_pool = LEGAL_SUFFIX_VARIANTS[0]  # default

    def _variant_name(base: str) -> str:
        """Create a variant of a supplier name by swapping legal suffix."""
        # Try to swap last word if it looks like a suffix
        words = base.split()
        suffix_variants = rng.choice(LEGAL_SUFFIX_VARIANTS)
        new_suffix = rng.choice(suffix_variants)
        # Capitalise the base part
        cap = _capitalise_variant(" ".join(words[:-1]) if len(words) > 1 else base, messiness, rng)
        return f"{cap} {new_suffix}"

    # ------------------------------------------------------------------
    # 2. Date range
    # ------------------------------------------------------------------
    start_date = date(2023, 1, 1)
    end_date = date(2024, 12, 31)
    date_range_days = (end_date - start_date).days

    # ------------------------------------------------------------------
    # 3. Missing rates (driven by messiness)
    # ------------------------------------------------------------------
    po_missing_rate    = messiness * 0.30 / 0.3 * 0.3 if messiness <= 1.0 else 0.30  # ~30% at m=0.3
    cost_ctr_missing   = messiness * 0.20 / 0.3 * 0.3 if messiness <= 1.0 else 0.20  # ~20% at m=0.3
    pay_terms_missing  = messiness * 0.10 / 0.3 * 0.3 if messiness <= 1.0 else 0.10  # ~10% at m=0.3
    ccy_missing_rate   = messiness * 0.10 / 0.3 * 0.3 if messiness <= 1.0 else 0.10  # ~10% at m=0.3

    # Simplify: linear scaling
    po_missing_rate   = min(messiness * 1.0, 0.30)
    cost_ctr_missing  = min(messiness * 0.667, 0.20)
    pay_terms_missing = min(messiness * 0.333, 0.10)
    ccy_missing_rate  = min(messiness * 0.333, 0.10)

    # ------------------------------------------------------------------
    # 4. Generate rows
    # ------------------------------------------------------------------
    records = []
    inv_counter = 1

    for i in range(rows):
        # Determine row type
        is_credit_note = rng.random() < credit_note_rate
        is_intercompany = rng.random() < intercompany_rate

        # --- Vendor ---
        if is_intercompany:
            dept = rng.choice(DEPARTMENTS)
            vendor_name = f"INTERCOMPANY - {dept}"
            vendor_num = "V-INTCO"
        else:
            base = rng.choice(base_suppliers)
            vendor_num = supplier_nums[base]
            if rng.random() < duplicate_supplier_rate:
                vendor_name = _variant_name(base)
            else:
                vendor_name = _capitalise_variant(base, messiness * 0.3, rng)

        # --- Invoice number ---
        if is_credit_note:
            inv_no = f"CN-{rng.randint(2023, 2024)}-{inv_counter:04d}"
        else:
            inv_no = f"INV-{rng.randint(2023, 2024)}-{inv_counter:04d}"
        inv_counter += 1

        # --- Date ---
        inv_date_obj = start_date + timedelta(days=rng.randint(0, date_range_days))
        inv_date_str = _make_date_string(inv_date_obj, messiness, rng)

        # --- Line description ---
        line_desc = rng.choice(LINE_DESCS)
        if is_credit_note:
            line_desc = "Credit " + line_desc.lower()

        # --- Amount ---
        if is_credit_note:
            amt = -round(rng.uniform(50, 5000), 2)
        else:
            amt = round(rng.uniform(100, 50000), 2)

        # --- Currency ---
        ccy_weights_normalised = [w / sum(CURRENCY_WEIGHTS) for w in CURRENCY_WEIGHTS]
        ccy = rng.choices(CURRENCIES, weights=ccy_weights_normalised, k=1)[0]
        ccy_val = _apply_missing(ccy, ccy_missing_rate if not is_intercompany else 0, rng)
        if not ccy_val and not is_intercompany:
            ccy_val = ""  # genuinely missing
        elif not ccy_val:
            ccy_val = "AUD"

        # --- GL Code ---
        gl_code = _make_gl_code(messiness, rng)

        # --- Cost Centre ---
        cost_ctr = _make_cost_centre(rng, messiness)
        cost_ctr = _apply_missing(cost_ctr, cost_ctr_missing, rng)

        # --- Payment Terms ---
        pay_terms = _make_pay_terms(messiness, rng)
        pay_terms = _apply_missing(pay_terms, pay_terms_missing, rng)

        # --- PO Number ---
        po_num = _make_po_num(rng)
        if is_credit_note:
            po_num = ""  # credit notes rarely have PO
        else:
            po_num = _apply_missing(po_num, po_missing_rate, rng)

        # --- Business Unit / Site ---
        bus_unit = rng.choice(BUSINESS_UNITS)
        site = rng.choice(SITES)

        records.append({
            "VENDOR_NAME": vendor_name,
            "VENDOR_NUM": vendor_num,
            "INV_NO": inv_no,
            "INV_DATE": inv_date_str,
            "LINE_DESC": line_desc,
            "AMT": amt,
            "CCY": ccy_val,
            "GL_CODE": gl_code,
            "COST_CTR": cost_ctr,
            "PAY_TERMS": pay_terms,
            "PO_NUM": po_num,
            "BUS_UNIT": bus_unit,
            "SITE": site,
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="SpendCube synthetic test data generator")
    parser.add_argument("--rows",                   type=int,   default=10000, help="Number of rows")
    parser.add_argument("--suppliers",              type=int,   default=500,   help="Number of distinct suppliers")
    parser.add_argument("--categories",             type=int,   default=50,    help="Category diversity (reserved)")
    parser.add_argument("--messiness",              type=float, default=0.3,   help="Messiness level 0.0-1.0")
    parser.add_argument("--duplicate_supplier_rate",type=float, default=0.15,  help="Fraction with supplier name variants")
    parser.add_argument("--credit_note_rate",       type=float, default=0.05,  help="Fraction that are credit notes")
    parser.add_argument("--intercompany_rate",      type=float, default=0.03,  help="Fraction that are intercompany")
    parser.add_argument("--output",                 type=str,   default="data/input/test_data.csv", help="Output CSV path")
    parser.add_argument("--seed",                   type=int,   default=42,    help="Random seed")
    args = parser.parse_args()

    df = generate_test_data(
        rows=args.rows,
        suppliers=args.suppliers,
        categories=args.categories,
        messiness=args.messiness,
        duplicate_supplier_rate=args.duplicate_supplier_rate,
        credit_note_rate=args.credit_note_rate,
        intercompany_rate=args.intercompany_rate,
        seed=args.seed,
    )

    df.to_csv(args.output, index=False)
    print(f"Generated {len(df)} rows → {args.output}")


if __name__ == "__main__":
    main()
