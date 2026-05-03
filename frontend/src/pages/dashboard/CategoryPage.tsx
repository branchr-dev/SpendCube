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
import { useFilters } from '@/hooks/useFilters'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber } from '@/lib/formatters'
import type { CategoryRow } from '@/types'
import type { FilterState, FilterOptions } from '@/types/filters'

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

  const l1BarData = [...hierarchy.values()]
    .sort((a, b) => b.total_spend - a.total_spend)
    .map(entry => ({ label: entry.l1, value: entry.total_spend }))

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

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">Category Deep Dive</h1>

      <FilterBar filters={filters} onChange={handleFilterChange} options={filterOptions} />

      {selectedL1Entry && (
        <div className="grid grid-cols-3 gap-4">
          <KpiCard
            label={`${selectedL1} — Total Spend`}
            value={selectedL1Entry.total_spend}
            valueType="currency"
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
        </div>
      )}

      <div className="border rounded-lg p-4">
        <div className="flex items-center gap-3 mb-3">
          <h3 className="text-sm font-medium">Spend by L1 Category</h3>
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
            valueFormatter={v => formatCurrency(v)}
            onBarClick={handleL1Click}
          />
        )}
      </div>

      {selectedL1Entry && (
        <div className="border rounded-lg p-4">
          <div className="flex items-center gap-3 mb-1">
            <h3 className="text-sm font-medium">L2 Breakdown — {selectedL1}</h3>
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
          />
        </div>
      )}

      {selectedL2Entry && l3Rows.length > 0 && (
        <div className="border rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3">L3 Detail — {selectedL2}</h3>
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
