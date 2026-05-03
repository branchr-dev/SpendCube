import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { MonthRow } from '@/types/index'
import { formatMonth, formatCurrency } from '@/lib/formatters'
import { CHART_COLORS } from './constants'

interface SpendAreaChartProps {
  data: MonthRow[]
  title: string
  currency?: string
  showReferenceLine?: boolean
}

export default function SpendAreaChart({ data, title, currency = 'AUD', showReferenceLine = false }: SpendAreaChartProps) {
  const avgSpend = data.length > 0
    ? data.reduce((sum, d) => sum + (d.total_spend ?? 0), 0) / data.length
    : null
  const hasRollingAvg = data.some(
    d => d.rolling_3m_avg !== undefined && d.rolling_3m_avg !== null,
  )

  const fmt = (v: unknown) =>
    typeof v === 'number' ? formatCurrency(v, currency) : String(v)

  return (
    <div>
      {title && <h3 className="text-sm font-medium mb-3">{title}</h3>}
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="month"
            tickFormatter={(v: string) => formatMonth(v)}
            tick={{ fontSize: 12 }}
          />
          <YAxis tickFormatter={v => fmt(v)} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(v, name) => [
              fmt(v),
              name === 'total_spend' ? 'Monthly Spend' : '3M Rolling Avg',
            ]}
            labelFormatter={(label) => typeof label === 'string' ? formatMonth(label) : ''}
          />
          <Area
            type="monotone"
            dataKey="total_spend"
            stroke={CHART_COLORS[0]}
            fill={CHART_COLORS[5]}
            strokeWidth={2}
          />
          {hasRollingAvg && (
            <Area
              type="monotone"
              dataKey="rolling_3m_avg"
              stroke={CHART_COLORS[2]}
              fill="transparent"
              strokeWidth={2}
              strokeDasharray="5 5"
            />
          )}
          {showReferenceLine && avgSpend !== null && (
            <ReferenceLine
              y={avgSpend}
              stroke="#94a3b8"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{ value: 'Avg', position: 'insideTopRight', fontSize: 11, fill: '#94a3b8' }}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
