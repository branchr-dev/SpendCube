import { Card, CardContent } from '@/components/ui/card'
import { TrendingUp, TrendingDown } from 'lucide-react'
import { formatCurrency, formatNumber, formatPct } from '@/lib/formatters'

interface KpiCardProps {
  label: string
  value: string | number
  valueType?: 'currency' | 'number' | 'pct' | 'text'
  delta?: number
  deltaLabel?: string
  currency?: string
  subtext?: string
}

export default function KpiCard({
  label,
  value,
  valueType = 'text',
  delta,
  deltaLabel,
  currency = 'AUD',
  subtext,
}: KpiCardProps) {
  function formatValue(): string {
    if (typeof value === 'string') return value
    switch (valueType) {
      case 'currency': return formatCurrency(value, currency)
      case 'number': return formatNumber(value)
      case 'pct': return formatPct(value)
      default: return String(value)
    }
  }

  const isPositive = delta !== undefined && delta > 0
  const isNegative = delta !== undefined && delta < 0

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-3xl font-bold">{formatValue()}</div>
        <div className="text-sm text-muted-foreground mt-1">{label}</div>
        {delta !== undefined && (
          <div
            className={`flex items-center gap-1 mt-2 text-sm ${
              isPositive ? 'text-green-600' : isNegative ? 'text-red-600' : 'text-muted-foreground'
            }`}
          >
            {isPositive && <TrendingUp className="h-4 w-4" />}
            {isNegative && <TrendingDown className="h-4 w-4" />}
            <span>
              {formatPct(Math.abs(delta))} {deltaLabel}
            </span>
          </div>
        )}
        {subtext && <div className="text-xs text-muted-foreground mt-1">{subtext}</div>}
      </CardContent>
    </Card>
  )
}
