-- SpendCube v2 data model hardening migration
-- Applies to: Supabase (Postgres)
-- Adds: pgvector extension, ingestion_batches, transactions_raw,
--       description_embeddings, supplier_embeddings tables,
--       source_raw_id column on transactions, batch_id on pipeline_jobs

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

CREATE TABLE ingestion_batches (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id  UUID        NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    filename       TEXT        NOT NULL,
    row_count      INTEGER,
    new_rows       INTEGER,
    duplicate_rows INTEGER,
    status         TEXT        NOT NULL DEFAULT 'processing',
    uploaded_at    TIMESTAMPTZ DEFAULT now(),
    completed_at   TIMESTAMPTZ
);

CREATE TABLE transactions_raw (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id    UUID        NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    batch_id         UUID        NOT NULL REFERENCES ingestion_batches(id) ON DELETE CASCADE,
    source_row_hash  TEXT        NOT NULL,
    pipeline_status  TEXT        NOT NULL DEFAULT 'queued',
    invoice_number   TEXT,
    invoice_date     TEXT,
    raw_supplier_name TEXT,
    base_amount      DOUBLE PRECISION,
    raw_data         JSONB,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE description_embeddings (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    normalised_text TEXT        NOT NULL UNIQUE,
    embedding       VECTOR(384) NOT NULL,
    model_name      TEXT        NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE supplier_embeddings (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id   UUID        NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    normalised_name TEXT        NOT NULL,
    embedding       VECTOR(384) NOT NULL,
    model_name      TEXT        NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (engagement_id, normalised_name)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX ON transactions_raw(engagement_id, source_row_hash);

CREATE INDEX ON ingestion_batches(engagement_id, status);
CREATE INDEX ON transactions_raw(engagement_id, batch_id, pipeline_status);

CREATE INDEX ON description_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
CREATE INDEX ON supplier_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- ---------------------------------------------------------------------------
-- Additive columns on existing tables
-- ---------------------------------------------------------------------------

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS source_raw_id UUID REFERENCES transactions_raw(id);
ALTER TABLE pipeline_jobs ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES ingestion_batches(id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

ALTER TABLE ingestion_batches  ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions_raw   ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_embeddings ENABLE ROW LEVEL SECURITY;

-- ingestion_batches
CREATE POLICY select_own_engagement ON ingestion_batches
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON ingestion_batches
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON ingestion_batches
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON ingestion_batches
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- transactions_raw
CREATE POLICY select_own_engagement ON transactions_raw
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON transactions_raw
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON transactions_raw
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON transactions_raw
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

-- supplier_embeddings
CREATE POLICY select_own_engagement ON supplier_embeddings
    FOR SELECT USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY insert_own_engagement ON supplier_embeddings
    FOR INSERT WITH CHECK (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY update_own_engagement ON supplier_embeddings
    FOR UPDATE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));

CREATE POLICY delete_own_engagement ON supplier_embeddings
    FOR DELETE USING (engagement_id IN (SELECT id FROM engagements WHERE owner_email = auth.jwt() ->> 'email'));
