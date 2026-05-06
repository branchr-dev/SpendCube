import { useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import KpiCard from '@/components/dashboard/KpiCard'
import SpendAreaChart from '@/components/charts/SpendAreaChart'
import SpendPieChart from '@/components/charts/SpendPieChart'
import { DrilldownBreadcrumb } from '@/components/DrilldownBreadcrumb'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, formatPct } from '@/lib/formatters'
import type { SupplierRow, MonthRow, CategoryRow } from '@/types'
import type { DrilldownLevel, DrilldownState } from '@/hooks/useDrilldown'
import { Building2, ChevronRight, ChevronDown } from 'lucide-react'

type SortKey = 'canonical_supplier_name' | 'total_spend' | 'transaction_count' | 'avg_payment_days'
type SortDir = 'asc' | 'desc'

function SortIndicator({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 opacity-30">↕</span>
  return <span className="ml-1">{dir === 'asc' ? '↑' : '↓'}</span>
}

const isSortKey = (key: string): key is SortKey =>
  ['canonical_supplier_name', 'total_spend', 'transaction_count', 'avg_payment_days'].includes(key)

function AbcBadge({ segment }: { segment?: string }) {
  if (!segment) return null
  const classMap: Record<string, string> = {
    A: 'bg-emerald-100 text-emerald-800 border-0 text-xs',
    B: 'bg-blue-100 text-blue-800 border-0 text-xs',
    C: 'bg-slate-100 text-slate-600 border-0 text-xs',
  }
  return <Badge className={classMap[segment] ?? 'text-xs'}>{segment}</Badge>
}

const computeWc = (avgDays: number, spend: number) =>
  avgDays < 45 ? ((45 - avgDays) / 365) * spend * 0.08 : 0

export default function SupplierPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('total_spend')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [groupByParent, setGroupByParent] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())

  const toggleGroup = (g: string) =>
    setExpandedGroups(prev => {
      const n = new Set(prev)
      n.has(g) ? n.delete(g) : n.add(g)
      return n
    })

  const { data: supplierData = [], isLoading: loadingSuppliers } = useQuery<SupplierRow[]>({
    queryKey: ['all-suppliers', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/by-supplier`, { params: { limit: 500 } }).then(r => r.data?.data ?? []),
    enabled: !!engagementId,
    staleTime: 5 * 60 * 1000,
  })

  const { data: monthData = [] } = useQuery<MonthRow[]>({
    queryKey: ['by-month-detail', engagementId, selectedSupplierId],
    queryFn: () =>
      api
        .get(`/api/engagements/${engagementId}/cube/by-month`, {
          params: { supplier_id: selectedSupplierId },
        })
        .then(r => r.data),
    enabled: !!engagementId && !!selectedSupplierId,
    staleTime: 5 * 60 * 1000,
  })

  const { data: categoryData = [] } = useQuery<CategoryRow[]>({
    queryKey: ['by-category-detail', engagementId, selectedSupplierId],
    queryFn: () =>
      api
        .get(`/api/engagements/${engagementId}/cube/by-category`, {
          params: { supplier_id: selectedSupplierId },
        })
        .then(r => r.data),
    enabled: !!engagementId && !!selectedSupplierId,
    staleTime: 5 * 60 * 1000,
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

  const groupedData = useMemo(() => {
    if (!groupByParent) return null
    const map = new Map<string, { rows: SupplierRow[]; totalSpend: number }>()
    for (const row of sorted) {
      const key = row.parent_company_name ?? '__independent__'
      const existing = map.get(key) ?? { rows: [], totalSpend: 0 }
      existing.rows.push(row)
      existing.totalSpend += row.total_spend ?? 0
      map.set(key, existing)
    }
    return [...map.entries()]
      .sort(([keyA, a], [keyB, b]) => {
        if (keyA === '__independent__') return 1
        if (keyB === '__independent__') return -1
        return b.totalSpend - a.totalSpend
      })
  }, [sorted, groupByParent])

  const selectedSupplier = selectedSupplierId
    ? (supplierData.find(s => s.canonical_supplier_id === selectedSupplierId) ?? null)
    : null

  const totalSupplierSpend = supplierData.reduce((s, r) => s + (r.total_spend ?? 0), 0)

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

  const columns: { key: string; label: string; align?: 'right' }[] = [
    { key: 'canonical_supplier_name', label: 'Supplier Name' },
    { key: 'abc', label: 'ABC' },
    { key: 'total_spend', label: 'Total Spend', align: 'right' },
    { key: 'share', label: 'Share', align: 'right' },
    { key: 'transaction_count', label: 'Invoice Count', align: 'right' },
    { key: 'avg_payment_days', label: 'Avg Payment Days', align: 'right' },
    { key: 'wc_opp', label: 'WC Opp.', align: 'right' },
  ]

  const top5Spend = sorted.slice(0, 5).reduce((s, r) => s + (r.total_spend ?? 0), 0)
  const top10Spend = sorted.slice(0, 10).reduce((s, r) => s + (r.total_spend ?? 0), 0)

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
      <h1 className="text-2xl font-bold">Supplier Deep Dive</h1>

      <DrilldownBreadcrumb
        state={drilldownState}
        drillTo={handleBreadcrumbDrillTo}
        reset={handleBreadcrumbReset}
      />

      <div className="flex items-center gap-3">
        <Input
          placeholder="Search suppliers…"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className="max-w-sm"
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => setGroupByParent(p => !p)}
        >
          <Building2 className="h-4 w-4 mr-2" />
          {groupByParent ? 'Show All' : 'Group by Parent'}
        </Button>
      </div>

      {totalSupplierSpend > 0 && sorted.length >= 5 && (
        <div className="flex items-center gap-6 text-sm text-muted-foreground bg-muted/30 rounded-lg px-4 py-2">
          <span>Top 5 suppliers: {formatPct((top5Spend / totalSupplierSpend) * 100)} of spend</span>
          <span>Top 10 suppliers: {formatPct((top10Spend / totalSupplierSpend) * 100)} of spend</span>
        </div>
      )}

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
                    {isSortKey(col.key) ? (
                      <button
                        className="font-semibold hover:text-foreground/80 transition-colors"
                        onClick={() => handleSort(col.key as SortKey)}
                      >
                        {col.label}
                        <SortIndicator active={sortKey === col.key} dir={sortDir} />
                      </button>
                    ) : (
                      <span className="font-semibold">{col.label}</span>
                    )}
                  </TableHead>
                ))}
                <TableHead>Parent Company</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!groupByParent ? (
                <>
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
                        <TableCell>
                          <AbcBadge segment={row.abc_segment} />
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(row.total_spend ?? 0)}
                        </TableCell>
                        <TableCell className="text-right">
                          {totalSupplierSpend > 0
                            ? formatPct(((row.total_spend ?? 0) / totalSupplierSpend) * 100)
                            : '—'}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatNumber(row.transaction_count ?? 0)}
                        </TableCell>
                        <TableCell
                          className={
                            (row.avg_payment_days ?? 0) < 30
                              ? 'text-right font-medium bg-rose-50 text-rose-700'
                              : (row.avg_payment_days ?? 0) < 45
                                ? 'text-right font-medium bg-amber-50 text-amber-700'
                                : 'text-right'
                          }
                        >
                          {row.avg_payment_days != null ? formatNumber(row.avg_payment_days) : '—'}
                        </TableCell>
                        <TableCell className="text-right">
                          {(() => {
                            const wc = computeWc(row.avg_payment_days ?? 0, row.total_spend ?? 0)
                            return wc > 0 ? (
                              <span className="text-emerald-600 font-medium">{formatCurrency(wc)}</span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )
                          })()}
                        </TableCell>
                        <TableCell>{row.parent_company_name ?? '—'}</TableCell>
                      </TableRow>
                    )
                  })}
                  {sorted.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                        No suppliers match your search.
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ) : (
                <>
                  {(groupedData ?? []).map(([groupKey, { rows, totalSpend }]) => {
                    const isExpanded = expandedGroups.has(groupKey)
                    const displayName =
                      groupKey === '__independent__' ? 'Independent Suppliers' : groupKey
                    return (
                      <>
                        <TableRow
                          key={`group-${groupKey}`}
                          className="bg-muted/40 cursor-pointer hover:bg-muted/60"
                          onClick={() => toggleGroup(groupKey)}
                        >
                          <TableCell colSpan={8}>
                            <div className="flex items-center gap-2 font-semibold">
                              {isExpanded ? (
                                <ChevronDown className="h-4 w-4 shrink-0" />
                              ) : (
                                <ChevronRight className="h-4 w-4 shrink-0" />
                              )}
                              <span>{displayName}</span>
                              <span className="ml-2 text-muted-foreground font-normal">
                                {formatCurrency(totalSpend)}
                              </span>
                              <span className="text-muted-foreground font-normal text-sm">
                                · {rows.length} supplier{rows.length !== 1 ? 's' : ''}
                              </span>
                            </div>
                          </TableCell>
                        </TableRow>
                        {isExpanded &&
                          rows.map(row => {
                            const sid =
                              row.canonical_supplier_id ?? row.canonical_supplier_name ?? ''
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
                                <TableCell className="font-bold pl-8">
                                  {row.canonical_supplier_name ?? '—'}
                                </TableCell>
                                <TableCell>
                                  <AbcBadge segment={row.abc_segment} />
                                </TableCell>
                                <TableCell className="text-right">
                                  {formatCurrency(row.total_spend ?? 0)}
                                </TableCell>
                                <TableCell className="text-right">
                                  {totalSupplierSpend > 0
                                    ? formatPct(
                                        ((row.total_spend ?? 0) / totalSupplierSpend) * 100,
                                      )
                                    : '—'}
                                </TableCell>
                                <TableCell className="text-right">
                                  {formatNumber(row.transaction_count ?? 0)}
                                </TableCell>
                                <TableCell
                                  className={
                                    (row.avg_payment_days ?? 0) < 30
                                      ? 'text-right font-medium bg-rose-50 text-rose-700'
                                      : (row.avg_payment_days ?? 0) < 45
                                        ? 'text-right font-medium bg-amber-50 text-amber-700'
                                        : 'text-right'
                                  }
                                >
                                  {row.avg_payment_days != null
                                    ? formatNumber(row.avg_payment_days)
                                    : '—'}
                                </TableCell>
                                <TableCell className="text-right">
                                  {(() => {
                                    const wc = computeWc(
                                      row.avg_payment_days ?? 0,
                                      row.total_spend ?? 0,
                                    )
                                    return wc > 0 ? (
                                      <span className="text-emerald-600 font-medium">
                                        {formatCurrency(wc)}
                                      </span>
                                    ) : (
                                      <span className="text-muted-foreground">—</span>
                                    )
                                  })()}
                                </TableCell>
                                <TableCell>{row.parent_company_name ?? '—'}</TableCell>
                              </TableRow>
                            )
                          })}
                      </>
                    )
                  })}
                  {(groupedData ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                        No suppliers match your search.
                      </TableCell>
                    </TableRow>
                  )}
                </>
              )}
            </TableBody>
          </Table>
        )}
      </div>

      <Sheet
        open={!!selectedSupplierId}
        onOpenChange={open => {
          if (!open) setSelectedSupplierId(null)
        }}
      >
        <SheetContent side="right" className="w-[500px] sm:w-[560px] overflow-y-auto p-6">
          <SheetHeader>
            <SheetTitle>{selectedSupplier?.canonical_supplier_name ?? ''}</SheetTitle>
          </SheetHeader>

          {(selectedSupplier?.parent_company_name || selectedSupplier?.abc_segment) && (
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              {selectedSupplier?.parent_company_name && (
                <Badge variant="outline" className="text-xs">
                  {selectedSupplier.parent_company_name}
                </Badge>
              )}
              {selectedSupplier?.abc_segment && (
                <AbcBadge segment={selectedSupplier.abc_segment} />
              )}
            </div>
          )}

          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <KpiCard
                label="Total Spend"
                value={selectedSupplier?.total_spend ?? 0}
                valueType="currency"
              />
              <KpiCard
                label="Invoice Count"
                value={selectedSupplier?.transaction_count ?? 0}
                valueType="number"
              />
              <KpiCard
                label="Avg Payment Days"
                value={selectedSupplier?.avg_payment_days ?? 0}
                valueType="number"
              />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <KpiCard
                label="Spend Share"
                value={
                  totalSupplierSpend > 0
                    ? ((selectedSupplier?.total_spend ?? 0) / totalSupplierSpend) * 100
                    : 0
                }
                valueType="pct"
              />
              <KpiCard
                label="WC Opportunity"
                value={computeWc(
                  selectedSupplier?.avg_payment_days ?? 0,
                  selectedSupplier?.total_spend ?? 0,
                )}
                valueType="currency"
                accentColor={
                  computeWc(
                    selectedSupplier?.avg_payment_days ?? 0,
                    selectedSupplier?.total_spend ?? 0,
                  ) > 0
                    ? 'opportunity'
                    : 'neutral'
                }
              />
              <KpiCard
                label="Segment"
                value={selectedSupplier?.abc_segment ?? '—'}
                valueType="text"
                accentColor={selectedSupplier?.abc_segment === 'A' ? 'opportunity' : 'neutral'}
              />
            </div>

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
        </SheetContent>
      </Sheet>
    </div>
  )
}
