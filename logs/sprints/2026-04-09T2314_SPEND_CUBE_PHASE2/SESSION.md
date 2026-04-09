# SpendCube Phase 2 - Supplier Harmonisation — Session Log

## Project Overview
- **Sprint:** `logs/sprints/2026-04-09T2314_SPEND_CUBE_PHASE2`
- **PRD:** `PRD.json`
- **Status:** In Progress
- **Started:** 2026-04-09
- **Phase:** 2 of 6

## Summary
Builds the supplier harmonisation pipeline on top of the Phase 1 foundation. 5-stage pipeline: normalise → deterministic → fuzzy → embedding → LLM parent enrichment. Produces supplier_master and supplier_match_log tables. Populates canonical supplier fields on transactions.

**Validation gate:** Acme x3 and Sodexo x2 from sample.csv correctly merged into single canonical entries.

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| canonical_supplier_id | SHA256(normalised_name)[:12] | Stable, reproducible across runs (not UUID) |
| Pipeline flow | 5 stages, each returns (matched, unmatched) | Unmatched only passed to next stage — efficient |
| Fuzzy composite | token_sort*0.4 + token_set*0.4 + partial*0.2 | Handles abbreviations, reordering, partial names |
| Embedding cache | data/cache/supplier_embeddings.pkl | Avoid recomputing on repeated runs |
| LLM parent confidence | Capped at 0.50 | Always requires human review — never auto-accepted |
| Review queue threshold | confidence < 0.60 | Config: categorisation.confidence_medium |
| Over-strip protection | Empty result → fallback to lowercase original | Prevents e.g. 'Group Pty Ltd' → '' |

## 5-Stage Pipeline Architecture
```
unique raw suppliers
       ↓
Stage 1: SupplierNormaliser    → normalised_name (always runs)
       ↓
Stage 2: DeterministicMatcher  → exact name / exact vendor ID
       ↓ (unmatched only)
Stage 3: FuzzyMatcher          → rapidfuzz composite score + corroboration
       ↓ (unmatched only)
Stage 4: EmbeddingMatcher      → sentence-transformers cosine similarity
       ↓ (all canonical suppliers)
Stage 5: ParentMapper          → LLM parent company enrichment (dry_run aware)
       ↓
supplier_master + supplier_match_log → transactions updated
```

## Story Status
| ID | Title | Status |
|----|-------|--------|
| US-001 | Implement supplier name normaliser | ○ |
| US-002 | Implement deterministic and fuzzy matcher | ○ |
| US-003 | Implement embedding-based matcher | ○ |
| US-004 | Implement LLM parent company enrichment | ○ |
| US-005 | Implement supplier master builder | ○ |
| US-006 | Implement harmoniser orchestrator | ○ |
| US-007 | Integrate with Makefile and end-to-end pipeline | ○ |
| US-008 | Write Phase 2 unit tests | ○ |
| US-009 | Update CLAUDE.md with Phase 2 patterns | ○ |

## Validation Targets
```
Input (sample.csv):          Output (supplier_master):
Acme Pty Ltd     ─┐
ACME PTY LIMITED  ├─→ 1 canonical "Acme Pty Ltd"  (canonical_supplier_id: sha256('acme')[:12])
acme p/l         ─┘
SODEXO AUSTRALIA ─┬─→ 1 canonical "Sodexo Australia" (sha256('sodexo australia')[:12])
Sodexo Aust P/L  ─┘
```
