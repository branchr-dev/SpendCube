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
def debug():
    from jose import jwt as jose_jwt, JWTError

    secret = os.getenv("SUPABASE_JWT_SECRET", "")
    db_url = os.getenv("SUPABASE_DATABASE_URL", "")

    # Verify JWT secret by decoding the known anon key
    ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV5YmJ5ZGpleWpycGJiZGlncXJxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc4NzUyMTcsImV4cCI6MjA5MzQ1MTIxN30.2GKmF1T9tnoTx8lxGPGZ1wFFe6ipJGOTtppO3KVdqxY"
    jwt_secret_valid = False
    jwt_secret_error = ""
    try:
        jose_jwt.decode(ANON_KEY, secret, algorithms=["HS256"], options={"verify_aud": False})
        jwt_secret_valid = True
    except JWTError as e:
        jwt_secret_error = str(e)

    # Test DB connection
    db_ok = False
    db_error = ""
    if db_url:
        try:
            from sqlalchemy import create_engine, text
            eng = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception as e:
            db_error = str(e)

    return {
        "jwt_secret_set": bool(secret),
        "jwt_secret_length": len(secret),
        "jwt_secret_valid": jwt_secret_valid,
        "jwt_secret_error": jwt_secret_error,
        "db_url_set": bool(db_url),
        "db_connection_ok": db_ok,
        "db_error": db_error,
    }
