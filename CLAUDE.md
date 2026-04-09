# CLAUDE.md — SpendCube Project Context

This file documents the SpendCube codebase for Claude Code sessions. Read this before making changes.

## Project Purpose

SpendCube is a procurement spend analytics pipeline for consulting and client diagnostic engagements. It ingests raw AP/ERP exports (CSV or Excel), harmonises messy supplier names, categorises spend against UNSPSC, and produces a clean spend cube (Parquet) with Streamlit dashboards and recommendation narratives. Designed to handle the reality of real-world client data: variant supplier names, mixed date formats, multi-currency, missing fields, intercompany transactions, and tax lines.

## Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Data manipulation | pandas >= 2.0 |
| Schema validation | pydantic v2 |
| Database layer | SQLAlchemy Core (not ORM) + SQLite |
| Fuzzy matching | rapidfuzz >= 3.0 |
| Embedding similarity | sentence-transformers >= 2.2 |
| LLM integration | anthropic SDK >= 0.25 |
| Dashboard | Streamlit >= 1.30 |
| Output format | Parquet (pyarrow) |
| Config | YAML (pyyaml) |
| Testing | pytest + pytest-cov + faker |

## Key Design Decisions

**SQLAlchemy Core, not ORM** — all table definitions in `src/models/database.py` use `Table`, `Column`, and `MetaData` directly. No declarative base, no relationships, no lazy loading. SQL is explicit and readable.

**Pydantic v2 with `use_enum_values=True`** — `CanonicalTransaction` uses `model_config = ConfigDict(populate_by_name=True, use_enum_values=True)`. Enum fields store their `.value` (string), not the enum object. This is intentional for JSON serialisation compatibility.

**Confidence scoring 0–1 with bands** — all categorisation and matching operations produce a `float` confidence score. `ConfidenceBand.get_band(score)` maps to `HIGH` (>= 0.85), `MEDIUM` (0.60–0.85), `LOW` (< 0.60). Only `LOW` band scores trigger LLM fallback.

**LLM is last resort, not first pass** — categorisation runs deterministic GL rules → keyword matching → embedding similarity → LLM fallback. The LLM is called only when all prior methods score below `categorisation.llm_fallback_threshold` (default 0.60). This keeps costs low and results auditable.

**`dry_run: true` is the default** — `config.yaml` has `llm.dry_run: true`. No Anthropic API calls happen unless this is explicitly set to `false` and `ANTHROPIC_API_KEY` is set. This prevents accidental spend during development.

**DD/MM/YYYY assumed for ambiguous dates** — the date parser tries formats in order: DD/MM/YYYY → YYYY-MM-DD → DD-Mon-YYYY → M/D/YYYY → dateutil fallback. Always assume Australian convention (day-first) before US convention (month-first) for ambiguous inputs like `5/4/2024`.

**Raw data preserved** — every ingested row stores all original source columns as JSON in the `raw_data` column. Transformations are fully reversible and auditable.

**Postgres-compatible types** — although SQLite is used in Phase 1, all column types are chosen to migrate cleanly to Postgres. No `BLOB`, no `REAL` for money (use `NUMERIC`), no SQLite-specific pragmas in schema definitions.

## LLM Usage Policy

The LLM (Claude via Anthropic API) is used **only** for:

1. **Uncategorised spend** — transactions with categorisation confidence below 0.60 after deterministic + embedding methods
2. **Parent company identification** — identifying ultimate parent entities for supplier master records
3. **Recommendation narratives** — generating human-readable narrative summaries of consolidation/WC opportunities
4. **Description enrichment** — expanding abbreviated or cryptic line descriptions where needed

The LLM is **not** used for: date parsing, currency conversion, column mapping, deduplication, or any task solvable deterministically.

## Phase 2: Supplier Harmonisation

Phase 2 implements a 5-stage supplier harmonisation pipeline in `src/suppliers/`. Each stage processes only the suppliers not resolved by earlier stages.

**Pipeline order (strict):** normalise → deterministic → fuzzy → embedding → LLM

| Stage | Module | Description |
|-------|--------|-------------|
| 1. Normalise | `normaliser.py` | Lowercase, strip legal suffixes, expand abbreviations, strip T/A prefixes, collapse whitespace. Runs on every supplier name before any matching. |
| 2. Deterministic | `matcher.py` | Exact match on normalised name (confidence 0.95) or exact vendor ID (confidence 0.99). |
| 3. Fuzzy | `matcher.py` | rapidfuzz composite: `token_sort_ratio * 0.40 + token_set_ratio * 0.40 + partial_ratio * 0.20`. Corroboration boosts (city, postcode, ABN) added as flat points. Auto-accept threshold: 88; review threshold: 70. |
| 4. Embedding | `embeddings.py` | sentence-transformers `all-MiniLM-L6-v2`, cosine similarity on normalised names. Embeddings cached to `data/cache/supplier_embeddings.pkl`. Auto threshold: 0.90; review threshold: 0.80. |
| 5. LLM | `parent_mapper.py` | Parent company identification only. Batches 20 suppliers per call. Only runs when `config.llm.dry_run = false`. |

**`canonical_supplier_id` generation** — SHA256 of the normalised supplier name, first 12 hex characters. Example: `hashlib.sha256(normalised_name.encode()).hexdigest()[:12]`. IDs are stable and reproducible across pipeline runs (not random UUIDs).

**Confidence bands** — `ConfidenceBand.get_band(score)` in `src/models/schema.py`:
- `HIGH`: score >= 0.85
- `MEDIUM`: score >= 0.60
- `LOW`: score < 0.60

**Review queue** — any raw supplier with `supplier_match_confidence < 0.60` is written to `supplier_match_log` with `review_status = PENDING`. These require human review before downstream use.

**LLM parent enrichment** — results are always capped at confidence 0.50 (LOW band), never auto-accepted. Always goes to the review queue regardless of LLM output confidence. Only runs when `dry_run = false`.

**Idempotency** — the harmoniser checks `canonical_supplier_id` against the existing `supplier_master` before inserting. Running twice on the same input leaves row counts unchanged.

## Phase 3: Spend Categorisation

Phase 3 implements a 6-pass hybrid categorisation pipeline in `src/categorisation/`. Each pass processes only the transactions not yet classified at or above the confidence threshold (0.60) by earlier passes.

**Pipeline order (strict):** overrides → GL → supplier → keyword → embedding → LLM

| Pass | Method | Module | Description |
|------|--------|--------|-------------|
| 0. Overrides | `MANUAL` | `deterministic.py` | Reads `category_overrides` table — matches on `canonical_supplier_id` OR `gl_account`. Highest priority, always checked first. Confidence = 1.0. |
| 1. GL mapping | `DETERMINISTIC_GL` | `deterministic.py` | Exact GL code match first, then GL prefix (first 4 digits). Uses `category_seed_mappings.csv` rows with `mapping_type='GL'`. Confidence 0.85–0.95. |
| 2. Supplier mapping | `DETERMINISTIC_SUPPLIER` | `deterministic.py` | Case-insensitive match on `canonical_supplier_name` against seed mappings (`mapping_type='SUPPLIER'`). Confidence 0.85–0.95. |
| 3. Keyword rules | `KEYWORD` | `deterministic.py` | Regex rules from `data/reference/keyword_rules.yaml` applied to `cleaned_description + raw_line_description`. First (highest-confidence) matching rule wins. Confidence 0.75–0.85. |
| 4. Embedding similarity | `EMBEDDING` | `embedding_classifier.py` | sentence-transformers `all-MiniLM-L6-v2`, cosine similarity against category description embeddings. Confidence = `top_similarity * 0.9`. Ambiguous (top-2 within 0.05): `top_similarity * 0.75`. Embeddings cached to `data/cache/category_embeddings.pkl`. |
| 5. LLM fallback | `LLM` | `llm_classifier.py` | Claude API, batched (20 items per call). Only runs when `config.llm.dry_run = false` AND item is still below `llm_fallback_threshold=0.60` after pass 4. Confidence always capped at **0.70** regardless of model output. |

**Confidence caps per method:**
- `MANUAL` (overrides): 1.0
- `DETERMINISTIC_GL` / `DETERMINISTIC_SUPPLIER`: 0.85–0.95 (from seed mapping row)
- `KEYWORD`: 0.75–0.85 (from rule definition in YAML)
- `EMBEDDING`: `top_similarity * 0.9` (max ~0.90 in practice)
- `LLM`: capped at 0.70 unconditionally

**Review queue** — any transaction with `category_confidence < 0.60` after all passes is included in the review queue, sorted by `abs(base_amount)` descending (highest spend reviewed first). Items in the review queue have `category_method = None`.

**`category_overrides` as feedback mechanism** — the `category_overrides` table (defined in `src/models/database.py`) stores human-reviewed corrections keyed on `canonical_supplier_id` or `gl_account`. Writing a row here causes Pass 0 to apply it as an override on all future runs. Use `SpendCategoriser.apply_feedback()` to insert overrides programmatically.

**`llm_fallback_threshold`** — configured in `config.yaml` under `categorisation.llm_fallback_threshold` (default 0.60). The LLM is invoked only when `dry_run=false` and the transaction is still below this threshold after pass 4.

**Idempotency** — running categoriser twice on the same transactions skips rows already classified at >= MEDIUM confidence (0.60) unless `--force` is passed.

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Foundation: ingestion pipeline, canonical schema, SQLite, reference data, unit tests | **Complete** |
| **Phase 2** | Supplier harmonisation (name normalisation, fuzzy + embedding matching, parent mapping) | **Complete** |
| **Phase 3** | Spend categorisation (GL rules, keywords, embeddings, LLM fallback) | **Complete** |
| Phase 4 | Spend cube construction + data quality diagnostics | Planned |
| Phase 5 | Streamlit dashboards (overview, category, supplier, payment terms, quality) | Planned |
| Phase 6 | Recommendation engine + review workstation | Planned |

Each phase is a separate Ralph sprint. Do not implement Phase 3+ logic in Phase 1–2 modules — use `# TODO: Phase N` comments as placeholders where needed.

## Running the Pipeline

```bash
make install           # Install dependencies
make generate-test-data  # Generate synthetic test data
make ingest            # Ingest data/input/ → SQLite
make harmonise         # Supplier harmonisation (Phase 2)
make categorise        # Categorisation (Phase 3)
make build-cube        # Build Parquet spend cube (Phase 4)
make serve-dashboard   # Launch Streamlit (Phase 5)
make run-tests         # Run full test suite with coverage
make export            # Export cube to CSV/Excel
```

For development, the typical Phase 1 loop is:
```bash
make generate-test-data && make ingest && make run-tests
```

For the full 3-phase pipeline (ingest → harmonise → categorise):
```bash
make ingest && make harmonise && make categorise
```

## Reference Data

All reference data is in `data/reference/` and is bundled with the project:

| File | Description |
|------|-------------|
| `unspsc_v24.csv` | ~500-commodity UNSPSC subset covering common procurement categories (full v24 is proprietary) |
| `fx_rates.csv` | Monthly average FX rates 2023–2025 for AUD, USD, EUR, GBP, SGD, NZD, JPY, CNY |
| `legal_suffixes.yaml` | 40+ entity suffix patterns for supplier name normalisation (Pty Ltd, P/L, Inc, GmbH, etc.) |
| `abbreviation_map.yaml` | 30+ abbreviation expansions (AUST → Australia, INTL → International, etc.) |
| `category_seed_mappings.csv` | 200+ seed mappings from supplier name / GL code / keyword → UNSPSC category |

These files are deliberately curated subsets — not full licensed datasets. They are sufficient for Phase 1 validation and will be extended in later phases.
