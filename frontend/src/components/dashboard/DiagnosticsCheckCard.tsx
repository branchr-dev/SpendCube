import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { formatPct } from '@/lib/formatters'

type Status = 'GREEN' | 'AMBER' | 'RED'

interface Props {
  check_name: string
  status: Status
  value_pct: number
  description: string
  affectsRecommendations?: boolean
  onClick?: () => void
  expanded?: boolean
}

const CHECK_GUIDANCE: Record<string, { meaning: string; impacts: string; fix: string }> = {
  missing_supplier: {
    meaning: 'Transactions with no canonical supplier name matched.',
    impacts: 'Impacts supplier consolidation recommendations and spend-by-supplier views.',
    fix: 'Upload a supplier master file or manually map raw names in the Review Workstation.',
  },
  missing_category: {
    meaning: 'Transactions not assigned to a UNSPSC category after all 6 pipeline passes.',
    impacts: 'Directly reduces recommendation coverage.',
    fix: 'Add keyword rules in data/reference/keyword_rules.yaml or run the Review Workstation category queue.',
  },
  missing_gl_account: {
    meaning: 'Transactions with no GL account code.',
    impacts: 'Reduces GL-based categorisation accuracy.',
    fix: 'Ensure the source ERP export includes GL codes and re-ingest.',
  },
  missing_cost_centre: {
    meaning: 'Transactions with no cost centre or business unit.',
    impacts: 'Limits spend-by-BU analysis.',
    fix: 'Add cost centre column mapping during ingestion.',
  },
  low_confidence_category: {
    meaning: 'Categories assigned with confidence below 0.60.',
    impacts: 'These are likely miscategorised.',
    fix: 'Review low-confidence transactions in the Review Workstation and add overrides.',
  },
  low_confidence_supplier: {
    meaning: 'Supplier matches with confidence below 0.60.',
    impacts: 'These may be incorrectly harmonised.',
    fix: 'Review PENDING entries in the Review Workstation supplier queue.',
  },
  duplicate_transactions: {
    meaning: 'Potential duplicate invoice rows detected.',
    impacts: 'Inflates spend totals.',
    fix: 'Check source data for duplicate invoice numbers and re-ingest after deduplication.',
  },
  maverick_spend: {
    meaning: 'Spend without a purchase order on non-contracted suppliers.',
    impacts: 'Indicates off-contract buying.',
    fix: 'Enforce PO requirements and expand contract coverage.',
  },
  tail_spend_ratio: {
    meaning: 'Proportion of spend in low-volume tail suppliers.',
    impacts: 'High tail spend increases admin cost and reduces leverage.',
    fix: 'Consolidate tail suppliers to preferred vendors.',
  },
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

export default function DiagnosticsCheckCard({ check_name, status, value_pct, description, affectsRecommendations, onClick, expanded }: Props) {
  const isExpandable = status === 'RED' || status === 'AMBER'
  const guidance = CHECK_GUIDANCE[check_name] ?? { meaning: '', impacts: '', fix: '' }

  return (
    <Card
      className={`border-l-4 ${BORDER[status]}${isExpandable ? ' cursor-pointer' : ''}`}
      onClick={isExpandable ? onClick : undefined}
    >
      <CardContent className="pt-4 pb-4 space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold leading-tight">{humanize(check_name)}</span>
          <div className="flex items-center gap-1">
            <Badge className={BADGE_CLASS[status]}>{status}</Badge>
            {isExpandable && (
              expanded
                ? <ChevronUp className="h-3 w-3 text-muted-foreground" />
                : <ChevronDown className="h-3 w-3 text-muted-foreground" />
            )}
          </div>
        </div>
        <div className="text-2xl font-bold">{formatPct(value_pct)}</div>
        <p className="text-xs text-muted-foreground">{description}</p>
        {affectsRecommendations && (
          <Badge className="text-xs bg-blue-50 text-blue-700 border-blue-200 mt-1">⚠ Affects recommendations</Badge>
        )}
        <div className="mt-2">
          <Progress value={Math.min(value_pct, 100)} className={PROGRESS_CLASS[status]} />
        </div>
        {expanded && isExpandable && (
          <div className="mt-3 pt-3 border-t space-y-2 text-xs">
            <div>
              <span className="font-medium">What it measures: </span>
              <span className="text-muted-foreground">{guidance.meaning}</span>
            </div>
            <div>
              <span className="font-medium">Impact: </span>
              <span className="text-muted-foreground">{guidance.impacts}</span>
            </div>
            <div>
              <span className="font-medium">How to fix: </span>
              <span className="text-muted-foreground">{guidance.fix}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
