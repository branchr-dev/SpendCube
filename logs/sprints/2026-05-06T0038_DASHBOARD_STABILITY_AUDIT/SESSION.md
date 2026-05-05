# DASHBOARD STABILITY AUDIT - Session Log

## Project Overview
- **Sprint:** `logs/sprints/2026-05-06T0038_DASHBOARD_STABILITY_AUDIT`
- **PRD:** `PRD.json`
- **Status:** In Progress
- **Started:** 2026-05-06 00:38

## Summary
Fixes white-page crashes (root cause: by-supplier envelope extraction bug), adds ErrorBoundary, sets staleTime:5min on all dashboard queries, fixes CategoryPage L2 null crash + adds Back button, and adds an Ingestion Audit page with backend endpoints so clients can verify uploaded data.

## Root Cause
`/cube/by-supplier` returns `{data: SupplierRow[], total_count: N}`. Every page does `.then(r => r.data)` and stores the envelope object as `SupplierRow[]`. Calling `.filter()`/`.sort()` on a plain object throws `TypeError` → crash → white screen. No ErrorBoundary catches it.

## Decisions Made
- Fix consumers (extract `.data.data`), not the endpoint (envelope shape is correct for pagination)
- ErrorBoundary as class component (getDerivedStateFromError is class-only)
- staleTime: 5 * 60 * 1000 on all dashboard queries — data only changes on upload
- New audit route /engagements/:id/audit, nav link below Upload Data
- Audit endpoints added to existing ingestion router (same prefix, no new file)

## Story Status
| ID | Title | Status |
|----|-------|--------|
| US-001 | Add global ErrorBoundary + wrap all routes | pending |
| US-002 | Fix by-supplier extraction in SupplierPage + PaymentTermsPage | pending |
| US-003 | Fix by-supplier extraction in CategoryPage + staleTime on remaining pages | pending |
| US-004 | Fix CategoryPage L2 null crash + Back button | pending |
| US-005 | Backend ingestion batch audit endpoints | pending |
| US-006 | Ingestion Audit page + navigation | pending |
| US-007 | CLAUDE.md update | pending |
