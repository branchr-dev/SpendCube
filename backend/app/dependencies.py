from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine


async def get_current_user_email(request: Request) -> str:
    return request.state.user_email


async def verify_engagement_ownership(engagement_id: str, user_email: str, engine: Engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM engagements WHERE id = :id"),
            {"id": engagement_id},
        ).mappings().first()

    if row is None or row["owner_email"] != user_email:
        raise HTTPException(status_code=403, detail="Engagement not found or access denied")

    return dict(row)
