import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent } from '@/components/ui/card'
import DiagnosticsCheckCard from '@/components/dashboard/DiagnosticsCheckCard'
import { api } from '@/lib/api'
import { formatPct } from '@/lib/formatters'

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

  const { data, isLoading } = useQuery<DiagnosticsResponse>({
    queryKey: ['diagnostics', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/diagnostics`).then(r => r.data),
    enabled: !!engagementId,
  })

  const checks = data
    ? Object.entries(data).map(([name, c]) => ({
        check_name: name,
        status: (STATUS_NORMALIZE[c.status ?? 'GREEN'] ?? 'GREEN') as Status,
        value_pct: c.pct ?? 0,
        description: c.description ?? '',
      }))
    : []

  const overall_score =
    checks.length > 0
      ? checks.reduce((sum, c) => sum + (STATUS_SCORE[c.status] ?? 0), 0) / checks.length
      : 0

  const scoreColor =
    overall_score >= 80
      ? 'text-green-600'
      : overall_score >= 50
        ? 'text-amber-600'
        : 'text-red-600'

  const scoreBorder =
    overall_score >= 80
      ? 'border-l-green-500'
      : overall_score >= 50
        ? 'border-l-amber-500'
        : 'border-l-red-500'

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">Data Quality</h1>

      {isLoading ? (
        <Skeleton className="h-28 max-w-xs" />
      ) : (
        <Card className={`max-w-xs border-l-4 ${scoreBorder}`}>
          <CardContent className="pt-6">
            <div className={`text-4xl font-bold ${scoreColor}`}>{formatPct(overall_score)}</div>
            <div className="text-sm text-muted-foreground mt-1">Overall Quality Score</div>
            <div className="text-xs text-muted-foreground mt-1">
              Based on {checks.length} diagnostic checks
            </div>
          </CardContent>
        </Card>
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
              />
            ))}
      </div>
    </div>
  )
}
