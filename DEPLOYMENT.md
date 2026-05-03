# SpendCube v2 — Deployment Guide

## Prerequisites

- Supabase account (supabase.com)
- Railway account (railway.app)
- Vercel account (vercel.com)
- GitHub repository with SpendCube v2 code pushed

## Required Environment Variables

### Backend (Railway)

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Your Supabase project URL (e.g. `https://xyz.supabase.co`) |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret (Settings → API) |
| `SUPABASE_DATABASE_URL` | Postgres connection string (Settings → Database → Connection string) |
| `ANTHROPIC_API_KEY` | Anthropic API key (only needed if `DRY_RUN=false`) |
| `SPENDCUBE_CONFIG_PATH` | Path to config file — set to `config.yaml` |
| `DRY_RUN` | `true` to disable LLM calls (recommended for first deploy) |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins (your Vercel frontend URL) |

### Frontend (Vercel)

| Variable | Description |
|----------|-------------|
| `VITE_SUPABASE_URL` | Your Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `VITE_API_BASE_URL` | Your Railway backend URL (e.g. `https://spendcube-backend.railway.app`) |

---

## Step 1: Create Supabase Project

1. Log in to supabase.com and create a new project.
2. Wait for the project to provision.
3. Go to **Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon public** key → `SUPABASE_ANON_KEY`
   - **JWT Secret** → `SUPABASE_JWT_SECRET`
4. Go to **Settings → Database → Connection string** (URI format) and copy → `SUPABASE_DATABASE_URL`
5. Apply the schema migration:

```bash
npx supabase login
npx supabase link --project-ref <your-project-ref>
npx supabase db push
```

The migration file is at `supabase/migrations/001_initial_schema.sql`.

---

## Step 2: Deploy Backend to Railway

1. Go to railway.app and create a new project.
2. Click **Deploy from GitHub repo** and select your repository.
3. In the service settings, set **Root Directory** to `backend/`.
4. Railway detects the `Dockerfile` automatically (via `railway.toml`).
5. Add all backend environment variables from the table above under **Variables**.
6. Deploy. Railway will build the Docker image and start the service.
7. Copy the generated Railway domain (e.g. `https://spendcube-backend.railway.app`) — you'll need it for Step 4.

---

## Step 3: Deploy Frontend to Vercel

1. Go to vercel.com and click **Add New Project**.
2. Import your GitHub repository.
3. In project settings, set **Root Directory** to `frontend/`.
4. Vercel detects `vercel.json` and uses `npm run build` with output from `dist/`.
5. Add the `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` environment variables.
6. Deploy. Note your Vercel URL (e.g. `https://spendcube.vercel.app`).

---

## Step 4: Wire Backend and Frontend Together

1. In Vercel project settings → **Environment Variables**, add:
   - `VITE_API_BASE_URL` = your Railway backend URL from Step 2
2. Redeploy the frontend (Vercel → Deployments → Redeploy).
3. In Railway project settings → **Variables**, add:
   - `ALLOWED_ORIGINS` = your Vercel frontend URL from Step 3
4. Railway redeploys automatically when variables change.

---

## Step 5: First Login and Test

1. Navigate to your Vercel URL.
2. Sign up using **Supabase Auth** (email + password).
3. Create a new **Engagement** — enter client name, engagement title, and currency.
4. Upload test data: go to the engagement, click **Upload Data**, and use the sample file at `data/input/test_1k.csv`.
5. Map columns if needed, then click **Run Pipeline**.
6. Monitor progress on the upload page — the pipeline runs: ingest → harmonise → categorise → build cube.
7. Navigate to **Spend Overview** once the pipeline completes.

---

## Local Development

```bash
# Option A: Docker Compose (full stack)
cp backend/.env.example backend/.env   # fill in your values
docker compose up

# Option B: Separate processes
# Terminal 1 — backend
cd backend
SUPABASE_DATABASE_URL=... uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

---

## Troubleshooting

- **Empty data after pipeline**: Check Railway logs for errors in the pipeline stages. Common issue: `SUPABASE_DATABASE_URL` missing or incorrect.
- **Auth errors (401)**: Verify `SUPABASE_JWT_SECRET` matches the value in Supabase Settings → API.
- **CORS errors**: Ensure `ALLOWED_ORIGINS` in Railway includes the exact Vercel URL (no trailing slash).
- **LLM calls failing**: Set `DRY_RUN=true` to disable Anthropic API calls if the key is not configured.
