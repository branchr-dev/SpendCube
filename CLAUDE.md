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

## Phase 4: Spend Cube and Diagnostics

Phase 4 builds a multi-dimensional spend cube from the categorised transactions table and runs 9 data quality diagnostics checks. Outputs are written to `data/output/` as Parquet files.

### Cube Architecture

The cube is built from the `transactions` table (post-Phase 3 categorisation). `SpendCubeBuilder` in `src/cube/builder.py` produces 6 output DataFrames, each saved as a separate Parquet file:

| DataFrame | Parquet file | Description |
|-----------|-------------|-------------|
| `transactions` | `transactions.parquet` | Full transaction-level detail with all canonical fields |
| `by_supplier` | `by_supplier.parquet` | Aggregated spend, transaction count, and avg payment terms per canonical supplier |
| `by_category` | `by_category.parquet` | Spend and count aggregated by UNSPSC category (L1–L4) |
| `by_bu` | `by_bu.parquet` | Spend aggregated by business unit / cost centre |
| `by_month` | `by_month.parquet` | Monthly spend trend with rolling 3-month average |
| `by_payment_terms` | `by_payment_terms.parquet` | Spend segmented by payment terms bucket (0–30, 31–60, 61–90, 90+) |

### Key Metrics Definitions

**`tail_spend`** — suppliers in the bottom 80% by transaction count that collectively contribute ≤ 20% of total spend. Identified by sorting all suppliers by transaction count ascending and finding the cutoff where cumulative spend share crosses 20%. Tail suppliers are flagged `is_tail_spend = True` in `by_supplier.parquet`.

**`maverick`** — a transaction is maverick if it has no associated PO number (`po_number IS NULL`) AND the supplier is not flagged as on-contract (`is_on_contract = False`). Maverick spend percentage = `maverick_amount / total_spend`. Stored as `is_maverick` boolean on the transaction row.

**Payment terms buckets** — `payment_terms_days` is binned into: `0-30`, `31-60`, `61-90`, `90+`. The `by_payment_terms` cube exposes working capital opportunity by showing spend concentration in early buckets.

### Data Quality Diagnostics

`DataQualityDiagnostics` in `src/cube/diagnostics.py` runs 9 checks and assigns GREEN/AMBER/RED bands:

| Check | GREEN | AMBER | RED |
|-------|-------|-------|-----|
| `missing_supplier` | < 1% rows | 1–5% | > 5% |
| `missing_category` | < 5% rows | 5–15% | > 15% |
| `missing_gl_account` | < 2% rows | 2–10% | > 10% |
| `missing_cost_centre` | < 10% rows | 10–25% | > 25% |
| `low_confidence_category` | < 10% rows below 0.60 | 10–25% | > 25% |
| `low_confidence_supplier` | < 5% rows below 0.60 | 5–15% | > 15% |
| `duplicate_transactions` | 0 duplicates | 1–5 | > 5 |
| `maverick_spend` | < 10% spend | 10–25% | > 25% |
| `tail_spend_ratio` | < 30% suppliers tail | 30–50% | > 50% |

Diagnostics output is written to `data/output/diagnostics.json` and also returned as a `DiagnosticsReport` dataclass.

### Idempotency

`make build-cube` is safe to re-run. Parquet files are overwritten on each run. No state is mutated in the SQLite database by Phase 4.

## Phase 5: Streamlit Dashboards

Phase 5 implements a 5-page Streamlit dashboard suite in `dashboard/`. All pages share a common app shell, data loader, and filter sidebar.

### App Shell

`dashboard/app.py` is the entry point. It configures the Streamlit page, renders the sidebar filter panel via `render_filters()`, and routes to the selected page module.

### Data Loading

`dashboard/data_loader.py` exposes `load_cube_data()`, which reads all Parquet files from `data/output/` (built by `make build-cube`). All data-loading functions are decorated with `@st.cache_data` to avoid re-reading Parquet files on every interaction. The cache is keyed on the Parquet file modification time so stale data is never served after a cube rebuild.

```python
@st.cache_data
def load_cube_data() -> dict[str, pd.DataFrame]:
    ...
```

### Shared Components

`dashboard/components.py` provides:
- `render_filters(data)` — renders sidebar widgets (date range, business unit, category, supplier) and returns a `FilterState` dataclass
- `render_kpi_card(label, value, delta, delta_direction)` — renders a styled metric tile
- `apply_filters(df, filters)` — applies a `FilterState` to a DataFrame and returns the filtered subset

### Chart Library

All charts use **Plotly Express** (`import plotly.express as px`). No Altair, Bokeh, or Matplotlib. This keeps chart styling consistent and enables interactivity (hover, zoom, click-to-filter) without extra dependencies.

Chart helpers in `dashboard/components/charts.py`: `horizontal_bar(df, x, y, title, max_rows)`, `donut_chart(df, names, values, title)`, `heatmap(df, x, y, values, title)`, `pareto_chart(df, x, y, title)`, `line_chart(df, x, y, title)`, `bar_chart(df, x, y, title, color)`, `boxplot(df, x, y, title)` — box plot grouped by x, `scatter_bubble(df, x, y, size, color, label, title, hover_name)` — bubble scatter, `dumbbell(df, label_col, left_col, right_col, left_name, right_name, title)` — dumbbell/lollipop for benchmark comparison.

### Cross-Filtering Pattern

Pages use Streamlit `on_select` events for within-page cross-filtering. Pattern:

1. `event = st.plotly_chart(fig, on_select="rerun", key="unique_page_key", use_container_width=True)`
2. `points = (event or {}).get("selection", {}).get("points", [])`
3. For horizontal bars: `selected = [p["y"] for p in points if "y" in p]`. For scatter with `text=`: `selected = [p.get("text") for p in points if p.get("text")]`
4. `if selected: st.caption(f"Cross-filter active: {...} — click chart background to clear")`
5. `cf = df[df[col].isin(selected)] if selected else df`. Apply `cf` to secondary charts only.

Cross-filter is within-page only — no cross-page state sharing.

### Pages

| Page module | Route label | Description |
|-------------|-------------|-------------|
| `dashboard/pages/overview.py` | Spend Overview | KPI tiles, monthly trend, top-10 suppliers, spend-by-category treemap |
| `dashboard/pages/category.py` | Category Deep Dive | Category hierarchy drill-down, supplier breakdown within category, trend |
| `dashboard/pages/supplier.py` | Supplier Deep Dive | Supplier search, spend history, category mix, payment terms distribution |
| `dashboard/pages/payment_terms.py` | Payment Terms | Bucket distribution, working capital opportunity, supplier-level terms table |
| `dashboard/pages/quality.py` | Data Quality | 9-check diagnostics scorecard with GREEN/AMBER/RED badges, drill-down tables |

### Running the Dashboard

```bash
make serve-dashboard   # Runs: streamlit run dashboard/app.py
```

Requires Phase 4 cube outputs (`data/output/*.parquet`) to exist. Run `make build-cube` first if the output directory is empty.

### Client Configuration

Client branding is controlled by the `client:` block in `config.yaml` (`name`, `engagement`, `currency_label`). The `dashboard/client_config.py` module exposes: `get_client_name()`, `get_engagement_title()`, `get_currency_label()`, `get_page_header(page_title)`, `get_data_freshness()`. All dashboard pages import from this module — never read `config.yaml` directly in a page file. To set up for a new client: edit `config.yaml` `client.name` and `client.engagement` fields.

## Phase 6: Recommendations and Review Workstation

Phase 6 (final) adds a rule-based recommendation engine and a human review workstation to close the feedback loop between analytics and action.

### Recommendation Engine

`src/recommendations/` contains five modules:

| Module | Class | Description |
|--------|-------|-------------|
| `rules.py` | `RecommendationRules` | 6 deterministic rule methods — generates recommendations from cube metrics with no LLM dependency |
| `savings_rates.py` | `SavingsRates` | Loads `data/reference/savings_rates.yaml`; provides per-lever × L1-category rate lookup with fallback to defaults |
| `deduplicator.py` | `SpendAllocator` | Prevents two recommendations from double-counting the same spend pool via exclusive group assignment |
| `narratives.py` | `NarrativeGenerator` | Optional LLM narrative enrichment (dry_run skips; batches all recs into one Claude call when live) |
| `engine.py` | `RecommendationEngine` | Orchestrator: builds cube → computes metrics → runs rules → deduplicates → enriches narratives → exports JSON |

**Rule types implemented** (saving percentages sourced from `data/reference/savings_rates.yaml`):
- `SUPPLIER_CONSOLIDATION` — categories with > 5 suppliers; default saving = 8% of addressable category spend
- `PAYMENT_TERM_EXTENSION` — top-50 suppliers with avg terms < 45 days; WC opportunity = (target − current) / 365 × addressable spend × WACC
- `TAIL_SPEND_RATIONALISATION` — tail spend > 5% threshold; default saving = 10% of addressable tail spend
- `CONTRACT_COMPLIANCE` — maverick spend > 15% threshold; default saving = 5% of addressable maverick spend
- `COMPETITIVE_TENDER` — single-source categories with spend > `competitive_tender_min_spend`; default saving = 7%
- `CONTRACT_COVERAGE_GAP` — L1 categories with contract coverage < 50% and spend > `contract_coverage_gap_min_spend`; default saving = 5%

**Output:** `data/output/recommendations.json` — wrapped object with two top-level keys. Each recommendation dict: `{type, context, evidence, estimated_impact_aud, confidence, action, lever, narrative, baseline_spend, addressability_pct, saving_pct, addressable_baseline}`.

**Wrapped JSON export format:**
```json
{
  "recommendations": [...],
  "portfolio_summary": {
    "total_spend": 0.0,
    "total_identified_savings": 0.0,
    "savings_as_pct_of_spend": 0.0,
    "sanity_check_passed": true,
    "recommendation_count": 0
  }
}
```
The engine emits a WARNING log and sets `sanity_check_passed=False` when `total_identified_savings / total_spend > 0.20`. Dashboard `_load_recommendations()` handles both wrapped and bare-list formats for backwards compatibility.

**CLI:** `python src/recommendations/engine.py --db data/db/spend_cube.db`

### Savings Rate Reference Data

`data/reference/savings_rates.yaml` holds per-lever saving rates and addressability percentages. It has two top-level keys:

- **`defaults`** — one entry per lever type, used as fallback when no category override exists
- **`categories`** — L1 category name → lever type → rate entry (overrides defaults for that category)

Each rate entry has:
- `saving_pct` — fraction of addressable baseline to use as estimated saving (omitted for `PAYMENT_TERM_EXTENSION`, which uses a WACC formula)
- `addressability_pct` — fraction of baseline spend that is addressable (see below)

**Lookup order:** `categories[category_l1][lever_type]` → `defaults[lever_type]` → hardcoded fallback `{saving_pct: None, addressability_pct: 0.70}`.

`SavingsRates.get(lever_type, category_l1=None) -> dict` is the interface. A module-level lazy singleton `get_default_rates()` avoids repeated YAML reads.

### Addressability

Not all spend in a category baseline is actionable. `addressability_pct` accounts for spend that is locked-in, regulatory-mandated, or otherwise unaddressable by the initiative even though it forms part of the category baseline.

Each rule computes:

```
addressable_baseline = baseline_spend * addressability_pct
estimated_impact_aud = addressable_baseline * saving_pct   # (or WACC formula)
```

`addressability_pct` is sourced from `savings_rates.yaml` (category-specific if available, else default for that lever). `_addressable()` in `rules.py` still strips intercompany and tax lines before computing `baseline_spend` — addressability is a separate multiplier applied afterwards.

### Double-Counting Prevention

`SpendAllocator` in `src/recommendations/deduplicator.py` prevents two recommendations from claiming the same spend pool. Each rule type belongs to an exclusive group:

| Exclusive Group | Rule Types |
|-----------------|-----------|
| `SOURCING` | `SUPPLIER_CONSOLIDATION`, `COMPETITIVE_TENDER` |
| `COVERAGE` | `CONTRACT_COVERAGE_GAP` |
| `WORKING_CAPITAL` | `PAYMENT_TERM_EXTENSION` |
| `PORTFOLIO_TAIL` | `TAIL_SPEND_RATIONALISATION` |
| `PORTFOLIO_COMPLIANCE` | `CONTRACT_COMPLIANCE` |

**Deduplication mechanism:** `pool_key = (context, exclusive_group)`. For `PORTFOLIO_*` groups the pool key is `('PORTFOLIO', exclusive_group)` (portfolio-level, not per-category). `allocate(recommendations)` sorts by `estimated_impact_aud` descending, then iterates: if `pool_key` already claimed, the recommendation is zeroed and filtered out; otherwise the pool is claimed. The input list is deep-copied to avoid mutation.

**Known limitation:** `SUPPLIER_CONSOLIDATION` context is the L2 category name; `CONTRACT_COVERAGE_GAP` context is the L1 category name. These rarely share the same string, so cross-deduplication between these two rules at the L1/L2 boundary is incomplete.

### Audit Trail Fields

Four fields are added to every recommendation dict to make the impact calculation fully traceable:

| Field | Type | Description |
|-------|------|-------------|
| `baseline_spend` | `float` | Total addressable spend before addressability reduction (intercompany/tax already stripped) |
| `addressability_pct` | `float` | Fraction of baseline that is addressable (sourced from `savings_rates.yaml`) |
| `saving_pct` | `float \| None` | Saving rate applied to addressable baseline; `None` for `PAYMENT_TERM_EXTENSION` (WACC formula used instead) |
| `addressable_baseline` | `float` | `baseline_spend × addressability_pct` — the spend the saving rate is applied to |

These fields are display-only and do not affect engine logic. The recommendations dashboard detail cards show a **Calculation Basis** section using these fields.

### Review Workstation

`dashboard/pages/99_admin_review_workstation.py` is the internal analyst review tool (renamed from `07_review_workstation.py`). It should **not** be shown to clients — it is positioned at the bottom of the Streamlit sidebar by the `99_` prefix and displays a prominent internal-use-only banner. It implements a Streamlit page with four sections:

1. **Supplier Match Review** — shows PENDING rows from `supplier_match_log`, sorted by confidence asc / spend desc. Approve / Reject / Override buttons write to DB and log to `audit_log`.
2. **Category Review Queue** — shows transactions with `category_confidence < 0.60`, sorted by abs spend desc. L1/L2 selectboxes with Override button insert to `category_overrides_table` and update the transaction row.
3. **Category Override Rules** — shows existing `category_overrides` rows with per-row Delete button and an add-new-rule form.
4. **Audit Trail** — last 50 `audit_log` entries as a dataframe.

All DB mutations call `st.cache_data.clear()` + `st.rerun()` to keep the UI consistent.

### Recommendations Dashboard Page

`dashboard/pages/06_recommendations.py` — page 6 of the dashboard suite. Loads `data/output/recommendations.json`, shows KPI tiles (total savings, count by confidence), a sortable recommendations table, a savings heatmap (type × lever), expandable detail cards, confidence filter, and Excel download.

## Phase Status — All 6 Phases Complete

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Foundation: ingestion pipeline, canonical schema, SQLite, reference data, unit tests | **Complete** |
| **Phase 2** | Supplier harmonisation (name normalisation, fuzzy + embedding matching, parent mapping) | **Complete** |
| **Phase 3** | Spend categorisation (GL rules, keywords, embeddings, LLM fallback) | **Complete** |
| **Phase 4** | Spend cube construction + data quality diagnostics | **Complete** |
| **Phase 5** | Streamlit dashboards (overview, category, supplier, payment terms, quality) | **Complete** |
| **Phase 6** | Recommendation engine + review workstation | **Complete** |

Each phase is a separate Ralph sprint. All 6 Phases Complete.

## End-to-End Pipeline

Full pipeline from raw data to recommendations and dashboard:

```bash
make install                          # Install dependencies (first run only)
make generate-test-data               # Generate synthetic test data (1000 rows)
make ingest                           # Ingest data/input/ → SQLite (Phase 1)
make harmonise                        # Supplier harmonisation (Phase 2)
make categorise                       # Spend categorisation (Phase 3)
make build-cube                       # Build Parquet cube + run recommendations (Phases 4 & 6)
make export                           # Export cube to CSV/Excel
make serve-dashboard                  # Launch Streamlit dashboard (Phases 5 & 6)
make run-tests                        # Run full test suite with coverage
```

For the full 6-phase pipeline in one command sequence:
```bash
make ingest && make harmonise && make categorise && make build-cube && make export
```

For development, the typical Phase 1 loop is:
```bash
make generate-test-data && make ingest && make run-tests
```

Integration test on 1000-row dataset (separate DB):
```bash
python src/utils/generate_test_data.py --rows 1000 --seed 42 --output data/input/test_1k.csv
python src/ingestion/ingest.py --file data/input/test_1k.csv --db data/db/spend_cube_1k.db
python src/suppliers/harmoniser.py --db data/db/spend_cube_1k.db
python src/categorisation/categoriser.py --db data/db/spend_cube_1k.db
python src/cube/pipeline.py --db data/db/spend_cube_1k.db
python src/recommendations/engine.py --db data/db/spend_cube_1k.db
```

## Definition of Done

All items verified against 1000-row integration test (2026-04-10):

- [x] Phase 1 — Ingestion pipeline ingests 1000 rows, all pass canonical schema validation
- [x] Phase 2 — Supplier harmoniser deduplicates 576 raw names to 468 canonical suppliers
- [x] Phase 3 — Categorisation achieves 83% MEDIUM+ confidence (target: 70%) in dry_run mode
- [x] Phase 4 — Spend cube built: 6 Parquet files + diagnostics scorecard exported to `data/output/`
- [x] Phase 5 — Dashboard launches with all 5 analysis pages and shared filter sidebar
- [x] Phase 6 — Recommendation engine generates ≥ 5 recommendation types from 1000-row test data (actual: 32 from 6 types)
- [x] Phase 6 — Review workstation supplier and category queues persist to DB with audit trail
- [x] Phase 6 — `data/output/recommendations.json` created and read by dashboard page 06
- [x] All unit tests pass: `pytest tests/ -v` (including `tests/test_recommendations.py` with ≥ 70% coverage)
- [x] Full pipeline runs end-to-end without errors on 1000-row synthetic dataset

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

## SpendCube v2 Architecture (React + Supabase)

SpendCube v2 migrates the Streamlit+SQLite prototype to a production-grade web application. The existing `src/` Python pipeline is preserved intact; a FastAPI backend wraps it as an HTTP adapter. The frontend is rebuilt in React+TypeScript.

### Directory Layout

```
SpendCube/
├── src/                        # Original Python pipeline (all 6 phases) — unchanged
├── tests/                      # Original pytest suite — still runs against src/
├── data/                       # Reference data, input files, SQLite DB (local dev)
├── config.yaml                 # Shared pipeline config
├── backend/                    # FastAPI backend (v2)
│   ├── app/
│   │   ├── main.py             # FastAPI app entry point + CORS + startup hook
│   │   ├── database.py         # get_engine() — routes SQLite or Postgres by URL
│   │   ├── dependencies.py     # get_current_user_email(), verify_engagement_ownership()
│   │   ├── middleware/
│   │   │   └── auth.py         # SupabaseAuthMiddleware — JWT validation, injects user_email
│   │   └── routers/
│   │       ├── engagements.py  # CRUD: GET/POST/PATCH engagements
│   │       ├── ingestion.py    # POST /upload, POST /run, GET /status/{job_id}
│   │       ├── cube.py         # GET /overview, /by-supplier, /by-category, /by-month, etc.
│   │       ├── recommendations.py  # POST /run, GET /
│   │       └── review.py       # Supplier queue, category queue, overrides, audit log
│   ├── tests/                  # Backend pytest suite (30+ tests)
│   ├── pyproject.toml
│   ├── .env.example
│   ├── Dockerfile
│   └── railway.toml
├── frontend/                   # React frontend (v2)
│   ├── src/
│   │   ├── pages/              # Page components (auth, engagements, ingest, dashboard, admin)
│   │   ├── components/         # Shared UI (KpiCard, FilterBar, charts, shadcn/ui primitives)
│   │   ├── hooks/              # useAuth, useFilters, useIngestion
│   │   ├── lib/                # supabase.ts, api.ts (Axios), utils.ts, formatters.ts
│   │   └── types/              # TypeScript interfaces
│   ├── Dockerfile              # Multi-stage: node:20-alpine build → nginx:alpine serve
│   ├── nginx.conf              # SPA routing (try_files → /index.html)
│   └── vercel.json             # Vercel SPA rewrites + build config
├── supabase/
│   └── migrations/
│       └── 001_initial_schema.sql  # Full Postgres schema with RLS policies
├── docker-compose.yml          # Local dev: backend (8000) + frontend (5173)
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions: python-tests + frontend-build
└── DEPLOYMENT.md               # Step-by-step deploy guide (Supabase + Railway + Vercel)
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend framework | React 18 + TypeScript + Vite |
| UI components | shadcn/ui (New York style, Tailwind v4) |
| Charts | Recharts (BarChart, AreaChart, PieChart, ComposedChart) |
| Frontend state | TanStack Query v5 (React Query) |
| Auth (frontend) | Supabase Auth — email+password, JWT |
| Backend framework | FastAPI 0.111+ (Python 3.11) |
| Backend ORM | SQLAlchemy Core (not ORM) — same as v1 |
| Database | Supabase Postgres (cloud) or SQLite (local dev/tests) |
| Auth (backend) | python-jose JWT validation, user_email injected via middleware |
| Pipeline | All 6 phases from src/ — called directly by FastAPI BackgroundTasks |
| Deployment (frontend) | Vercel (zero-config, SPA routing via vercel.json) |
| Deployment (backend) | Railway (Dockerfile-based, `railway.toml`) |
| Deployment (DB + Auth) | Supabase cloud |

### Multi-Tenancy

Every data table has an `engagement_id UUID` column referencing the `engagements` table. All backend queries are scoped to the authenticated user's engagement. Supabase Row Level Security (RLS) enforces this at the database layer — a misconfigured API cannot leak another tenant's data.

`engagements` table maps `owner_email` (from Supabase JWT) → `engagement_id`. A user can own multiple engagements (one per client).

### Pipeline Adapter Pattern

`src/models/database.py get_engine()` accepts either:
- A bare SQLite file path → `sqlite:///path` (backwards compatible, used by all original tests)
- A full SQLAlchemy URL (`sqlite:///:memory:`, `postgresql://...`) → passed through directly

When `SUPABASE_DATABASE_URL` env var is set, the backend uses Postgres. When absent, it falls back to `config.yaml` SQLite path. This is fully backwards-compatible — all original tests continue to use in-memory SQLite.

### Background Jobs

FastAPI `BackgroundTasks` runs the pipeline asynchronously. A `pipeline_jobs` table tracks job state (`queued` → `running` → `done`/`failed`). The frontend polls `GET /ingest/status/{job_id}` every 3 seconds for progress.

### Deployment Targets

| Service | Provider | Config file |
|---------|----------|-------------|
| Frontend | Vercel | `frontend/vercel.json` |
| Backend | Railway | `backend/railway.toml`, `backend/Dockerfile` |
| Database + Auth | Supabase cloud | `supabase/migrations/001_initial_schema.sql` |

### Environment Variables

**Backend (`backend/.env` / Railway)**

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_JWT_SECRET` | JWT secret for token validation |
| `SUPABASE_DATABASE_URL` | Postgres connection string |
| `ANTHROPIC_API_KEY` | Anthropic API key (only if `DRY_RUN=false`) |
| `SPENDCUBE_CONFIG_PATH` | Path to `config.yaml` (default: `config.yaml`) |
| `DRY_RUN` | `true` disables LLM calls (default: `true`) |
| `ALLOWED_ORIGINS` | CORS origins — set to Vercel frontend URL in production |

**Frontend (`frontend/.env` / Vercel)**

| Variable | Description |
|----------|-------------|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon key |
| `VITE_API_BASE_URL` | Backend URL (Railway URL in production; `http://localhost:8000` locally) |

### Local Development Commands

```bash
# Full stack via Docker Compose
cp backend/.env.example backend/.env   # fill in Supabase credentials
docker compose up                       # backend :8000, frontend :5173

# Or run services separately:
# Backend
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev              # Vite dev server at :5173
```

### Test Commands

```bash
# Original pipeline tests (src/)
pytest tests/ -v

# Backend API tests
pytest backend/tests/ -v

# Frontend TypeScript check + build
cd frontend && npm run build
```

## Analytics Foundation

Sprint `SPENDCUBE-ANALYTICS-FOUNDATION-2026-05` added purely additive structural extensions to support full procurement analytics across direct and indirect spend.

### 12 New Transaction Fields

Added to `CanonicalTransaction` (Pydantic) and `transactions_table` (SQLAlchemy) as nullable columns. All have `Optional` defaults so existing tests are unaffected.

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `legal_entity` | `str` | `None` | Buying legal entity code (e.g. "AU01") |
| `vendor_country` | `str` | `None` | Supplier country of origin (ISO-2) |
| `plant_country` | `str` | `None` | Receiving plant / delivery country |
| `categorisation_status` | `str` | `'uncategorised'` | `'categorised'` if confidence >= 0.60 after pipeline; populated by categoriser |
| `manual_override_flag` | `int` | `0` | 1 if classified by MANUAL override (Pass 0) |
| `ai_classification_flag` | `int` | `0` | 1 if classified by LLM (Pass 5) |
| `harmonised_payment_term` | `str` | `None` | Standardised payment term label from `payment_term_mappings` |
| `discount_percent` | `float` | `0.0` | Early payment discount rate (e.g. 2.0 = 2%) |
| `discount_days` | `int` | `0` | Days window for early payment discount |
| `has_early_payment_discount` | `int` | `0` | 1 if the payment term carries an early pay discount |
| `payment_term_confidence` | `float` | `None` | Confidence score from payment term mapping |
| `abc_segment` | `str` | `None` | ABC segment: `'A'`, `'B'`, or `'C'` — populated by cube builder |

**Population logic:**
- `categorisation_status`, `ai_classification_flag`, `manual_override_flag` are set in `SpendCategoriser.update_transactions_in_db()` after the 6-pass pipeline.
- `abc_segment` is computed in `src/cube/pipeline.py` (`_compute_abc_segments()`) after the cube is built, then written back to the transactions table.

### Three New Reference Tables (Supabase migration `002_analytics_extensions.sql`)

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| `categories` | `engagement_id`, `category_id`, `parent_category_id`, `category_level`, `category_name` | Flexible taxonomy tree (L1–L5+); replaces hardcoded L1/L2/L3 for future use |
| `legal_entities` | `engagement_id`, `legal_entity_code`, `legal_entity_name`, `country`, `currency` | Registry of buying entities; used for legal-entity spend analysis |
| `payment_term_mappings` | `engagement_id`, `raw_payment_term`, `harmonised_payment_term`, `payment_term_days`, `discount_percent`, `discount_days`, `has_early_payment_discount`, `confidence_score` | Maps raw AP payment terms to standardised terms with discount fields |

All three tables have RLS enabled with the same `owner_email = auth.jwt()->>'email'` policy pattern as `001_initial_schema.sql`.

### Five New Cube Endpoints (`backend/app/routers/cube.py`)

| Endpoint | Description |
|----------|-------------|
| `GET /cube/by-legal-entity` | Spend by legal entity (transaction_count, total_spend, supplier_count, category_count) |
| `GET /cube/by-currency` | Spend by currency (total_spend_base, total_spend_original, supplier_count) |
| `GET /cube/by-country` | Spend by vendor country (transaction_count, total_spend, supplier_count) |
| `GET /cube/abc-analysis` | Per-supplier spend with ABC segment, cumulative_spend_pct |
| `GET /cube/categorisation-quality` | Categorisation quality summary: counts by method, confidence band, and a top-50 low-confidence backlog |

All endpoints support `date_from` / `date_to` query params and enforce `verify_engagement_ownership()`.

### FilterContext Architecture (`frontend/src/contexts/FilterContext.tsx`)

`FilterContext` replaces per-page `useState` with a React Context + `useReducer` pattern so filter state is shared across all pages without prop drilling.

- `FilterProvider` wraps the app at `main.tsx` (inside `QueryClientProvider`)
- `useFilterContext()` returns `{ filters, updateFilter, clearFilters, toQueryParams }` — throws if used outside the provider
- State is initialised from URL search params on mount (date_from, date_to, array fields, min_confidence)
- `useFilters.ts` is a thin wrapper over `useFilterContext()` — existing pages call `useFilters()` unchanged

**`FilterState` analytics dimensions** (in addition to existing date/BU/category/supplier):
- `legal_entities: string[]`
- `currencies: string[]`
- `countries: string[]`
- `categorisation_statuses: string[]`
- `abc_segments: ABCSegment[]`
- `min_confidence: number | null`

### `aggregations.ts` Utility Functions (`frontend/src/lib/aggregations.ts`)

Pure data transformation functions with no React imports or API calls:

| Function | Signature | Description |
|----------|-----------|-------------|
| `calculateABCSegments` | `<T extends ABCInputRow>(rows: T[]) → ABCOutputRow<T>[]` | Sorts by spend desc, assigns A/B/C at 80%/95% cumulative thresholds |
| `calculateSpendConcentration` | `(rows, topN) → { top_n_spend, top_n_pct, total_spend }` | Top-N concentration metrics |
| `getTopN` | `<T>(rows, n) → T[]` | Generic sort by spend/total_spend, sliced to N |
| `calculateTailSpendMetrics` | `(rows) → { tail_supplier_count, tail_spend, tail_pct, core_supplier_count }` | Core = suppliers to 80% of spend; tail = remainder |
| `formatSpendSummary` | `(totalSpend, currency) → { formatted, millions, billions, scale }` | Formats to K/M/B with currency prefix |

### DrilldownState Pattern (`frontend/src/hooks/useDrilldown.ts`)

`useDrilldown()` manages a history stack for within-page drill-down navigation:

```typescript
type DrilldownLevel = 'overview' | 'category_l1' | 'category_l2' | 'supplier' | 'transaction'

interface DrilldownState {
  level: DrilldownLevel
  category_l1?: string
  category_l2?: string
  supplier_id?: string
  supplier_name?: string
}
```

- `drillTo(level, context)` — pushes new state onto the stack
- `drillUp()` — pops to the previous level
- `reset()` — clears stack back to `{ level: 'overview' }`
- `isFiltered` — `true` when level is not `'overview'`

`DrilldownBreadcrumb` (`frontend/src/components/DrilldownBreadcrumb.tsx`) renders nothing when `level === 'overview'`. For deeper levels it renders clickable path segments (shadcn/ui `Button` + `ChevronRight`) with the current level as plain text.

### ABC Segmentation Convention

ABC segmentation follows the Pareto convention, computed from `SUM(base_amount)` per canonical supplier sorted descending:

| Segment | Threshold | Meaning |
|---------|-----------|---------|
| **A** | Cumulative spend ≤ 80% of total | High-value suppliers — priority for contract and sourcing activity |
| **B** | Cumulative spend > 80% and ≤ 95% | Mid-value suppliers — opportunistic renegotiation |
| **C** | Cumulative spend > 95% | Low-value / tail suppliers — consolidation or rationalisation candidates |

Computed server-side in `_compute_abc_segments()` in `src/cube/pipeline.py` (Step 1b of the Phase 4 pipeline) and stored as `abc_segment TEXT` on every transaction row. Also available client-side via `calculateABCSegments()` in `aggregations.ts` for in-browser chart rendering.

## Dashboard UX Conventions (Sprint A)

### Semantic Colours

Defined in `frontend/src/components/charts/constants.ts` and mirrored as CSS custom properties in `frontend/src/index.css`:

```ts
export const SEMANTIC_COLORS = {
  opportunity: '#10b981',  // emerald-500 — positive signal, savings, WC gain
  risk:        '#f43f5e',  // rose-500   — high fragmentation, maverick spend
  attention:   '#f59e0b',  // amber-500  — moderate concern, review needed
  neutral:     '#64748b',  // slate-500  — context/informational, no signal
}
```

CSS custom properties (`:root`): `--color-opportunity`, `--color-risk`, `--color-attention`, `--color-neutral`.  
Tailwind aliases (`tailwind.config.js` `theme.extend.colors`): `opportunity`, `risk`, `attention` — enables `bg-opportunity/10`, `text-risk`, etc.

Use `SEMANTIC_COLORS` for Recharts `fill`/`stroke` props. Use Tailwind aliases for non-chart UI elements.

### KpiCard — `accentColor` and `benchmarkLabel` Props

`frontend/src/components/dashboard/KpiCard.tsx`

- `accentColor?: 'green' | 'amber' | 'red' | 'opportunity' | 'risk' | 'neutral'` — adds a 4px left border to the Card:
  - `opportunity` → `border-l-4 border-l-emerald-500`
  - `risk` → `border-l-4 border-l-rose-500`
  - `neutral` → `border-l-4 border-l-slate-300`
  - `green/amber/red` → standard green-500/amber-500/red-500
- `benchmarkLabel?: string` — renders a small italic line below the delta (`text-xs text-muted-foreground italic mt-1`)
- Omitting `accentColor` renders a plain card with no left border (backwards compatible)

Example usage:
```tsx
<KpiCard label="WC Opportunity" value={wcTotal} valueType="currency"
  accentColor="opportunity" benchmarkLabel="vs. 45-day target" />
```

### SpendTreemap Component

`frontend/src/components/charts/SpendTreemap.tsx` — exported from `frontend/src/components/charts/index.ts`

Props:
```ts
data: { name: string; value: number; color?: string }[]
title: string
valueFormatter?: (v: number) => string
onCellClick?: (name: string) => void
```

- Renders `section-header` title, then a `ResponsiveContainer` wrapping Recharts `Treemap` (height 320)
- Cell labels (name truncated to 16 chars + formatted value) shown only when cell is wide enough (`width > 60 && height > 40`)
- Falls back to `CHART_COLORS[index % length]` when no per-item `color`
- Empty state (`data.length === 0` or all-zero values): renders `h-80` centred "No data available" message

### SpendBarChart — New Props

`frontend/src/components/charts/SpendBarChart.tsx`

- `showLabel?: boolean` (default `false`) — adds a Recharts `LabelList`: `position='right'` for horizontal bars, `position='top'` for vertical. Font size 11, fill `#64748b`. Uses `valueFormatter` if provided.
- `clickHint?: boolean` (default `false`) — when `true` and `onBarClick` is provided, renders `"Click a bar to explore"` italic hint aligned right beside the chart title.
- `colors?: string[]` — per-bar fill via `Cell` components; index-mapped. Falls back to `CHART_COLORS[0]` for out-of-range indices.
- Empty/undefined `data` renders `h-64` "No data available" instead of the chart.

### `.section-header` CSS Class

Defined in `frontend/src/index.css` `@layer utilities`:
```css
.section-header {
  @apply text-sm font-semibold border-l-2 border-primary pl-2 mb-3;
}
```

Use for chart section titles (`<h3 className="section-header">`) inside chart containers. `SpendTreemap` applies it automatically. For pages, apply manually to `<h3>` tags inside chart containers (replacing `text-sm font-medium mb-3`).

### Chart Container Class Convention

All chart wrapper `<div>` elements use:
```
className="border rounded-xl p-5 bg-card shadow-sm"
```

Applied on `OverviewPage` and `CategoryPage` chart containers (Sprint A). Replaces the older `border rounded-lg p-4` pattern.

### Sheet Drawer — Supplier Detail Panel Pattern

`SupplierPage` uses `shadcn/ui Sheet` (right-side drawer) for supplier detail. Pattern:

```tsx
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'

<Sheet open={!!selectedSupplierId} onOpenChange={(open) => { if (!open) setSelectedSupplierId(null) }}>
  <SheetContent side="right" className="w-[500px] sm:w-[560px] overflow-y-auto p-6">
    <SheetHeader>
      <SheetTitle>{selectedSupplier?.canonical_supplier_name ?? ''}</SheetTitle>
    </SheetHeader>
    {/* KPI row + charts */}
  </SheetContent>
</Sheet>
```

- Clicking an already-selected table row closes the drawer (toggle via `setSelectedSupplierId(null)`)
- Detail charts query with `supplier_id` param; render empty state if backend returns `[]`

### FilterBar — Collapsed and Expanded States

`frontend/src/components/dashboard/FilterBar.tsx`

- **Collapsed (default, `expanded=false`):** single flex row with an "Filters [N]" outline button + removable badge pills for each active filter + "Clear all" text link. Active filters as `{ label, onRemove }` objects derived from all `FilterState` fields.
- **Expanded (`expanded=true`):** full filter UI (all selects/date inputs) with a "Close ↑" ghost button to collapse.
- State: `const [expanded, setExpanded] = useState(false)` — starts collapsed on every page load.
- Active pill sources: `date_from`, `date_to`, `business_units[]`, `category_l1s[]`, `supplier_search`, `legal_entities[]`, `currencies[]`, `countries[]`, `abc_segments[]`.
