# Supabase Migrations

This directory contains SQL migrations for the SpendCube v2 Postgres schema.

## Prerequisites

Install the Supabase CLI:

```bash
npm install -g supabase
```

## Applying the migration

1. Authenticate with Supabase:

   ```bash
   npx supabase login
   ```

2. Link to your Supabase project (find the project ref in the Supabase dashboard URL):

   ```bash
   npx supabase link --project-ref <your-project-ref>
   ```

3. Push the migration to apply it to your remote database:

   ```bash
   npx supabase db push
   ```

## Migration contents

`001_initial_schema.sql` creates:

- **7 tables:** `engagements`, `pipeline_jobs`, `transactions`, `supplier_master`, `supplier_match_log`, `category_overrides`, `audit_log`
- **6 indexes** on high-traffic query paths
- **5 views:** `v_by_supplier`, `v_by_category`, `v_by_month`, `v_by_bu`, `v_by_payment_terms` — these replace the Parquet cube files from v1
- **Row Level Security** policies on all 7 tables — each row is scoped to the `owner_email` extracted from the Supabase Auth JWT

## Local development

To run Supabase locally:

```bash
npx supabase start
npx supabase db reset   # applies all migrations from scratch
```

The local Postgres instance will be available at `postgresql://postgres:postgres@localhost:54322/postgres`.
