# Data Accuracy Fixes - Session Log

## Project Overview
- **Sprint:** `logs/sprints/2026-05-06T0121_DATA_ACCURACY_FIXES`
- **PRD:** `PRD.json`
- **Status:** In Progress
- **Started:** 2026-05-06 01:21

## Summary
Three silent data bugs fixed + backend test coverage for audit endpoints:
1. abc_segment missing from by-supplier SQL SELECT — badges always empty
2. Supplier detail Sheet shows engagement-wide data — by-month/by-category ignore supplier_id
3. column_mapping silently discarded — unit_price only works if CSV column literally named unit_price

## Decisions Made
- MAX(abc_segment) in GROUP BY — safe because all rows for a supplier share the same abc_segment after pipeline runs
- supplier_id added as Optional Query param — backwards compatible, callers that omit it get existing behaviour
- column_mapping injected as mapper.mappings['__ADHOC__'] — Ingestor is fresh per run so mutation is safe; source_row_hash computed before mapping so hashes stable
- Audit tests use execute.side_effect list to handle 4 calls in one connection block

## Story Status
| ID | Title | Status |
|----|-------|--------|
| US-001 | Add abc_segment to GET /cube/by-supplier | pending |
| US-002 | Add supplier_id filter to GET /cube/by-month | pending |
| US-003 | Add supplier_id filter to GET /cube/by-category | pending |
| US-004 | Wire column_mapping through ingest_to_raw | pending |
| US-005 | Add backend tests for audit endpoints | pending |
| US-006 | Update CLAUDE.md | pending |
