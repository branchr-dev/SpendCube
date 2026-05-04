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
  abc_segment?: string
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

export interface Category {
  id?: string
  category_id: string
  parent_category_id?: string | null
  category_level: number
  category_name: string
  taxonomy_version?: string
  is_active?: boolean
  mapping_confidence?: number
  mapping_source?: string
  children?: Category[]
}

export interface LegalEntity {
  id?: string
  legal_entity_code: string
  legal_entity_name: string
  country?: string
  currency?: string
}

export interface PaymentTermMapping {
  id?: string
  raw_payment_term: string
  harmonised_payment_term?: string
  payment_term_days?: number
  discount_percent?: number
  discount_days?: number
  has_early_payment_discount?: boolean
  confidence_score?: number
}

export type ABCSegment = 'A' | 'B' | 'C'

export interface ABCRow {
  canonical_supplier_id: string
  canonical_supplier_name?: string
  total_spend: number
  transaction_count: number
  cumulative_spend_pct: number
  abc_segment: ABCSegment
}

export interface LegalEntityRow {
  legal_entity: string
  transaction_count: number
  total_spend: number
  supplier_count: number
  category_count: number
}

export interface CurrencyRow {
  currency: string
  transaction_count: number
  total_spend_base: number
  total_spend_original: number
  supplier_count: number
}

export interface CountryRow {
  country: string
  country_type: string
  transaction_count: number
  total_spend: number
  supplier_count: number
}

export interface RecommendationConfig {
  consolidation_threshold?: number
  target_payment_days?: number
  wacc?: number
  min_wc_opportunity?: number
  tail_spend_alert_pct?: number
  maverick_alert_pct?: number
  competitive_tender_min_spend?: number
  contract_coverage_gap_min_spend?: number
  concentration_threshold_pct?: number
  min_discount_opportunity?: number
}

export interface CategoryQualityReport {
  total_transactions: number
  categorised_count: number
  uncategorised_count: number
  categorised_pct: number
  by_method: { method: string; count: number; spend: number; avg_confidence: number }[]
  by_confidence_band: { band: string; count: number; spend: number }[]
  low_confidence_backlog: {
    transaction_id: string
    raw_supplier_name?: string
    base_amount: number
    category_l1?: string
    category_confidence?: number
  }[]
}
