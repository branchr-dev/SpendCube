# SpendCube — Consultant Handover Guide

This document is the primary reference for a consultant taking over SpendCube to run it for a client.
It covers everything from understanding what the tool does to deploying it and running your first
engagement. For pure deployment steps, see `DEPLOYMENT.md`. For architecture internals, see `CLAUDE.md`.

---

## Overview

SpendCube is a procurement spend analytics platform. You give it a raw AP or ERP export (CSV or Excel)
and it produces a clean spend cube with interactive dashboards and a prioritised savings recommendation
report.

**What it does in plain English:**

1. **Ingests** raw supplier invoices — handles messy supplier names, mixed currencies, date formats, and
   missing fields that are common in client exports.
2. **Harmonises** supplier names — deduplicates variant spellings (e.g. "Accenture", "ACCENTURE PTY LTD",
   "Accenture Australia") into a single canonical supplier entry.
3. **Categorises** every transaction against the UNSPSC taxonomy using GL codes, keyword rules, and
   machine learning (embedding similarity + optional Claude AI fallback).
4. **Builds a spend cube** — aggregated views by supplier, category, business unit, month, and payment terms.
5. **Generates recommendations** — six types of procurement opportunity (supplier consolidation, payment
   term extension, tail spend rationalisation, contract compliance, competitive tender, contract coverage
   gaps) with estimated savings in AUD.
6. **Presents dashboards** — a React web app with six pages: Overview, Recommendations, Category, Supplier,
   Payment Terms, and Data Quality.

**Who it is for:** Procurement consultants running diagnostic engagements. A client uploads their AP export;
the tool does the analytical heavy lifting. The consultant then presents the findings and recommendations.

---

## Architecture

SpendCube has three layers. You do not need to understand the code to run it, but knowing the layers
helps when something goes wrong.

### Layer 1 — Python Pipeline (`src/`)

Six processing phases run server-side when a file is uploaded:

| Phase | What it does |
|-------|-------------|
| Ingestion | Reads CSV/Excel, validates rows, flags credit notes and intercompany lines, converts currency |
| Supplier harmonisation | Normalises names, fuzzy-matches to canonical supplier master, assigns confidence scores |
| Categorisation | Maps each transaction to a UNSPSC category (up to 6 passes: GL code → supplier → keyword → embedding → LLM) |
| Cube build | Aggregates transactions into 6 Parquet files and runs 9 data quality checks |
| ABC segmentation | Classifies suppliers as A (top 80% of spend), B (80–95%), or C (tail) |
| Recommendations | Applies 6 rule types to the cube to identify savings opportunities |

### Layer 2 — FastAPI Backend (`backend/`)

A Python web API that:
- Accepts file uploads and queues them for pipeline processing
- Exposes REST endpoints for the frontend to query cube data and recommendations
- Validates authentication via Supabase JWTs
- Enforces data isolation — each client engagement is scoped to a unique `engagement_id`

### Layer 3 — React Frontend (`frontend/`)

A TypeScript/React web application that:
- Provides login (email + password via Supabase Auth)
- Allows creating engagements (one per client), uploading data, and monitoring pipeline progress
- Renders six dashboard pages with interactive charts

### Hosting

| Component | Where it runs |
|-----------|-------------|
| Database + Auth | Supabase (managed Postgres + authentication) |
| Backend API | Railway (Docker container) |
| Frontend web app | Vercel (static hosting with SPA routing) |

Data never leaves Supabase. Railway and Vercel are stateless — they read from and write to the Supabase
Postgres database.

---

## Prerequisites

Before you start, make sure you have accounts and tools ready:

**Accounts (all have free tiers sufficient for a single engagement):**
- [ ] Supabase account — [supabase.com](https://supabase.com)
- [ ] Railway account — [railway.app](https://railway.app)
- [ ] Vercel account — [vercel.com](https://vercel.com)
- [ ] GitHub account with the SpendCube repository pushed to it

**Local tools (for running the Python pipeline locally or the evaluation harness):**
- [ ] Python 3.11 or later — `python3 --version`
- [ ] Node.js 20 or later (only needed for local frontend dev) — `node --version`
- [ ] Git — `git --version`
- [ ] `make` — available by default on macOS and Linux

**Optional:**
- [ ] Docker Desktop — only needed if running the full stack locally via Docker Compose
- [ ] Anthropic API key — only needed if you want LLM-powered categorisation (disabled by default)

---

## Local Development

Use this to test the pipeline against a client file before deploying to production, or to run the
evaluation harness.

### Install dependencies

```bash
cd /path/to/SpendCube
make install
```

This installs all Python dependencies into a virtual environment.

### Run the pipeline locally (SQLite, no cloud required)

```bash
# Generate 1000-row synthetic test data (or place a real client CSV in data/input/)
make generate-test-data

# Run all 6 pipeline phases end-to-end
make ingest && make harmonise && make categorise && make build-cube

# Launch the Streamlit dashboard (Phase 5 prototype — not the React v2 app)
make serve-dashboard
```

The Streamlit dashboard runs at `http://localhost:8501`. This is a self-contained local prototype
useful for quick diagnostics and client demos without any cloud accounts.

### Run the full React stack locally (Docker Compose)

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and fill in your Supabase credentials
docker compose up
```

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`

---

## Supabase Setup

Supabase is the database and authentication layer. Set this up first — Railway and Vercel both
depend on it.

### 1. Create a Supabase project

1. Log in at [supabase.com](https://supabase.com) and click **New project**.
2. Choose a region close to your client (e.g. Sydney for Australian clients).
3. Wait 1–2 minutes for the project to provision.

### 2. Copy your credentials

Go to **Settings → API** and copy:
- **Project URL** — you'll use this as `SUPABASE_URL` and `VITE_SUPABASE_URL`
- **anon public key** — you'll use this as `SUPABASE_ANON_KEY` and `VITE_SUPABASE_ANON_KEY`
- **JWT Secret** — you'll use this as `SUPABASE_JWT_SECRET`

Go to **Settings → Database → Connection string** (URI format) and copy the full string.
You'll use this as `SUPABASE_DATABASE_URL`.

### 3. Enable the pgvector extension

SpendCube uses pgvector for caching ML embeddings. Enable it before running migrations.

In the Supabase dashboard, go to **SQL Editor** and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Click **Run**. You should see "Success. No rows returned."

### 4. Apply migrations in order

There are three migration files. They **must** be applied in this exact order:

| Order | File | What it creates |
|-------|------|----------------|
| 1st | `supabase/migrations/001_initial_schema.sql` | Core tables: engagements, transactions, supplier_master, pipeline_jobs, audit_log |
| 2nd | `supabase/migrations/002_analytics_extensions.sql` | Extended analytics tables: categories, legal_entities, payment_term_mappings |
| 3rd | `supabase/migrations/003_data_model_hardening.sql` | Incremental ingestion tables: transactions_raw, ingestion_batches, embedding caches |

**Option A — Supabase CLI (recommended):**

```bash
npx supabase login
npx supabase link --project-ref <your-project-ref>
npx supabase db push
```

The CLI picks up all three files from `supabase/migrations/` and applies them in filename order.

**Option B — SQL Editor (manual):**

Open each file in a text editor, copy its contents, and paste into **SQL Editor → New query** in the
Supabase dashboard. Run each file separately, in the order listed above.

After applying all three migrations, go to **Table Editor** and verify these tables exist:
`engagements`, `transactions`, `transactions_raw`, `supplier_master`, `ingestion_batches`.

---

## Backend Deployment (Railway)

### 1. Create a Railway project

1. Log in at [railway.app](https://railway.app) and click **New Project**.
2. Select **Deploy from GitHub repo** and authorise Railway to access your repository.
3. Choose the SpendCube repository.
4. In the service settings, set **Root Directory** to `backend/`.
5. Railway detects the `Dockerfile` automatically via `backend/railway.toml`.

### 2. Add environment variables

In Railway, go to your service → **Variables** tab and add all backend variables from the
[Environment Variables Reference](#environment-variables-reference) table below.

### 3. Deploy

Railway deploys automatically once variables are saved. Watch the **Deployments** tab for the build log.
A successful deploy shows a green checkmark and a public URL like `https://spendcube-backend.railway.app`.

Copy this URL — you'll need it for the frontend.

---

## Frontend Deployment (Vercel)

### 1. Create a Vercel project

1. Log in at [vercel.com](https://vercel.com) and click **Add New → Project**.
2. Import your GitHub repository.
3. In **Configure Project**, set **Root Directory** to `frontend/`.
4. Vercel detects `frontend/vercel.json` and uses `npm run build` automatically.

### 2. Add environment variables

In Vercel project settings → **Environment Variables**, add the three frontend variables from the
[Environment Variables Reference](#environment-variables-reference) table below.

Include your Railway backend URL as `VITE_API_BASE_URL`.

### 3. Deploy

Click **Deploy**. Vercel builds the React app and serves it from a URL like `https://spendcube.vercel.app`.

### 4. Wire backend CORS

Back in Railway → **Variables**, set `ALLOWED_ORIGINS` to your Vercel URL (no trailing slash):

```
ALLOWED_ORIGINS=https://spendcube.vercel.app
```

Railway redeploys automatically. The backend will now accept requests from the frontend.

---

## Environment Variables Reference

### Backend (Railway)

| Variable | Service | Required | Description |
|----------|---------|----------|-------------|
| `SUPABASE_URL` | Backend | Yes | Supabase project URL (e.g. `https://xyz.supabase.co`) |
| `SUPABASE_ANON_KEY` | Backend | Yes | Supabase anon/public key (Settings → API) |
| `SUPABASE_JWT_SECRET` | Backend | Yes | JWT secret for token validation (Settings → API) |
| `SUPABASE_DATABASE_URL` | Backend | Yes | Postgres connection string (Settings → Database → Connection string) |
| `SPENDCUBE_CONFIG_PATH` | Backend | Yes | Path to config file — set to `config.yaml` |
| `ALLOWED_ORIGINS` | Backend | Yes | Comma-separated CORS origins — set to your Vercel frontend URL |
| `DRY_RUN` | Backend | Yes | `true` disables LLM calls (recommended unless Anthropic key is set) |
| `ANTHROPIC_API_KEY` | Backend | No | Anthropic API key — only required when `DRY_RUN=false` |

### Frontend (Vercel)

| Variable | Service | Required | Description |
|----------|---------|----------|-------------|
| `VITE_SUPABASE_URL` | Frontend | Yes | Supabase project URL (same as `SUPABASE_URL`) |
| `VITE_SUPABASE_ANON_KEY` | Frontend | Yes | Supabase anon/public key (same as `SUPABASE_ANON_KEY`) |
| `VITE_API_BASE_URL` | Frontend | Yes | Railway backend URL (e.g. `https://spendcube-backend.railway.app`) |

---

## First Engagement Walkthrough

Follow these steps after deployment to run your first client engagement end-to-end.

### Step 1 — Create an engagement via the UI

1. Navigate to your Vercel URL and sign up (or log in) with your email and password.
2. On the **Engagements** page, click **New Engagement**.
3. Enter the client name, engagement title, and currency (AUD for Australian clients).
4. Click **Create**. You are taken to the engagement dashboard.

An engagement is a data container scoped to one client. All data, pipeline outputs, and
recommendations are isolated per engagement.

### Step 2 — Upload a CSV on the Upload page

1. In the engagement sidebar, click **Upload Data**.
2. Click **Choose file** and select the client's AP export CSV.
   - Supported column names include common ERP headers for vendor name, invoice number, date,
     amount, currency, GL code, cost centre, and payment terms. The system maps common variants
     automatically.
   - For a test run, use `data/input/test_1k.csv` (1000-row synthetic dataset).
3. Click **Upload and Run Pipeline**. The file is uploaded and the pipeline queues.

### Step 3 — Wait for pipeline completion

The pipeline runs asynchronously. The Upload page polls `GET /ingest/status/{job_id}` every 3 seconds
and shows a progress indicator. Typical completion times:

| Dataset size | Expected time |
|-------------|-------------|
| 500 rows | 30–60 seconds |
| 1,000 rows | 1–2 minutes |
| 10,000 rows | 5–10 minutes |

Wait until the status shows **Complete** before navigating to dashboards. If the status shows **Failed**,
check the Railway deployment logs for the error message.

### Step 4 — View the Overview dashboard

1. Click **Overview** in the sidebar.
2. The Overview page shows total spend, transaction count, average payment terms, and top-10 suppliers.
3. Use the filter bar to narrow by date range, business unit, or category.
4. Click a supplier bar to navigate to the Supplier page; click a category treemap cell to navigate
   to the Category page.

### Step 5 — Review the Recommendations page

1. Click **Recommendations** in the sidebar.
2. The page shows the total identified savings, a lever summary strip, and individual recommendation cards.
3. Each card shows the opportunity type, estimated savings, confidence level, and a suggested action.
4. Click the **Download Excel** button to export a recommendations table suitable for a client deliverable.

---

## Running the Evaluation Harness

Before delivering findings to a client, run the evaluation harness to verify pipeline output quality.
The harness runs the full 6-phase pipeline against a temporary SQLite database and prints a
structured report with PASS/WARN/FAIL verdicts.

### Quick run (200-row synthetic data)

From the project root:

```bash
python3 scripts/evaluate_pipeline.py
```

This generates 200 synthetic rows, runs all pipeline phases, prints a 5-section report, and deletes
the temporary files. No side effects on production data.

### Run against a real client file

```bash
python3 scripts/evaluate_pipeline.py --csv /path/to/client_export.csv
```

### Run and keep the SQLite DB for inspection

```bash
python3 scripts/evaluate_pipeline.py --csv /path/to/client_export.csv --db /tmp/eval_output.db
```

### Interpreting the report

The report has five sections:

| Section | Key metric | PASS threshold | WARN threshold |
|---------|-----------|----------------|----------------|
| 1 Ingestion | Row count, credit notes, intercompany flags | (informational) | — |
| 2 Supplier Harmonisation | Canonical supplier count, confidence band breakdown | (informational) | — |
| 3 Categorisation | `coverage_pct` — rows with confidence ≥ 0.60 | ≥ 70% | ≥ 50% |
| 4 Recommendations | Recommendation count | ≥ 3 | ≥ 1 |
| 4 Recommendations | Sanity check (savings ≤ 20% of total spend) | True | — |
| 5 Data Quality | Per-check GREEN/AMBER/RED status | (informational) | — |

A `FAIL` verdict on categorisation coverage means the dataset has too many uncategorised transactions
to produce reliable recommendations. Common causes: non-standard GL codes not in the seed mapping, or
generic line descriptions with no keywords.

---

## Troubleshooting

### pgvector extension missing

**Symptom:** Pipeline fails with `ERROR: type "vector" does not exist` in Railway logs.

**Fix:** In the Supabase SQL Editor, run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then re-run the pipeline job. The `vector` type is required for storing ML embeddings in Postgres.

---

### CORS error on API calls

**Symptom:** The frontend shows a network error and the browser console logs `CORS policy blocked`.

**Fix:** In Railway → Variables, ensure `ALLOWED_ORIGINS` is set to the exact Vercel URL with no
trailing slash. For example:

```
ALLOWED_ORIGINS=https://spendcube.vercel.app
```

If you have both a preview and a production URL, separate them with a comma:

```
ALLOWED_ORIGINS=https://spendcube.vercel.app,https://spendcube-git-main.vercel.app
```

Saving the variable triggers an automatic Railway redeploy.

---

### JWT validation failure

**Symptom:** All API calls return HTTP 401 with message `Invalid token` or `JWT signature failed`.

**Cause:** The `SUPABASE_JWT_SECRET` in Railway does not match the JWT secret in your Supabase project.

**Fix:**
1. In Supabase → Settings → API, copy the **JWT Secret** value.
2. In Railway → Variables, update `SUPABASE_JWT_SECRET` with the copied value.
3. Railway redeploys. Clear browser storage (Supabase auth tokens) and log in again.

---

### Pipeline job stuck in 'queued'

**Symptom:** After uploading a file, the status stays `queued` indefinitely and the progress bar
does not advance.

**Causes and fixes:**

1. **Backend crashed on startup** — Check Railway → Deployments → the latest deployment logs.
   A startup error (e.g. missing environment variable) prevents the background task worker from
   starting. Fix the error and redeploy.

2. **Database connection failed** — Verify `SUPABASE_DATABASE_URL` is the full URI string from
   Supabase Settings → Database → Connection string. It should start with `postgresql://`.

3. **Pipeline exception swallowed** — Check Railway logs filtered by the `running` keyword.
   The pipeline catches exceptions and marks jobs as `failed`, but the job status endpoint may
   show `queued` if the job never started.

---

### Empty dashboard after successful upload

**Symptom:** The pipeline status shows `Complete` but all KPIs show zero and charts are blank.

**Causes and fixes:**

1. **Wrong engagement selected** — Confirm the engagement ID in the URL matches the one you uploaded
   to. Each engagement is isolated.

2. **Cube Parquet files not written** — The cube build phase writes to `data/output/`. On Railway,
   this is ephemeral (container filesystem). Verify the backend is writing to the Supabase Postgres
   `transactions` table, not just local files.

3. **Date filter excluding all data** — Check the filter bar. If the date range is set to a period
   before the invoice dates in the uploaded file, all charts will be empty. Click **Clear all** on
   the filter bar and reload.

4. **CSV column mapping failed silently** — Download the pipeline log from the Upload page and check
   for `WARNING: No rows passed validation`. This means the CSV columns could not be mapped to the
   expected schema. Ensure the CSV has recognisable column headers for vendor name, invoice date, and
   amount.

---

## Notes for Client Delivery

- Set `DRY_RUN=true` in Railway variables unless you have explicitly configured an Anthropic API key.
  With `DRY_RUN=true`, the pipeline skips LLM categorisation and relies on deterministic rules and
  embeddings — sufficient for 70–85% categorisation coverage on most datasets.
- Run `python3 scripts/evaluate_pipeline.py --csv <client_file.csv>` before the client presentation
  to verify pipeline quality on the actual data.
- The Review Workstation page (accessible at the bottom of the sidebar) is for internal use only.
  It exposes supplier match review, category override rules, and the full audit log. Do not share
  this page with clients during workshops.
- Recommendations are deterministic and fully auditable. Each card shows a **Calculation Basis**
  section with `baseline_spend`, `addressability_pct`, `saving_pct`, and `addressable_baseline`.
  These figures can be explained to a CFO without referencing the underlying code.
