"""Tests for SpendCube recommendations engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.cube.metrics import CubeMetrics
from src.recommendations.engine import RecommendationEngine
from src.recommendations.narratives import NarrativeGenerator
from src.recommendations.rules import (
    CONTRACT_COMPLIANCE,
    CONTRACT_COVERAGE_GAP,
    COMPETITIVE_TENDER,
    PAYMENT_TERM_EXTENSION,
    SUPPLIER_CONSOLIDATION,
    TAIL_SPEND_RATIONALISATION,
    RecommendationRules,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(**overrides) -> dict:
    """Minimal metrics dict with sensible defaults, updated by overrides."""
    defaults = {
        "total_spend": 100_000.0,
        "maverick_spend_pct": 0.0,
        "tail_spend_pct": 0.0,
        "tail_supplier_count": 0,
    }
    defaults.update(overrides)
    return defaults


def _txn_df(**col_overrides) -> pd.DataFrame:
    """Four-row transaction DataFrame with optional column overrides."""
    data: dict = {
        "canonical_supplier_id": ["sup_a", "sup_b", "sup_c", "sup_d"],
        "canonical_supplier_name": ["Alpha", "Beta", "Gamma", "Delta"],
        "base_amount": [10_000.0, 20_000.0, 30_000.0, 40_000.0],
        "payment_terms_days": [30.0, 30.0, 30.0, 30.0],
        "po_number": [None, None, None, None],
        "category_l1": ["IT"] * 4,
        "category_l2": ["Software"] * 4,
        "is_intercompany": [0] * 4,
        "is_tax_line": [0] * 4,
    }
    data.update(col_overrides)
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# RecommendationRules
# ---------------------------------------------------------------------------

class TestRecommendationRules:

    def test_generates_at_least_one_recommendation_from_sample(self, cube_df, config):
        """At least one recommendation must be generated from the sample cube fixture."""
        # cube_df has ~50% maverick spend (no PO) which exceeds the 0.15 alert threshold
        metrics = CubeMetrics(cube_df, config).compute_all()
        rules = RecommendationRules(cube_df, metrics, config)
        recs = rules.generate_all()
        assert len(recs) >= 1, "Expected at least one recommendation from sample cube"

    def test_maverick_recommendation_generated_when_po_missing(self, config):
        """CONTRACT_COMPLIANCE must fire when maverick_spend_pct > maverick_alert_pct."""
        cube = {"transactions": _txn_df()}  # all transactions have po_number=None
        # maverick_alert_pct default = 0.15; use 0.50 to be well above threshold
        metrics = _metrics(total_spend=100_000.0, maverick_spend_pct=0.50)

        rules = RecommendationRules(cube, metrics, config)
        recs = rules.generate_all()

        types = {r["type"] for r in recs}
        assert CONTRACT_COMPLIANCE in types, (
            f"CONTRACT_COMPLIANCE not found in {types}"
        )

    def test_tail_spend_recommendation_generated(self, config):
        """TAIL_SPEND_RATIONALISATION must fire when tail_spend_pct > tail_spend_alert_pct."""
        cube = {"transactions": _txn_df()}
        # tail_spend_alert_pct default = 0.05; use 0.25 to ensure it fires
        metrics = _metrics(
            total_spend=200_000.0,
            tail_spend_pct=0.25,
            tail_supplier_count=20,
        )

        rules = RecommendationRules(cube, metrics, config)
        recs = rules.generate_all()

        types = {r["type"] for r in recs}
        assert TAIL_SPEND_RATIONALISATION in types, (
            f"TAIL_SPEND_RATIONALISATION not found in {types}"
        )

    def test_payment_term_rec_only_for_suppliers_below_target(self, config):
        """PAYMENT_TERM_EXTENSION must only fire for suppliers with terms < target_payment_days."""
        target = config.recommendations.target_payment_days  # 45 by default

        # Below-target suppliers: 20 days (diff=25) with large enough spend to
        # exceed min_wc_opportunity (10_000 AUD).
        # impact = 25/365 * 2_000_000 * 0.08 ≈ 10_958 > 10_000 ✓
        txn = pd.DataFrame({
            "canonical_supplier_id": ["below_a", "below_b", "above_a", "above_b"],
            "canonical_supplier_name": ["Below A", "Below B", "Above A", "Above B"],
            "base_amount": [2_000_000.0, 2_000_000.0, 1_000_000.0, 1_000_000.0],
            "payment_terms_days": [
                float(target - 25),   # below target
                float(target - 25),   # below target
                float(target + 15),   # above target
                float(target + 30),   # above target
            ],
            "is_intercompany": [0, 0, 0, 0],
            "is_tax_line": [0, 0, 0, 0],
        })
        cube = {"transactions": txn}
        metrics = _metrics(total_spend=6_000_000.0)

        rules = RecommendationRules(cube, metrics, config)
        payment_recs = [r for r in rules.generate_all() if r["type"] == PAYMENT_TERM_EXTENSION]
        contexts = {r["context"] for r in payment_recs}

        assert "Above A" not in contexts, "Supplier above target must NOT get a payment term rec"
        assert "Above B" not in contexts, "Supplier above target must NOT get a payment term rec"
        assert "Below A" in contexts, "Supplier below target must get a payment term rec"
        assert "Below B" in contexts, "Supplier below target must get a payment term rec"

    def test_recommendations_sorted_by_impact_desc(self, config):
        """generate_all() must return recommendations sorted by estimated_impact_aud descending."""
        cube = {"transactions": _txn_df()}
        metrics = _metrics(
            total_spend=500_000.0,
            maverick_spend_pct=0.40,
            tail_spend_pct=0.30,
            tail_supplier_count=30,
        )

        rules = RecommendationRules(cube, metrics, config)
        recs = rules.generate_all()

        if len(recs) >= 2:
            impacts = [r["estimated_impact_aud"] for r in recs]
            assert impacts == sorted(impacts, reverse=True), (
                f"Recommendations not sorted by impact descending: {impacts}"
            )

    def test_no_negative_impact_recommendations(self, cube_df, config):
        """No recommendation from generate_all() should have a negative estimated_impact_aud."""
        metrics = CubeMetrics(cube_df, config).compute_all()
        rules = RecommendationRules(cube_df, metrics, config)
        recs = rules.generate_all()

        for rec in recs:
            impact = rec.get("estimated_impact_aud", 0.0)
            assert impact >= 0.0, (
                f"Negative impact found for {rec.get('type')}: {impact}"
            )

    def test_supplier_consolidation_fires_for_many_suppliers(self, config):
        """SUPPLIER_CONSOLIDATION must fire when a category has > consolidation_threshold suppliers."""
        threshold = config.recommendations.consolidation_threshold  # 5
        # Build n_suppliers > threshold suppliers all in the same L2 category
        n = threshold + 2
        txn = pd.DataFrame({
            "canonical_supplier_id": [f"sup_{i}" for i in range(n)],
            "canonical_supplier_name": [f"Vendor {i}" for i in range(n)],
            "base_amount": [50_000.0] * n,
            "category_l2": ["IT Services"] * n,
            "is_intercompany": [0] * n,
            "is_tax_line": [0] * n,
        })
        cube = {"transactions": txn}
        metrics = _metrics(total_spend=float(n * 50_000))

        rules = RecommendationRules(cube, metrics, config)
        recs = [r for r in rules.generate_all() if r["type"] == SUPPLIER_CONSOLIDATION]

        assert len(recs) >= 1, "Expected SUPPLIER_CONSOLIDATION recommendation"
        assert recs[0]["estimated_impact_aud"] > 0

    def test_competitive_tender_fires_for_single_source_high_spend(self, config):
        """COMPETITIVE_TENDER must fire for a category with exactly 1 supplier and spend > $50k."""
        txn = pd.DataFrame({
            "canonical_supplier_id": ["sole_sup", "sole_sup", "sole_sup"],
            "canonical_supplier_name": ["Sole Supplier Ltd"] * 3,
            "base_amount": [30_000.0, 40_000.0, 50_000.1],  # total >50k
            "category_l2": ["Facilities Management"] * 3,
            "is_intercompany": [0, 0, 0],
            "is_tax_line": [0, 0, 0],
        })
        cube = {"transactions": txn}
        metrics = _metrics(total_spend=120_000.0)

        rules = RecommendationRules(cube, metrics, config)
        recs = [r for r in rules.generate_all() if r["type"] == COMPETITIVE_TENDER]

        assert len(recs) >= 1, "Expected COMPETITIVE_TENDER recommendation"
        assert "Facilities Management" in recs[0]["context"]

    def test_contract_coverage_gap_fires_for_low_coverage(self, config):
        """CONTRACT_COVERAGE_GAP must fire when contract coverage < 50% and spend > $20k."""
        # 4 rows in same L1 category, spend > 20k, none on contract
        txn = pd.DataFrame({
            "category_l1": ["Professional Services"] * 4,
            "base_amount": [15_000.0, 20_000.0, 10_000.0, 5_001.0],  # total > 20k
            "is_on_contract": [0, 0, 0, 0],  # 0% coverage
            "canonical_supplier_id": ["s1", "s2", "s3", "s4"],
            "is_intercompany": [0, 0, 0, 0],
            "is_tax_line": [0, 0, 0, 0],
        })
        cube = {"transactions": txn}
        metrics = _metrics(total_spend=50_001.0)

        rules = RecommendationRules(cube, metrics, config)
        recs = [r for r in rules.generate_all() if r["type"] == CONTRACT_COVERAGE_GAP]

        assert len(recs) >= 1, "Expected CONTRACT_COVERAGE_GAP recommendation"
        assert recs[0]["estimated_impact_aud"] > 0

    def test_rules_handle_empty_transactions_gracefully(self, config):
        """RecommendationRules must return an empty list when there are no transactions."""
        rules = RecommendationRules({"transactions": pd.DataFrame()}, _metrics(), config)
        recs = rules.generate_all()
        assert recs == []


# ---------------------------------------------------------------------------
# NarrativeGenerator
# ---------------------------------------------------------------------------

class TestNarrativeGenerator:

    def test_dry_run_returns_recommendations_unchanged(self, config):
        """With dry_run=True, enrich() must add narrative=None and preserve all other fields."""
        assert config.llm.dry_run is True, (
            "This test requires llm.dry_run=True (configured in config.yaml)"
        )
        generator = NarrativeGenerator(config)

        original = [
            {
                "type": "CONTRACT_COMPLIANCE",
                "context": "Portfolio",
                "estimated_impact_aud": 5_000.0,
                "confidence": "MEDIUM",
            },
            {
                "type": "TAIL_SPEND_RATIONALISATION",
                "context": "Portfolio",
                "estimated_impact_aud": 3_000.0,
                "confidence": "LOW",
            },
        ]
        enriched = generator.enrich(original)

        assert len(enriched) == len(original)
        for orig, enc in zip(original, enriched):
            assert "narrative" in enc, "enrich() must add the 'narrative' key"
            assert enc["narrative"] is None, "narrative must be None when dry_run=True"
            for key, value in orig.items():
                assert enc[key] == value, f"Field '{key}' was modified by enrich()"

    def test_dry_run_makes_no_api_calls(self, config):
        """With dry_run=True, no Anthropic client must be created or called."""
        assert config.llm.dry_run is True

        generator = NarrativeGenerator(config)

        # _client must remain None — Anthropic() should never be instantiated
        assert generator._client is None, (
            "Anthropic client must be None when dry_run=True"
        )

        # enrich() must complete cleanly without any external network call
        recs = [{"type": "X", "context": "Y", "estimated_impact_aud": 100.0}]
        result = generator.enrich(recs)

        assert len(result) == 1
        assert result[0]["narrative"] is None

    def test_enrich_with_no_client_returns_none_narratives(self, config):
        """enrich() must return recommendations without narratives when _client is None."""
        generator = NarrativeGenerator(config)
        # Force non-dry-run mode but keep _client as None to simulate missing SDK
        generator._dry_run = False
        generator._client = None

        recs = [{"type": "X", "context": "Y", "estimated_impact_aud": 50.0}]
        result = generator.enrich(recs)

        assert len(result) == 1
        assert result[0]["narrative"] is None

    def test_parse_response_plain_json(self):
        """_parse_response must parse a plain JSON array string."""
        raw = '[{"type": "X", "context": "Cat", "narrative": "A story."}]'
        result = NarrativeGenerator._parse_response(raw)
        assert isinstance(result, list)
        assert result[0]["narrative"] == "A story."

    def test_parse_response_strips_markdown_fences(self):
        """_parse_response must strip ```json ... ``` fences before parsing."""
        raw = '```json\n[{"type": "Y", "context": "C", "narrative": "B"}]\n```'
        result = NarrativeGenerator._parse_response(raw)
        assert isinstance(result, list)
        assert result[0]["type"] == "Y"

    def test_parse_response_raises_for_non_list(self):
        """_parse_response must raise ValueError when the response is not a JSON array."""
        with pytest.raises(ValueError, match="Expected JSON array"):
            NarrativeGenerator._parse_response('{"type": "not_a_list"}')

    def test_enrich_empty_list_returns_immediately(self, config):
        """enrich([]) must return an empty list without calling the LLM."""
        gen = NarrativeGenerator(config)
        gen._dry_run = False  # force non-dry-run to test the early-return path
        result = gen.enrich([])
        assert result == []

    def test_enrich_calls_llm_and_merges_narratives(self, config):
        """enrich() must call _call_llm and merge returned narratives when client is set."""
        gen = NarrativeGenerator(config)
        gen._dry_run = False

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='[{"type": "X", "context": "Y", "narrative": "A story."}]')
        ]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        gen._client = mock_client

        recs = [{"type": "X", "context": "Y", "estimated_impact_aud": 1.0}]
        result = gen.enrich(recs)

        assert len(result) == 1
        assert result[0]["narrative"] == "A story."
        mock_client.messages.create.assert_called_once()

    def test_enrich_handles_llm_api_error_gracefully(self, config):
        """enrich() must return recs with narrative=None when the LLM call raises an exception."""
        gen = NarrativeGenerator(config)
        gen._dry_run = False

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API unavailable")
        gen._client = mock_client

        recs = [{"type": "X", "context": "Y", "estimated_impact_aud": 1.0}]
        result = gen.enrich(recs)

        assert len(result) == 1
        assert result[0]["narrative"] is None  # no exception raised, graceful fallback


# ---------------------------------------------------------------------------
# RecommendationEngine
# ---------------------------------------------------------------------------

class TestRecommendationEngine:

    def test_run_returns_list(self, cube_df, in_memory_engine, config):
        """run() must return a list of recommendation dicts."""
        # cube_df fixture populates in_memory_engine with 10 sample transactions
        engine = RecommendationEngine(config, in_memory_engine)
        result = engine.run()
        assert isinstance(result, list)

    def test_export_creates_json_file(self, in_memory_engine, config, tmp_path):
        """export() must write a valid JSON array to the given path and return it."""
        eng = RecommendationEngine(config, in_memory_engine)
        recs = [
            {
                "type": "CONTRACT_COMPLIANCE",
                "context": "Portfolio",
                "evidence": "40% maverick spend",
                "estimated_impact_aud": 10_000.0,
                "confidence": "MEDIUM",
                "action": "Enforce PO compliance",
                "lever": "Contract Compliance",
                "narrative": None,
            }
        ]
        output_path = str(tmp_path / "recs.json")
        returned_path = eng.export(recs, output_path)

        assert Path(returned_path).exists(), f"Expected file at {returned_path}"
        with open(returned_path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert isinstance(loaded, list)
        assert len(loaded) == 1
        assert loaded[0]["type"] == "CONTRACT_COMPLIANCE"
        assert loaded[0]["estimated_impact_aud"] == 10_000.0

    def test_to_dataframe_has_correct_columns(self, in_memory_engine, config):
        """to_dataframe() must return a DataFrame with exactly the required 8 columns."""
        eng = RecommendationEngine(config, in_memory_engine)
        recs = [
            {
                "type": "TAIL_SPEND_RATIONALISATION",
                "context": "Portfolio",
                "evidence": "20 tail suppliers, 25% of spend",
                "estimated_impact_aud": 8_000.0,
                "confidence": "MEDIUM",
                "action": "Rationalise tail vendors",
                "lever": "Tail Spend Rationalisation",
                "narrative": None,
            }
        ]
        df = eng.to_dataframe(recs)

        expected_columns = {
            "type", "context", "evidence", "estimated_impact_aud",
            "confidence", "action", "lever", "narrative",
        }
        assert set(df.columns) == expected_columns, (
            f"Column mismatch: got {set(df.columns)}, expected {expected_columns}"
        )
        assert len(df) == 1
        assert df.iloc[0]["type"] == "TAIL_SPEND_RATIONALISATION"
        assert df.iloc[0]["estimated_impact_aud"] == 8_000.0
