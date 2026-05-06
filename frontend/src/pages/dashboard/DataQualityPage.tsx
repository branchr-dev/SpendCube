import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ChevronDown, ChevronRight } from 'lucide-react'
import DiagnosticsCheckCard from '@/components/dashboard/DiagnosticsCheckCard'
import { api } from '@/lib/api'
import { formatDate } from '@/lib/formatters'

type Status = 'GREEN' | 'AMBER' | 'RED'

const STATUS_SCORE: Record<string, number> = {
  GREEN: 100, AMBER: 50, RED: 0, INFO: 100, WARN: 50, ALERT: 0,
}

const STATUS_NORMALIZE: Record<string, Status> = {
  GREEN: 'GREEN', INFO: 'GREEN', AMBER: 'AMBER', WARN: 'AMBER', RED: 'RED', ALERT: 'RED',
}

interface CheckResult {
  value?: number
  pct?: number
  status?: string
  description?: string
}

interface BatchSummary {
  id: string
  filename: string
  row_count: number
  new_rows: number
  duplicate_rows: number
  status: string
  uploaded_at: string | null
  completed_at: string | null
}

interface StatusBreakdown {
  pipeline_status: string
  count: number
}

interface BatchDetail {
  batch: BatchSummary
  pipeline_status_breakdown: StatusBreakdown[]
  sample_rows: { id: string; invoice_number: string | null; invoice_date: string | null; raw_supplier_name: string | null; base_amount: number | null; pipeline_status: string }[]
}

function batchStatusBadge(status: string) {
  if (status === 'complete') return <Badge className="bg-green-100 text-green-800 border-green-200">Complete</Badge>
  if (status === 'processing') return <Badge className="bg-blue-100 text-blue-800 border-blue-200">Processing</Badge>
  if (status === 'failed') return <Badge className="bg-red-100 text-red-800 border-red-200">Failed</Badge>
  return <Badge className="bg-slate-100 text-slate-700 border-slate-200">{status}</Badge>
}

function pipelineStatusBadge(status: string) {
  if (status === 'processed') return <Badge className="bg-green-100 text-green-800 border-green-200">Promoted</Badge>
  if (status === 'review_required') return <Badge className="bg-amber-100 text-amber-800 border-amber-200">Review Required</Badge>
  if (status === 'failed') return <Badge className="bg-red-100 text-red-800 border-red-200">Failed</Badge>
  if (status === 'queued') return <Badge className="bg-slate-100 text-slate-600 border-slate-200">Queued</Badge>
  return <Badge variant="outline">{status}</Badge>
}

function ReconciliationBanner({ batches, analyticsCount }: { batches: BatchSummary[]; analyticsCount: number | null }) {
  const totalUploaded = batches.reduce((s, b) => s + (b.new_rows ?? 0), 0)
  const totalDuplicates = batches.reduce((s, b) => s + (b.duplicate_rows ?? 0), 0)

  const reconciles = analyticsCount != null && analyticsCount <= totalUploaded

  return (
    <div className="border rounded-xl p-4 bg-card shadow-sm space-y-3">
      <h3 className="section-header">Row Reconciliation</h3>
      <div className="flex flex-wrap gap-6 text-sm">
        <div>
          <p className="text-2xl font-bold">{(totalUploaded + totalDuplicates).toLocaleString()}</p>
          <p className="text-muted-foreground text-xs mt-0.5">Raw rows received</p>
        </div>
        <div className="flex items-center text-muted-foreground text-lg">→</div>
        <div>
          <p className="text-2xl font-bold">{totalUploaded.toLocaleString()}</p>
          <p className="text-muted-foreground text-xs mt-0.5">New rows ({totalDuplicates.toLocaleString()} duplicates skipped)</p>
        </div>
        <div className="flex items-center text-muted-foreground text-lg">→</div>
        <div>
          <p className={`text-2xl font-bold ${analyticsCount == null ? 'text-muted-foreground' : ''}`}>
            {analyticsCount != null ? analyticsCount.toLocaleString() : '—'}
          </p>
          <p className="text-muted-foreground text-xs mt-0.5">In analytics now</p>
        </div>
        {analyticsCount != null && totalUploaded > 0 && (
          <div className="flex items-center">
            {reconciles ? (
              <Badge className="bg-green-100 text-green-800 border-green-200">✓ Reconciled</Badge>
            ) : (
              <Badge className="bg-amber-100 text-amber-800 border-amber-200">
                {(totalUploaded - analyticsCount).toLocaleString()} rows pending review
              </Badge>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function AuditTab({ engagementId, analyticsCount }: { engagementId: string; analyticsCount: number | null }) {
  const [expandedBatchId, setExpandedBatchId] = useState<string | null>(null)

  const { data: batches, isLoading } = useQuery<BatchSummary[]>({
    queryKey: ['ingest-batches', engagementId],
    queryFn: () => api.get(`/api/engagements/${engagementId}/ingest/batches`).then(r => r.data),
    enabled: !!engagementId,
    staleTime: 5 * 60 * 1000,
  })

  const { data: batchDetail, isLoading: detailLoading } = useQuery<BatchDetail>({
    queryKey: ['ingest-batch-detail', engagementId, expandedBatchId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/ingest/batches/${expandedBatchId}`).then(r => r.data),
    enabled: !!expandedBatchId,
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />

  if (!batches || batches.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p className="text-sm">No uploads found for this engagement.</p>
        <p className="text-xs mt-1">Upload a CSV or Excel file to get started.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <ReconciliationBanner batches={batches} analyticsCount={analyticsCount} />

      <div className="border rounded-xl overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Filename</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead className="text-right">Total Rows</TableHead>
              <TableHead className="text-right">Promoted</TableHead>
              <TableHead className="text-right">Duplicates</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {batches.map(batch => (
              <>
                <TableRow
                  key={batch.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => setExpandedBatchId(prev => prev === batch.id ? null : batch.id)}
                >
                  <TableCell>
                    {expandedBatchId === batch.id
                      ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                  </TableCell>
                  <TableCell className="font-medium">{batch.filename}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {batch.uploaded_at ? formatDate(batch.uploaded_at) : '—'}
                  </TableCell>
                  <TableCell className="text-right">{batch.row_count?.toLocaleString() ?? '—'}</TableCell>
                  <TableCell className="text-right">{batch.new_rows?.toLocaleString() ?? '—'}</TableCell>
                  <TableCell className="text-right">{batch.duplicate_rows?.toLocaleString() ?? '—'}</TableCell>
                  <TableCell>{batchStatusBadge(batch.status)}</TableCell>
                </TableRow>

                {expandedBatchId === batch.id && (
                  <TableRow key={`${batch.id}-detail`}>
                    <TableCell colSpan={7} className="bg-muted/30 p-4">
                      {detailLoading ? (
                        <Skeleton className="h-24" />
                      ) : batchDetail ? (
                        <div className="space-y-4">
                          <div>
                            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Pipeline Status</p>
                            <div className="flex flex-wrap gap-3">
                              {batchDetail.pipeline_status_breakdown.map(s => (
                                <div key={s.pipeline_status} className="border rounded-lg px-3 py-2 bg-card flex items-center gap-2">
                                  {pipelineStatusBadge(s.pipeline_status)}
                                  <span className="font-semibold text-sm">{s.count.toLocaleString()}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                          {batchDetail.sample_rows.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Sample Rows</p>
                              <div className="border rounded-lg overflow-hidden">
                                <Table>
                                  <TableHeader>
                                    <TableRow>
                                      <TableHead>Invoice #</TableHead>
                                      <TableHead>Date</TableHead>
                                      <TableHead>Supplier</TableHead>
                                      <TableHead className="text-right">Amount</TableHead>
                                      <TableHead>Status</TableHead>
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {batchDetail.sample_rows.slice(0, 10).map(row => (
                                      <TableRow key={row.id}>
                                        <TableCell className="font-mono text-xs">{row.invoice_number ?? '—'}</TableCell>
                                        <TableCell className="text-xs">{row.invoice_date ? (() => { try { return formatDate(row.invoice_date) } catch { return row.invoice_date } })() : '—'}</TableCell>
                                        <TableCell className="text-xs max-w-[160px] truncate">{row.raw_supplier_name ?? '—'}</TableCell>
                                        <TableCell className="text-right text-xs">{row.base_amount != null ? row.base_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</TableCell>
                                        <TableCell>{pipelineStatusBadge(row.pipeline_status)}</TableCell>
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                              </div>
                            </div>
                          )}
                        </div>
                      ) : null}
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

export default function DataQualityPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const [expandedCheck, setExpandedCheck] = useState<string | null>(null)

  const { data, isLoading } = useQuery<Record<string, CheckResult>>({
    queryKey: ['diagnostics', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/diagnostics`).then(r => r.data),
    enabled: !!engagementId,
    staleTime: 5 * 60 * 1000,
  })

  const { data: overview } = useQuery<{ invoice_count: number }>({
    queryKey: ['overview', engagementId],
    queryFn: () => api.get(`/api/engagements/${engagementId}/cube/overview`).then(r => r.data),
    enabled: !!engagementId,
    staleTime: 5 * 60 * 1000,
  })

  const SEVERITY_ORDER: Record<string, number> = { RED: 0, AMBER: 1, GREEN: 2 }

  const checks = data
    ? Object.entries(data)
        .map(([name, c]) => ({
          check_name: name,
          status: (STATUS_NORMALIZE[c.status ?? 'GREEN'] ?? 'GREEN') as Status,
          value_pct: c.pct ?? 0,
          description: c.description ?? '',
        }))
        .sort((a, b) => (SEVERITY_ORDER[a.status] ?? 2) - (SEVERITY_ORDER[b.status] ?? 2))
    : []

  const overall_score =
    checks.length > 0
      ? checks.reduce((sum, c) => sum + (STATUS_SCORE[c.status] ?? 0), 0) / checks.length
      : 0

  const passingCount = checks.filter(c => c.status === 'GREEN').length
  const redCount = checks.filter(c => c.status === 'RED').length
  const amberCount = checks.filter(c => c.status === 'AMBER').length

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Data Quality</h1>

      <Tabs defaultValue="checks">
        <TabsList>
          <TabsTrigger value="checks">Quality Checks</TabsTrigger>
          <TabsTrigger value="audit">Ingestion Audit</TabsTrigger>
        </TabsList>

        <TabsContent value="checks" className="space-y-4 mt-4">
          {isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="flex items-center gap-6 p-4 border rounded-xl bg-card shadow-sm flex-wrap">
              <p className="text-base font-semibold">{passingCount} of {checks.length} checks passing</p>
              <div className="flex gap-3">
                <span className="flex items-center gap-1.5 text-sm">
                  <div className="w-3 h-3 rounded-full bg-red-500" />
                  <span className="text-rose-700 font-medium">{redCount} issue{redCount !== 1 ? 's' : ''}</span>
                </span>
                <span className="flex items-center gap-1.5 text-sm">
                  <div className="w-3 h-3 rounded-full bg-amber-500" />
                  <span className="text-amber-700 font-medium">{amberCount} warning{amberCount !== 1 ? 's' : ''}</span>
                </span>
                <span className="flex items-center gap-1.5 text-sm">
                  <div className="w-3 h-3 rounded-full bg-green-500" />
                  <span className="text-green-700 font-medium">{passingCount} passing</span>
                </span>
              </div>
              {overall_score >= 80 ? (
                <Badge className="bg-green-100 text-green-800 border-green-200">Good</Badge>
              ) : overall_score >= 50 ? (
                <Badge className="bg-amber-100 text-amber-800 border-amber-200">Needs attention</Badge>
              ) : (
                <Badge className="bg-red-100 text-red-800 border-red-200">Review required</Badge>
              )}
            </div>
          )}

          <div className="grid grid-cols-3 gap-4">
            {isLoading
              ? Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} className="h-28" />)
              : checks.map(c => (
                  <DiagnosticsCheckCard
                    key={c.check_name}
                    check_name={c.check_name}
                    status={c.status}
                    value_pct={c.value_pct}
                    description={c.description}
                    affectsRecommendations={['missing_category', 'low_confidence_category', 'uncategorised_spend'].includes(c.check_name)}
                    onClick={c.status !== 'GREEN' ? () => setExpandedCheck(prev => prev === c.check_name ? null : c.check_name) : undefined}
                    expanded={expandedCheck === c.check_name}
                  />
                ))}
          </div>
        </TabsContent>

        <TabsContent value="audit" className="mt-4">
          {engagementId && (
            <AuditTab
              engagementId={engagementId}
              analyticsCount={overview?.invoice_count ?? null}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
