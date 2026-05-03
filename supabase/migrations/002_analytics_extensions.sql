-- SpendCube v2 analytics extensions migration
-- Applies to: Supabase (Postgres)
-- Purely additive — no existing columns, tables, or views are modified.
-- Safe to re-run: all DDL uses IF NOT EXISTS guards.

-- ---------------------------------------------------------------------------
-- 1. Add analytics columns to transactions (all nullable)
-- ---------------------------------------------------------------------------

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS legal_entity             TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS vendor_country           TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS plant_country            TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS categorisation_status    TEXT DEFAULT 'uncategorised';
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS manual_override_flag     INTEGER DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS ai_classification_flag   INTEGER DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS harmonised_payment_term  TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS discount_percent         DOUBLE PRECISION DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS discount_days            INTEGER DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS has_early_payment_discount INTEGER DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_term_confidence  DOUBLE PRECISION;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS abc_segment              TEXT;

-- ---------------------------------------------------------------------------
-- 2. New reference tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS categories (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id       UUID        NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    category_id         TEXT        NOT NULL,
    parent_category_id  TEXT,
    category_level      INTEGER     NOT NULL DEFAULT 1,
    category_name       TEXT        NOT NULL,
    taxonomy_version    TEXT        NOT NULL DEFAULT 'v1',
    is_active           BOOLEAN     NOT NULL DEFAULT true,
    mapping_confidence  DOUBLE PRECISION,
    mapping_source      TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (engagement_id, category_id, taxonomy_version)
);

CREATE TABLE IF NOT EXISTS legal_entities (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id       UUID        NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    legal_entity_code   TEXT        NOT NULL,
    legal_entity_name   TEXT        NOT NULL,
    country             TEXT,
    currency            TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (engagement_id, legal_entity_code)
);

CREATE TABLE IF NOT EXISTS payment_term_mappings (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id               UUID        NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    raw_payment_term            TEXT        NOT NULL,
    harmonised_payment_term     TEXT,
    payment_term_days           INTEGER,
    discount_percent            DOUBLE PRECISION DEFAULT 0,
    discount_days               INTEGER DEFAULT 0,
    has_early_payment_discount  BOOLEAN DEFAULT false,
    confidence_score            DOUBLE PRECISION,
    created_at                  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (engagement_id, raw_payment_term)
);

-- ---------------------------------------------------------------------------
-- 3. Indexes on new transaction columns
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_transactions_legal_entity  ON transactions(engagement_id, legal_entity);
CREATE INDEX IF NOT EXISTS idx_transactions_vendor_country ON transactions(engagement_id, vendor_country);
CREATE INDEX IF NOT EXISTS idx_transactions_abc_segment   ON transactions(engagement_id, abc_segment);
CREATE INDEX IF NOT EXISTS idx_transactions_cat_status    ON transactions(engagement_id, categorisation_status);

-- ---------------------------------------------------------------------------
-- 4. New aggregation views
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_by_legal_entity AS
SELECT
    engagement_id,
    legal_entity,
    COUNT(*)                            AS transaction_count,
    SUM(base_amount)                    AS total_spend,
    COUNT(DISTINCT canonical_supplier_id) AS supplier_count,
    COUNT(DISTINCT category_l1)         AS category_count
FROM transactions
WHERE COALESCE(is_intercompany, 0) = 0
  AND COALESCE(is_tax_line, 0)     = 0
  AND legal_entity IS NOT NULL
GROUP BY engagement_id, legal_entity;

CREATE OR REPLACE VIEW v_by_currency AS
SELECT
    engagement_id,
    original_currency                   AS currency,
    COUNT(*)                            AS transaction_count,
    SUM(base_amount)                    AS total_spend_base,
    SUM(original_amount)                AS total_spend_original,
    COUNT(DISTINCT canonical_supplier_id) AS supplier_count
FROM transactions
WHERE COALESCE(is_intercompany, 0) = 0
  AND COALESCE(is_tax_line, 0)     = 0
GROUP BY engagement_id, original_currency;

CREATE OR REPLACE VIEW v_by_country AS
SELECT
    engagement_id,
    vendor_country                      AS country,
    'vendor'                            AS country_type,
    COUNT(*)                            AS transaction_count,
    SUM(base_amount)                    AS total_spend,
    COUNT(DISTINCT canonical_supplier_id) AS supplier_count
FROM transactions
WHERE COALESCE(is_intercompany, 0) = 0
  AND COALESCE(is_tax_line, 0)     = 0
  AND vendor_country IS NOT NULL
GROUP BY engagement_id, vendor_country;

CREATE OR REPLACE VIEW v_abc_analysis AS
SELECT
    engagement_id,
    canonical_supplier_id,
    canonical_supplier_name,
    SUM(base_amount)                                                          AS total_spend,
    COUNT(*)                                                                  AS transaction_count,
    SUM(SUM(base_amount)) OVER (PARTITION BY engagement_id ORDER BY SUM(base_amount) DESC) AS cumulative_spend,
    SUM(SUM(base_amount)) OVER (PARTITION BY engagement_id)                   AS grand_total
FROM transactions
WHERE COALESCE(is_intercompany, 0) = 0
  AND COALESCE(is_tax_line, 0)     = 0
GROUP BY engagement_id, canonical_supplier_id, canonical_supplier_name;

-- ---------------------------------------------------------------------------
-- 5. Row Level Security on new tables
-- ---------------------------------------------------------------------------

ALTER TABLE categories          ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_entities      ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_term_mappings ENABLE ROW LEVEL SECURITY;

-- categories
CREATE POLICY select_own_engagement ON categories
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON categories
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON categories
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON categories
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- legal_entities
CREATE POLICY select_own_engagement ON legal_entities
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON legal_entities
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON legal_entities
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON legal_entities
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- payment_term_mappings
CREATE POLICY select_own_engagement ON payment_term_mappings
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON payment_term_mappings
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON payment_term_mappings
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON payment_term_mappings
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));
