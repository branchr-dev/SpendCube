import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import get_engine
from app.dependencies import get_current_user_email, verify_engagement_ownership

router = APIRouter(
    prefix="/api/engagements/{engagement_id}/review",
    tags=["review"],
)


def _engine() -> Engine:
    return get_engine()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_audit(conn, engagement_id: str, table_name: str, record_id: str,
                  field_name: str, old_value: str, new_value: str, changed_by: str) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_log (id, engagement_id, table_name, record_id,"
            " field_name, old_value, new_value, changed_by, changed_at)"
            " VALUES (:id, :eid, :table_name, :record_id,"
            " :field_name, :old_value, :new_value, :changed_by, :changed_at)"
        ),
        {
            "id": str(uuid4()),
            "eid": engagement_id,
            "table_name": table_name,
            "record_id": record_id,
            "field_name": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "changed_by": changed_by,
            "changed_at": _now(),
        },
    )


# ---------------------------------------------------------------------------
# GET /supplier-queue
# ---------------------------------------------------------------------------

@router.get("/supplier-queue")
async def get_supplier_queue(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, raw_supplier_name, raw_supplier_id, canonical_supplier_id,"
                " match_method, confidence, evidence, review_status, created_at"
                " FROM supplier_match_log"
                " WHERE engagement_id = :eid AND review_status = 'PENDING'"
                " ORDER BY confidence ASC"
            ),
            {"eid": engagement_id},
        ).mappings().all()

    result = []
    for r in rows:
        item = dict(r)
        if item.get("evidence"):
            try:
                item["evidence"] = json.loads(item["evidence"])
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(item)

    return result


# ---------------------------------------------------------------------------
# POST /supplier/{match_id}/approve
# ---------------------------------------------------------------------------

@router.post("/supplier/{match_id}/approve")
async def approve_supplier_match(
    engagement_id: str,
    match_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.begin() as conn:
        updated = conn.execute(
            text(
                "UPDATE supplier_match_log SET review_status = 'APPROVED'"
                " WHERE id = :match_id AND engagement_id = :eid"
            ),
            {"match_id": match_id, "eid": engagement_id},
        ).rowcount

        if updated == 0:
            raise HTTPException(status_code=404, detail="Match record not found")

        _insert_audit(
            conn, engagement_id,
            table_name="supplier_match_log",
            record_id=match_id,
            field_name="review_status",
            old_value="PENDING",
            new_value="APPROVED",
            changed_by=user_email,
        )

    return {"status": "approved"}


# ---------------------------------------------------------------------------
# POST /supplier/{match_id}/reject
# ---------------------------------------------------------------------------

@router.post("/supplier/{match_id}/reject")
async def reject_supplier_match(
    engagement_id: str,
    match_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.begin() as conn:
        updated = conn.execute(
            text(
                "UPDATE supplier_match_log SET review_status = 'REJECTED'"
                " WHERE id = :match_id AND engagement_id = :eid"
            ),
            {"match_id": match_id, "eid": engagement_id},
        ).rowcount

        if updated == 0:
            raise HTTPException(status_code=404, detail="Match record not found")

        _insert_audit(
            conn, engagement_id,
            table_name="supplier_match_log",
            record_id=match_id,
            field_name="review_status",
            old_value="PENDING",
            new_value="REJECTED",
            changed_by=user_email,
        )

    return {"status": "rejected"}


# ---------------------------------------------------------------------------
# POST /supplier/{match_id}/override
# ---------------------------------------------------------------------------

class SupplierOverrideBody(BaseModel):
    canonical_supplier_id: str
    canonical_name: str


@router.post("/supplier/{match_id}/override")
async def override_supplier_match(
    engagement_id: str,
    match_id: str,
    body: SupplierOverrideBody,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT raw_supplier_name FROM supplier_match_log"
                " WHERE id = :match_id AND engagement_id = :eid"
            ),
            {"match_id": match_id, "eid": engagement_id},
        ).mappings().first()

        if row is None:
            raise HTTPException(status_code=404, detail="Match record not found")

        raw_name = row["raw_supplier_name"]

        conn.execute(
            text(
                "UPDATE supplier_match_log"
                " SET canonical_supplier_id = :cid, review_status = 'OVERRIDDEN'"
                " WHERE id = :match_id AND engagement_id = :eid"
            ),
            {"cid": body.canonical_supplier_id, "match_id": match_id, "eid": engagement_id},
        )

        conn.execute(
            text(
                "UPDATE transactions"
                " SET canonical_supplier_id = :cid, canonical_supplier_name = :cname"
                " WHERE engagement_id = :eid AND raw_supplier_name = :raw_name"
            ),
            {
                "cid": body.canonical_supplier_id,
                "cname": body.canonical_name,
                "eid": engagement_id,
                "raw_name": raw_name,
            },
        )

        _insert_audit(
            conn, engagement_id,
            table_name="supplier_match_log",
            record_id=match_id,
            field_name="canonical_supplier_id",
            old_value="",
            new_value=body.canonical_supplier_id,
            changed_by=user_email,
        )

    return {"status": "overridden"}


# ---------------------------------------------------------------------------
# GET /category-queue
# ---------------------------------------------------------------------------

@router.get("/category-queue")
async def get_category_queue(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT transaction_id, raw_supplier_name, raw_line_description,"
                " base_amount, category_l1, category_l2, category_l3, category_confidence"
                " FROM transactions"
                " WHERE engagement_id = :eid AND category_confidence < 0.60"
                " ORDER BY ABS(base_amount) DESC"
                " LIMIT 100"
            ),
            {"eid": engagement_id},
        ).mappings().all()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# POST /category-override
# ---------------------------------------------------------------------------

class CategoryOverrideBody(BaseModel):
    canonical_supplier_id: Optional[str] = None
    gl_account: Optional[str] = None
    override_l1: str
    override_l2: str
    override_l3: str
    unspsc_code: Optional[str] = None
    reason: str


@router.post("/category-override", status_code=201)
async def create_category_override(
    engagement_id: str,
    body: CategoryOverrideBody,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    if not body.canonical_supplier_id and not body.gl_account:
        raise HTTPException(
            status_code=400,
            detail="At least one of canonical_supplier_id or gl_account must be provided",
        )

    override_id = str(uuid4())
    now = _now()

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO category_overrides"
                " (id, engagement_id, canonical_supplier_id, gl_account,"
                " override_l1, override_l2, override_l3, unspsc_code,"
                " reviewer, reason, created_at)"
                " VALUES (:id, :eid, :canonical_supplier_id, :gl_account,"
                " :override_l1, :override_l2, :override_l3, :unspsc_code,"
                " :reviewer, :reason, :created_at)"
            ),
            {
                "id": override_id,
                "eid": engagement_id,
                "canonical_supplier_id": body.canonical_supplier_id,
                "gl_account": body.gl_account,
                "override_l1": body.override_l1,
                "override_l2": body.override_l2,
                "override_l3": body.override_l3,
                "unspsc_code": body.unspsc_code,
                "reviewer": user_email,
                "reason": body.reason,
                "created_at": now,
            },
        )

        _insert_audit(
            conn, engagement_id,
            table_name="category_overrides",
            record_id=override_id,
            field_name="created",
            old_value="",
            new_value=f"{body.override_l1}/{body.override_l2}/{body.override_l3}",
            changed_by=user_email,
        )

        row = conn.execute(
            text("SELECT * FROM category_overrides WHERE id = :id"),
            {"id": override_id},
        ).mappings().first()

    return dict(row)


# ---------------------------------------------------------------------------
# GET /category-overrides
# ---------------------------------------------------------------------------

@router.get("/category-overrides")
async def list_category_overrides(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT * FROM category_overrides WHERE engagement_id = :eid"
                " ORDER BY created_at DESC"
            ),
            {"eid": engagement_id},
        ).mappings().all()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# DELETE /category-override/{override_id}
# ---------------------------------------------------------------------------

@router.delete("/category-override/{override_id}")
async def delete_category_override(
    engagement_id: str,
    override_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.begin() as conn:
        deleted = conn.execute(
            text(
                "DELETE FROM category_overrides WHERE id = :oid AND engagement_id = :eid"
            ),
            {"oid": override_id, "eid": engagement_id},
        ).rowcount

        if deleted == 0:
            raise HTTPException(status_code=404, detail="Override not found")

        _insert_audit(
            conn, engagement_id,
            table_name="category_overrides",
            record_id=override_id,
            field_name="deleted",
            old_value="exists",
            new_value="",
            changed_by=user_email,
        )

    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# GET /audit-log
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def get_audit_log(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT * FROM audit_log WHERE engagement_id = :eid"
                " ORDER BY changed_at DESC LIMIT 100"
            ),
            {"eid": engagement_id},
        ).mappings().all()

    return [dict(r) for r in rows]
