import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LabelList,
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
  colors?: string[]
  valueFormatter?: (v: number) => string
  maxItems?: number
  onBarClick?: (label: string) => void
  showLabel?: boolean
  clickHint?: boolean
  selectedLabel?: string
}

export default function SpendBarChart({
  data,
  title,
  horizontal = false,
  color = CHART_COLORS[0],
  colors,
  valueFormatter,
  maxItems,
  onBarClick,
  showLabel = false,
  clickHint = false,
  selectedLabel,
}: SpendBarChartProps) {
  if (!data || data.length === 0) {
    return (
      <div>
        {title && <h3 className="text-sm font-medium mb-3">{title}</h3>}
        <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
          No data available
        </div>
      </div>
    )
  }

  const displayData = maxItems ? data.slice(0, maxItems) : data
  const chartData = displayData.map(d => ({ name: d.label, value: d.value }))

  const fmt = (v: unknown) =>
    valueFormatter && typeof v === 'number' ? valueFormatter(v) : String(v)

  const labelFormatter = (v: unknown) =>
    valueFormatter && typeof v === 'number' ? valueFormatter(v) : String(v)

  return (
    <div>
      <div className="flex justify-between items-center mb-3">
        {title && <h3 className="text-sm font-medium">{title}</h3>}
        {clickHint && onBarClick && (
          <span className="text-xs text-muted-foreground italic">Click a bar to explore</span>
        )}
      </div>
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
            <Bar
              dataKey="value"
              fill={color}
              onClick={onBarClick ? (entry: { name?: string }) => { if (entry.name) onBarClick(entry.name) } : undefined}
              style={onBarClick ? { cursor: 'pointer' } : undefined}
            >
              {(colors || selectedLabel) && chartData.map((entry, index) => {
                const fill = colors?.[index] ?? color
                if (selectedLabel && entry.name === selectedLabel) {
                  return <Cell key={`cell-${index}`} fill={fill} opacity={1} stroke='#ffffff' strokeWidth={2} />
                } else if (selectedLabel) {
                  return <Cell key={`cell-${index}`} fill={fill} opacity={0.55} />
                }
                return <Cell key={`cell-${index}`} fill={colors![index] ?? color} />
              })}
              {showLabel && (
                <LabelList
                  dataKey="value"
                  position="right"
                  formatter={labelFormatter}
                  style={{ fontSize: 11, fill: '#64748b' }}
                />
              )}
            </Bar>
          </BarChart>
        ) : (
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={v => fmt(v)} tick={{ fontSize: 11 }} />
            <Tooltip formatter={v => fmt(v)} />
            <Bar
              dataKey="value"
              fill={color}
              onClick={onBarClick ? (entry: { name?: string }) => { if (entry.name) onBarClick(entry.name) } : undefined}
              style={onBarClick ? { cursor: 'pointer' } : undefined}
            >
              {(colors || selectedLabel) && chartData.map((entry, index) => {
                const fill = colors?.[index] ?? color
                if (selectedLabel && entry.name === selectedLabel) {
                  return <Cell key={`cell-${index}`} fill={fill} opacity={1} stroke='#ffffff' strokeWidth={2} />
                } else if (selectedLabel) {
                  return <Cell key={`cell-${index}`} fill={fill} opacity={0.55} />
                }
                return <Cell key={`cell-${index}`} fill={colors![index] ?? color} />
              })}
              {showLabel && (
                <LabelList
                  dataKey="value"
                  position="top"
                  formatter={labelFormatter}
                  style={{ fontSize: 11, fill: '#64748b' }}
                />
              )}
            </Bar>
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
