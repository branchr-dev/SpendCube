import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.auth import SupabaseAuthMiddleware
from app.routers import engagements, ingestion, cube

app = FastAPI(title="SpendCube API", version="2.0.0")

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in allowed_origins_raw.split(",")] if allowed_origins_raw != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SupabaseAuthMiddleware)

app.include_router(engagements.router)
app.include_router(ingestion.router)
app.include_router(cube.router)


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
