import sys
import os

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import get_engine
from app.dependencies import get_current_user_email, verify_engagement_ownership

router = APIRouter(
    prefix="/api/engagements/{engagement_id}/cube",
    tags=["cube"],
)

_BUCKET_MIDPOINTS = {"0-30": 15, "31-60": 46, "61-90": 76, "90+": 120}
_VALID_SORT_BY = {"total_spend", "transaction_count", "canonical_supplier_name", "avg_payment_days"}


def _engine() -> Engine:
    return get_engine()


def _load_config():
    try:
        from src.config import load_config
        config_path = os.getenv("SPENDCUBE_CONFIG_PATH", "config.yaml")
        return load_config(config_path)
    except Exception:
        return None


def _compute_tail_spend_pct(supplier_spends: list, total_spend: float) -> float:
    if not supplier_spends or total_spend == 0:
        return 0.0
    values = sorted([float(s or 0) for s in supplier_spends], reverse=True)
    series = pd.Series(values)
    cumsum = series.cumsum()
    shifted = cumsum.shift(1, fill_value=0.0)
    tail_mask = shifted >= total_spend * 0.80
    return float(series[tail_mask].sum() / total_spend)


# ---------------------------------------------------------------------------
# GET /overview
# ---------------------------------------------------------------------------

@router.get("/overview")
async def get_overview(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    engagement = await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        agg = conn.execute(
            text(
                "SELECT"
                " COALESCE(SUM(base_amount), 0) AS total_spend,"
                " COUNT(*) AS invoice_count,"
                " COUNT(DISTINCT canonical_supplier_id) AS supplier_count,"
                " COUNT(DISTINCT category_l1) AS category_count,"
                " MAX(invoice_date) AS data_freshness,"
                " COALESCE(SUM(CASE WHEN po_number IS NULL THEN base_amount ELSE 0 END), 0) AS maverick_spend"
                " FROM transactions"
                " WHERE engagement_id = :eid"
                " AND COALESCE(is_intercompany, 0) = 0"
                " AND COALESCE(is_tax_line, 0) = 0"
            ),
            {"eid": engagement_id},
        ).mappings().first()

        supplier_spends = [
            r["total_spend"]
            for r in conn.execute(
                text(
                    "SELECT SUM(base_amount) AS total_spend"
                    " FROM transactions"
                    " WHERE engagement_id = :eid"
                    " AND COALESCE(is_intercompany, 0) = 0"
                    " AND COALESCE(is_tax_line, 0) = 0"
                    " GROUP BY canonical_supplier_id"
                ),
                {"eid": engagement_id},
            ).mappings().all()
        ]

    total_spend = float(agg["total_spend"] or 0)
    maverick_spend = float(agg["maverick_spend"] or 0)
    maverick_spend_pct = maverick_spend / total_spend if total_spend else 0.0
    tail_spend_pct = _compute_tail_spend_pct(supplier_spends, total_spend)

    return {
        "total_spend": total_spend,
        "invoice_count": int(agg["invoice_count"] or 0),
        "supplier_count": int(agg["supplier_count"] or 0),
        "category_count": int(agg["category_count"] or 0),
        "currency_label": engagement.get("currency_label", "AUD"),
        "maverick_spend_pct": round(maverick_spend_pct, 4),
        "tail_spend_pct": round(tail_spend_pct, 4),
        "data_freshness": agg["data_freshness"],
    }


# ---------------------------------------------------------------------------
# GET /by-supplier
# ---------------------------------------------------------------------------

@router.get("/by-supplier")
async def get_by_supplier(
    engagement_id: str,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="total_spend"),
    order: str = Query(default="desc"),
    category_l1: Optional[str] = Query(default=None),
    bu: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    supplier_search: Optional[str] = Query(default=None),
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    if sort_by not in _VALID_SORT_BY:
        sort_by = "total_spend"
    order_dir = "DESC" if order.lower() == "desc" else "ASC"

    where_clauses = [
        "engagement_id = :eid",
        "COALESCE(is_intercompany, 0) = 0",
        "COALESCE(is_tax_line, 0) = 0",
    ]
    params: dict = {"eid": engagement_id, "limit": limit, "offset": offset}

    if category_l1:
        where_clauses.append("category_l1 = :category_l1")
        params["category_l1"] = category_l1
    if bu:
        where_clauses.append("business_unit = :bu")
        params["bu"] = bu
    if date_from:
        where_clauses.append("invoice_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("invoice_date <= :date_to")
        params["date_to"] = date_to
    if supplier_search:
        where_clauses.append("LOWER(canonical_supplier_name) LIKE LOWER(:supplier_search)")
        params["supplier_search"] = f"%{supplier_search}%"

    where_sql = " AND ".join(where_clauses)
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    data_sql = (
        f"SELECT canonical_supplier_id, canonical_supplier_name, parent_company_name,"
        f" COUNT(*) AS transaction_count, SUM(base_amount) AS total_spend,"
        f" AVG(payment_terms_days) AS avg_payment_days"
        f" FROM transactions WHERE {where_sql}"
        f" GROUP BY canonical_supplier_id, canonical_supplier_name, parent_company_name"
        f" ORDER BY {sort_by} {order_dir}"
        f" LIMIT :limit OFFSET :offset"
    )
    count_sql = (
        f"SELECT COUNT(*) AS total_count FROM ("
        f"SELECT canonical_supplier_id FROM transactions WHERE {where_sql}"
        f" GROUP BY canonical_supplier_id) sub"
    )

    with engine.connect() as conn:
        rows = conn.execute(text(data_sql), params).mappings().all()
        count_row = conn.execute(text(count_sql), count_params).mappings().first()

    data = [
        {
            "canonical_supplier_id": r["canonical_supplier_id"],
            "canonical_supplier_name": r["canonical_supplier_name"],
            "parent_company_name": r["parent_company_name"],
            "transaction_count": int(r["transaction_count"] or 0),
            "total_spend": float(r["total_spend"] or 0),
            "avg_payment_days": (
                float(r["avg_payment_days"]) if r["avg_payment_days"] is not None else None
            ),
        }
        for r in rows
    ]

    return {"data": data, "total_count": int(count_row["total_count"] or 0)}


# ---------------------------------------------------------------------------
# GET /by-category
# ---------------------------------------------------------------------------

@router.get("/by-category")
async def get_by_category(
    engagement_id: str,
    l1: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    where_clauses = [
        "engagement_id = :eid",
        "COALESCE(is_intercompany, 0) = 0",
        "COALESCE(is_tax_line, 0) = 0",
    ]
    params: dict = {"eid": engagement_id}

    if l1:
        where_clauses.append("category_l1 = :l1")
        params["l1"] = l1
    if date_from:
        where_clauses.append("invoice_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("invoice_date <= :date_to")
        params["date_to"] = date_to

    where_sql = " AND ".join(where_clauses)
    sql = (
        f"SELECT category_l1, category_l2, category_l3, unspsc_code,"
        f" COUNT(*) AS transaction_count, SUM(base_amount) AS total_spend,"
        f" COUNT(DISTINCT canonical_supplier_id) AS supplier_count"
        f" FROM transactions WHERE {where_sql}"
        f" GROUP BY category_l1, category_l2, category_l3, unspsc_code"
        f" ORDER BY total_spend DESC"
    )

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    return [
        {
            "category_l1": r["category_l1"],
            "category_l2": r["category_l2"],
            "category_l3": r["category_l3"],
            "unspsc_code": r["unspsc_code"],
            "transaction_count": int(r["transaction_count"] or 0),
            "total_spend": float(r["total_spend"] or 0),
            "supplier_count": int(r["supplier_count"] or 0),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /by-month
# ---------------------------------------------------------------------------

@router.get("/by-month")
async def get_by_month(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT"
                " SUBSTR(invoice_date, 1, 7) AS month,"
                " SUM(base_amount) AS total_spend,"
                " COUNT(*) AS transaction_count"
                " FROM transactions"
                " WHERE engagement_id = :eid"
                " AND COALESCE(is_intercompany, 0) = 0"
                " AND COALESCE(is_tax_line, 0) = 0"
                " AND invoice_date IS NOT NULL"
                " GROUP BY month"
                " ORDER BY month ASC"
            ),
            {"eid": engagement_id},
        ).mappings().all()

    if not rows:
        return []

    df = pd.DataFrame(
        [
            {
                "month": r["month"],
                "total_spend": float(r["total_spend"] or 0),
                "transaction_count": int(r["transaction_count"] or 0),
            }
            for r in rows
        ]
    )
    df["rolling_3m_avg"] = df["total_spend"].rolling(3).mean()

    return [
        {
            "month": row["month"],
            "total_spend": row["total_spend"],
            "transaction_count": row["transaction_count"],
            "rolling_3m_avg": (
                None if pd.isna(row["rolling_3m_avg"]) else round(row["rolling_3m_avg"], 2)
            ),
        }
        for _, row in df.iterrows()
    ]


# ---------------------------------------------------------------------------
# GET /by-payment-terms
# ---------------------------------------------------------------------------

@router.get("/by-payment-terms")
async def get_by_payment_terms(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT"
                " CASE"
                "  WHEN payment_terms_days <= 30 THEN '0-30'"
                "  WHEN payment_terms_days <= 60 THEN '31-60'"
                "  WHEN payment_terms_days <= 90 THEN '61-90'"
                "  ELSE '90+'"
                " END AS bucket,"
                " COUNT(*) AS transaction_count,"
                " SUM(base_amount) AS total_spend"
                " FROM transactions"
                " WHERE engagement_id = :eid"
                " AND payment_terms_days IS NOT NULL"
                " AND COALESCE(is_intercompany, 0) = 0"
                " GROUP BY bucket"
                " ORDER BY bucket"
            ),
            {"eid": engagement_id},
        ).mappings().all()

    config = _load_config()
    target_days: int = config.recommendations.target_payment_days if config else 45
    wacc: float = config.recommendations.wacc if config else 0.08

    total_spend = sum(float(r["total_spend"] or 0) for r in rows)

    return [
        {
            "bucket": r["bucket"],
            "transaction_count": int(r["transaction_count"] or 0),
            "total_spend": float(r["total_spend"] or 0),
            "spend_pct": (
                round(float(r["total_spend"] or 0) / total_spend, 4) if total_spend else 0.0
            ),
            "wc_opportunity_aud": round(
                max(
                    0.0,
                    (target_days - _BUCKET_MIDPOINTS.get(r["bucket"], 45))
                    / 365
                    * float(r["total_spend"] or 0)
                    * wacc,
                ),
                2,
            ),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /by-bu
# ---------------------------------------------------------------------------

@router.get("/by-bu")
async def get_by_bu(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT business_unit, cost_centre,"
                " SUM(base_amount) AS total_spend, COUNT(*) AS transaction_count"
                " FROM transactions"
                " WHERE engagement_id = :eid"
                " AND COALESCE(is_intercompany, 0) = 0"
                " GROUP BY business_unit, cost_centre"
                " ORDER BY total_spend DESC"
            ),
            {"eid": engagement_id},
        ).mappings().all()

    return [
        {
            "business_unit": r["business_unit"],
            "cost_centre": r["cost_centre"],
            "total_spend": float(r["total_spend"] or 0),
            "transaction_count": int(r["transaction_count"] or 0),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /diagnostics
# ---------------------------------------------------------------------------

@router.get("/diagnostics")
async def get_diagnostics(
    engagement_id: str,
    user_email: str = Depends(get_current_user_email),
    engine: Engine = Depends(_engine),
):
    await verify_engagement_ownership(engagement_id, user_email, engine)

    from src.diagnostics.quality import DataQualityDiagnostics
    from src.config import load_config
    from src.models.database import get_transactions, get_engine as src_get_engine

    config_path = os.getenv("SPENDCUBE_CONFIG_PATH", "config.yaml")
    config = load_config(config_path)

    db_url = os.getenv("SUPABASE_DATABASE_URL")
    src_engine = src_get_engine(db_url) if db_url else engine

    df = get_transactions(src_engine, {"engagement_id": engagement_id})
    diag = DataQualityDiagnostics(df, config)
    return diag.run_all()
