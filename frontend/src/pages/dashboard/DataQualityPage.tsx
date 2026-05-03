import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import DiagnosticsCheckCard from '@/components/dashboard/DiagnosticsCheckCard'
import { api } from '@/lib/api'

type Status = 'GREEN' | 'AMBER' | 'RED'

const STATUS_SCORE: Record<string, number> = {
  GREEN: 100,
  AMBER: 50,
  RED: 0,
  INFO: 100,
  WARN: 50,
  ALERT: 0,
}

const STATUS_NORMALIZE: Record<string, Status> = {
  GREEN: 'GREEN',
  INFO: 'GREEN',
  AMBER: 'AMBER',
  WARN: 'AMBER',
  RED: 'RED',
  ALERT: 'RED',
}

interface CheckResult {
  value?: number
  pct?: number
  status?: string
  description?: string
}

type DiagnosticsResponse = Record<string, CheckResult>

export default function DataQualityPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const [expandedCheck, setExpandedCheck] = useState<string | null>(null)

  const { data, isLoading } = useQuery<DiagnosticsResponse>({
    queryKey: ['diagnostics', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/diagnostics`).then(r => r.data),
    enabled: !!engagementId,
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
                affectsRecommendations={['missing_category', 'low_confidence_category'].includes(c.check_name)}
                onClick={c.status !== 'GREEN' ? () => setExpandedCheck(prev => prev === c.check_name ? null : c.check_name) : undefined}
                expanded={expandedCheck === c.check_name}
              />
            ))}
      </div>
    </div>
  )
}
