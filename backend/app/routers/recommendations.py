import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import get_engine
from app.dependencies import get_current_user_email, verify_engagement_ownership

router = APIRouter(
    prefix="/api/engagements/{engagement_id}/recommendations",
    tags=["recommendations"],
)


def _engine() -> Engine:
    return get_engine()


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------

@router.post("/run")
async def run_recommendations(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    engagement = await verify_engagement_ownership(engagement_id, user_email, engine)

    from src.config import load_config
    from src.models.database import get_engine as src_get_engine
    from src.recommendations.engine import RecommendationEngine

    config_path = os.getenv("SPENDCUBE_CONFIG_PATH", "config.yaml")
    config = load_config(config_path)

    db_url = os.getenv("SUPABASE_DATABASE_URL")
    src_engine = src_get_engine(db_url) if db_url else engine

    llm_dry_run = engagement.get("llm_dry_run", True)
    if not llm_dry_run and os.getenv("ANTHROPIC_API_KEY"):
        config.llm.dry_run = False
    else:
        config.llm.dry_run = True

    rec_engine = RecommendationEngine(config, src_engine)
    recommendations = rec_engine.run()

    payload = {
        "recommendations": recommendations,
        "portfolio_summary": rec_engine._portfolio_summary,
    }
    payload_json = json.dumps(payload, default=str)

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE engagements SET recommendations_json = :rjson WHERE id = :eid"
            ),
            {"rjson": payload_json, "eid": engagement_id},
        )

    return payload


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@router.get("")
async def get_recommendations(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT recommendations_json FROM engagements"
                " WHERE id = :eid AND owner_email = :email"
            ),
            {"eid": engagement_id, "email": user_email},
        ).mappings().first()

    if row is None:
        raise HTTPException(status_code=403, detail="Engagement not found or access denied")

    if row["recommendations_json"] is None:
        raise HTTPException(
            status_code=404,
            detail="Recommendations not yet generated — call POST /run first",
        )

    return json.loads(row["recommendations_json"])
