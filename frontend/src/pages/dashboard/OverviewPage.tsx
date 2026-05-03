import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { DollarSign, Lightbulb, AlertTriangle } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import FilterBar from '@/components/dashboard/FilterBar'
import KpiCard from '@/components/dashboard/KpiCard'
import SpendAreaChart from '@/components/charts/SpendAreaChart'
import SpendBarChart from '@/components/charts/SpendBarChart'
import SpendTreemap from '@/components/charts/SpendTreemap'
import { CHART_COLORS } from '@/components/charts/constants'
import { useFilters } from '@/hooks/useFilters'
import { api } from '@/lib/api'
import { formatCurrency } from '@/lib/formatters'
import type { OverviewData, MonthRow, SupplierRow, CategoryRow, PaymentTermsRow, DiagnosticsCheck } from '@/types'
import type { FilterState, FilterOptions } from '@/types/filters'

interface RecommendationsResponse {
  recommendations?: unknown[]
}

export default function OverviewPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const { filters, updateFilter, toQueryParams } = useFilters()
  const qp = toQueryParams()

  const { data: overview, isLoading: loadingOverview } = useQuery<OverviewData>({
    queryKey: ['overview', engagementId, qp],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/overview`, { params: qp }).then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: monthData = [], isLoading: loadingMonths } = useQuery<MonthRow[]>({
    queryKey: ['by-month', engagementId, qp],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/by-month`, { params: qp }).then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: supplierData = [], isLoading: loadingSuppliers } = useQuery<SupplierRow[]>({
    queryKey: ['top-suppliers', engagementId, qp],
    queryFn: () =>
      api
        .get(`/api/engagements/${engagementId}/cube/by-supplier`, { params: { ...qp, limit: 10 } })
        .then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: categoryData = [], isLoading: loadingCategories } = useQuery<CategoryRow[]>({
    queryKey: ['by-category-overview', engagementId, qp],
    queryFn: () =>
      api
        .get(`/api/engagements/${engagementId}/cube/by-category`, { params: qp })
        .then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: ptData = [] } = useQuery<PaymentTermsRow[]>({
    queryKey: ['pt-overview', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/by-payment-terms`).then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: recData } = useQuery<RecommendationsResponse | null>({
    queryKey: ['rec-overview', engagementId],
    queryFn: () =>
      api
        .get(`/api/engagements/${engagementId}/recommendations`)
        .then(r => r.data)
        .catch((err: { response?: { status?: number } }) => {
          if (err?.response?.status === 404) return null
          throw err
        }),
    retry: false,
    enabled: !!engagementId,
  })

  const { data: diagData = [] } = useQuery<DiagnosticsCheck[]>({
    queryKey: ['diag-overview', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/diagnostics`).then(r => r.data),
    enabled: !!engagementId,
  })

  function handleFilterChange(newFilters: FilterState) {
    updateFilter('date_from', newFilters.date_from)
    updateFilter('date_to', newFilters.date_to)
    updateFilter('business_units', newFilters.business_units)
    updateFilter('category_l1s', newFilters.category_l1s)
    updateFilter('supplier_search', newFilters.supplier_search)
  }

  const filterOptions: FilterOptions = {
    business_units: [],
    category_l1s: [...new Set(categoryData.map(c => c.category_l1 ?? '').filter(Boolean))].sort(),
    legal_entities: [],
    currencies: [],
    countries: [],
  }

  const supplierBarData = supplierData.map(s => ({
    label: s.canonical_supplier_name ?? '',
    value: s.total_spend ?? 0,
  }))

  const categoryL1Map = new Map<string, number>()
  categoryData.forEach(c => {
    const l1 = c.category_l1 ?? 'Unknown'
    categoryL1Map.set(l1, (categoryL1Map.get(l1) ?? 0) + (c.total_spend ?? 0))
  })
  const categoryPieData = [...categoryL1Map.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8)

  const treemapData = categoryPieData.map((d, i) => ({
    ...d,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }))

  const totalWcOpportunity = ptData.reduce((s, r) => s + (r.wc_opportunity_aud ?? 0), 0)
  const recCount = recData?.recommendations?.length ?? 0
  const redCount = diagData.filter(c => c.status === 'RED' || c.status === 'ALERT').length

  const currency = overview?.currency_label ?? 'AUD'
  const maverickPct = overview?.maverick_spend_pct ?? 0
  const maverickAccent = maverickPct > 25 ? 'risk' : maverickPct > 10 ? 'amber' : 'green'

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Spend Overview</h1>

      <FilterBar filters={filters} onChange={handleFilterChange} options={filterOptions} />

      <div className="grid grid-cols-4 gap-4">
        {loadingOverview ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <KpiCard
              label="Total Spend"
              value={overview?.total_spend ?? 0}
              valueType="currency"
              currency={currency}
              accentColor="neutral"
            />
            <KpiCard
              label="Supplier Count"
              value={overview?.supplier_count ?? 0}
              valueType="number"
            />
            <KpiCard
              label="Invoice Count"
              value={overview?.invoice_count ?? 0}
              valueType="number"
            />
            <KpiCard
              label="Maverick Spend"
              value={maverickPct}
              valueType="pct"
              accentColor={maverickAccent}
            />
          </>
        )}
      </div>

      <div className="flex gap-3">
        <Link
          to="payment-terms"
          className="flex items-center gap-3 px-4 py-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors cursor-pointer"
        >
          <DollarSign className="h-5 w-5 text-emerald-600 shrink-0" />
          <div>
            <div className="text-xs text-muted-foreground">WC Opportunity</div>
            <div className="font-semibold text-sm">{formatCurrency(totalWcOpportunity, currency)}</div>
          </div>
        </Link>
        <Link
          to="recommendations"
          className="flex items-center gap-3 px-4 py-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors cursor-pointer"
        >
          <Lightbulb className="h-5 w-5 text-blue-600 shrink-0" />
          <div>
            <div className="text-xs text-muted-foreground">Recommendations</div>
            <div className="font-semibold text-sm">{recCount || '—'}</div>
          </div>
        </Link>
        <Link
          to="quality"
          className="flex items-center gap-3 px-4 py-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors cursor-pointer"
        >
          <AlertTriangle className={`h-5 w-5 shrink-0 ${redCount > 0 ? 'text-rose-600' : 'text-slate-400'}`} />
          <div>
            <div className="text-xs text-muted-foreground">Data Issues</div>
            <div className="font-semibold text-sm">{redCount}</div>
          </div>
        </Link>
      </div>

      <div className="border rounded-xl p-5 bg-card shadow-sm">
        {loadingMonths ? (
          <Skeleton className="h-80" />
        ) : (
          <SpendAreaChart data={monthData} title="Monthly Spend Trend" currency={currency} showReferenceLine={true} />
        )}
      </div>

      <div className="grid grid-cols-5 gap-4">
        <div className="col-span-3 border rounded-xl p-5 bg-card shadow-sm">
          {loadingSuppliers ? (
            <Skeleton className="h-80" />
          ) : (
            <SpendBarChart
              data={supplierBarData}
              title="Top 10 Suppliers"
              horizontal
              valueFormatter={v => formatCurrency(v, currency)}
            />
          )}
        </div>
        <div className="col-span-2 border rounded-xl p-5 bg-card shadow-sm">
          {loadingCategories ? (
            <Skeleton className="h-80" />
          ) : (
            <SpendTreemap
              data={treemapData}
              title="Spend by Category"
              valueFormatter={v => formatCurrency(v, currency)}
            />
          )}
        </div>
      </div>
    </div>
  )
}
