import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { formatPct } from '@/lib/formatters'

type Status = 'GREEN' | 'AMBER' | 'RED'

interface Props {
  check_name: string
  status: Status
  value_pct: number
  description: string
  affectsRecommendations?: boolean
}

const BORDER: Record<Status, string> = {
  GREEN: 'border-l-green-500',
  AMBER: 'border-l-amber-500',
  RED: 'border-l-red-500',
}

const BADGE_CLASS: Record<Status, string> = {
  GREEN: 'bg-green-100 text-green-800 border-green-200',
  AMBER: 'bg-amber-100 text-amber-800 border-amber-200',
  RED: 'bg-red-100 text-red-800 border-red-200',
}

function humanize(s: string) {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const PROGRESS_CLASS: Record<Status, string> = {
  GREEN: '',
  AMBER: '[&>div]:bg-amber-500',
  RED: '[&>div]:bg-red-500',
}

export default function DiagnosticsCheckCard({ check_name, status, value_pct, description, affectsRecommendations }: Props) {
  return (
    <Card className={`border-l-4 ${BORDER[status]}`}>
      <CardContent className="pt-4 pb-4 space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold leading-tight">{humanize(check_name)}</span>
          <Badge className={BADGE_CLASS[status]}>{status}</Badge>
        </div>
        <div className="text-2xl font-bold">{formatPct(value_pct)}</div>
        <p className="text-xs text-muted-foreground">{description}</p>
        {affectsRecommendations && (
          <Badge className="text-xs bg-blue-50 text-blue-700 border-blue-200 mt-1">⚠ Affects recommendations</Badge>
        )}
        <div className="mt-2">
          <Progress value={Math.min(value_pct, 100)} className={PROGRESS_CLASS[status]} />
        </div>
      </CardContent>
    </Card>
  )
}
