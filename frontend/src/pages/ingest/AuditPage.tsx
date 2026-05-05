import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { api } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/formatters'

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

interface SampleRow {
  id: string
  invoice_number: string | null
  invoice_date: string | null
  raw_supplier_name: string | null
  base_amount: number | null
  pipeline_status: string
}

interface BatchDetail {
  batch: BatchSummary
  pipeline_status_breakdown: StatusBreakdown[]
  sample_rows: SampleRow[]
}

function statusBadge(status: string) {
  switch (status) {
    case 'complete':
      return <Badge className="bg-green-100 text-green-800 border-green-200">{status}</Badge>
    case 'processing':
      return <Badge className="bg-blue-100 text-blue-800 border-blue-200">{status}</Badge>
    case 'failed':
      return <Badge className="bg-red-100 text-red-800 border-red-200">{status}</Badge>
    default:
      return <Badge className="bg-slate-100 text-slate-700 border-slate-200">{status}</Badge>
  }
}

function pipelineStatusBadge(status: string) {
  switch (status) {
    case 'processed':
      return <Badge className="bg-green-100 text-green-800 border-green-200">Promoted</Badge>
    case 'review_required':
      return <Badge className="bg-amber-100 text-amber-800 border-amber-200">Review Required</Badge>
    case 'failed':
      return <Badge className="bg-red-100 text-red-800 border-red-200">Failed</Badge>
    case 'queued':
      return <Badge className="bg-slate-100 text-slate-600 border-slate-200">Queued</Badge>
    case 'processing':
      return <Badge className="bg-blue-100 text-blue-800 border-blue-200">Processing</Badge>
    default:
      return <Badge variant="outline">{status}</Badge>
  }
}

const PIPELINE_STATUS_LABELS: Record<string, string> = {
  processed: 'Promoted',
  review_required: 'Review Required',
  failed: 'Failed',
  queued: 'Queued',
  processing: 'Processing',
}

export default function AuditPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)

  const { data: batches, isLoading } = useQuery<BatchSummary[]>({
    queryKey: ['ingest-batches', engagementId],
    queryFn: () => api.get(`/api/engagements/${engagementId}/ingest/batches`).then(r => r.data),
    enabled: !!engagementId,
    staleTime: 5 * 60 * 1000,
  })

  const { data: batchDetail } = useQuery<BatchDetail>({
    queryKey: ['ingest-batch-detail', engagementId, selectedBatchId],
    queryFn: () =>
      api
        .get(`/api/engagements/${engagementId}/ingest/batches/${selectedBatchId}`)
        .then(r => r.data),
    enabled: !!selectedBatchId,
    staleTime: 5 * 60 * 1000,
  })

  const selectedBatch = batchDetail?.batch ?? null

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Ingestion Audit</h1>
        <p className="text-muted-foreground mt-1">
          Verify your uploaded data was ingested and processed correctly.
        </p>
      </div>

      {isLoading ? (
        <Skeleton className="h-64" />
      ) : !batches || batches.length === 0 ? (
        <p className="text-muted-foreground text-center py-8">No uploads yet</p>
      ) : (
        <div className="border rounded-xl overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Filename</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="text-right">Total Rows</TableHead>
                <TableHead className="text-right">Promoted</TableHead>
                <TableHead className="text-right">Review Required</TableHead>
                <TableHead className="text-right">Duplicates</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {batches.map(batch => {
                const reviewRequired =
                  batch.duplicate_rows != null
                    ? Math.max(
                        0,
                        batch.row_count - batch.new_rows - batch.duplicate_rows,
                      )
                    : null
                return (
                  <TableRow
                    key={batch.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() =>
                      setSelectedBatchId(prev => (prev === batch.id ? null : batch.id))
                    }
                  >
                    <TableCell className="font-medium">{batch.filename}</TableCell>
                    <TableCell>
                      {batch.uploaded_at ? formatDate(batch.uploaded_at) : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      {batch.row_count?.toLocaleString() ?? '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      {batch.new_rows?.toLocaleString() ?? '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      {reviewRequired != null ? reviewRequired.toLocaleString() : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      {batch.duplicate_rows?.toLocaleString() ?? '—'}
                    </TableCell>
                    <TableCell>{statusBadge(batch.status)}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <Sheet
        open={!!selectedBatchId}
        onOpenChange={open => {
          if (!open) setSelectedBatchId(null)
        }}
      >
        <SheetContent side="right" className="w-[560px] sm:w-[560px] overflow-y-auto p-6">
          <SheetHeader>
            <SheetTitle>{selectedBatch?.filename ?? 'Batch Detail'}</SheetTitle>
          </SheetHeader>

          {batchDetail ? (
            <div className="mt-6 space-y-6">
              {/* Pipeline status tiles */}
              <div>
                <h3 className="section-header">Pipeline Status</h3>
                <div className="flex flex-wrap gap-3 mt-3">
                  {batchDetail.pipeline_status_breakdown.map(s => (
                    <div
                      key={s.pipeline_status}
                      className="border rounded-lg p-3 flex flex-col items-start min-w-[110px]"
                    >
                      <span className="text-lg font-bold">{s.count.toLocaleString()}</span>
                      <span className="mt-1">{pipelineStatusBadge(s.pipeline_status)}</span>
                      <span className="text-xs text-muted-foreground mt-1">
                        {PIPELINE_STATUS_LABELS[s.pipeline_status] ?? s.pipeline_status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Sample rows */}
              <div>
                <h3 className="section-header">Sample Rows</h3>
                {batchDetail.sample_rows.length === 0 ? (
                  <p className="text-muted-foreground text-center py-4 text-sm">No rows found</p>
                ) : (
                  <div className="border rounded-lg overflow-hidden mt-3">
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
                        {batchDetail.sample_rows.map(row => (
                          <TableRow key={row.id}>
                            <TableCell className="font-mono text-xs">
                              {row.invoice_number ?? '—'}
                            </TableCell>
                            <TableCell className="text-xs">
                              {row.invoice_date
                                ? (() => {
                                    try {
                                      return formatDate(row.invoice_date)
                                    } catch {
                                      return row.invoice_date
                                    }
                                  })()
                                : '—'}
                            </TableCell>
                            <TableCell className="text-xs max-w-[120px] truncate">
                              {row.raw_supplier_name ?? '—'}
                            </TableCell>
                            <TableCell className="text-right text-xs">
                              {row.base_amount != null
                                ? formatCurrency(row.base_amount)
                                : '—'}
                            </TableCell>
                            <TableCell>{pipelineStatusBadge(row.pipeline_status)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="mt-6 space-y-3">
              <Skeleton className="h-24" />
              <Skeleton className="h-64" />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
