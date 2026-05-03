export interface Engagement {
  id?: string
  name?: string
  client_name?: string
  currency_label?: string
  engagement_title?: string
  is_admin?: boolean
  llm_dry_run?: boolean
  recommendations_json?: string
  created_at?: string
}

export interface SupplierRow {
  engagement_id?: string
  canonical_supplier_id?: string
  canonical_supplier_name?: string
  parent_company_name?: string
  transaction_count?: number
  total_spend?: number
  avg_payment_days?: number
}

export interface CategoryRow {
  engagement_id?: string
  category_l1?: string
  category_l2?: string
  category_l3?: string
  unspsc_code?: string
  transaction_count?: number
  total_spend?: number
  supplier_count?: number
}

export interface MonthRow {
  month?: string
  total_spend?: number
  transaction_count?: number
  rolling_3m_avg?: number
}

export interface PaymentTermsRow {
  bucket?: string
  transaction_count?: number
  total_spend?: number
  spend_pct?: number
  wc_opportunity_aud?: number
}

export interface OverviewData {
  total_spend?: number
  invoice_count?: number
  supplier_count?: number
  category_count?: number
  currency_label?: string
  maverick_spend_pct?: number
  tail_spend_pct?: number
  data_freshness?: string
}

export interface Recommendation {
  type?: string
  context?: string
  evidence?: string
  estimated_impact_aud?: number
  confidence?: string
  action?: string
  lever?: string
  narrative?: string
  baseline_spend?: number
  addressability_pct?: number
  saving_pct?: number
  addressable_baseline?: number
}

export interface PortfolioSummary {
  total_spend?: number
  total_identified_savings?: number
  savings_as_pct_of_spend?: number
  sanity_check_passed?: boolean
  recommendation_count?: number
}

export interface DiagnosticsCheck {
  check_name?: string
  status?: string
  value_pct?: number
  threshold_amber?: number
  threshold_red?: number
  row_count?: number
  description?: string
}

export interface PipelineJob {
  id?: string
  engagement_id?: string
  status?: string
  stage?: string
  started_at?: string
  completed_at?: string
  error_message?: string
}

export interface SupplierMatchLog {
  id?: string
  raw_supplier_name?: string
  canonical_supplier_id?: string
  match_method?: string
  confidence?: number
  evidence?: string
  review_status?: string
}

export interface CategoryOverride {
  id?: string
  canonical_supplier_id?: string
  gl_account?: string
  override_l1?: string
  override_l2?: string
  override_l3?: string
  reviewer?: string
  reason?: string
  created_at?: string
}

export interface AuditLogEntry {
  id?: string
  table_name?: string
  record_id?: string
  field_name?: string
  old_value?: string
  new_value?: string
  changed_by?: string
  changed_at?: string
}
