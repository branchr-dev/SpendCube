"""SpendCube canonical pydantic v2 schema definitions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentType(str, Enum):
    INVOICE = "INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"
    DEBIT_NOTE = "DEBIT_NOTE"
    ACCRUAL = "ACCRUAL"


class CategoryMethod(str, Enum):
    DETERMINISTIC_GL = "DETERMINISTIC_GL"
    DETERMINISTIC_SUPPLIER = "DETERMINISTIC_SUPPLIER"
    KEYWORD = "KEYWORD"
    EMBEDDING = "EMBEDDING"
    LLM = "LLM"
    MANUAL = "MANUAL"


class SpendType(str, Enum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    CAPEX = "CAPEX"
    OPEX = "OPEX"


class Addressability(str, Enum):
    ADDRESSABLE = "ADDRESSABLE"
    NON_ADDRESSABLE = "NON_ADDRESSABLE"
    EXCLUDED = "EXCLUDED"


class ManagedStatus(str, Enum):
    MANAGED = "MANAGED"
    UNMANAGED = "UNMANAGED"
    PARTIALLY_MANAGED = "PARTIALLY_MANAGED"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


# ---------------------------------------------------------------------------
# ConfidenceBand helper
# ---------------------------------------------------------------------------

class ConfidenceBand:
    HIGH: float = 0.85
    MEDIUM: float = 0.60

    @classmethod
    def get_band(cls, score: float) -> str:
        if score >= cls.HIGH:
            return "HIGH"
        if score >= cls.MEDIUM:
            return "MEDIUM"
        return "LOW"


# ---------------------------------------------------------------------------
# Canonical Transaction
# ---------------------------------------------------------------------------

class CanonicalTransaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    # System / identity
    transaction_id: str = Field(default_factory=lambda: str(uuid4()))
    source_system: str
    source_row_number: int
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    last_modified_at: datetime = Field(default_factory=datetime.utcnow)

    # Document
    invoice_number: str
    document_type: Optional[DocumentType] = None
    invoice_date: Optional[date] = None

    # Raw supplier
    raw_supplier_name: Optional[str] = None
    raw_supplier_id: Optional[str] = None

    # Raw line
    raw_line_description: Optional[str] = None

    # Financial — original currency
    original_amount: Decimal
    original_currency: str

    # Financial — base currency (AUD)
    base_amount: Decimal
    base_currency: str
    fx_rate: Optional[Decimal] = None

    # GL / cost
    gl_account: Optional[str] = None
    cost_centre: Optional[str] = None

    # Payment terms
    raw_payment_terms: Optional[str] = None
    payment_terms_days: Optional[int] = None

    # Procurement references
    po_number: Optional[str] = None
    business_unit: Optional[str] = None
    plant_site: Optional[str] = None

    # Canonical supplier (resolved)
    canonical_supplier_id: Optional[str] = None
    canonical_supplier_name: Optional[str] = None
    canonical_supplier_confidence: Optional[float] = None
    parent_company_id: Optional[str] = None
    parent_company_name: Optional[str] = None

    # Categorisation
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    category_l3: Optional[str] = None
    unspsc_code: Optional[str] = None
    category_confidence: Optional[float] = None
    category_method: Optional[CategoryMethod] = None

    # Spend classification
    spend_type: Optional[SpendType] = None
    addressability: Optional[Addressability] = None
    managed_status: Optional[ManagedStatus] = None

    # Boolean flags
    is_credit_note: bool = False
    is_intercompany: bool = False
    is_tax_line: bool = False
    is_duplicate: bool = False

    # Review workflow
    review_status: Optional[ReviewStatus] = None
    reviewer: Optional[str] = None
    review_notes: Optional[str] = None
    review_date: Optional[date] = None

    # Raw source data (all original columns preserved as JSON)
    raw_data: dict[str, Any]

    # Analytics foundation fields
    legal_entity: Optional[str] = None
    vendor_country: Optional[str] = None
    plant_country: Optional[str] = None
    categorisation_status: Optional[str] = 'uncategorised'
    manual_override_flag: Optional[int] = 0
    ai_classification_flag: Optional[int] = 0
    harmonised_payment_term: Optional[str] = None
    discount_percent: Optional[float] = 0.0
    discount_days: Optional[int] = 0
    has_early_payment_discount: Optional[int] = 0
    payment_term_confidence: Optional[float] = None
    abc_segment: Optional[str] = None


# ---------------------------------------------------------------------------
# Supplier Master
# ---------------------------------------------------------------------------

class SupplierMaster(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    canonical_supplier_id: str
    canonical_name: str
    parent_company_id: Optional[str] = None
    parent_name: Optional[str] = None
    country: Optional[str] = None
    identifiers: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Supplier Match Log
# ---------------------------------------------------------------------------

class SupplierMatchLog(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    raw_supplier_name: str
    raw_supplier_id: Optional[str] = None
    canonical_supplier_id: Optional[str] = None
    match_method: Optional[str] = None
    confidence: Optional[float] = None
    evidence: Optional[dict[str, Any]] = None
    review_status: ReviewStatus = ReviewStatus.PENDING


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample = CanonicalTransaction(
        source_system="TEST",
        source_row_number=1,
        invoice_number="INV-001",
        original_amount=Decimal("1250.00"),
        original_currency="AUD",
        base_amount=Decimal("1250.00"),
        base_currency="AUD",
        invoice_date=date(2024, 3, 15),
        raw_supplier_name="Acme Pty Ltd",
        raw_data={},
    )
    print(sample.model_dump_json(indent=2))
    print("Schema OK")
