"""Tests for SpendCube supplier harmonisation — Phase 2.

Covers: SupplierNormaliser, DeterministicMatcher, FuzzyMatcher,
EmbeddingMatcher, and the SupplierHarmoniser orchestrator.

Validation gate: sample data correctly merges Acme x3 and Sodexo x3 into
single canonical entries each.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.database import init_db
from src.suppliers.embeddings import EmbeddingMatcher
from src.suppliers.harmoniser import SupplierHarmoniser
from src.suppliers.matcher import DeterministicMatcher, FuzzyMatcher
from src.suppliers.normaliser import SupplierNormaliser


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def normaliser():
    """SupplierNormaliser loaded from project reference data."""
    return SupplierNormaliser(
        suffixes_path=str(_PROJECT_ROOT / "data" / "reference" / "legal_suffixes.yaml"),
        abbreviations_path=str(_PROJECT_ROOT / "data" / "reference" / "abbreviation_map.yaml"),
    )


@pytest.fixture(scope="module")
def sample_suppliers_df():
    """DataFrame of the 10 sample.csv rows' supplier fields.

    Matches the raw vendor data in data/input/sample.csv exactly.
    """
    return pd.DataFrame([
        {"raw_supplier_name": "Acme Pty Ltd",            "raw_supplier_id": "V-001"},
        {"raw_supplier_name": "ACME PTY LIMITED",         "raw_supplier_id": "V-001"},
        {"raw_supplier_name": "acme p/l",                 "raw_supplier_id": "V-001"},
        {"raw_supplier_name": "Sodexo Australia Pty Ltd", "raw_supplier_id": "V-002"},
        {"raw_supplier_name": "SODEXO AUSTRALIA",         "raw_supplier_id": "V-002"},
        {"raw_supplier_name": "Sodexo Aust P/L",          "raw_supplier_id": "V-002"},
        {"raw_supplier_name": "INTERCOMPANY - LEGAL",     "raw_supplier_id": "V-003"},
        {"raw_supplier_name": None,                        "raw_supplier_id": "V-999"},
        {"raw_supplier_name": "DHL Express",              "raw_supplier_id": "V-004"},
        {"raw_supplier_name": "BHP Billiton Ltd",         "raw_supplier_id": "V-005"},
    ])


@pytest.fixture
def minimal_master_df():
    """Minimal supplier master DataFrame for isolated matcher unit tests."""
    return pd.DataFrame([
        {
            "canonical_supplier_id": "abc000acme11",
            "canonical_name": "Acme Pty Ltd",
            "normalised_name": "acme",
            "identifiers": json.dumps({"raw_ids": ["V-001"]}),
        },
        {
            "canonical_supplier_id": "def000sod012",
            "canonical_name": "Sodexo Australia",
            "normalised_name": "sodexo australia",
            "identifiers": json.dumps({"raw_ids": ["V-002"]}),
        },
    ])


# ---------------------------------------------------------------------------
# Normaliser tests
# ---------------------------------------------------------------------------

def test_normalise_acme_pty_ltd(normaliser):
    assert normaliser.normalise("Acme Pty Ltd") == "acme"


def test_normalise_acme_pty_limited(normaliser):
    assert normaliser.normalise("ACME PTY LIMITED") == "acme"


def test_normalise_acme_pl(normaliser):
    assert normaliser.normalise("acme p/l") == "acme"


def test_normalise_sodexo_australia(normaliser):
    assert normaliser.normalise("SODEXO AUSTRALIA") == "sodexo australia"


def test_normalise_sodexo_aust_pl(normaliser):
    assert normaliser.normalise("Sodexo Aust P/L") == "sodexo australia"


def test_normalise_none_returns_empty(normaliser):
    assert normaliser.normalise(None) == ""
    assert normaliser.normalise("") == ""
    assert normaliser.normalise("   ") == ""


def test_normalise_strips_ta_prefix(normaliser):
    """T/A / Trading As prefixes must be stripped so the result matches the bare name."""
    bare = normaliser.normalise("Acme Pty Ltd")
    assert normaliser.normalise("T/A Acme Pty Ltd") == bare
    assert normaliser.normalise("t/a Acme Pty Ltd") == bare
    assert normaliser.normalise("Trading As Acme Pty Ltd") == bare


def test_normalise_series(normaliser):
    """normalise_series applies normalise() vectorised to a pandas Series."""
    series = pd.Series(["Acme Pty Ltd", "SODEXO AUSTRALIA", "acme p/l", ""])
    result = normaliser.normalise_series(series)
    assert result[0] == "acme"
    assert result[1] == "sodexo australia"
    assert result[2] == "acme"
    assert result[3] == ""  # blank string → empty


# ---------------------------------------------------------------------------
# DeterministicMatcher tests
# ---------------------------------------------------------------------------

def test_exact_name_match_returns_high_confidence(minimal_master_df):
    matcher = DeterministicMatcher(minimal_master_df)
    canon_id, confidence, method = matcher.match("Acme Pty Ltd", "acme")
    assert canon_id == "abc000acme11"
    assert confidence == 0.95
    assert method == "EXACT_NAME"


def test_exact_vendor_id_match_returns_099(minimal_master_df):
    matcher = DeterministicMatcher(minimal_master_df)
    # raw_supplier_id "V-001" is listed in Acme's identifiers; name does not match
    canon_id, confidence, method = matcher.match(
        "Unknown Supplier Name", "unknown supplier name", raw_supplier_id="V-001"
    )
    assert canon_id == "abc000acme11"
    assert confidence == 0.99
    assert method == "EXACT_VENDOR_ID"


def test_no_match_returns_none(minimal_master_df):
    matcher = DeterministicMatcher(minimal_master_df)
    canon_id, confidence, method = matcher.match("XYZ Widgets", "xyz widgets", "V-999")
    assert canon_id is None
    assert confidence == 0.0
    assert method == ""


# ---------------------------------------------------------------------------
# FuzzyMatcher tests
# ---------------------------------------------------------------------------

def test_fuzzy_composite_score_acme_variants_above_88(minimal_master_df, config):
    """Composite fuzzy score for the normalised 'acme' string against the master
    must be >= 0.88 (auto threshold) and produce FUZZY_AUTO."""
    fuzzy = FuzzyMatcher(minimal_master_df, config)

    # All Acme variants normalise to 'acme'; score against master 'acme' = 1.0
    raw_score = fuzzy.score("acme", "acme")
    assert raw_score >= 0.88

    # Full match() should return FUZZY_AUTO for score >= auto_threshold
    canon_id, confidence, method, _evidence = fuzzy.match("acme")
    assert method == "FUZZY_AUTO"
    assert canon_id == "abc000acme11"
    assert confidence >= 0.88 * 0.95  # FUZZY_AUTO scales by 0.95


def test_fuzzy_below_threshold_returns_none(minimal_master_df, config):
    """Completely unrelated supplier must return FUZZY_REJECT with None canonical_id."""
    fuzzy = FuzzyMatcher(minimal_master_df, config)
    canon_id, _confidence, method, _evidence = fuzzy.match(
        "xyz completely unrelated supplier company"
    )
    assert method == "FUZZY_REJECT"
    assert canon_id is None


# ---------------------------------------------------------------------------
# EmbeddingMatcher tests
# ---------------------------------------------------------------------------

def test_embedding_matcher_initialises():
    """EmbeddingMatcher.__init__ must not raise even if model is unavailable."""
    matcher = EmbeddingMatcher(cache_path="/tmp/test_supplier_embeddings.pkl")
    assert hasattr(matcher, "_model")
    assert hasattr(matcher, "_cache")


def test_embedding_matcher_match_returns_unavailable_when_model_none(config):
    """EmbeddingMatcher.match returns EMBEDDING_UNAVAILABLE when model is None."""
    matcher = EmbeddingMatcher(cache_path="/tmp/test_supplier_embeddings2.pkl")
    original_model = matcher._model
    matcher._model = None  # force unavailable path
    try:
        canon_id, conf, method, evidence = matcher.match(
            "acme", ["acme", "sodexo australia"], ["id1", "id2"], config
        )
        assert method == "EMBEDDING_UNAVAILABLE"
        assert canon_id is None
        assert conf == 0.0
    finally:
        matcher._model = original_model


# ---------------------------------------------------------------------------
# Harmoniser integration tests
# ---------------------------------------------------------------------------

def test_harmonise_sample_data_merges_acme_to_one_canonical(
    in_memory_engine, config, sample_suppliers_df
):
    """All 3 Acme raw name variants must be collapsed to exactly 1 canonical entry."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    txn_df = sample_suppliers_df.dropna(subset=["raw_supplier_name"]).copy()
    supplier_master_df, _ = harmoniser.harmonise(txn_df)

    acme_rows = supplier_master_df[
        supplier_master_df["canonical_name"].str.lower().str.contains("acme", na=False)
    ]
    assert len(acme_rows) == 1, (
        f"Expected 1 Acme canonical entry, got {len(acme_rows)}: "
        f"{acme_rows['canonical_name'].tolist()}"
    )


def test_harmonise_sample_data_merges_sodexo_to_one_canonical(
    in_memory_engine, config, sample_suppliers_df
):
    """All Sodexo raw name variants must be collapsed to exactly 1 canonical entry."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    txn_df = sample_suppliers_df.dropna(subset=["raw_supplier_name"]).copy()
    supplier_master_df, _ = harmoniser.harmonise(txn_df)

    sodexo_rows = supplier_master_df[
        supplier_master_df["canonical_name"].str.lower().str.contains("sodexo", na=False)
    ]
    assert len(sodexo_rows) == 1, (
        f"Expected 1 Sodexo canonical entry, got {len(sodexo_rows)}: "
        f"{sodexo_rows['canonical_name'].tolist()}"
    )


def test_harmonise_is_idempotent(in_memory_engine, config, sample_suppliers_df):
    """Running harmoniser twice on the same input must not duplicate supplier_master rows."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    txn_df = sample_suppliers_df.dropna(subset=["raw_supplier_name"]).copy()

    master_1, _ = harmoniser.harmonise(txn_df)
    count_first = len(master_1)

    master_2, _ = harmoniser.harmonise(txn_df)
    count_second = len(master_2)

    assert count_first > 0, "First run must produce at least one canonical supplier"
    assert count_first == count_second, (
        f"Second run changed row count: {count_first} → {count_second} "
        "(idempotency violated)"
    )


def test_harmonise_update_transactions_populates_canonical_columns(
    in_memory_engine, config, sample_suppliers_df
):
    """update_transactions must add canonical_supplier_id column; Acme rows share one ID."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    txn_df = sample_suppliers_df.dropna(subset=["raw_supplier_name"]).copy()
    _, match_log_df = harmoniser.harmonise(txn_df)

    enriched = harmoniser.update_transactions(txn_df, match_log_df)
    assert "canonical_supplier_id" in enriched.columns

    acme_rows = enriched[
        enriched["raw_supplier_name"].str.lower().str.contains("acme", na=False)
    ]
    assert acme_rows["canonical_supplier_id"].nunique() == 1, (
        "All Acme variants must map to the same canonical_supplier_id after enrichment"
    )


def test_harmonise_get_review_queue_filters_by_confidence(
    in_memory_engine, config, sample_suppliers_df
):
    """get_review_queue must only include rows with confidence < 0.60."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    txn_df = sample_suppliers_df.dropna(subset=["raw_supplier_name"]).copy()
    _, match_log_df = harmoniser.harmonise(txn_df)

    review_queue = harmoniser.get_review_queue(match_log_df)

    # All sample suppliers are matched with confidence >= 1.0 (NEW_CANONICAL / NORMALISED_NAME_GROUP)
    assert review_queue.empty, (
        f"Expected empty review queue for sample data (all high confidence); "
        f"got {len(review_queue)} rows"
    )


def test_harmonise_empty_transactions(in_memory_engine, config):
    """harmonise() with all-null supplier names returns empty master and log."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    empty_df = pd.DataFrame({
        "raw_supplier_name": [None, None],
        "raw_supplier_id": ["V-999", "V-998"],
    })
    master, log = harmoniser.harmonise(empty_df)
    assert master.empty or len(master) == 0
    assert log.empty or len(log) == 0


def test_harmonise_update_transactions_empty_match_log(in_memory_engine, config, sample_suppliers_df):
    """update_transactions with empty match_log returns copy of original DataFrame."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    txn_df = sample_suppliers_df.dropna(subset=["raw_supplier_name"]).copy()
    empty_log = pd.DataFrame()
    result = harmoniser.update_transactions(txn_df, empty_log)
    assert len(result) == len(txn_df)


def test_harmonise_update_transactions_empty_master(in_memory_engine, config):
    """update_transactions with empty supplier_master DB falls back gracefully."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    # Build a minimal match_log without running harmonise first (master DB is empty)
    match_log_df = pd.DataFrame([{
        "raw_supplier_name": "Acme Pty Ltd",
        "canonical_supplier_id": "abc000acme11",
        "confidence": 0.95,
        "match_method": "EXACT_NAME",
    }])
    txn_df = pd.DataFrame([{"raw_supplier_name": "Acme Pty Ltd", "raw_supplier_id": "V-001"}])
    result = harmoniser.update_transactions(txn_df, match_log_df)
    assert "canonical_supplier_id" in result.columns


def test_harmonise_get_review_queue_with_low_confidence(in_memory_engine, config):
    """get_review_queue returns rows where confidence < 0.60."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)
    match_log_df = pd.DataFrame([
        {
            "raw_supplier_name": "Unknown Co",
            "canonical_supplier_id": "abc123",
            "match_method": "FUZZY_REVIEW",
            "confidence": 0.45,
            "evidence": "{}",
            "review_status": "PENDING",
        },
        {
            "raw_supplier_name": "Acme Pty Ltd",
            "canonical_supplier_id": "abc000acme11",
            "match_method": "EXACT_NAME",
            "confidence": 0.95,
            "evidence": "{}",
            "review_status": "APPROVED",
        },
    ])
    review_queue = harmoniser.get_review_queue(match_log_df)
    assert not review_queue.empty
    assert len(review_queue) == 1
    assert float(review_queue.iloc[0]["confidence"]) < 0.60


# ---------------------------------------------------------------------------
# Additional matcher coverage tests
# ---------------------------------------------------------------------------

def test_normalise_overstrip_protection(normaliser):
    """If normalisation strips all content, fall back to the lowercased original."""
    # "Pty Ltd" would strip entirely to '' → over-strip protection → "pty ltd"
    result = normaliser.normalise("Pty Ltd")
    assert result  # must not be empty
    assert "pty" in result.lower()


def test_deterministic_matcher_malformed_identifiers():
    """DeterministicMatcher handles malformed JSON identifiers without raising."""
    master_df = pd.DataFrame([{
        "canonical_supplier_id": "abc123",
        "canonical_name": "Test Supplier",
        "normalised_name": "test supplier",
        "identifiers": "{not valid json}",
    }])
    matcher = DeterministicMatcher(master_df)
    # normalised_name still works for exact match
    canon_id, confidence, method = matcher.match("Test Supplier", "test supplier")
    assert canon_id == "abc123"
    assert method == "EXACT_NAME"


def test_fuzzy_review_threshold(minimal_master_df, config):
    """Composite score between review (70) and auto (88) thresholds returns FUZZY_REVIEW."""
    fuzzy = FuzzyMatcher(minimal_master_df, config)
    # "xyz acme" vs "acme": token_sort~67, token_set~100, partial~100 → composite~0.868
    # 0.868 < 0.88 (auto) and >= 0.70 (review) → FUZZY_REVIEW
    canon_id, confidence, method, _evidence = fuzzy.match("xyz acme")
    assert method == "FUZZY_REVIEW"
    assert canon_id is not None
    assert 0.60 <= confidence <= 0.95


def test_fuzzy_corroboration_boost_raises_to_auto(minimal_master_df, config):
    """Corroboration same_city boost (+5 pts) can push a FUZZY_REVIEW score to FUZZY_AUTO."""
    fuzzy = FuzzyMatcher(minimal_master_df, config)
    # Without corroboration: "xyz acme" → FUZZY_REVIEW (~86.8)
    # With same_city +5 → 91.8 >= 88 → FUZZY_AUTO
    canon_id, confidence, method, evidence = fuzzy.match(
        "xyz acme", corroboration={"same_city": True}
    )
    assert method == "FUZZY_AUTO"
    assert "city_match" in evidence


def test_fuzzy_skips_empty_candidate_names(config):
    """FuzzyMatcher skips master entries with empty normalised_name without error."""
    master_with_empty = pd.DataFrame([
        {"canonical_supplier_id": "id1", "canonical_name": "Acme", "normalised_name": "acme",
         "identifiers": "{}"},
        {"canonical_supplier_id": "id2", "canonical_name": "Empty Row", "normalised_name": "",
         "identifiers": "{}"},
    ])
    fuzzy = FuzzyMatcher(master_with_empty, config)
    canon_id, _conf, method, _ev = fuzzy.match("acme")
    assert method == "FUZZY_AUTO"
    assert canon_id == "id1"  # the non-empty entry wins


# ---------------------------------------------------------------------------
# EmbeddingMatcher live tests (sentence-transformers available)
# ---------------------------------------------------------------------------

def test_embedding_matcher_encode():
    """EmbeddingMatcher.encode returns correct shape when model is available."""
    matcher = EmbeddingMatcher(cache_path="/tmp/test_emb_encode.pkl")
    if matcher._model is None:
        pytest.skip("sentence-transformers model not available")
    import numpy as np
    vectors = matcher.encode(["acme", "sodexo australia"])
    assert vectors.shape[0] == 2
    assert vectors.shape[1] > 0
    # Second call uses cache — no re-encoding
    vectors2 = matcher.encode(["acme"])
    assert vectors2.shape == (1, vectors.shape[1])


def test_embedding_matcher_match_with_candidates(config):
    """EmbeddingMatcher.match returns a recognised method when model is available."""
    matcher = EmbeddingMatcher(cache_path="/tmp/test_emb_match.pkl")
    if matcher._model is None:
        pytest.skip("sentence-transformers model not available")
    canon_id, conf, method, evidence = matcher.match(
        "acme", ["acme", "sodexo australia"], ["id1", "id2"], config
    )
    assert method in ("EMBEDDING_AUTO", "EMBEDDING_REVIEW", "EMBEDDING_REJECT")
    assert 0.0 <= conf <= 1.0
    assert "cosine_similarity" in evidence


def test_embedding_matcher_match_batch(config):
    """EmbeddingMatcher.match_batch returns one result tuple per query name."""
    matcher = EmbeddingMatcher(cache_path="/tmp/test_emb_batch.pkl")
    if matcher._model is None:
        pytest.skip("sentence-transformers model not available")
    results = matcher.match_batch(
        ["acme", "sodexo australia"],
        ["acme", "sodexo australia"],
        ["id1", "id2"],
        config,
    )
    assert len(results) == 2
    for _canon_id, conf, method, evidence in results:
        assert method in ("EMBEDDING_AUTO", "EMBEDDING_REVIEW", "EMBEDDING_REJECT")
        assert "cosine_similarity" in evidence


def test_embedding_matcher_match_no_candidates(config):
    """EmbeddingMatcher.match returns EMBEDDING_REJECT when candidate list is empty."""
    matcher = EmbeddingMatcher(cache_path="/tmp/test_emb_no_cand.pkl")
    if matcher._model is None:
        pytest.skip("sentence-transformers model not available")
    canon_id, conf, method, evidence = matcher.match("acme", [], [], config)
    assert method == "EMBEDDING_REJECT"
    assert canon_id is None


def test_embedding_matcher_encode_uncached(config):
    """EmbeddingMatcher.encode encodes and caches names not yet in cache."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=True) as f:
        tmp_path = f.name
    # Fresh cache file — names guaranteed uncached
    matcher = EmbeddingMatcher(cache_path=tmp_path)
    if matcher._model is None:
        pytest.skip("sentence-transformers model not available")
    matcher._cache.clear()  # belt-and-suspenders: ensure empty cache
    import numpy as np
    vectors = matcher.encode(["dhl express", "intercompany"])
    assert vectors.shape[0] == 2
    # Second call hits cache for both names
    vectors2 = matcher.encode(["dhl express"])
    assert vectors2.shape[0] == 1
    assert np.allclose(vectors[0], vectors2[0])


def test_embedding_matcher_match_batch_no_candidates(config):
    """EmbeddingMatcher.match_batch returns EMBEDDING_REJECT for each query when no candidates."""
    matcher = EmbeddingMatcher(cache_path="/tmp/test_emb_mb_nocat.pkl")
    if matcher._model is None:
        pytest.skip("sentence-transformers model not available")
    results = matcher.match_batch(["acme", "sodexo australia"], [], [], config)
    assert len(results) == 2
    for _canon_id, _conf, method, _ev in results:
        assert method == "EMBEDDING_REJECT"


# ---------------------------------------------------------------------------
# FuzzyMatcher — additional corroboration coverage
# ---------------------------------------------------------------------------

def test_fuzzy_all_corroboration_signals(minimal_master_df, config):
    """All three corroboration signals (city, postcode, ABN) appear in evidence."""
    fuzzy = FuzzyMatcher(minimal_master_df, config)
    _, _, _, evidence = fuzzy.match(
        "acme xyz",
        corroboration={"same_city": True, "same_postcode": True, "same_abn": True},
    )
    assert "city_match" in evidence
    assert "postcode_match" in evidence
    assert "abn_match" in evidence


# ---------------------------------------------------------------------------
# Harmoniser — second-run matcher stage coverage
# ---------------------------------------------------------------------------

def test_harmonise_second_run_exercises_matcher_stages(in_memory_engine, config):
    """Second harmonise() run with a new single-occurrence supplier exercises det/fuzzy stages."""
    harmoniser = SupplierHarmoniser(config, in_memory_engine)

    # Run 1: establish Acme in the master (count > 1 so NORMALISED_NAME_GROUP path)
    run1_df = pd.DataFrame([
        {"raw_supplier_name": "Acme Pty Ltd",   "raw_supplier_id": "V-001"},
        {"raw_supplier_name": "ACME PTY LIMITED", "raw_supplier_id": "V-001"},
    ])
    harmoniser.harmonise(run1_df)

    # Run 2: new single-occurrence supplier — different normalised name, not in master
    # → triggers det matcher (miss) → fuzzy matcher (reject vs "acme") → NEW_CANONICAL
    run2_df = pd.DataFrame([{"raw_supplier_name": "DHL Express", "raw_supplier_id": "V-004"}])
    master_df, log_df = harmoniser.harmonise(run2_df)

    assert len(master_df) >= 2  # Acme + DHL
    dhl_log = log_df[log_df["raw_supplier_name"] == "DHL Express"]
    assert not dhl_log.empty


# ---------------------------------------------------------------------------
# ParentMapper — non-dry-run and _parse_response coverage
# ---------------------------------------------------------------------------

def test_parent_mapper_parse_response_valid_json(config):
    """_parse_response parses valid JSON and caps confidence at 0.50."""
    from src.suppliers.parent_mapper import ParentMapper
    mapper = ParentMapper(config)  # dry_run=True; no client needed

    valid_json = (
        '[{"supplier_name": "Acme", "parent_company_name": "Global Corp", "confidence": 0.9},'
        ' {"supplier_name": "DHL Express", "parent_company_name": null, "confidence": 0.0}]'
    )
    results = mapper._parse_response(valid_json, ["Acme", "DHL Express"])

    assert len(results) == 2
    acme = next(r for r in results if r["supplier_name"] == "Acme")
    assert acme["parent_company_name"] == "Global Corp"
    assert acme["confidence"] == 0.50  # capped from 0.9 to 0.50
    assert acme["method"] == "LLM_PARENT"


def test_parent_mapper_parse_response_markdown_fences(config):
    """_parse_response strips markdown code fences before JSON parsing."""
    from src.suppliers.parent_mapper import ParentMapper
    mapper = ParentMapper(config)

    fenced = (
        "```json\n"
        '[{"supplier_name": "Sodexo", "parent_company_name": null, "confidence": 0.0}]\n'
        "```"
    )
    results = mapper._parse_response(fenced, ["Sodexo"])
    assert len(results) == 1
    assert results[0]["supplier_name"] == "Sodexo"


def test_parent_mapper_parse_response_invalid_json(config):
    """_parse_response returns LLM_PARSE_ERROR when JSON is malformed."""
    from src.suppliers.parent_mapper import ParentMapper
    mapper = ParentMapper(config)

    results = mapper._parse_response("not valid json at all", ["Acme"])
    assert len(results) == 1
    assert results[0]["method"] == "LLM_PARSE_ERROR"
    assert results[0]["parent_company_name"] is None


def test_parent_mapper_no_client_returns_llm_unavailable(config, monkeypatch):
    """enrich() with dry_run=False but _client=None returns LLM_UNAVAILABLE."""
    from types import SimpleNamespace
    from src.suppliers.parent_mapper import ParentMapper

    # Set a fake API key so Anthropic client creation doesn't raise
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key-for-testing-coverage")

    non_dry_config = SimpleNamespace(
        llm=SimpleNamespace(
            dry_run=False,
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-sonnet-4-6",
            batch_size=20,
        ),
        logging=SimpleNamespace(level="WARNING", json_format=False, log_file=None),
    )
    mapper = ParentMapper(non_dry_config)
    mapper._client = None  # force no-client path

    results = mapper.enrich(["Acme Pty Ltd", "Sodexo Australia"])
    assert len(results) == 2
    assert all(r["method"] == "LLM_UNAVAILABLE" for r in results)


def test_parent_mapper_enrich_with_api_error(config, monkeypatch):
    """enrich() with a mock client that raises returns LLM_ERROR per supplier."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from src.suppliers.parent_mapper import ParentMapper

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key-for-testing-coverage")

    non_dry_config = SimpleNamespace(
        llm=SimpleNamespace(
            dry_run=False,
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-sonnet-4-6",
            batch_size=20,
        ),
        logging=SimpleNamespace(level="WARNING", json_format=False, log_file=None),
    )
    mapper = ParentMapper(non_dry_config)
    # Replace client with a mock that raises on API calls
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Simulated API failure")
    mapper._client = mock_client

    results = mapper.enrich(["Acme Pty Ltd"])
    assert len(results) == 1
    assert results[0]["method"] == "LLM_ERROR"
    assert results[0]["parent_company_name"] is None
