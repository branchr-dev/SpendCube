from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import get_engine
from app.dependencies import get_current_user_email, verify_engagement_ownership

router = APIRouter(prefix="/api/engagements", tags=["engagements"])


def _engine() -> Engine:
    return get_engine()


class EngagementCreate(BaseModel):
    name: str
    client_name: str
    currency_label: str = "AUD"
    engagement_title: str = "Procurement Spend Diagnostic"
    llm_dry_run: bool = True


class EngagementUpdate(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    currency_label: Optional[str] = None
    engagement_title: Optional[str] = None
    llm_dry_run: Optional[bool] = None


@router.get("")
async def list_engagements(
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM engagements WHERE owner_email = :email ORDER BY created_at DESC"),
            {"email": user_email},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_engagement(
    body: EngagementCreate,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    engagement_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO engagements "
                "(id, name, client_name, currency_label, engagement_title, owner_email, is_admin, llm_dry_run, created_at) "
                "VALUES (:id, :name, :client_name, :currency_label, :engagement_title, :owner_email, false, :llm_dry_run, :created_at)"
            ),
            {
                "id": engagement_id,
                "name": body.name,
                "client_name": body.client_name,
                "currency_label": body.currency_label,
                "engagement_title": body.engagement_title,
                "owner_email": user_email,
                "llm_dry_run": body.llm_dry_run,
                "created_at": now,
            },
        )
        row = conn.execute(
            text("SELECT * FROM engagements WHERE id = :id"),
            {"id": engagement_id},
        ).mappings().first()
    return dict(row)


@router.get("/{engagement_id}")
async def get_engagement(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    return await verify_engagement_ownership(engagement_id, user_email, engine)


@router.patch("/{engagement_id}")
async def update_engagement(
    engagement_id: str,
    body: EngagementUpdate,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    updates["engagement_id"] = engagement_id

    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE engagements SET {set_clauses} WHERE id = :engagement_id"),
            updates,
        )
        row = conn.execute(
            text("SELECT * FROM engagements WHERE id = :id"),
            {"id": engagement_id},
        ).mappings().first()
    return dict(row)
