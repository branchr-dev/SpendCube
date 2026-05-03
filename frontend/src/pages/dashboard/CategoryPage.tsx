import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import FilterBar from '@/components/dashboard/FilterBar'
import KpiCard from '@/components/dashboard/KpiCard'
import SpendBarChart from '@/components/charts/SpendBarChart'
import { SEMANTIC_COLORS } from '@/components/charts/constants'
import { DrilldownBreadcrumb } from '@/components/DrilldownBreadcrumb'
import { useFilters } from '@/hooks/useFilters'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber } from '@/lib/formatters'
import type { CategoryRow, SupplierRow } from '@/types'
import type { FilterState, FilterOptions } from '@/types/filters'
import type { DrilldownLevel, DrilldownState } from '@/hooks/useDrilldown'

interface L2Summary {
  l2: string
  total_spend: number
  supplier_count: number
  transaction_count: number
  l3s: CategoryRow[]
}

interface L1Summary {
  l1: string
  total_spend: number
  supplier_count: number
  transaction_count: number
  l2Map: Map<string, L2Summary>
}

function buildHierarchy(rows: CategoryRow[]): Map<string, L1Summary> {
  return rows.reduce((acc, row) => {
    const l1 = row.category_l1 ?? 'Unknown'
    const l2 = row.category_l2 ?? 'Unknown'

    if (!acc.has(l1)) {
      acc.set(l1, { l1, total_spend: 0, supplier_count: 0, transaction_count: 0, l2Map: new Map() })
    }
    const l1Entry = acc.get(l1)!
    l1Entry.total_spend += row.total_spend ?? 0
    l1Entry.supplier_count += row.supplier_count ?? 0
    l1Entry.transaction_count += row.transaction_count ?? 0

    if (!l1Entry.l2Map.has(l2)) {
      l1Entry.l2Map.set(l2, { l2, total_spend: 0, supplier_count: 0, transaction_count: 0, l3s: [] })
    }
    const l2Entry = l1Entry.l2Map.get(l2)!
    l2Entry.total_spend += row.total_spend ?? 0
    l2Entry.supplier_count += row.supplier_count ?? 0
    l2Entry.transaction_count += row.transaction_count ?? 0
    l2Entry.l3s.push(row)

    return acc
  }, new Map<string, L1Summary>())
}

function fragmentationBadge(supplierCount: number) {
  if (supplierCount > 5) {
    return <Badge variant="destructive">Fragmented ({supplierCount} suppliers)</Badge>
  }
  if (supplierCount >= 3) {
    return (
      <Badge className="bg-amber-500 hover:bg-amber-600 text-white">
        Moderate ({supplierCount} suppliers)
      </Badge>
    )
  }
  return (
    <Badge className="bg-green-600 hover:bg-green-700 text-white">
      Focused ({supplierCount} suppliers)
    </Badge>
  )
}

export default function CategoryPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const { filters, updateFilter, toQueryParams } = useFilters()
  const qp = toQueryParams()
  const [selectedL1, setSelectedL1] = useState<string | null>(null)
  const [selectedL2, setSelectedL2] = useState<string | null>(null)

  const { data: categoryData = [], isLoading } = useQuery<CategoryRow[]>({
    queryKey: ['by-category', engagementId, qp],
    queryFn: () =>
      api
        .get(`/api/engagements/${engagementId}/cube/by-category`, { params: qp })
        .then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: topCategorySuppliers = [] } = useQuery<SupplierRow[]>({
    queryKey: ['suppliers-by-category', engagementId, selectedL1],
    queryFn: () =>
      api
        .get(`/api/engagements/${engagementId}/cube/by-supplier`, {
          params: { category_l1: selectedL1 },
        })
        .then(r => r.data),
    enabled: !!engagementId && !!selectedL1,
  })

  function handleFilterChange(newFilters: FilterState) {
    updateFilter('date_from', newFilters.date_from)
    updateFilter('date_to', newFilters.date_to)
    updateFilter('business_units', newFilters.business_units)
    updateFilter('category_l1s', newFilters.category_l1s)
    updateFilter('supplier_search', newFilters.supplier_search)
  }

  function handleL1Click(label: string) {
    setSelectedL1(prev => (prev === label ? null : label))
    setSelectedL2(null)
  }

  function handleL2Click(label: string) {
    setSelectedL2(prev => (prev === label ? null : label))
  }

  const filterOptions: FilterOptions = {
    business_units: [],
    category_l1s: [...new Set(categoryData.map(c => c.category_l1 ?? '').filter(Boolean))].sort(),
    legal_entities: [],
    currencies: [],
    countries: [],
  }

  const hierarchy = buildHierarchy(categoryData)

  const l1Entries = [...hierarchy.values()].sort((a, b) => b.total_spend - a.total_spend)
  const totalSpend = l1Entries.reduce((sum, e) => sum + e.total_spend, 0)

  function fragColor(supplierCount: number): string {
    if (supplierCount <= 2) return SEMANTIC_COLORS.opportunity
    if (supplierCount <= 5) return SEMANTIC_COLORS.attention
    return SEMANTIC_COLORS.risk
  }

  const l1BarData = l1Entries.map(entry => ({ label: entry.l1, value: entry.total_spend }))
  const l1Colors = l1Entries.map(entry => fragColor(entry.supplier_count))

  const selectedL1Entry = selectedL1 ? hierarchy.get(selectedL1) : null

  const l2BarData = selectedL1Entry
    ? [...selectedL1Entry.l2Map.values()]
        .sort((a, b) => b.total_spend - a.total_spend)
        .map(entry => ({ label: entry.l2, value: entry.total_spend }))
    : []

  const selectedL2Entry = selectedL1Entry && selectedL2
    ? selectedL1Entry.l2Map.get(selectedL2)
    : null

  const l3Rows = selectedL2Entry
    ? [...selectedL2Entry.l3s].sort((a, b) => (b.total_spend ?? 0) - (a.total_spend ?? 0))
    : []

  const drilldownState: DrilldownState = selectedL2 && selectedL1
    ? { level: 'category_l2', category_l1: selectedL1, category_l2: selectedL2 }
    : selectedL1
    ? { level: 'category_l1', category_l1: selectedL1 }
    : { level: 'overview' }

  function handleBreadcrumbDrillTo(_level: DrilldownLevel, context: Partial<DrilldownState>) {
    setSelectedL1(context.category_l1 ?? null)
    setSelectedL2(context.category_l2 ?? null)
  }

  function handleBreadcrumbReset() {
    setSelectedL1(null)
    setSelectedL2(null)
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Category Deep Dive</h1>

      <FilterBar filters={filters} onChange={handleFilterChange} options={filterOptions} />

      <DrilldownBreadcrumb
        state={drilldownState}
        drillTo={handleBreadcrumbDrillTo}
        reset={handleBreadcrumbReset}
      />

      {selectedL1Entry && (
        <div className="grid grid-cols-4 gap-4">
          <KpiCard
            label={`${selectedL1} — Total Spend`}
            value={selectedL1Entry.total_spend}
            valueType="currency"
            accentColor={
              selectedL1Entry.supplier_count <= 2
                ? 'opportunity'
                : selectedL1Entry.supplier_count <= 5
                ? 'amber'
                : 'risk'
            }
          />
          <KpiCard
            label="Supplier Count"
            value={selectedL1Entry.supplier_count}
            valueType="number"
          />
          <KpiCard
            label="Transactions"
            value={selectedL1Entry.transaction_count}
            valueType="number"
          />
          <KpiCard
            label="Share of Total"
            value={totalSpend > 0 ? (selectedL1Entry.total_spend / totalSpend) * 100 : 0}
            valueType="pct"
          />
        </div>
      )}

      {!isLoading && !selectedL1Entry && (
        <div className="border rounded-xl p-5 bg-card shadow-sm">
          <h3 className="section-header">Fragmentation Scorecard</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>L1 Category</TableHead>
                <TableHead className="text-right">Total Spend</TableHead>
                <TableHead className="text-right">% of Total</TableHead>
                <TableHead className="text-right">Suppliers</TableHead>
                <TableHead className="text-right">Avg Invoice</TableHead>
                <TableHead className="text-right">Spend / Supplier</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {l1Entries.map((entry, i) => (
                <TableRow key={i}>
                  <TableCell className="font-medium">{entry.l1}</TableCell>
                  <TableCell className="text-right">{formatCurrency(entry.total_spend)}</TableCell>
                  <TableCell className="text-right">
                    {totalSpend > 0 ? ((entry.total_spend / totalSpend) * 100).toFixed(1) : '0.0'}%
                  </TableCell>
                  <TableCell className="text-right">{formatNumber(entry.supplier_count)}</TableCell>
                  <TableCell
                    className={
                      entry.total_spend / Math.max(entry.transaction_count, 1) > 50000
                        ? 'text-right font-medium text-amber-600'
                        : 'text-right'
                    }
                  >
                    {formatCurrency(entry.total_spend / Math.max(entry.transaction_count, 1))}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatCurrency(entry.total_spend / Math.max(entry.supplier_count, 1))}
                  </TableCell>
                  <TableCell>{fragmentationBadge(entry.supplier_count)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="border rounded-xl p-5 bg-card shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <h3 className="section-header">Spend by L1 Category</h3>
          {selectedL1Entry && (
            <>
              <span className="text-sm font-medium text-primary">— {selectedL1}</span>
              {fragmentationBadge(selectedL1Entry.supplier_count)}
              <button
                className="text-xs text-muted-foreground underline"
                onClick={() => { setSelectedL1(null); setSelectedL2(null) }}
              >
                Clear selection
              </button>
            </>
          )}
        </div>
        {isLoading ? (
          <Skeleton className="h-80" />
        ) : (
          <SpendBarChart
            data={l1BarData}
            title=""
            horizontal
            colors={l1Colors}
            valueFormatter={v => formatCurrency(v)}
            onBarClick={handleL1Click}
            clickHint
            selectedLabel={selectedL1 ?? undefined}
          />
        )}
      </div>

      {selectedL1Entry && (
        <div className="border rounded-xl p-5 bg-card shadow-sm">
          <div className="flex items-center gap-3 mb-1">
            <h3 className="section-header">L2 Breakdown — {selectedL1}</h3>
            {selectedL2 && (
              <>
                <span className="text-sm text-muted-foreground">/ {selectedL2}</span>
                <button
                  className="text-xs text-muted-foreground underline"
                  onClick={() => setSelectedL2(null)}
                >
                  Clear
                </button>
              </>
            )}
          </div>
          <SpendBarChart
            data={l2BarData}
            title=""
            horizontal
            valueFormatter={v => formatCurrency(v)}
            onBarClick={handleL2Click}
            showLabel
          />
        </div>
      )}

      {selectedL1Entry && (
        <div className="border rounded-xl p-5 bg-card shadow-sm">
          <h3 className="section-header">Top Suppliers — {selectedL1}</h3>
          {topCategorySuppliers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No supplier data available for this category.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Supplier Name</TableHead>
                  <TableHead className="text-right">Total Spend</TableHead>
                  <TableHead className="text-right">Invoice Count</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...topCategorySuppliers]
                  .sort((a, b) => (b.total_spend ?? 0) - (a.total_spend ?? 0))
                  .slice(0, 5)
                  .map((row, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium">{row.canonical_supplier_name ?? '—'}</TableCell>
                      <TableCell className="text-right">{formatCurrency(row.total_spend ?? 0)}</TableCell>
                      <TableCell className="text-right">{formatNumber(row.transaction_count ?? 0)}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}

      {selectedL2Entry && l3Rows.length > 0 && (
        <div className="border rounded-xl p-5 bg-card shadow-sm">
          <h3 className="section-header">L3 Detail — {selectedL2}</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">Spend</TableHead>
                <TableHead className="text-right">Transactions</TableHead>
                <TableHead className="text-right">Suppliers</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {l3Rows.map((row, i) => (
                <TableRow key={i}>
                  <TableCell className="font-medium">{row.category_l3 ?? row.category_l2 ?? '—'}</TableCell>
                  <TableCell className="text-right">{formatCurrency(row.total_spend ?? 0)}</TableCell>
                  <TableCell className="text-right">{formatNumber(row.transaction_count ?? 0)}</TableCell>
                  <TableCell className="text-right">{formatNumber(row.supplier_count ?? 0)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
