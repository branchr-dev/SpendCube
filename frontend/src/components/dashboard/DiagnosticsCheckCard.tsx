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

const DISPLAY_NAMES: Record<string, string> = {
  missing_supplier_name: 'Missing Supplier Name',
  uncategorised_spend: 'Uncategorised Spend',
  unresolved_suppliers: 'Unresolved Suppliers',
  missing_payment_terms: 'Missing Payment Terms',
  duplicate_invoice_risk: 'Duplicate Invoice Risk',
  negative_reversal_lines: 'Negative Reversal Lines',
  weak_descriptions: 'Weak Descriptions',
  missing_contract_linkage: 'Missing Contract Linkage',
  missing_bu_cost_centre: 'Missing BU / Cost Centre',
}

const CHECK_GUIDANCE: Record<string, { meaning: string; impacts: string; fix: string }> = {
  missing_supplier_name: {
    meaning: 'Transactions with no canonical supplier name matched.',
    impacts: 'Impacts supplier consolidation recommendations and spend-by-supplier views.',
    fix: 'Upload a supplier master file or manually map raw names in the Review Workstation.',
  },
  uncategorised_spend: {
    meaning: 'Transactions not assigned to a UNSPSC category after all 6 pipeline passes.',
    impacts: 'Directly reduces recommendation coverage — uncategorised spend cannot be analysed.',
    fix: 'Add keyword rules in data/reference/keyword_rules.yaml or run the Review Workstation category queue.',
  },
  unresolved_suppliers: {
    meaning: 'Supplier names that could not be matched to a canonical supplier with sufficient confidence.',
    impacts: 'Reduces accuracy of supplier consolidation and spend-by-supplier analytics.',
    fix: 'Review PENDING entries in the Review Workstation supplier queue and approve or override matches.',
  },
  missing_payment_terms: {
    meaning: 'Transactions with no payment terms data present.',
    impacts: 'Limits working capital opportunity analysis and payment terms benchmarking.',
    fix: 'Ensure the source ERP export includes payment terms and re-ingest.',
  },
  duplicate_invoice_risk: {
    meaning: 'Potential duplicate invoice rows detected based on supplier, amount, and date proximity.',
    impacts: 'Inflates spend totals and can skew supplier concentration metrics.',
    fix: 'Check source data for duplicate invoice numbers and re-ingest after deduplication.',
  },
  negative_reversal_lines: {
    meaning: 'Negative-value transaction lines (credit notes and reversals) as a share of total rows.',
    impacts: 'High reversal rates indicate invoicing errors or disputes that may mask true spend levels.',
    fix: 'Investigate source system for high reversal volumes; consider excluding from analytics if systemic.',
  },
  weak_descriptions: {
    meaning: 'Transaction line descriptions that are too short or generic to support categorisation.',
    impacts: 'Reduces keyword and embedding categorisation accuracy; more rows fall through to LLM or remain uncategorised.',
    fix: 'Enrich descriptions at source or add keyword rules in data/reference/keyword_rules.yaml.',
  },
  missing_contract_linkage: {
    meaning: 'Transactions with no PO or contract reference that could link them to a managed agreement.',
    impacts: 'Inflates maverick spend figures and reduces contract compliance visibility.',
    fix: 'Enforce PO requirements at source and map PO number column during ingestion.',
  },
  missing_bu_cost_centre: {
    meaning: 'Transactions with no business unit or cost centre assignment.',
    impacts: 'Limits spend-by-BU analysis and stakeholder accountability reporting.',
    fix: 'Add cost centre column mapping during ingestion or enrich via GL code lookup.',
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
  return DISPLAY_NAMES[s] ?? s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
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
        <div className="mt-2 rounded overflow-hidden bg-muted">
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
