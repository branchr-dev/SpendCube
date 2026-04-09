"""Tests for SpendCube spend categorisation — Phase 3."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.categorisation.categoriser import SpendCategoriser
from src.categorisation.deterministic import DeterministicCategoriser
from src.categorisation.embedding_classifier import EmbeddingCategoriser
from src.categorisation.llm_classifier import LLMCategoriser
from src.models.database import get_transactions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def deterministic_categoriser(in_memory_engine, config):
    """DeterministicCategoriser loaded from real reference data."""
    seed_path = str(_PROJECT_ROOT / "data" / "reference" / "category_seed_mappings.csv")
    return DeterministicCategoriser(seed_path, in_memory_engine, config)


@pytest.fixture
def embedding_categoriser(config):
    """EmbeddingCategoriser loaded from real hierarchy data."""
    hierarchy_path = str(
        _PROJECT_ROOT / "data" / "reference" / "internal_category_hierarchy.csv"
    )
    cache_path = str(_PROJECT_ROOT / "data" / "cache" / "category_embeddings.pkl")
    return EmbeddingCategoriser(
        hierarchy_path=hierarchy_path,
        cache_path=cache_path,
        config=config,
    )


@pytest.fixture
def llm_categoriser(config):
    """LLMCategoriser in dry_run mode (default from config.yaml)."""
    hierarchy_path = str(
        _PROJECT_ROOT / "data" / "reference" / "internal_category_hierarchy.csv"
    )
    return LLMCategoriser(config=config, hierarchy_path=hierarchy_path)


@pytest.fixture
def spend_categoriser(in_memory_engine, config):
    """SpendCategoriser orchestrator."""
    return SpendCategoriser(config=config, engine=in_memory_engine)


@pytest.fixture
def categorised_sample_df(in_memory_engine, config):
    """Run full ingestion + categorise pipeline on sample.csv, return result DataFrame."""
    from src.ingestion.ingest import Ingestor

    ingestor = Ingestor(config)
    ingestor.ingest_to_db(
        str(_PROJECT_ROOT / "data" / "input" / "sample.csv"),
        in_memory_engine,
    )
    transactions_df = get_transactions(in_memory_engine)
    categoriser = SpendCategoriser(config=config, engine=in_memory_engine)
    return categoriser.categorise(transactions_df)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _txn(**kwargs) -> pd.DataFrame:
    """Build a minimal single-row transaction DataFrame for unit tests."""
    defaults = {
        "transaction_id": "t001",
        "gl_account": None,
        "canonical_supplier_id": None,
        "canonical_supplier_name": None,
        "raw_line_description": "",
        "cleaned_description": None,
        "base_amount": 1000.0,
    }
    defaults.update(kwargs)
    return pd.DataFrame([defaults])


# ---------------------------------------------------------------------------
# DeterministicCategoriser — GL mapping (Pass 1)
# ---------------------------------------------------------------------------


def test_gl_mapping_6420_returns_office_supplies(deterministic_categoriser):
    """GL code 6420 should match exactly to Office Supplies."""
    df = _txn(gl_account="6420")
    classified, unclassified = deterministic_categoriser.apply_gl_mapping(df)
    assert len(classified) == 1, "Row should be classified"
    assert len(unclassified) == 0
    assert classified.iloc[0]["category_l1"] == "Office Supplies"
    assert classified.iloc[0]["category_confidence"] >= 0.60


def test_gl_mapping_prefix_fallback(deterministic_categoriser):
    """GL code 6420999 not in seeds; prefix '6420' is → Office Supplies via fallback."""
    df = _txn(gl_account="6420999")
    classified, unclassified = deterministic_categoriser.apply_gl_mapping(df)
    assert len(classified) == 1, "Prefix fallback should classify the row"
    assert classified.iloc[0]["category_l1"] == "Office Supplies"


# ---------------------------------------------------------------------------
# DeterministicCategoriser — supplier mapping (Pass 2)
# ---------------------------------------------------------------------------


def test_supplier_mapping_telstra_returns_it_telecoms(deterministic_categoriser):
    """Supplier 'Telstra' should map to IT / Telecommunications."""
    df = _txn(canonical_supplier_name="Telstra")
    classified, unclassified = deterministic_categoriser.apply_supplier_mapping(df)
    assert len(classified) == 1
    assert classified.iloc[0]["category_l1"] == "IT"
    assert "Telecom" in classified.iloc[0]["category_l2"]


def test_supplier_mapping_dhl_returns_logistics(deterministic_categoriser):
    """Supplier 'DHL' should map to Logistics."""
    df = _txn(canonical_supplier_name="DHL")
    classified, unclassified = deterministic_categoriser.apply_supplier_mapping(df)
    assert len(classified) == 1
    assert classified.iloc[0]["category_l1"] == "Logistics"


# ---------------------------------------------------------------------------
# DeterministicCategoriser — keyword rules (Pass 3)
# ---------------------------------------------------------------------------


def test_keyword_toner_returns_office_supplies(deterministic_categoriser):
    """Description containing 'toner' should match keyword rule → Office Supplies."""
    df = _txn(raw_line_description="Office supplies - toner cartridges HP")
    classified, unclassified = deterministic_categoriser.apply_keyword_rules(df)
    assert len(classified) == 1
    assert classified.iloc[0]["category_l1"] == "Office Supplies"


def test_keyword_catering_returns_facilities(deterministic_categoriser):
    """Description containing 'catering' should match keyword rule → Facilities."""
    df = _txn(raw_line_description="Catering - Q1 events")
    classified, unclassified = deterministic_categoriser.apply_keyword_rules(df)
    assert len(classified) == 1
    assert classified.iloc[0]["category_l1"] == "Facilities"


def test_keyword_freight_returns_logistics(deterministic_categoriser):
    """Description containing 'freight' should match keyword rule → Logistics."""
    df = _txn(raw_line_description="International freight - Shanghai to Melb")
    classified, unclassified = deterministic_categoriser.apply_keyword_rules(df)
    assert len(classified) == 1
    assert classified.iloc[0]["category_l1"] == "Logistics"


def test_keyword_mobile_fleet_returns_it(deterministic_categoriser):
    """Description containing 'mobile fleet' should match keyword rule → IT."""
    df = _txn(raw_line_description="Mobile fleet - Feb 2024 (450 handsets)")
    classified, unclassified = deterministic_categoriser.apply_keyword_rules(df)
    assert len(classified) == 1
    assert classified.iloc[0]["category_l1"] == "IT"


# ---------------------------------------------------------------------------
# EmbeddingCategoriser
# ---------------------------------------------------------------------------


def test_embedding_classify_returns_tuple_of_correct_shape(embedding_categoriser, config):
    """classify() must return a 7-tuple regardless of similarity score."""
    result = embedding_categoriser.classify("office stationery and printer paper", config)
    assert isinstance(result, tuple)
    assert len(result) == 7
    l1, l2, l3, unspsc, confidence, method, evidence = result
    assert isinstance(confidence, float)
    assert isinstance(method, str)
    assert isinstance(evidence, str)


def test_embedding_unavailable_returns_passthrough(config):
    """When sentence-transformers unavailable, classify_batch passes all rows to LLM."""
    hierarchy_path = str(
        _PROJECT_ROOT / "data" / "reference" / "internal_category_hierarchy.csv"
    )

    with patch(
        "src.categorisation.embedding_classifier._SENTENCE_TRANSFORMERS_AVAILABLE", False
    ):
        categoriser = EmbeddingCategoriser(
            hierarchy_path=hierarchy_path,
            cache_path="/tmp/spendcube_test_no_embeddings.pkl",
            config=config,
        )

    assert not categoriser._available

    df = pd.DataFrame(
        [
            {"raw_line_description": "office supplies", "cleaned_description": None},
            {"raw_line_description": "freight forwarding", "cleaned_description": None},
        ]
    )
    classified, unclassified = categoriser.classify_batch(df, config)

    assert len(classified) == 0
    assert len(unclassified) == 2


# ---------------------------------------------------------------------------
# LLMCategoriser
# ---------------------------------------------------------------------------


def test_dry_run_returns_empty_classifications(llm_categoriser, config):
    """In dry_run mode every item must be returned with method='DRY_RUN' and confidence=0."""
    items = [
        {
            "transaction_id": "T001",
            "description": "Software licence renewal",
            "supplier_name": "Oracle",
            "gl_account": "6442",
        },
        {
            "transaction_id": "T002",
            "description": "Miscellaneous services",
            "supplier_name": "Unknown Co",
            "gl_account": "9999",
        },
    ]
    results = llm_categoriser.classify_batch(items, config)
    assert len(results) == 2
    for r in results:
        assert r["method"] == "DRY_RUN", f"Expected DRY_RUN, got {r['method']}"
        assert r["confidence"] == 0.0
        assert r["internal_category_l1"] is None


def test_dry_run_makes_no_api_calls(llm_categoriser, config):
    """classify_batch must never call the Anthropic API when dry_run=True."""
    mock_client = MagicMock()
    llm_categoriser._client = mock_client

    items = [
        {
            "transaction_id": "X1",
            "description": "catering event",
            "supplier_name": "Sodexo",
            "gl_account": "6512",
        }
    ]
    llm_categoriser.classify_batch(items, config)
    mock_client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# SpendCategoriser orchestrator
# ---------------------------------------------------------------------------


def test_categorise_sample_data_80pct_medium_or_high_confidence(
    categorised_sample_df, config
):
    """At least 80% of sample rows must reach MEDIUM confidence (>= 0.60)."""
    confidence_medium = getattr(
        getattr(config, "categorisation", None), "confidence_medium", 0.60
    )
    total = len(categorised_sample_df)
    assert total > 0
    n_ok = (
        categorised_sample_df["category_confidence"].fillna(0.0) >= confidence_medium
    ).sum()
    pct = n_ok / total
    assert pct >= 0.80, (
        f"Only {n_ok}/{total} ({pct:.0%}) at MEDIUM+ confidence, expected >= 80%.\n"
        f"Methods:\n{categorised_sample_df['category_method'].value_counts().to_string()}"
    )


def test_review_queue_sorted_by_spend_desc(spend_categoriser):
    """get_review_queue returns rows with confidence < 0.60, sorted by |base_amount| desc."""
    df = pd.DataFrame(
        [
            {"transaction_id": "A", "category_confidence": 0.30, "base_amount": 500.0},
            {"transaction_id": "B", "category_confidence": 0.10, "base_amount": 2000.0},
            {"transaction_id": "C", "category_confidence": 0.50, "base_amount": 150.0},
            # High-confidence row — should NOT appear in review queue
            {"transaction_id": "D", "category_confidence": 0.90, "base_amount": 9999.0},
        ]
    )
    review_queue = spend_categoriser.get_review_queue(df)

    # High-confidence row excluded
    assert "D" not in review_queue["transaction_id"].values
    assert len(review_queue) == 3

    # Sorted by base_amount descending
    amounts = review_queue["base_amount"].tolist()
    assert amounts == sorted(amounts, reverse=True), (
        f"Review queue not sorted by spend desc: {amounts}"
    )


# ---------------------------------------------------------------------------
# DeterministicCategoriser — apply_overrides (Pass 0)
# ---------------------------------------------------------------------------


def test_apply_overrides_matches_supplier_id(deterministic_categoriser, in_memory_engine):
    """Pass 0 override should classify a row matching on canonical_supplier_id."""
    import uuid
    from sqlalchemy import insert as sa_insert

    from src.models.database import category_overrides_table

    # Insert a manual override into the DB
    with in_memory_engine.begin() as conn:
        conn.execute(
            sa_insert(category_overrides_table),
            [
                {
                    "id": str(uuid.uuid4()),
                    "canonical_supplier_id": "override_supplier_001",
                    "gl_account": None,
                    "override_l1": "IT",
                    "override_l2": "Software",
                    "override_l3": "Cloud",
                    "unspsc_code": "43",
                    "reviewer": "test",
                    "reason": "Test override",
                    "created_at": "2026-01-01T00:00:00",
                }
            ],
        )

    # Reload overrides on the instance to pick up the newly inserted row
    deterministic_categoriser.overrides = pd.read_sql(
        "SELECT * FROM category_overrides", in_memory_engine
    )

    df = _txn(canonical_supplier_id="override_supplier_001")
    classified, unclassified = deterministic_categoriser.apply_overrides(df)

    assert len(classified) == 1
    assert len(unclassified) == 0
    assert classified.iloc[0]["category_l1"] == "IT"
    assert classified.iloc[0]["category_confidence"] == 1.0


def test_apply_overrides_no_match_passes_through(deterministic_categoriser):
    """Pass 0 with no matching overrides should return all rows as unclassified."""
    df = pd.concat(
        [
            _txn(transaction_id="T1", canonical_supplier_id="unknown_001"),
            _txn(transaction_id="T2", canonical_supplier_id="unknown_002"),
        ],
        ignore_index=True,
    )
    classified, unclassified = deterministic_categoriser.apply_overrides(df)
    assert len(classified) == 0
    assert len(unclassified) == 2


# ---------------------------------------------------------------------------
# LLMCategoriser — classify_dataframe and live path (mocked)
# ---------------------------------------------------------------------------


def test_llm_classify_dataframe_dry_run(llm_categoriser, config):
    """classify_dataframe in dry_run mode returns all rows as unclassified."""
    df = pd.DataFrame(
        [
            {
                "transaction_id": "T001",
                "raw_line_description": "Software licence renewal",
                "cleaned_description": None,
                "canonical_supplier_name": "Oracle",
                "gl_account": "6442",
            },
            {
                "transaction_id": "T002",
                "raw_line_description": "International freight",
                "cleaned_description": None,
                "canonical_supplier_name": "DHL",
                "gl_account": "6301",
            },
        ]
    )
    classified, unclassified = llm_categoriser.classify_dataframe(df, config)
    # dry_run → confidence=0.0, category=None → all go to unclassified
    assert len(classified) == 0
    assert len(unclassified) == 2


def test_llm_live_path_caps_confidence_at_0_70(llm_categoriser):
    """Live LLM path must cap response confidence at 0.70 regardless of model output."""
    import json

    # Mock config with dry_run=False
    mock_config = MagicMock()
    mock_config.llm.dry_run = False
    mock_config.llm.batch_size = 20
    mock_config.llm.model = "claude-sonnet-4-20250514"

    # Build a mock Anthropic response with confidence=0.95 (should be capped)
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps(
        [
            {
                "transaction_id": "T001",
                "internal_category_l1": "IT",
                "internal_category_l2": "Cloud Services",
                "internal_category_l3": None,
                "unspsc_segment_code": "43",
                "confidence": 0.95,
                "reasoning": "Azure subscription",
            }
        ]
    )
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    llm_categoriser._client = MagicMock()
    llm_categoriser._client.messages.create.return_value = mock_response

    items = [
        {
            "transaction_id": "T001",
            "description": "Azure cloud subscription",
            "supplier_name": "Microsoft",
            "gl_account": "6444",
        }
    ]
    results = llm_categoriser.classify_batch(items, mock_config)

    assert len(results) == 1
    assert results[0]["internal_category_l1"] == "IT"
    assert results[0]["confidence"] == 0.70, "Confidence must be capped at 0.70"
    assert results[0]["method"] == "LLM"
    llm_categoriser._client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# SpendCategoriser — DB persistence
# ---------------------------------------------------------------------------


def test_update_transactions_in_db(spend_categoriser, in_memory_engine):
    """update_transactions_in_db should return the count of rows processed."""
    df = pd.DataFrame(
        [
            {
                "transaction_id": "T-DB-001",
                "category_l1": "IT",
                "category_l2": "Software",
                "category_l3": None,
                "unspsc_code": "43",
                "category_confidence": 0.90,
                "category_method": "DETERMINISTIC_GL",
            },
            {
                "transaction_id": "T-DB-002",
                "category_l1": "Logistics",
                "category_l2": "Freight",
                "category_l3": None,
                "unspsc_code": "78",
                "category_confidence": 0.82,
                "category_method": "KEYWORD",
            },
        ]
    )
    count = spend_categoriser.update_transactions_in_db(df, in_memory_engine)
    assert count == 2


def test_apply_feedback_inserts_overrides(spend_categoriser, in_memory_engine):
    """apply_feedback should insert new rows into the category_overrides table."""
    from sqlalchemy import func, select

    from src.models.database import category_overrides_table

    overrides = [
        {
            "canonical_supplier_id": "feed_supplier_001",
            "gl_account": None,
            "l1": "IT",
            "l2": "Software",
            "l3": None,
            "unspsc_code": "43",
            "reviewer": "test_user",
            "reason": "Confirmed via invoice review",
        }
    ]
    spend_categoriser.apply_feedback(overrides, in_memory_engine)

    with in_memory_engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(category_overrides_table)
        ).scalar()

    assert count == 1


def test_update_transactions_in_db_no_transaction_id_returns_zero(spend_categoriser, in_memory_engine):
    """update_transactions_in_db returns 0 when DataFrame has no transaction_id column."""
    df = pd.DataFrame([{"category_l1": "IT", "category_confidence": 0.90}])
    count = spend_categoriser.update_transactions_in_db(df, in_memory_engine)
    assert count == 0


# ---------------------------------------------------------------------------
# EmbeddingCategoriser — edge cases
# ---------------------------------------------------------------------------


def test_embedding_classify_empty_description_returns_reject(embedding_categoriser, config):
    """classify with empty string returns EMBEDDING_REJECT (not-available / empty path)."""
    result = embedding_categoriser.classify("", config)
    l1, l2, l3, unspsc, confidence, method, evidence = result
    assert method == "EMBEDDING_REJECT"
    assert l1 is None


# ---------------------------------------------------------------------------
# LLMCategoriser — live-path edge cases
# ---------------------------------------------------------------------------


def test_llm_classify_batch_live_empty_items(llm_categoriser):
    """classify_batch with empty list in live mode returns empty list without API call."""
    mock_config = MagicMock()
    mock_config.llm.dry_run = False
    mock_config.llm.batch_size = 20
    mock_config.llm.model = "test-model"

    llm_categoriser._client = MagicMock()

    results = llm_categoriser.classify_batch([], mock_config)

    assert results == []
    llm_categoriser._client.messages.create.assert_not_called()


def test_llm_classify_batch_no_client_skips_gracefully(llm_categoriser):
    """When _client is None in live mode, _call_llm_batch returns empty classifications."""
    mock_config = MagicMock()
    mock_config.llm.dry_run = False
    mock_config.llm.batch_size = 20
    mock_config.llm.model = "test-model"

    # Simulate missing API key: client was not initialised
    llm_categoriser._client = None

    items = [
        {"transaction_id": "T001", "description": "test service", "supplier_name": "Acme", "gl_account": "9999"}
    ]
    results = llm_categoriser.classify_batch(items, mock_config)

    assert len(results) == 1
    assert results[0]["confidence"] == 0.0


def test_update_transactions_in_db_skips_nan_transaction_id(spend_categoriser, in_memory_engine):
    """Rows with NaN transaction_id are silently skipped; updated count stays 0."""
    df = pd.DataFrame(
        [
            {
                "transaction_id": float("nan"),
                "category_l1": "IT",
                "category_l2": "Software",
                "category_l3": None,
                "unspsc_code": "43",
                "category_confidence": float("nan"),
                "category_method": "DETERMINISTIC_GL",
            }
        ]
    )
    count = spend_categoriser.update_transactions_in_db(df, in_memory_engine)
    assert count == 0
