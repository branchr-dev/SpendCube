"""SpendAllocator — prevents two recommendations from double-counting the same spend pool."""

import copy

EXCLUSIVE_GROUPS: dict[str, str] = {
    "SUPPLIER_CONSOLIDATION": "SOURCING",
    "COMPETITIVE_TENDER": "SOURCING",
    "CONTRACT_COVERAGE_GAP": "COVERAGE",
    "PAYMENT_TERM_EXTENSION": "WORKING_CAPITAL",
    "TAIL_SPEND_RATIONALISATION": "PORTFOLIO_TAIL",
    "CONTRACT_COMPLIANCE": "PORTFOLIO_COMPLIANCE",
    "SPEND_CONCENTRATION_RISK": "SOURCING_CONCENTRATION",
    "EARLY_PAYMENT_DISCOUNT_CAPTURE": "EARLY_PAYMENT",
    "BEST_PRICE_EXTRAPOLATION": "PRICE_BENCHMARK",
}

_DEDUP_NOTE = "Spend pool already claimed by higher-impact recommendation of same exclusive group"


class SpendAllocator:
    """Allocates spend pools across recommendations, zeroing out lower-priority duplicates."""

    def allocate(self, recommendations: list[dict]) -> list[dict]:
        """Return deduplicated recommendations sorted by estimated_impact_aud descending.

        Recommendations that share the same exclusive group and spend pool context are
        deduplicated: only the highest-impact one is retained. PORTFOLIO_* groups use a
        single shared pool key ('PORTFOLIO', exclusive_group) rather than per-context keys.
        """
        recs = copy.deepcopy(recommendations)
        recs.sort(key=lambda r: r.get("estimated_impact_aud", 0.0), reverse=True)

        claimed: set[tuple] = set()

        for rec in recs:
            rec_type = rec.get("type", "")
            exclusive_group = EXCLUSIVE_GROUPS.get(rec_type)

            if exclusive_group is None:
                # Unknown type — no deduplication applied
                continue

            if exclusive_group.startswith("PORTFOLIO"):
                pool_key = ("PORTFOLIO", exclusive_group)
            else:
                pool_key = (rec.get("context", ""), exclusive_group)

            if pool_key in claimed:
                rec["estimated_impact_aud"] = 0.0
                rec["deduplication_note"] = _DEDUP_NOTE
            else:
                claimed.add(pool_key)

        return [r for r in recs if r.get("estimated_impact_aud", 0.0) != 0.0]
