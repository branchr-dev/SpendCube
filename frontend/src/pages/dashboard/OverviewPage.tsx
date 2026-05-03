import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import FilterBar from '@/components/dashboard/FilterBar'
import KpiCard from '@/components/dashboard/KpiCard'
import SpendAreaChart from '@/components/charts/SpendAreaChart'
import SpendBarChart from '@/components/charts/SpendBarChart'
import SpendPieChart from '@/components/charts/SpendPieChart'
import { useFilters } from '@/hooks/useFilters'
import { api } from '@/lib/api'
import { formatCurrency } from '@/lib/formatters'
import type { OverviewData, MonthRow, SupplierRow, CategoryRow } from '@/types'
import type { FilterState, FilterOptions } from '@/types/filters'

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

  const currency = overview?.currency_label ?? 'AUD'

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
              value={overview?.maverick_spend_pct ?? 0}
              valueType="pct"
            />
          </>
        )}
      </div>

      <div className="border rounded-lg p-4">
        {loadingMonths ? (
          <Skeleton className="h-80" />
        ) : (
          <SpendAreaChart data={monthData} title="Monthly Spend Trend" currency={currency} />
        )}
      </div>

      <div className="grid grid-cols-5 gap-4">
        <div className="col-span-3 border rounded-lg p-4">
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
        <div className="col-span-2 border rounded-lg p-4">
          {loadingCategories ? (
            <Skeleton className="h-80" />
          ) : (
            <SpendPieChart
              data={categoryPieData}
              title="Spend by Category"
              valueFormatter={v => formatCurrency(v, currency)}
            />
          )}
        </div>
      </div>
    </div>
  )
}
