# SpendCube v2 — React + Supabase — Session Log

## Project Overview
- **Sprint:** `logs/sprints/2026-05-03T1244_SPENDCUBE_V2_REACT_SUPABASE`
- **PRD:** `PRD.json`
- **Status:** In Progress
- **Started:** 2026-05-03 12:44

## Summary
Migrate SpendCube from a Streamlit+SQLite prototype to a production-grade React+FastAPI+Supabase web application. All 6 phases of the Python analytics pipeline are preserved as a FastAPI backend. The frontend is rebuilt in React+TypeScript with shadcn/ui and Recharts. Multi-tenancy via engagement_id. Deployable to Vercel + Railway + Supabase cloud.

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Monorepo layout | frontend/ + backend/ alongside src/ | Pipeline logic untouched; clean separation |
| Parquet files | Eliminated in v2 — cube data from Postgres views | No filesystem state in cloud deployment |
| Pipeline DB adapter | get_engine() extended to accept full URL | Zero changes to pipeline logic; backwards-compatible |
| Multi-tenancy | engagement_id UUID on all 5 tables + new engagements table | One deployment, many clients; RLS enforced in Supabase |
| Background jobs | FastAPI BackgroundTasks + pipeline_jobs table | Avoids Celery/Redis complexity for v1 |
| Charts | shadcn/ui + Recharts | TypeScript-native, composable, no proprietary deps |
| Frontend state | TanStack Query v5 | Standard for React server-state management |
| Auth | Supabase Auth JWT, email extracted from claims | Free, battle-tested, RLS integration |
| Deployment | Vercel + Railway + Supabase cloud | Zero-config deploys, no DevOps overhead |

## Key Files Modified/Created

### Existing files changed
- `src/models/database.py` — get_engine() accepts full DB URL; engagement_id columns added (nullable for backwards compat)
- `src/config.py` — PathsConfig.database_url optional field added

### New directories
- `backend/` — FastAPI application
- `frontend/` — React application
- `supabase/migrations/` — SQL schema

## Story Status

| ID | Title | Status |
|----|-------|--------|
| US-001 | Monorepo structure — scaffold backend/ and frontend/ | not started |
| US-002 | Supabase SQL schema migration | not started |
| US-003 | FastAPI auth middleware + engagements CRUD | not started |
| US-004 | Pipeline database adapter — Postgres support | not started |
| US-005 | Ingestion API endpoints — upload, map, run | not started |
| US-006 | Cube data query endpoints — all 5 views | not started |
| US-007 | Recommendations and review workstation API | not started |
| US-008 | React frontend scaffold | not started |
| US-009 | Auth pages, engagement selector, upload wizard | not started |
| US-010 | Shared dashboard components | not started |
| US-011 | Spend Overview and Category Deep Dive pages | not started |
| US-012 | Supplier Deep Dive and Payment Terms pages | not started |
| US-013 | Data Quality and Recommendations pages | not started |
| US-014 | Admin Review Workstation page | not started |
| US-015 | Deployment config, CI/CD, CLAUDE.md update | not started |

## Critical Risks to Watch

1. **Postgres type compatibility** — invoice_date stored as TEXT; v_by_month casts ::date. Validate with integration test before deploying.
2. **RLS policy** — misconfigured policy silently returns empty results. Test in Supabase Studio before go-live.
3. **SpendCubePipeline Parquet output** — check if output_dir=None is safe; may need to pass /tmp path and discard.
4. **sentence-transformers model** — pre-download in Dockerfile to avoid cold-start delays.
