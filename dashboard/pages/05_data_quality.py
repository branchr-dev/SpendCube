"""SpendCube data quality dashboard page."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.app import load_cube_data, load_quality_scorecard

_SCORECARD_PATH = Path("data/output/quality_scorecard.json")

# Status normalisation: diagnostics uses two naming schemes
_GOOD_STATUSES = {"GREEN", "INFO"}
_AMBER_STATUSES = {"AMBER", "WARN"}
_BAD_STATUSES = {"RED", "ALERT"}

_STATUS_SCORE = {
    **{s: 100 for s in _GOOD_STATUSES},
    **{s: 50 for s in _AMBER_STATUSES},
    **{s: 0 for s in _BAD_STATUSES},
}

_CHECK_DISPLAY_NAMES = {
    "missing_supplier_name": "Missing Supplier Name",
    "uncategorised_spend": "Uncategorised Spend",
    "unresolved_suppliers": "Unresolved Suppliers",
    "missing_payment_terms": "Missing Payment Terms",
    "duplicate_invoice_risk": "Duplicate Invoice Risk",
    "negative_reversal_lines": "Negative / Reversal Lines",
    "weak_descriptions": "Weak Descriptions",
    "missing_contract_linkage": "Missing Contract Linkage",
    "missing_bu_cost_centre": "Missing BU / Cost Centre",
}

_WEAK_DESCRIPTION_TERMS = frozenset(
    {"misc", "miscellaneous", "services", "payment", "invoice", "charges"}
)


def _compute_overall_score(scorecard: dict) -> int:
    if not scorecard:
        return 0
    total = sum(_STATUS_SCORE.get(r.get("status", "RED"), 0) for r in scorecard.values())
    return round(total / len(scorecard))


def _status_display(status: str) -> str:
    mapping = {
        "GREEN": "Green",
        "INFO": "Green",
        "AMBER": "Amber",
        "WARN": "Amber",
        "RED": "Red",
        "ALERT": "Red",
    }
    return mapping.get(status, status)


def _colour_status(val: str) -> str:
    if val == "Green":
        return "background-color: #d4edda; color: #155724; font-weight: bold"
    if val == "Amber":
        return "background-color: #fff3cd; color: #856404; font-weight: bold"
    if val == "Red":
        return "background-color: #f8d7da; color: #721c24; font-weight: bold"
    return ""


def _build_scorecard_df(scorecard: dict) -> pd.DataFrame:
    rows = []
    for key, r in scorecard.items():
        rows.append(
            {
                "Check": _CHECK_DISPLAY_NAMES.get(key, key.replace("_", " ").title()),
                "Value": r.get("value", ""),
                "% / Amount": f"{r.get('pct', 0):.1f}%",
                "Status": _status_display(r.get("status", "")),
                "Green Threshold": f"< {r.get('green_threshold', '')}%",
                "Amber Threshold": f"< {r.get('amber_threshold', '')}%",
                "Remediation": r.get("remediation", ""),
            }
        )
    return pd.DataFrame(rows)


def _get_problematic_rows(check_key: str, txn: pd.DataFrame) -> pd.DataFrame:
    """Return the subset of transactions relevant to the failing check."""
    if txn.empty:
        return pd.DataFrame()

    if check_key == "missing_supplier_name":
        if "raw_supplier_name" not in txn.columns:
            return pd.DataFrame()
        return txn[txn["raw_supplier_name"].isna()]

    if check_key == "uncategorised_spend":
        col = "category_l1" if "category_l1" in txn.columns else "internal_category_l1"
        if col not in txn.columns:
            return pd.DataFrame()
        return txn[txn[col].isna()]

    if check_key == "unresolved_suppliers":
        if "canonical_supplier_id" not in txn.columns:
            return pd.DataFrame()
        mask = txn["canonical_supplier_id"].isna()
        if "raw_supplier_name" in txn.columns:
            mask = mask & txn["raw_supplier_name"].notna()
        return txn[mask]

    if check_key == "missing_payment_terms":
        if "payment_terms_days" not in txn.columns:
            return pd.DataFrame()
        return txn[txn["payment_terms_days"].isna()]

    if check_key == "duplicate_invoice_risk":
        needed = {"invoice_number", "base_amount", "transaction_id"}
        if not needed.issubset(txn.columns):
            return pd.DataFrame()
        counts = txn.groupby(["invoice_number", "base_amount"])["transaction_id"].transform("count")
        return txn[counts > 1].sort_values(["invoice_number", "base_amount"])

    if check_key == "negative_reversal_lines":
        if "base_amount" not in txn.columns:
            return pd.DataFrame()
        return txn[txn["base_amount"] < 0]

    if check_key == "weak_descriptions":
        if "raw_line_description" not in txn.columns:
            return pd.DataFrame()
        col = txn["raw_line_description"]
        is_null = col.isna()
        is_generic = col.str.lower().isin(_WEAK_DESCRIPTION_TERMS).fillna(False)
        is_short = (~is_null & ~is_generic) & (col.str.split().str.len().fillna(0) < 5)
        return txn[is_null | is_generic | is_short]

    if check_key == "missing_contract_linkage":
        po_null = txn["po_number"].isna() if "po_number" in txn.columns else pd.Series(True, index=txn.index)
        contract_null = txn["contract_id"].isna() if "contract_id" in txn.columns else pd.Series(True, index=txn.index)
        return txn[po_null & contract_null]

    if check_key == "missing_bu_cost_centre":
        bu_null = txn["business_unit"].isna() if "business_unit" in txn.columns else pd.Series(True, index=txn.index)
        cc_null = txn["cost_centre"].isna() if "cost_centre" in txn.columns else pd.Series(True, index=txn.index)
        return txn[bu_null & cc_null]

    return pd.DataFrame()


def _display_columns_for_check(check_key: str, txn: pd.DataFrame) -> list[str]:
    """Return a concise list of columns to display in the drill-down table."""
    base_cols = [c for c in ["transaction_id", "invoice_number", "invoice_date", "raw_supplier_name", "base_amount"] if c in txn.columns]

    extra: dict[str, list[str]] = {
        "missing_supplier_name": ["raw_supplier_id", "gl_account"],
        "uncategorised_spend": ["category_l1", "category_confidence", "category_method", "raw_line_description"],
        "unresolved_suppliers": ["canonical_supplier_id", "canonical_supplier_name", "canonical_supplier_confidence"],
        "missing_payment_terms": ["raw_payment_terms", "payment_terms_days"],
        "duplicate_invoice_risk": ["invoice_number", "base_amount", "original_currency"],
        "negative_reversal_lines": ["base_amount", "raw_line_description", "gl_account"],
        "weak_descriptions": ["raw_line_description", "category_l1"],
        "missing_contract_linkage": ["po_number", "raw_supplier_name", "category_l1"],
        "missing_bu_cost_centre": ["business_unit", "cost_centre", "gl_account"],
    }
    additional = [c for c in extra.get(check_key, []) if c in txn.columns and c not in base_cols]
    return base_cols + additional


def _drilldown_section(check_key: str, check_data: dict, txn: pd.DataFrame) -> None:
    status = check_data.get("status", "")
    if status in _GOOD_STATUSES:
        return

    display_name = _CHECK_DISPLAY_NAMES.get(check_key, check_key.replace("_", " ").title())
    pct = check_data.get("pct", 0)
    value = check_data.get("value", "")

    label = f"{'🔴' if status in _BAD_STATUSES else '🟡'} {display_name} — {pct:.1f}% ({value})"

    with st.expander(label):
        st.caption(check_data.get("description", ""))
        st.markdown(f"**Remediation:** {check_data.get('remediation', '')}")

        if txn.empty:
            st.info("No transaction data available for drill-down.")
            return

        problem_rows = _get_problematic_rows(check_key, txn)
        if problem_rows.empty:
            st.info("No problematic rows found (data may have changed since scorecard was generated).")
            return

        display_cols = _display_columns_for_check(check_key, problem_rows)
        st.dataframe(
            problem_rows[display_cols].head(100).reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
        )
        if len(problem_rows) > 100:
            st.caption(f"Showing first 100 of {len(problem_rows):,} rows.")


def main() -> None:
    st.title("Data Quality")

    # --- Refresh button ---
    if st.button("Re-run diagnostics"):
        st.cache_data.clear()
        st.rerun()

    scorecard = load_quality_scorecard()
    cube = load_cube_data()
    txn = cube.get("transactions", pd.DataFrame()) if cube else pd.DataFrame()

    if not scorecard:
        st.warning(
            "No quality scorecard found. Run `make build-cube` to generate diagnostics, "
            "or ensure `data/output/quality_scorecard.json` exists."
        )
        return

    # --- Overall score metric ---
    overall_score = _compute_overall_score(scorecard)
    st.metric("Overall Data Quality", f"{overall_score}/100")

    st.markdown("---")

    # --- Scorecard table ---
    st.subheader("Diagnostic Scorecard")

    scorecard_df = _build_scorecard_df(scorecard)
    styled = scorecard_df.style.applymap(_colour_status, subset=["Status"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.markdown("---")

    # --- Export button ---
    if _SCORECARD_PATH.exists():
        with open(_SCORECARD_PATH, "rb") as f:
            scorecard_bytes = f.read()
        st.download_button(
            label="Download quality_scorecard.json",
            data=scorecard_bytes,
            file_name="quality_scorecard.json",
            mime="application/json",
        )
    else:
        scorecard_bytes = json.dumps(scorecard, indent=2).encode()
        st.download_button(
            label="Download quality_scorecard.json",
            data=scorecard_bytes,
            file_name="quality_scorecard.json",
            mime="application/json",
        )

    st.markdown("---")

    # --- Drill-down sections for non-GREEN checks ---
    st.subheader("Drill-Down: Issues Requiring Attention")

    has_issues = any(r.get("status", "") not in _GOOD_STATUSES for r in scorecard.values())
    if not has_issues:
        st.success("All checks are GREEN — no issues requiring attention.")
        return

    for check_key, check_data in scorecard.items():
        _drilldown_section(check_key, check_data, txn)


if __name__ == "__main__":
    main()
