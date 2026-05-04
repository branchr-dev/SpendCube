import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  LabelList,
} from 'recharts'
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
import SpendBarChart from '@/components/charts/SpendBarChart'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, formatPct } from '@/lib/formatters'
import type { PaymentTermsRow, SupplierRow } from '@/types'

const BUCKET_COLORS: Record<string, string> = {
  '0-30': '#f43f5e',
  '31-60': '#f59e0b',
  '61-90': '#10b981',
  '90+': '#3b82f6',
}

function deriveBucket(avgDays: number): string {
  if (avgDays <= 30) return '0-30'
  if (avgDays <= 60) return '31-60'
  if (avgDays <= 90) return '61-90'
  return '90+'
}

const BUCKET_ORDER = ['0-30', '31-60', '61-90', '90+'] as const

export default function PaymentTermsPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const [waccPct, setWaccPct] = useState(8)
  const [targetDays, setTargetDays] = useState(45)

  function computeSupplierWc(avgDays: number, totalSpend: number): number {
    if (avgDays >= targetDays) return 0
    return ((targetDays - avgDays) / 365) * totalSpend * (waccPct / 100)
  }

  const { data: ptData = [], isLoading: loadingPt } = useQuery<PaymentTermsRow[]>({
    queryKey: ['by-payment-terms', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/by-payment-terms`).then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: supplierData = [], isLoading: loadingSuppliers } = useQuery<SupplierRow[]>({
    queryKey: ['all-suppliers-pt', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/by-supplier`).then(r => r.data),
    enabled: !!engagementId,
  })

  const totalWcOpportunity = ptData.reduce((sum, row) => sum + (row.wc_opportunity_aud ?? 0), 0)

  const bucket0_30 = ptData.find(r => r.bucket === '0-30')
  const bucket90plus = ptData.find(r => r.bucket === '90+')
  const pct0_30 = bucket0_30?.spend_pct ?? 0
  const pct90plus = bucket90plus?.spend_pct ?? 0

  const totalBucketSpend = ptData.reduce((s, r) => s + (r.total_spend ?? 0), 0)

  const stackedData = [
    BUCKET_ORDER.reduce((acc, b) => {
      const row = ptData.find(r => r.bucket === b)
      const spend = row?.total_spend ?? 0
      const pct = totalBucketSpend > 0 ? (spend / totalBucketSpend) * 100 : 0
      acc[b] = pct
      acc[`${b}_aud`] = spend
      return acc
    }, {} as Record<string, number>),
  ]

  const suppliersSorted = [...supplierData]
    .filter(s => s.avg_payment_days != null)
    .sort((a, b) =>
      computeSupplierWc(b.avg_payment_days ?? 0, b.total_spend ?? 0) -
      computeSupplierWc(a.avg_payment_days ?? 0, a.total_spend ?? 0)
    )

  const supplierWcData = suppliersSorted
    .map(s => ({
      label: (s.canonical_supplier_name ?? '').slice(0, 22),
      value: computeSupplierWc(s.avg_payment_days ?? 0, s.total_spend ?? 0),
    }))
    .filter(d => d.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 15)

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Payment Terms</h1>

      <div className="grid grid-cols-3 gap-4">
        {loadingPt ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <KpiCard
              label="Total WC Opportunity"
              value={totalWcOpportunity}
              valueType="currency"
              accentColor="opportunity"
            />
            <KpiCard
              label="Spend in 0–30 Day Bucket"
              value={pct0_30}
              valueType="pct"
            />
            <KpiCard
              label="Spend in 90+ Day Bucket"
              value={pct90plus}
              valueType="pct"
            />
          </>
        )}
      </div>

      <div className="flex items-center gap-6 p-4 bg-muted/30 rounded-lg border mb-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Target Days</label>
          <Input
            type="number"
            min={30}
            max={120}
            value={targetDays}
            onChange={e => setTargetDays(Number(e.target.value))}
            className="w-20"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">WACC %</label>
          <Input
            type="number"
            min={1}
            max={20}
            step={0.5}
            value={waccPct}
            onChange={e => setWaccPct(Number(e.target.value))}
            className="w-20"
          />
        </div>
        <p className="text-xs text-muted-foreground">
          WC opportunity = (target − current days) / 365 × spend × WACC
        </p>
      </div>

      <div className="border rounded-lg p-4">
        {loadingSuppliers ? (
          <Skeleton className="h-80" />
        ) : (
          <SpendBarChart
            data={supplierWcData}
            title="Top WC Opportunities by Supplier"
            horizontal={true}
            valueFormatter={v => formatCurrency(v)}
            showLabel={false}
          />
        )}
      </div>

      <div className="border rounded-xl p-5 bg-card shadow-sm">
        <h3 className="section-header">Payment Terms Distribution</h3>
        {loadingPt ? (
          <Skeleton className="h-20" />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={80}>
              <BarChart data={stackedData} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis type="category" hide />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any, name: any) => {
                    const numVal = typeof value === 'number' ? value : 0
                    const nameStr = String(name)
                    const aud = stackedData[0][`${nameStr}_aud`] ?? 0
                    return [`${formatPct(numVal)} — ${formatCurrency(aud)}`, nameStr]
                  }}
                />
                {BUCKET_ORDER.map(b => (
                  <Bar key={b} dataKey={b} stackId="a" fill={BUCKET_COLORS[b]}>
                    <LabelList
                      dataKey={b}
                      position="center"
                      style={{ fontSize: 11, fill: '#fff', fontWeight: 500 }}
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      formatter={(v: any) => {
                        const n = typeof v === 'number' ? v : 0
                        return n >= 5 ? `${n.toFixed(1)}%` : ''
                      }}
                    />
                    <Cell fill={BUCKET_COLORS[b]} />
                  </Bar>
                ))}
              </BarChart>
            </ResponsiveContainer>
            <div className="flex gap-4 mt-2">
              {BUCKET_ORDER.map(b => (
                <div key={b} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: BUCKET_COLORS[b] }} />
                  {b} days
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="border rounded-lg overflow-auto">
        {loadingSuppliers ? (
          <Skeleton className="h-80 m-4" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Supplier</TableHead>
                <TableHead className="text-right">Avg Days</TableHead>
                <TableHead className="text-right">Total Spend</TableHead>
                <TableHead>Bucket</TableHead>
                <TableHead className="text-right">WC Opportunity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppliersSorted.map(row => {
                const avgDays = row.avg_payment_days ?? 0
                const spend = row.total_spend ?? 0
                const wc = computeSupplierWc(avgDays, spend)
                return (
                  <TableRow key={row.canonical_supplier_id ?? row.canonical_supplier_name}>
                    <TableCell className="font-medium">
                      {row.canonical_supplier_name ?? '—'}
                    </TableCell>
                    <TableCell
                      className={
                        avgDays < 30
                          ? 'text-right font-medium text-rose-700'
                          : avgDays < 45
                          ? 'text-right font-medium text-amber-700'
                          : 'text-right'
                      }
                    >
                      {formatNumber(Math.round(avgDays))}
                    </TableCell>
                    <TableCell className="text-right">{formatCurrency(spend)}</TableCell>
                    <TableCell>{deriveBucket(avgDays)}</TableCell>
                    <TableCell className="text-right">
                      {wc > 0 ? formatCurrency(wc) : '—'}
                    </TableCell>
                  </TableRow>
                )
              })}
              {suppliersSorted.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                    No supplier data available.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        WC opportunity uses target {targetDays}-day terms at {waccPct}% WACC
      </p>
    </div>
  )
}
