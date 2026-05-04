"""SpendCube rule-based recommendation generation.

All rules are deterministic — no LLM calls. Rules derive recommendations
from cube DataFrames and pre-computed scalar metrics.

Recommendation dict schema:
    type (str): recommendation type constant
    context (str): category name or supplier name
    evidence (str): human-readable supporting evidence
    estimated_impact_aud (float): estimated annual saving in AUD
    confidence (str): 'HIGH' | 'MEDIUM' | 'LOW'
    action (str): recommended procurement action
    lever (str): savings lever category
"""

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
from src.recommendations.savings_rates import SavingsRates
from src.utils.logging import get_logger_from_config

# ---------------------------------------------------------------------------
# Recommendation type constants
# ---------------------------------------------------------------------------

SUPPLIER_CONSOLIDATION = "SUPPLIER_CONSOLIDATION"
PAYMENT_TERM_EXTENSION = "PAYMENT_TERM_EXTENSION"
TAIL_SPEND_RATIONALISATION = "TAIL_SPEND_RATIONALISATION"
CONTRACT_COMPLIANCE = "CONTRACT_COMPLIANCE"
COMPETITIVE_TENDER = "COMPETITIVE_TENDER"
CONTRACT_COVERAGE_GAP = "CONTRACT_COVERAGE_GAP"
SPEND_CONCENTRATION_RISK = "SPEND_CONCENTRATION_RISK"
EARLY_PAYMENT_DISCOUNT_CAPTURE = "EARLY_PAYMENT_DISCOUNT_CAPTURE"


class RecommendationRules:
    """Rule-based recommendation generator from spend cube metrics.

    Args:
        cube: Dict returned by SpendCubeBuilder.build().
        metrics: Dict returned by CubeMetrics.compute_all().
        config: SpendCube Config object.
    """

    def __init__(self, cube: dict[str, pd.DataFrame], metrics: dict, config):
        self.cube = cube
        self.metrics = metrics
        self.config = config
        self.logger = get_logger_from_config(__name__, config)
        self._rec_cfg = config.recommendations
        self._rates = SavingsRates()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_all(self) -> list[dict]:
        """Run all rule methods and return recommendations sorted by impact descending."""
        recommendations: list[dict] = []

        rule_methods = [
            self.rule_supplier_consolidation,
            self.rule_payment_term_extension,
            self.rule_tail_spend_rationalisation,
            self.rule_maverick_spend,
            self.rule_competitive_tender,
            self.rule_contract_coverage_gap,
            self.rule_spend_concentration_risk,
            self.rule_early_payment_discount_capture,
        ]

        for rule_method in rule_methods:
            try:
                recs = rule_method()
                recommendations.extend(recs)
                self.logger.debug(
                    "%s generated %d recommendation(s)",
                    rule_method.__name__,
                    len(recs),
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Rule %s failed: %s", rule_method.__name__, exc)

        recommendations.sort(
            key=lambda r: r.get("estimated_impact_aud", 0.0), reverse=True
        )
        return recommendations

    # ------------------------------------------------------------------
    # Rule methods
    # ------------------------------------------------------------------

    def rule_supplier_consolidation(self) -> list[dict]:
        """SUPPLIER_CONSOLIDATION — L2 categories with too many suppliers.

        Fires when a category has more suppliers than the consolidation_threshold.
        estimated_impact = category_spend * consolidation_saving_pct.
        """
        txn = self.cube.get("transactions", pd.DataFrame())
        if txn.empty:
            return []
        required = {"category_l2", "canonical_supplier_id", "base_amount"}
        if not required.issubset(txn.columns):
            return []

        cfg = self._rec_cfg
        addr = self._addressable(txn)
        if addr.empty:
            return []

        addr_cat = addr.dropna(subset=["category_l2"])
        if addr_cat.empty:
            return []

        recs: list[dict] = []
        for category, group in addr_cat.groupby("category_l2"):
            n_suppliers = int(group["canonical_supplier_id"].nunique())
            if n_suppliers <= cfg.consolidation_threshold:
                continue

            category_spend = float(group["base_amount"].sum())
            if category_spend <= 0:
                continue

            supplier_spend = group.groupby("canonical_supplier_id")["base_amount"].sum()
            top_pct = round(float(supplier_spend.max() / category_spend) * 100, 1)

            rates_row = self._rates.get(SUPPLIER_CONSOLIDATION, str(category))
            saving_pct = rates_row["saving_pct"]
            addressability_pct = rates_row["addressability_pct"]
            addressable_baseline = category_spend * addressability_pct
            estimated_impact = addressable_baseline * saving_pct

            recs.append({
                "type": SUPPLIER_CONSOLIDATION,
                "context": str(category),
                "evidence": (
                    f"{n_suppliers} suppliers in {category}, "
                    f"top supplier = {top_pct}%; "
                    f"{addressability_pct:.0%} addressable"
                ),
                "estimated_impact_aud": round(estimated_impact, 2),
                "confidence": "HIGH",
                "action": (
                    f"Consolidate {n_suppliers} suppliers in {category} "
                    f"to 2-3 preferred vendors"
                ),
                "lever": "Supplier Consolidation",
                "baseline_spend": round(category_spend, 2),
                "addressability_pct": addressability_pct,
                "saving_pct": saving_pct,
                "addressable_baseline": round(addressable_baseline, 2),
                "category_l1": str(category),
            })

        return recs

    def rule_payment_term_extension(self) -> list[dict]:
        """PAYMENT_TERM_EXTENSION — Top-50 suppliers with terms below target.

        estimated_impact = (target - current) / 365 * annual_spend * wacc.
        Only fires when estimated_impact > min_wc_opportunity.
        """
        txn = self.cube.get("transactions", pd.DataFrame())
        if txn.empty:
            return []
        required = {"canonical_supplier_id", "payment_terms_days", "base_amount"}
        if not required.issubset(txn.columns):
            return []

        cfg = self._rec_cfg
        addr = self._addressable(txn)
        if addr.empty:
            return []

        has_terms = addr.dropna(subset=["payment_terms_days", "canonical_supplier_id"])
        if has_terms.empty:
            return []

        agg_kwargs: dict = {
            "annual_spend": ("base_amount", "sum"),
            "weighted_avg_terms": ("payment_terms_days", "mean"),
        }
        if "canonical_supplier_name" in has_terms.columns:
            agg_kwargs["supplier_name"] = ("canonical_supplier_name", "first")

        supplier_stats = (
            has_terms.groupby("canonical_supplier_id")
            .agg(**agg_kwargs)
            .reset_index()
            .sort_values("annual_spend", ascending=False)
            .head(50)
        )

        target = float(cfg.target_payment_days)
        rates_row = self._rates.get(PAYMENT_TERM_EXTENSION)
        addressability_pct = rates_row["addressability_pct"]
        recs: list[dict] = []

        for _, row in supplier_stats.iterrows():
            current = float(row["weighted_avg_terms"])
            if current >= target:
                continue

            annual_spend = float(row["annual_spend"])
            annual_spend_addressable = annual_spend * addressability_pct
            estimated_impact = (target - current) / 365.0 * annual_spend_addressable * cfg.wacc

            if estimated_impact <= cfg.min_wc_opportunity:
                continue

            supplier_name = str(
                row.get("supplier_name", row["canonical_supplier_id"])
            )

            recs.append({
                "type": PAYMENT_TERM_EXTENSION,
                "context": supplier_name,
                "evidence": (
                    f"Current: {current:.0f} days, Target: {target:.0f} days"
                ),
                "estimated_impact_aud": round(estimated_impact, 2),
                "confidence": "HIGH",
                "action": (
                    f"Negotiate payment terms extension from {current:.0f} to "
                    f"{target:.0f} days with {supplier_name}"
                ),
                "lever": "Working Capital",
                "baseline_spend": round(annual_spend, 2),
                "addressability_pct": addressability_pct,
                "saving_pct": None,
                "addressable_baseline": round(annual_spend_addressable, 2),
            })

        return recs

    def rule_tail_spend_rationalisation(self) -> list[dict]:
        """TAIL_SPEND_RATIONALISATION — Alert when tail spend percentage is high.

        estimated_impact = tail_spend_amount * 0.10.
        """
        tail_spend_pct = float(self.metrics.get("tail_spend_pct", 0.0))
        tail_supplier_count = int(self.metrics.get("tail_supplier_count", 0))

        if tail_spend_pct <= self._rec_cfg.tail_spend_alert_pct:
            return []

        total_spend = float(self.metrics.get("total_spend", 0.0))
        tail_spend_amount = total_spend * tail_spend_pct
        rates = self._rates.get(TAIL_SPEND_RATIONALISATION)
        addressability_pct = rates["addressability_pct"]
        addressable_baseline = tail_spend_amount * addressability_pct
        estimated_impact = addressable_baseline * rates["saving_pct"]
        pct_str = f"{tail_spend_pct:.1%}"

        return [{
            "type": TAIL_SPEND_RATIONALISATION,
            "context": "Portfolio",
            "evidence": f"{tail_supplier_count} tail suppliers, {pct_str} of spend",
            "estimated_impact_aud": round(estimated_impact, 2),
            "confidence": "MEDIUM",
            "action": (
                f"Rationalise {tail_supplier_count} tail suppliers — "
                "consolidate or eliminate low-value vendors"
            ),
            "lever": "Tail Spend Rationalisation",
            "baseline_spend": round(tail_spend_amount, 2),
            "addressability_pct": addressability_pct,
            "saving_pct": rates["saving_pct"],
            "addressable_baseline": round(addressable_baseline, 2),
        }]

    def rule_maverick_spend(self) -> list[dict]:
        """CONTRACT_COMPLIANCE — Alert when maverick spend percentage is high.

        estimated_impact = maverick_spend * 0.05.
        """
        maverick_spend_pct = float(self.metrics.get("maverick_spend_pct", 0.0))

        if maverick_spend_pct <= self._rec_cfg.maverick_alert_pct:
            return []

        total_spend = float(self.metrics.get("total_spend", 0.0))
        maverick_spend = total_spend * maverick_spend_pct
        rates = self._rates.get(CONTRACT_COMPLIANCE)
        addressability_pct = rates["addressability_pct"]
        addressable_baseline = maverick_spend * addressability_pct
        estimated_impact = addressable_baseline * rates["saving_pct"]
        pct_str = f"{maverick_spend_pct:.1%}"

        return [{
            "type": CONTRACT_COMPLIANCE,
            "context": "Portfolio",
            "evidence": (
                f"{pct_str} of spend is maverick (no PO and not on-contract)"
            ),
            "estimated_impact_aud": round(estimated_impact, 2),
            "confidence": "MEDIUM",
            "action": (
                "Enforce PO compliance and contract coverage "
                "for maverick spend categories"
            ),
            "lever": "Contract Compliance",
            "baseline_spend": round(maverick_spend, 2),
            "addressability_pct": addressability_pct,
            "saving_pct": rates["saving_pct"],
            "addressable_baseline": round(addressable_baseline, 2),
        }]

    def rule_competitive_tender(self) -> list[dict]:
        """COMPETITIVE_TENDER — Single-source L2 categories with significant spend.

        Fires when a category has exactly 1 supplier and spend > 50,000 AUD.
        estimated_impact = category_spend * 0.07.
        """
        txn = self.cube.get("transactions", pd.DataFrame())
        if txn.empty:
            return []
        required = {"category_l2", "canonical_supplier_id", "base_amount"}
        if not required.issubset(txn.columns):
            return []

        addr = self._addressable(txn)
        if addr.empty:
            return []

        addr_cat = addr.dropna(subset=["category_l2"])
        if addr_cat.empty:
            return []

        cfg = self._rec_cfg
        recs: list[dict] = []
        for category, group in addr_cat.groupby("category_l2"):
            n_suppliers = int(group["canonical_supplier_id"].nunique())
            if n_suppliers != 1:
                continue

            category_spend = float(group["base_amount"].sum())
            if category_spend <= cfg.competitive_tender_min_spend:
                continue

            rates_row = self._rates.get(COMPETITIVE_TENDER, str(category))
            saving_pct = rates_row["saving_pct"]
            addressability_pct = rates_row["addressability_pct"]
            addressable_baseline = category_spend * addressability_pct
            estimated_impact = addressable_baseline * saving_pct

            if "canonical_supplier_name" in group.columns:
                supplier_name = str(group["canonical_supplier_name"].dropna().iloc[0])
            else:
                supplier_name = str(group["canonical_supplier_id"].iloc[0])

            recs.append({
                "type": COMPETITIVE_TENDER,
                "context": str(category),
                "evidence": (
                    f"Single source: all {category} spend "
                    f"(${category_spend:,.0f}) with {supplier_name}; "
                    f"{addressability_pct:.0%} addressable"
                ),
                "estimated_impact_aud": round(estimated_impact, 2),
                "confidence": "HIGH",
                "action": (
                    f"Run competitive tender for {category} — "
                    f"currently single-sourced from {supplier_name}"
                ),
                "lever": "Competitive Sourcing",
                "baseline_spend": round(category_spend, 2),
                "addressability_pct": addressability_pct,
                "saving_pct": saving_pct,
                "addressable_baseline": round(addressable_baseline, 2),
                "category_l1": str(category),
            })

        return recs

    def rule_contract_coverage_gap(self) -> list[dict]:
        """CONTRACT_COVERAGE_GAP — L1 categories with low contract coverage.

        Fires when contract_coverage_pct < 0.50 and spend > 20,000 AUD.
        estimated_impact = unmanaged_spend * 0.05.
        When is_on_contract column is absent, coverage is assumed 0%.
        """
        txn = self.cube.get("transactions", pd.DataFrame())
        if txn.empty:
            return []
        if "category_l1" not in txn.columns or "base_amount" not in txn.columns:
            return []

        addr = self._addressable(txn)
        if addr.empty:
            return []

        addr_cat = addr.dropna(subset=["category_l1"])
        if addr_cat.empty:
            return []

        cfg = self._rec_cfg
        has_contract_col = "is_on_contract" in addr_cat.columns
        recs: list[dict] = []

        for category, group in addr_cat.groupby("category_l1"):
            total_spend = float(group["base_amount"].sum())
            if total_spend <= cfg.contract_coverage_gap_min_spend:
                continue

            if has_contract_col:
                on_contract = float(
                    group[group["is_on_contract"] == 1]["base_amount"].sum()
                )
                coverage_pct = on_contract / total_spend
            else:
                coverage_pct = 0.0  # No contract data → assume 0% coverage

            if coverage_pct >= 0.50:
                continue

            unmanaged_spend = total_spend * (1.0 - coverage_pct)
            rates_row = self._rates.get(CONTRACT_COVERAGE_GAP, str(category))
            saving_pct = rates_row["saving_pct"]
            addressability_pct = rates_row["addressability_pct"]
            addressable_baseline = unmanaged_spend * addressability_pct
            estimated_impact = addressable_baseline * saving_pct
            coverage_str = f"{coverage_pct:.0%}"

            recs.append({
                "type": CONTRACT_COVERAGE_GAP,
                "context": str(category),
                "evidence": (
                    f"{coverage_str} contract coverage in {category} "
                    f"(${total_spend:,.0f} total spend); "
                    f"{addressability_pct:.0%} of unmanaged addressable"
                ),
                "estimated_impact_aud": round(estimated_impact, 2),
                "confidence": "MEDIUM",
                "action": (
                    f"Establish framework agreements for {category} — "
                    "target 80% contract coverage"
                ),
                "lever": "Contract Coverage",
                "baseline_spend": round(total_spend, 2),
                "addressability_pct": addressability_pct,
                "saving_pct": saving_pct,
                "addressable_baseline": round(addressable_baseline, 2),
            })

        return recs

    def rule_spend_concentration_risk(self) -> list[dict]:
        """SPEND_CONCENTRATION_RISK — L2 categories dominated by a single supplier.

        Fires when n_suppliers > 1, top supplier > concentration_threshold_pct of
        category spend, and category spend > competitive_tender_min_spend.
        """
        txn = self.cube.get("transactions", pd.DataFrame())
        if txn.empty:
            return []
        required = {"category_l2", "canonical_supplier_id", "base_amount"}
        if not required.issubset(txn.columns):
            return []

        cfg = self._rec_cfg
        addr = self._addressable(txn)
        if addr.empty:
            return []

        addr_cat = addr.dropna(subset=["category_l2"])
        if addr_cat.empty:
            return []

        recs: list[dict] = []
        for category, group in addr_cat.groupby("category_l2"):
            n_suppliers = int(group["canonical_supplier_id"].nunique())
            if n_suppliers <= 1:
                continue

            category_spend = float(group["base_amount"].sum())
            if category_spend <= cfg.competitive_tender_min_spend:
                continue

            supplier_spend = group.groupby("canonical_supplier_id")["base_amount"].sum()
            top_supplier_pct = float(supplier_spend.max() / category_spend)
            if top_supplier_pct <= cfg.concentration_threshold_pct:
                continue

            top_supplier_id = supplier_spend.idxmax()
            if "canonical_supplier_name" in group.columns:
                name_series = group.loc[
                    group["canonical_supplier_id"] == top_supplier_id,
                    "canonical_supplier_name",
                ].dropna()
                top_supplier_name = str(name_series.iloc[0]) if len(name_series) > 0 else str(top_supplier_id)
            else:
                top_supplier_name = str(top_supplier_id)

            rates_row = self._rates.get(SPEND_CONCENTRATION_RISK, str(category))
            saving_pct = rates_row["saving_pct"]
            addressability_pct = rates_row["addressability_pct"]
            addressable_baseline = category_spend * addressability_pct
            estimated_impact = addressable_baseline * saving_pct

            recs.append({
                "type": SPEND_CONCENTRATION_RISK,
                "context": str(category),
                "evidence": (
                    f"{top_supplier_pct:.0%} of {category} spend concentrated in "
                    f"{top_supplier_name}; {n_suppliers} total suppliers; "
                    f"{addressability_pct:.0%} addressable"
                ),
                "estimated_impact_aud": round(estimated_impact, 2),
                "confidence": "MEDIUM",
                "action": (
                    f"Introduce second-source competition in {category} — "
                    f"{top_supplier_name} holds {top_supplier_pct:.0%} of spend"
                ),
                "lever": "Supply Risk Management",
                "baseline_spend": round(category_spend, 2),
                "addressability_pct": addressability_pct,
                "saving_pct": saving_pct,
                "addressable_baseline": round(addressable_baseline, 2),
            })

        return recs

    def rule_early_payment_discount_capture(self) -> list[dict]:
        """EARLY_PAYMENT_DISCOUNT_CAPTURE — Suppliers with uncaptured early payment discounts.

        annual_discount_opportunity = SUM(base_amount * discount_percent / 100).
        Only fires when addressable_opportunity > min_discount_opportunity.
        """
        txn = self.cube.get("transactions", pd.DataFrame())
        if txn.empty:
            return []
        required = {"has_early_payment_discount", "discount_percent", "base_amount", "canonical_supplier_id"}
        if not required.issubset(txn.columns):
            return []

        cfg = self._rec_cfg
        addr = self._addressable(txn)
        if addr.empty:
            return []

        eligible = addr[
            (addr["has_early_payment_discount"] == 1)
            & (addr["discount_percent"].notna())
            & (addr["discount_percent"] > 0)
        ]
        if eligible.empty:
            return []

        eligible = eligible.copy()
        eligible["disc_opp"] = eligible["base_amount"] * eligible["discount_percent"] / 100

        agg_kwargs: dict = {
            "annual_spend": ("base_amount", "sum"),
            "avg_discount_pct": ("discount_percent", "mean"),
            "disc_opp_sum": ("disc_opp", "sum"),
        }
        if "canonical_supplier_name" in eligible.columns:
            agg_kwargs["supplier_name"] = ("canonical_supplier_name", "first")

        supplier_stats = (
            eligible.groupby("canonical_supplier_id")
            .agg(**agg_kwargs)
            .reset_index()
        )

        rates_row = self._rates.get(EARLY_PAYMENT_DISCOUNT_CAPTURE)
        addressability_pct = rates_row["addressability_pct"]
        recs: list[dict] = []

        for _, row in supplier_stats.iterrows():
            disc_opp_sum = float(row["disc_opp_sum"])
            addressable_opportunity = disc_opp_sum * addressability_pct
            if addressable_opportunity <= cfg.min_discount_opportunity:
                continue

            annual_spend = float(row["annual_spend"])
            avg_discount_pct = float(row["avg_discount_pct"])
            supplier_name = str(row.get("supplier_name", row["canonical_supplier_id"]))

            recs.append({
                "type": EARLY_PAYMENT_DISCOUNT_CAPTURE,
                "context": supplier_name,
                "evidence": (
                    f"Avg discount: {avg_discount_pct:.1f}%; "
                    f"annual spend with discount terms: ${annual_spend:,.0f}; "
                    f"capturing discount saves ${addressable_opportunity:,.0f}/yr"
                ),
                "estimated_impact_aud": round(addressable_opportunity, 2),
                "confidence": "HIGH",
                "action": (
                    f"Capture early payment discount with {supplier_name} "
                    "— pay within discount window"
                ),
                "lever": "Early Payment Discount",
                "baseline_spend": round(annual_spend, 2),
                "addressability_pct": addressability_pct,
                "saving_pct": None,
                "addressable_baseline": round(disc_opp_sum, 2),
            })

        return recs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _addressable(self, txn: pd.DataFrame) -> pd.DataFrame:
        """Filter to addressable spend — exclude intercompany and tax lines."""
        if txn.empty:
            return txn
        mask = pd.Series(True, index=txn.index)
        if "is_intercompany" in txn.columns:
            mask &= txn["is_intercompany"] != 1
        if "is_tax_line" in txn.columns:
            mask &= txn["is_tax_line"] != 1
        return txn[mask].copy()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_recommendations(recommendations: list[dict]) -> None:
    if not recommendations:
        print("No recommendations generated.")
        return

    total_impact = sum(r.get("estimated_impact_aud", 0.0) for r in recommendations)

    print(f"\n{'=' * 80}")
    print(f"  SpendCube Recommendations  ({len(recommendations)} generated)")
    print(f"{'=' * 80}")
    print(f"  Total identified savings opportunity: ${total_impact:,.0f} AUD")
    print(f"{'=' * 80}\n")

    for i, rec in enumerate(recommendations, 1):
        impact = rec.get("estimated_impact_aud", 0.0)
        conf = rec.get("confidence", "N/A")
        print(f"#{i:02d}  [{rec.get('type', 'UNKNOWN')}]  {rec.get('context', '')}")
        print(f"     Impact:    ${impact:,.0f} AUD  |  Confidence: {conf}")
        print(f"     Evidence:  {rec.get('evidence', '')}")
        print(f"     Action:    {rec.get('action', '')}")
        print(f"     Lever:     {rec.get('lever', '')}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run rule-based spend recommendation engine"
    )
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config.yaml"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    db_engine = get_engine(args.db)

    from src.cube.builder import SpendCubeBuilder  # noqa: PLC0415
    from src.cube.metrics import CubeMetrics  # noqa: PLC0415

    builder = SpendCubeBuilder(config, db_engine)
    cube = builder.build()

    metrics_obj = CubeMetrics(cube, config)
    metrics = metrics_obj.compute_all()

    rules = RecommendationRules(cube, metrics, config)
    recommendations = rules.generate_all()

    _print_recommendations(recommendations)
