import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
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
import { formatCurrency, formatNumber } from '@/lib/formatters'
import type { PaymentTermsRow, SupplierRow } from '@/types'

const TARGET_DAYS = 45
const WACC = 0.08

function deriveBucket(avgDays: number): string {
  if (avgDays <= 30) return '0-30'
  if (avgDays <= 60) return '31-60'
  if (avgDays <= 90) return '61-90'
  return '90+'
}

function computeSupplierWc(avgDays: number, totalSpend: number): number {
  if (avgDays >= TARGET_DAYS) return 0
  return ((TARGET_DAYS - avgDays) / 365) * totalSpend * WACC
}

const BUCKET_ORDER = ['0-30', '31-60', '61-90', '90+']

export default function PaymentTermsPage() {
  const { id: engagementId } = useParams<{ id: string }>()

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

  const bucketBarData = BUCKET_ORDER.map(b => {
    const row = ptData.find(r => r.bucket === b)
    return { label: b, value: row?.total_spend ?? 0 }
  })

  const suppliersSorted = [...supplierData]
    .filter(s => s.avg_payment_days != null)
    .sort((a, b) => (a.avg_payment_days ?? 0) - (b.avg_payment_days ?? 0))

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">Payment Terms</h1>

      <div className="grid grid-cols-3 gap-4">
        {loadingPt ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <KpiCard
              label="Total WC Opportunity"
              value={totalWcOpportunity}
              valueType="currency"
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

      <div className="border rounded-lg p-4">
        {loadingPt ? (
          <Skeleton className="h-80" />
        ) : (
          <SpendBarChart
            data={bucketBarData}
            title="Spend by Payment Terms Bucket"
            valueFormatter={v => formatCurrency(v)}
          />
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
                    <TableCell className="text-right">{formatNumber(avgDays)}</TableCell>
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
        WC opportunity uses target 45-day terms at 8% WACC
      </p>
    </div>
  )
}
