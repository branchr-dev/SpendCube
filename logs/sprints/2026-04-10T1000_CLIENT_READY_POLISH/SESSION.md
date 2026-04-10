# Client Ready Polish — Session Log

## Project Overview
- **Sprint:** `logs/sprints/2026-04-10T1000_CLIENT_READY_POLISH`
- **PRD:** `PRD.json`
- **Status:** In Progress
- **Started:** 2026-04-10

## Summary
Transform the dashboard from a developer tool into a client-presentable product. 10 issues identified and scoped.

## Issues Found (Audit)
| # | Issue | Fix |
|---|-------|-----|
| 1 | `make build-cube` visible in UI (12 instances) | Replace with "contact your analyst" |
| 2 | `dry_run=true or LLM skipped` on Recommendations | Replace with "Narrative not available" |
| 3 | "Procurement analytics pipeline" on homepage | Replace with professional language |
| 4 | No client name in any header | client_config.py + config.yaml client: block |
| 5 | Default Streamlit theme | .streamlit/config.toml navy theme |
| 6 | Review Workstation visible to clients | Rename to 99_ + internal banner |
| 7 | Homepage too sparse | Redesign with engagement title + data freshness |
| 8 | No data freshness indicator | Compute from ingested_at in transactions.parquet |
| 9 | No page descriptions | st.caption() after st.title() on pages 01-04 |
| 10 | 'AUD' hardcoded across pages | get_currency_label() from client_config |

## Key Decisions
- **client_config**: New `dashboard/client_config.py` reads `config.yaml` `client:` block. Pure Python, no streamlit import.
- **Review Workstation**: `git mv` to `99_admin_review_workstation.py` — goes to bottom of sidebar, gets internal banner
- **Theme**: navy #1B4F72 primary, white background — professional, no logo needed
- **Currency**: reads `spend_cube.base_currency` from config as fallback

## Story Status
| ID | Title | Status |
|----|-------|--------|
| US-001 | Create .streamlit/config.toml + client: block in config.yaml | ○ |
| US-002 | Create dashboard/client_config.py | ○ |
| US-003 | Redesign app.py homepage | ○ |
| US-004 | Remove developer strings from pages 01-06 | ○ |
| US-005 | Add page descriptions + rename Review Workstation | ○ |
| US-006 | Update CLAUDE.md | ○ |

## Notes
- `ingested_at` in transactions.parquet is ISO string format, parse with pd.to_datetime
- client_config.py must NOT import streamlit (called before st.set_page_config in app.py)
- Streamlit derives sidebar label from filename: `99_admin_review_workstation` → "Admin Review Workstation"
