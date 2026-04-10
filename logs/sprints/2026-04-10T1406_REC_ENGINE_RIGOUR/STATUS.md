# Sprint Status

**Status:** in_progress
**Started:** 2026-04-10 14:06
**Completed:** -

## Quick Links
- PRD: `PRD.json`
- Session: `SESSION.md`
- Progress: `PROGRESS.txt`

## Summary
Replace flat-rate double-counting engine with rigorous, auditable system: category-specific savings rates (savings_rates.yaml), addressability % per lever × category, SpendAllocator deduplication, 4 audit trail fields per rec, portfolio sanity check.

## Stories
- US-001: Create data/reference/savings_rates.yaml
- US-002: Create src/recommendations/savings_rates.py
- US-003: Update config.py + config.yaml (addressability_defaults, min-spend thresholds)
- US-004: Update rules.py (use SavingsRates, apply addressability, add audit fields)
- US-005: Create src/recommendations/deduplicator.py (SpendAllocator)
- US-006: Wire SpendAllocator + portfolio summary into engine.py
- US-007: Update dashboard/pages/06_recommendations.py (audit trail display)
- US-008: Add tests (TestSavingsRates, TestSpendAllocator, TestRulesAuditFields)
- US-009: Update CLAUDE.md
