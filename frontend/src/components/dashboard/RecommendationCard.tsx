import { useState } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { formatCurrency, formatPct } from '@/lib/formatters'
import { CHART_COLORS } from '@/components/charts/constants'
import type { Recommendation } from '@/types'

const CONFIDENCE_CLASS: Record<string, string> = {
  HIGH: 'bg-green-100 text-green-800 border-green-200',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-200',
  LOW: 'bg-red-100 text-red-800 border-red-200',
}

interface RecommendationCardProps {
  rec: Recommendation
  portfolioTotal?: number
  leverIndex?: number
}

export default function RecommendationCard({ rec, portfolioTotal, leverIndex }: RecommendationCardProps) {
  const [open, setOpen] = useState(false)

  const leverAccentStyle = leverIndex !== undefined
    ? { borderLeftWidth: '4px', borderLeftStyle: 'solid' as const, borderLeftColor: CHART_COLORS[leverIndex % CHART_COLORS.length] }
    : undefined

  const sharePct = portfolioTotal && portfolioTotal > 0
    ? ((rec.estimated_impact_aud ?? 0) / portfolioTotal) * 100
    : null

  return (
    <Card style={leverAccentStyle}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline">{rec.type?.replace(/_/g, ' ')}</Badge>
            <Badge className={CONFIDENCE_CLASS[rec.confidence ?? 'LOW'] ?? CONFIDENCE_CLASS.LOW}>
              {rec.confidence}
            </Badge>
          </div>
          <span className="text-2xl font-bold text-green-700">
            {formatCurrency(rec.estimated_impact_aud ?? 0)}
          </span>
        </div>
        <div className="text-sm font-medium mt-1">{rec.context}</div>
      </CardHeader>
      <CardContent className="pt-0 space-y-2">
        <p className="text-sm text-muted-foreground">{rec.action}</p>
        {sharePct !== null && (
          <div className="mt-2">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Share of portfolio savings</span>
              <span>{formatPct(sharePct)}</span>
            </div>
            <div className="h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-green-500"
                style={{ width: `${Math.min(sharePct, 100)}%` }}
              />
            </div>
          </div>
        )}
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors">
            Calculation Basis
            {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 space-y-2">
            <table className="w-full text-xs">
              <tbody>
                <tr className="border-b">
                  <td className="py-1 text-muted-foreground">Baseline Spend</td>
                  <td className="py-1 text-right font-medium">
                    {formatCurrency(rec.baseline_spend ?? 0)}
                  </td>
                </tr>
                <tr className="border-b">
                  <td className="py-1 text-muted-foreground">Addressability</td>
                  <td className="py-1 text-right font-medium">
                    {formatPct(rec.addressability_pct ?? 0)}
                  </td>
                </tr>
                <tr className="border-b">
                  <td className="py-1 text-muted-foreground">Addressable Baseline</td>
                  <td className="py-1 text-right font-medium">
                    {formatCurrency(rec.addressable_baseline ?? 0)}
                  </td>
                </tr>
                <tr className="border-b">
                  <td className="py-1 text-muted-foreground">Saving Rate</td>
                  <td className="py-1 text-right font-medium">
                    {rec.saving_pct !== null && rec.saving_pct !== undefined
                      ? formatPct(rec.saving_pct)
                      : 'WACC formula'}
                  </td>
                </tr>
                <tr>
                  <td className="py-1 text-muted-foreground">Estimated Saving</td>
                  <td className="py-1 text-right font-medium text-green-700">
                    {formatCurrency(rec.estimated_impact_aud ?? 0)}
                  </td>
                </tr>
              </tbody>
            </table>
            {rec.narrative && (
              <p className="text-xs text-muted-foreground italic">{rec.narrative}</p>
            )}
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  )
}
