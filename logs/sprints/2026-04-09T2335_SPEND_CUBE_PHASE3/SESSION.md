# SpendCube Phase 3 - Spend Categorisation — Session Log

## Project Overview
- **Sprint:** `logs/sprints/2026-04-09T2335_SPEND_CUBE_PHASE3`
- **PRD:** `PRD.json`
- **Status:** In Progress
- **Started:** 2026-04-09
- **Phase:** 3 of 6

## Summary
6-pass hybrid categorisation pipeline. Strict pass order ensures deterministic methods run first and LLM is last resort only. Validation gate: ≥80% of sample rows at MEDIUM or HIGH confidence.

## Pipeline Pass Order
```
Pass 0: Category overrides (DB table)      → confidence 1.0, method=MANUAL
Pass 1: GL code mapping (seed_mappings)    → confidence 0.90+, method=DETERMINISTIC_GL
Pass 2: Supplier mapping (seed_mappings)   → confidence 0.85+, method=DETERMINISTIC_SUPPLIER
Pass 3: Keyword rules (keyword_rules.yaml) → confidence 0.75-0.85, method=KEYWORD
Pass 4: Embedding similarity (MiniLM)      → confidence=similarity*0.9, method=EMBEDDING
Pass 5: LLM fallback (Claude API)          → confidence capped 0.70, method=LLM
→ Review queue: confidence < 0.60
```

## Key Design Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pass order | Deterministic first | LLM only as last resort — strict spec requirement |
| LLM confidence cap | 0.70 | Always lower than deterministic methods — per spec |
| Review queue | < 0.60 (MEDIUM) | Aligns with config.categorisation.confidence_medium |
| Keyword rules | YAML file | Configurable outside code, easy to extend |
| Embedding cache | data/cache/category_embeddings.pkl | Avoid recomputing category vectors each run |
| GL matching | Exact then prefix (4 digits) | Handles stripped leading zeros from Phase 1 sample |

## Story Status
| ID | Title | Status |
|----|-------|--------|
| US-001 | Create internal category hierarchy and keyword rules | ○ |
| US-002 | Implement deterministic GL and supplier categorisation | ○ |
| US-003 | Implement keyword rule-based categorisation | ○ |
| US-004 | Implement embedding-based category classifier | ○ |
| US-005 | Implement LLM fallback categoriser | ○ |
| US-006 | Implement categoriser orchestrator | ○ |
| US-007 | Integrate with Makefile and validate sample data | ○ |
| US-008 | Write Phase 3 unit tests | ○ |
| US-009 | Update CLAUDE.md with Phase 3 patterns | ○ |
