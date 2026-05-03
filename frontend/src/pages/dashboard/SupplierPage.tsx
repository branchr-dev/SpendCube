import { useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import KpiCard from '@/components/dashboard/KpiCard'
import SpendAreaChart from '@/components/charts/SpendAreaChart'
import SpendPieChart from '@/components/charts/SpendPieChart'
import { DrilldownBreadcrumb } from '@/components/DrilldownBreadcrumb'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber } from '@/lib/formatters'
import type { SupplierRow, MonthRow, CategoryRow } from '@/types'
import type { DrilldownLevel, DrilldownState } from '@/hooks/useDrilldown'

type SortKey = 'canonical_supplier_name' | 'total_spend' | 'transaction_count' | 'avg_payment_days'
type SortDir = 'asc' | 'desc'

function SortIndicator({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 opacity-30">↕</span>
  return <span className="ml-1">{dir === 'asc' ? '↑' : '↓'}</span>
}

export default function SupplierPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('total_spend')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data: supplierData = [], isLoading: loadingSuppliers } = useQuery<SupplierRow[]>({
    queryKey: ['all-suppliers', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/by-supplier`).then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: monthData = [] } = useQuery<MonthRow[]>({
    queryKey: ['by-month-detail', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/by-month`).then(r => r.data),
    enabled: !!engagementId && !!selectedSupplierId,
  })

  const { data: categoryData = [] } = useQuery<CategoryRow[]>({
    queryKey: ['by-category-detail', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/by-category`).then(r => r.data),
    enabled: !!engagementId && !!selectedSupplierId,
  })

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const filtered = useMemo(
    () =>
      supplierData.filter(s =>
        (s.canonical_supplier_name ?? '').toLowerCase().includes(searchTerm.toLowerCase()),
      ),
    [supplierData, searchTerm],
  )

  const sorted = useMemo(
    () =>
      [...filtered].sort((a, b) => {
        const isStr = sortKey === 'canonical_supplier_name'
        const av: string | number = isStr
          ? ((a[sortKey] as string | undefined) ?? '')
          : ((a[sortKey] as number | undefined) ?? 0)
        const bv: string | number = isStr
          ? ((b[sortKey] as string | undefined) ?? '')
          : ((b[sortKey] as number | undefined) ?? 0)
        if (av < bv) return sortDir === 'asc' ? -1 : 1
        if (av > bv) return sortDir === 'asc' ? 1 : -1
        return 0
      }),
    [filtered, sortKey, sortDir],
  )

  const selectedSupplier = selectedSupplierId
    ? (supplierData.find(s => s.canonical_supplier_id === selectedSupplierId) ?? null)
    : null

  const categoryPieData = useMemo(() => {
    const l1Map = new Map<string, number>()
    categoryData.forEach(c => {
      const l1 = c.category_l1 ?? 'Unknown'
      l1Map.set(l1, (l1Map.get(l1) ?? 0) + (c.total_spend ?? 0))
    })
    return [...l1Map.entries()]
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 8)
  }, [categoryData])

  const columns: { key: SortKey; label: string; align?: 'right' }[] = [
    { key: 'canonical_supplier_name', label: 'Supplier Name' },
    { key: 'total_spend', label: 'Total Spend', align: 'right' },
    { key: 'transaction_count', label: 'Invoice Count', align: 'right' },
    { key: 'avg_payment_days', label: 'Avg Payment Days', align: 'right' },
  ]

  const drilldownState: DrilldownState = selectedSupplier
    ? {
        level: 'supplier',
        supplier_id: selectedSupplierId ?? undefined,
        supplier_name: selectedSupplier.canonical_supplier_name,
      }
    : { level: 'overview' }

  function handleBreadcrumbDrillTo(_level: DrilldownLevel, _context: Partial<DrilldownState>) {
    // No intermediate levels in supplier drilldown
  }

  function handleBreadcrumbReset() {
    setSelectedSupplierId(null)
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">Supplier Deep Dive</h1>

      <DrilldownBreadcrumb
        state={drilldownState}
        drillTo={handleBreadcrumbDrillTo}
        reset={handleBreadcrumbReset}
      />

      <Input
        placeholder="Search suppliers…"
        value={searchTerm}
        onChange={e => setSearchTerm(e.target.value)}
        className="max-w-sm"
      />

      <div className="border rounded-lg overflow-auto">
        {loadingSuppliers ? (
          <Skeleton className="h-80 m-4" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map(col => (
                  <TableHead
                    key={col.key}
                    className={col.align === 'right' ? 'text-right' : ''}
                  >
                    <button
                      className="font-semibold hover:text-foreground/80 transition-colors"
                      onClick={() => handleSort(col.key)}
                    >
                      {col.label}
                      <SortIndicator active={sortKey === col.key} dir={sortDir} />
                    </button>
                  </TableHead>
                ))}
                <TableHead>Parent Company</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map(row => {
                const sid = row.canonical_supplier_id ?? row.canonical_supplier_name ?? ''
                const isSelected = selectedSupplierId === row.canonical_supplier_id
                return (
                  <TableRow
                    key={sid}
                    className={`cursor-pointer ${isSelected ? 'bg-primary/10' : 'hover:bg-muted/50'}`}
                    onClick={() =>
                      setSelectedSupplierId(
                        isSelected ? null : (row.canonical_supplier_id ?? null),
                      )
                    }
                  >
                    <TableCell className="font-bold">
                      {row.canonical_supplier_name ?? '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatCurrency(row.total_spend ?? 0)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatNumber(row.transaction_count ?? 0)}
                    </TableCell>
                    <TableCell className="text-right">
                      {row.avg_payment_days != null ? formatNumber(row.avg_payment_days) : '—'}
                    </TableCell>
                    <TableCell>{row.parent_company_name ?? '—'}</TableCell>
                  </TableRow>
                )
              })}
              {sorted.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center text-muted-foreground py-8"
                  >
                    No suppliers match your search.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </div>

      {selectedSupplier && (
        <div className="space-y-4 border-t pt-4">
          <h2 className="text-base font-semibold">{selectedSupplier.canonical_supplier_name}</h2>

          <div className="grid grid-cols-3 gap-4">
            <KpiCard
              label="Total Spend"
              value={selectedSupplier.total_spend ?? 0}
              valueType="currency"
            />
            <KpiCard
              label="Invoice Count"
              value={selectedSupplier.transaction_count ?? 0}
              valueType="number"
            />
            <KpiCard
              label="Avg Payment Days"
              value={selectedSupplier.avg_payment_days ?? 0}
              valueType="number"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="border rounded-lg p-4">
              <SpendAreaChart data={monthData} title="Monthly Spend Trend" />
            </div>
            <div className="border rounded-lg p-4">
              <SpendPieChart
                data={categoryPieData}
                title="Category Mix"
                valueFormatter={v => formatCurrency(v)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
