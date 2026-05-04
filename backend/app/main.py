import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.auth import SupabaseAuthMiddleware
from app.routers import engagements, ingestion, cube, recommendations, review

app = FastAPI(title="SpendCube API", version="2.0.0")

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in allowed_origins_raw.split(",")] if allowed_origins_raw != "*" else ["*"]

app.add_middleware(SupabaseAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(engagements.router)
app.include_router(ingestion.router)
app.include_router(cube.router)
app.include_router(recommendations.router)
app.include_router(review.router)


@app.on_event("startup")
async def _reset_stuck_jobs() -> None:
    db_url = os.getenv("SUPABASE_DATABASE_URL")
    if not db_url:
        return
    try:
        from app.database import get_engine
        from sqlalchemy import text

        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE pipeline_jobs SET status = 'failed', "
                    "error_message = 'Server restarted' WHERE status = 'running'"
                )
            )
    except Exception:
        pass


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/debug")
async def debug():
    import httpx
    supabase_url = os.getenv("SUPABASE_URL", "")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    db_url = os.getenv("SUPABASE_DATABASE_URL", "")
    allowed = os.getenv("ALLOWED_ORIGINS", "")

    supabase_reachable = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{supabase_url}/auth/v1/health", headers={"apikey": anon_key})
            supabase_reachable = r.status_code == 200
    except Exception as e:
        supabase_reachable = str(e)

    return {
        "env_vars_set": {
            "SUPABASE_URL": bool(supabase_url),
            "SUPABASE_ANON_KEY": bool(anon_key),
            "SUPABASE_DATABASE_URL": bool(db_url),
            "ALLOWED_ORIGINS": allowed,
        },
        "supabase_url_value": supabase_url[:40] if supabase_url else "(not set)",
        "supabase_auth_reachable": supabase_reachable,
    }
