# SpendCube Phase 1 - Foundation — Session Log

## Project Overview
- **Sprint:** `logs/sprints/2026-04-09T1736_SPEND_CUBE_PHASE1`
- **PRD:** `PRD.json`
- **Status:** In Progress
- **Started:** 2026-04-09
- **Phase:** 1 of 6

## Summary
Phase 1 establishes the complete foundation for the SpendCube procurement analytics system: project structure, configuration, canonical pydantic v2 schema, SQLite database setup, reference data files, structured logging, synthetic test data generator, and the full ingestion pipeline (date parser, currency converter, cleaner, column mapper, CSV/Excel loader).

**Validation gate:** Ingest the 10-row messy sample dataset → clean canonical transactions table + 15+ passing unit tests.

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Schema validation | pydantic v2 | Typed, validated, serialisable canonical schema |
| Database layer | SQLAlchemy Core (not ORM) | Explicit SQL, no magic, Postgres-compatible types |
| Config | Single config.yaml | One source of truth for all thresholds and paths |
| Date parsing | DD/MM/YYYY-first chain | Australian convention; dateutil fallback for edge cases |
| Monetary precision | Decimal | No float precision loss on monetary amounts |
| LLM default | dry_run: true | No accidental API calls during development |
| Raw data | raw_data JSON column | Full reversibility — every transformation auditable |

## Architecture Overview
```
data/input/sample.csv (or client CSV)
       ↓
ColumnMapper      → renames source cols to canonical names (YAML-driven)
       ↓
DataCleaner       → whitespace, nulls, payment terms, boolean flags
       ↓
DateParser        → multi-format → date objects
       ↓
CurrencyConverter → original_amount + base_amount (AUD)
       ↓
Ingestor          → UUID, timestamps, raw_data JSON
       ↓
SQLite (transactions table)
```

## Reference Data Bundled
- `data/reference/unspsc_v24.csv` — ~500 commodity subset
- `data/reference/fx_rates.csv` — 2023-2025 monthly averages, 8 currencies
- `data/reference/legal_suffixes.yaml` — 40+ entity suffix patterns
- `data/reference/abbreviation_map.yaml` — 30+ abbreviation expansions
- `data/reference/category_seed_mappings.csv` — 200+ supplier/GL/keyword → category mappings

## Story Status
| ID | Title | Status |
|----|-------|--------|
| US-001 | Create project directory structure and Makefile | ○ |
| US-002 | Create config.yaml and config loader | ○ |
| US-003 | Implement canonical transaction schema with pydantic v2 | ○ |
| US-004 | Implement SQLite database setup with SQLAlchemy Core | ○ |
| US-005 | Create reference data files | ○ |
| US-006 | Implement structured logging utility | ○ |
| US-007 | Implement multi-format date parser | ○ |
| US-008 | Implement currency converter | ○ |
| US-009 | Implement data cleaner | ○ |
| US-010 | Implement flexible column mapper | ○ |
| US-011 | Implement ingestion pipeline orchestrator and create sample.csv | ○ |
| US-012 | Implement synthetic test data generator | ○ |
| US-013 | Write Phase 1 unit tests | ○ |
| US-014 | Write README.md and CLAUDE.md | ○ |

## Subsequent Phases (separate sprints)
- **Phase 2:** Supplier harmonisation (name normalisation, fuzzy matching, entity resolution)
- **Phase 3:** Spend categorisation (GL mapping, keyword rules, embeddings, LLM fallback)
- **Phase 4:** Spend cube construction + data quality diagnostics
- **Phase 5:** Streamlit dashboards (overview, category, supplier, payment terms, quality)
- **Phase 6:** Recommendation engine + review workstation

## Sample Dataset (Phase 1 Validation Target)
The 10-row messy dataset exercises all ingestion edge cases:
- Duplicate supplier variants: Acme Pty Ltd / ACME PTY LIMITED / acme p/l
- Duplicate supplier variants: SODEXO AUSTRALIA / Sodexo Aust P/L
- Mixed date formats: DD/MM/YYYY, YYYY-MM-DD, DD-Mon-YYYY, M/D/YYYY
- Credit note: CN-2024-001 (negative amount + CN prefix)
- Intercompany: INTERCOMPANY - LEGAL (is_intercompany=True)
- Tax line: TAX-ADJ-001 with GL 2100100 (balance sheet → is_tax_line=True)
- Foreign currency: DHL row in USD → converted to AUD
- Missing fields: blank VENDOR_NAME, missing PO_NUM, missing COST_CTR
- GL code variants: 6420100 vs 642010 (leading zero stripped)
- Cost centre variants: CC-MKT-01 vs MKT01

## Notes
- Full spec provided upfront — no clarifying questions needed
- This is a 6-phase project; each phase is a separate Ralph sprint
- Phase 1 is greenfield — no existing codebase to read/extend
