-- SpendCube v2 initial schema migration
-- Applies to: Supabase (Postgres)
-- Tables: engagements, pipeline_jobs, transactions, supplier_master,
--         supplier_match_log, category_overrides, audit_log
-- Views:  v_by_supplier, v_by_category, v_by_month, v_by_bu, v_by_payment_terms

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

CREATE TABLE engagements (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name               TEXT        NOT NULL,
    client_name        TEXT        NOT NULL,
    currency_label     TEXT        NOT NULL DEFAULT 'AUD',
    engagement_title   TEXT        NOT NULL DEFAULT 'Procurement Spend Diagnostic',
    owner_email        TEXT        NOT NULL,
    is_admin           BOOLEAN     NOT NULL DEFAULT false,
    llm_dry_run        BOOLEAN     NOT NULL DEFAULT true,
    recommendations_json TEXT,
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pipeline_jobs (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id  UUID        NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    status         TEXT        NOT NULL DEFAULT 'queued',
    stage          TEXT,
    started_at     TIMESTAMPTZ DEFAULT now(),
    completed_at   TIMESTAMPTZ,
    error_message  TEXT
);

CREATE TABLE transactions (
    transaction_id                TEXT        PRIMARY KEY,
    engagement_id                 UUID        NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    source_system                 TEXT,
    source_row_number             INTEGER,
    ingested_at                   TEXT,
    last_modified_at              TEXT,
    invoice_number                TEXT,
    document_type                 TEXT,
    invoice_date                  TEXT,
    raw_supplier_name             TEXT,
    raw_supplier_id               TEXT,
    raw_line_description          TEXT,
    original_amount               DOUBLE PRECISION,
    original_currency             TEXT,
    base_amount                   DOUBLE PRECISION,
    base_currency                 TEXT,
    fx_rate                       DOUBLE PRECISION,
    gl_account                    TEXT,
    cost_centre                   TEXT,
    raw_payment_terms             TEXT,
    payment_terms_days            INTEGER,
    po_number                     TEXT,
    business_unit                 TEXT,
    plant_site                    TEXT,
    canonical_supplier_id         TEXT,
    canonical_supplier_name       TEXT,
    canonical_supplier_confidence DOUBLE PRECISION,
    parent_company_id             TEXT,
    parent_company_name           TEXT,
    category_l1                   TEXT,
    category_l2                   TEXT,
    category_l3                   TEXT,
    unspsc_code                   TEXT,
    category_confidence           DOUBLE PRECISION,
    category_method               TEXT,
    spend_type                    TEXT,
    addressability                TEXT,
    managed_status                TEXT,
    is_credit_note                INTEGER,
    is_intercompany               INTEGER,
    is_tax_line                   INTEGER,
    is_duplicate                  INTEGER,
    review_status                 TEXT,
    reviewer                      TEXT,
    review_notes                  TEXT,
    review_date                   TEXT,
    raw_data                      TEXT
);

CREATE TABLE supplier_master (
    canonical_supplier_id TEXT    NOT NULL,
    engagement_id         UUID    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    canonical_name        TEXT,
    parent_company_id     TEXT,
    parent_name           TEXT,
    country               TEXT,
    identifiers           TEXT,
    created_at            TEXT,
    updated_at            TEXT,
    PRIMARY KEY (canonical_supplier_id, engagement_id)
);

CREATE TABLE supplier_match_log (
    id                    TEXT    PRIMARY KEY,
    engagement_id         UUID    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    raw_supplier_name     TEXT,
    raw_supplier_id       TEXT,
    canonical_supplier_id TEXT,
    match_method          TEXT,
    confidence            DOUBLE PRECISION,
    evidence              TEXT,
    review_status         TEXT,
    created_at            TEXT
);

CREATE TABLE category_overrides (
    id                    TEXT    PRIMARY KEY,
    engagement_id         UUID    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    canonical_supplier_id TEXT,
    gl_account            TEXT,
    override_l1           TEXT,
    override_l2           TEXT,
    override_l3           TEXT,
    unspsc_code           TEXT,
    reviewer              TEXT,
    reason                TEXT,
    created_at            TEXT
);

CREATE TABLE audit_log (
    id          TEXT    PRIMARY KEY,
    engagement_id UUID  NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    table_name  TEXT,
    record_id   TEXT,
    field_name  TEXT,
    old_value   TEXT,
    new_value   TEXT,
    changed_by  TEXT,
    changed_at  TEXT
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX ON transactions(engagement_id);
CREATE INDEX ON transactions(engagement_id, invoice_date);
CREATE INDEX ON transactions(engagement_id, canonical_supplier_id);
CREATE INDEX ON transactions(engagement_id, category_l1);
CREATE INDEX ON supplier_match_log(engagement_id, review_status);
CREATE INDEX ON pipeline_jobs(engagement_id, status);

-- ---------------------------------------------------------------------------
-- Views (replace Parquet cube files from v1)
-- ---------------------------------------------------------------------------

CREATE VIEW v_by_supplier AS
SELECT
    engagement_id,
    canonical_supplier_id,
    canonical_supplier_name,
    parent_company_name,
    COUNT(*)                    AS transaction_count,
    SUM(base_amount)            AS total_spend,
    AVG(payment_terms_days)     AS avg_payment_days
FROM transactions
WHERE COALESCE(is_intercompany, 0) = 0
  AND COALESCE(is_tax_line, 0)     = 0
GROUP BY engagement_id, canonical_supplier_id, canonical_supplier_name, parent_company_name;

CREATE VIEW v_by_category AS
SELECT
    engagement_id,
    category_l1,
    category_l2,
    category_l3,
    unspsc_code,
    COUNT(*)                            AS transaction_count,
    SUM(base_amount)                    AS total_spend,
    COUNT(DISTINCT canonical_supplier_id) AS supplier_count
FROM transactions
WHERE COALESCE(is_intercompany, 0) = 0
  AND COALESCE(is_tax_line, 0)     = 0
GROUP BY engagement_id, category_l1, category_l2, category_l3, unspsc_code;

CREATE VIEW v_by_month AS
SELECT
    engagement_id,
    DATE_TRUNC('month', invoice_date::date) AS month,
    SUM(base_amount)                        AS total_spend,
    COUNT(*)                                AS transaction_count
FROM transactions
WHERE COALESCE(is_intercompany, 0) = 0
  AND COALESCE(is_tax_line, 0)     = 0
GROUP BY engagement_id, DATE_TRUNC('month', invoice_date::date);

CREATE VIEW v_by_bu AS
SELECT
    engagement_id,
    business_unit,
    cost_centre,
    SUM(base_amount)  AS total_spend,
    COUNT(*)          AS transaction_count
FROM transactions
WHERE COALESCE(is_intercompany, 0) = 0
GROUP BY engagement_id, business_unit, cost_centre;

CREATE VIEW v_by_payment_terms AS
SELECT
    engagement_id,
    CASE
        WHEN payment_terms_days <= 30 THEN '0-30'
        WHEN payment_terms_days <= 60 THEN '31-60'
        WHEN payment_terms_days <= 90 THEN '61-90'
        ELSE '90+'
    END               AS bucket,
    COUNT(*)          AS transaction_count,
    SUM(base_amount)  AS total_spend
FROM transactions
WHERE payment_terms_days IS NOT NULL
  AND COALESCE(is_intercompany, 0) = 0
GROUP BY engagement_id, bucket;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

ALTER TABLE engagements       ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_jobs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_master   ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_match_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE category_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log         ENABLE ROW LEVEL SECURITY;

-- engagements: policies scope to rows owned by the authenticated user
CREATE POLICY select_own_engagement ON engagements
    FOR SELECT USING (owner_email = auth.jwt() ->> 'email');

CREATE POLICY insert_own_engagement ON engagements
    FOR INSERT WITH CHECK (owner_email = auth.jwt() ->> 'email');

CREATE POLICY update_own_engagement ON engagements
    FOR UPDATE USING (owner_email = auth.jwt() ->> 'email');

CREATE POLICY delete_own_engagement ON engagements
    FOR DELETE USING (owner_email = auth.jwt() ->> 'email');

-- pipeline_jobs
CREATE POLICY select_own_engagement ON pipeline_jobs
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON pipeline_jobs
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON pipeline_jobs
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON pipeline_jobs
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- transactions
CREATE POLICY select_own_engagement ON transactions
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON transactions
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON transactions
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON transactions
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- supplier_master
CREATE POLICY select_own_engagement ON supplier_master
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON supplier_master
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON supplier_master
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON supplier_master
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- supplier_match_log
CREATE POLICY select_own_engagement ON supplier_match_log
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON supplier_match_log
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON supplier_match_log
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON supplier_match_log
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- category_overrides
CREATE POLICY select_own_engagement ON category_overrides
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON category_overrides
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON category_overrides
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON category_overrides
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- audit_log
CREATE POLICY select_own_engagement ON audit_log
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON audit_log
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON audit_log
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON audit_log
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));
