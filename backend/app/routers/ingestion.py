import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import tempfile
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import get_engine
from app.dependencies import get_current_user_email, verify_engagement_ownership

router = APIRouter(
    prefix="/api/engagements/{engagement_id}/ingest",
    tags=["ingestion"],
)


def _engine() -> Engine:
    return get_engine()


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_file(
    engagement_id: str,
    file: UploadFile,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".csv", ".xlsx"):
        raise HTTPException(status_code=400, detail="File must be .csv or .xlsx")

    job_id = str(uuid4())
    tmp_path = f"/tmp/spendcube_{job_id}{ext}"

    content = await file.read()
    with open(tmp_path, "wb") as fh:
        fh.write(content)

    if ext == ".csv":
        df_header = pd.read_csv(tmp_path, nrows=1)
        row_count_estimate = max(0, content.count(b"\n") - 1)
    else:
        df_header = pd.read_excel(tmp_path, nrows=1)
        row_count_estimate = max(0, content.count(b"\n") - 1)

    return {
        "job_id": job_id,
        "file_path": tmp_path,
        "columns": df_header.columns.tolist(),
        "row_count_estimate": row_count_estimate,
    }


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    job_id: str
    file_path: str
    column_mapping: dict[str, str]


@router.post("/run")
async def run_pipeline_endpoint(
    engagement_id: str,
    body: RunRequest,
    background_tasks: BackgroundTasks,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pipeline_jobs (id, engagement_id, status, started_at) "
                "VALUES (:id, :engagement_id, 'queued', :started_at)"
            ),
            {"id": body.job_id, "engagement_id": engagement_id, "started_at": now},
        )

    background_tasks.add_task(
        _run_pipeline, engagement_id, body.job_id, body.file_path, body.column_mapping
    )

    return {"job_id": body.job_id, "status": "queued"}


# ---------------------------------------------------------------------------
# GET /status/{job_id}
# ---------------------------------------------------------------------------

@router.get("/status/{job_id}")
async def get_job_status(
    engagement_id: str,
    job_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, status, stage, started_at, completed_at, error_message, batch_id "
                "FROM pipeline_jobs WHERE id = :job_id AND engagement_id = :engagement_id"
            ),
            {"job_id": job_id, "engagement_id": engagement_id},
        ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": row["id"],
        "status": row["status"],
        "stage": row["stage"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "error_message": row["error_message"],
        "batch_id": row["batch_id"],
    }


# ---------------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------------

def _update_job(engine: Engine, job_id: str, **kwargs) -> None:
    set_clauses = ", ".join(f"{k} = :{k}" for k in kwargs)
    kwargs["job_id"] = job_id
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE pipeline_jobs SET {set_clauses} WHERE id = :job_id"),
            kwargs,
        )


def _run_pipeline(
    engagement_id: str,
    job_id: str,
    file_path: str,
    column_mapping: dict,
    config_path: str = "config.yaml",
) -> None:
    import logging

    logger = logging.getLogger(__name__)
    db_url = os.environ["SUPABASE_DATABASE_URL"]
    bg_engine = get_engine()

    try:
        # Imports are inside try so missing src/ raises a caught, reported failure
        from src.config import load_config
        from src.models.database import get_engine as src_get_engine, init_db
        from src.ingestion.ingest import Ingestor
        from src.ingestion.promoter import IncrementalPromoter
        from src.cube.pipeline import run_pipeline as run_cube_pipeline

        # Stage 1: ingesting — write to transactions_raw via ingest_to_raw()
        _update_job(bg_engine, job_id, status="running", stage="ingesting")

        config = load_config(config_path)
        src_engine = src_get_engine(db_url)
        init_db(src_engine)

        ingestor = Ingestor(config)
        ingest_result = ingestor.ingest_to_raw(
            file_path, src_engine, engagement_id, source_system=None
        )
        batch_id = ingest_result["batch_id"]
        logger.info(
            "ingest_to_raw complete: batch_id=%s new_rows=%s duplicate_rows=%s",
            batch_id,
            ingest_result["new_rows"],
            ingest_result["duplicate_rows"],
        )

        # Store batch_id on the pipeline_jobs row so it is retrievable via /status
        with bg_engine.begin() as conn:
            conn.execute(
                text("UPDATE pipeline_jobs SET batch_id = :batch_id WHERE id = :job_id"),
                {"batch_id": batch_id, "job_id": job_id},
            )

        # Stage 2: promoting — run incremental harmonisation + categorisation on queued rows
        _update_job(bg_engine, job_id, stage="promoting")
        promoter = IncrementalPromoter(src_engine, config)
        promote_result = promoter.promote(engagement_id, batch_id)
        logger.info(
            "promote complete: promoted=%s review_required=%s failed=%s",
            promote_result["promoted_count"],
            promote_result["review_required_count"],
            promote_result["failed_count"],
        )

        # Stage 3: building cube
        _update_job(bg_engine, job_id, stage="building_cube")
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_cube_pipeline(db_url, config_path, tmp_dir)

        # Done
        now = datetime.now(timezone.utc).isoformat()
        _update_job(bg_engine, job_id, status="done", stage=None, completed_at=now)

    except Exception as exc:
        now = datetime.now(timezone.utc).isoformat()
        _update_job(
            bg_engine,
            job_id,
            status="failed",
            error_message=str(exc),
            completed_at=now,
        )
