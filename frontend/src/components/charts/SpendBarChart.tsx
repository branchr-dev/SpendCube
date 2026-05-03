import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { CHART_COLORS } from './constants'

interface BarData {
  label: string
  value: number
}

interface SpendBarChartProps {
  data: BarData[]
  title: string
  horizontal?: boolean
  color?: string
  valueFormatter?: (v: number) => string
  maxItems?: number
}

export default function SpendBarChart({
  data,
  title,
  horizontal = false,
  color = CHART_COLORS[0],
  valueFormatter,
  maxItems,
}: SpendBarChartProps) {
  const displayData = maxItems ? data.slice(0, maxItems) : data
  const chartData = displayData.map(d => ({ name: d.label, value: d.value }))

  const fmt = (v: unknown) =>
    valueFormatter && typeof v === 'number' ? valueFormatter(v) : String(v)

  return (
    <div>
      {title && <h3 className="text-sm font-medium mb-3">{title}</h3>}
      <ResponsiveContainer width="100%" height={300}>
        {horizontal ? (
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={v => fmt(v)} tick={{ fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="name"
              width={150}
              tick={{ fontSize: 12 }}
            />
            <Tooltip formatter={v => fmt(v)} />
            <Bar dataKey="value" fill={color} />
          </BarChart>
        ) : (
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={v => fmt(v)} tick={{ fontSize: 11 }} />
            <Tooltip formatter={v => fmt(v)} />
            <Bar dataKey="value" fill={color} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
