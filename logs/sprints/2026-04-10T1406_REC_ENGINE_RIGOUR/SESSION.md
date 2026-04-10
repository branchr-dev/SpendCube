# Recommendation Engine Rigour — Session Log

## Project Overview
- **Sprint:** `logs/sprints/2026-04-10T1406_REC_ENGINE_RIGOUR`
- **PRD:** `PRD.json`
- **Status:** In Progress
- **Started:** 2026-04-10

## Problems Identified (code audit)

| # | Problem | Location |
|---|---------|----------|
| 1 | Hardcoded flat saving % | `config.yaml:recommendations.consolidation_saving_pct` |
| 2 | No addressability % | `rules.py:_addressable()` only strips intercompany/tax |
| 3 | Double-counting | `SUPPLIER_CONSOLIDATION` + `CONTRACT_COVERAGE_GAP` can both claim same category spend |
| 4 | No audit trail | Output dict lacks baseline_spend, rate, addressability fields |
| 5 | Hardcoded thresholds | `50_000` and `20_000` literals in rules.py |

## Key Decisions

| Decision | Choice |
|----------|--------|
| Category rates | `data/reference/savings_rates.yaml` (defaults + per-L1-category overrides) |
| Addressability | Applied per-rule: `addressable_baseline = baseline_spend * addressability_pct` |
| Double-counting | `SpendAllocator` with exclusive groups: SOURCING, COVERAGE, WORKING_CAPITAL, PORTFOLIO_TAIL, PORTFOLIO_COMPLIANCE |
| Audit trail | 4 new fields on every rec dict: `baseline_spend`, `addressability_pct`, `saving_pct`, `addressable_baseline` |
| Sanity check | Warn if total savings > 20% of total spend |
| JSON export | Wrapped `{recommendations: [...], portfolio_summary: {...}}` |

## Story Status

| ID | Title | Status |
|----|-------|--------|
| US-001 | Create savings_rates.yaml | ○ |
| US-002 | Create SavingsRates lookup module | ○ |
| US-003 | Update config with addressability defaults | ○ |
| US-004 | Update rules.py to use SavingsRates and apply addressability | ○ |
| US-005 | Create SpendAllocator deduplication module | ○ |
| US-006 | Wire SpendAllocator and portfolio summary into engine.py | ○ |
| US-007 | Update recommendations dashboard | ○ |
| US-008 | Add tests | ○ |
| US-009 | Update CLAUDE.md | ○ |

## Known Limitations
- SpendAllocator uses `context` field as pool key. SUPPLIER_CONSOLIDATION context = L2 category name; CONTRACT_COVERAGE_GAP context = L1 category name. These rarely match the same string, so L1/L2 cross-deduplication is incomplete. Documented as known limitation in CLAUDE.md.
