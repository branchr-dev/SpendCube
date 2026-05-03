import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { CHART_COLORS } from './constants'

interface PieData {
  name: string
  value: number
}

interface SpendPieChartProps {
  data: PieData[]
  title: string
  valueFormatter?: (v: number) => string
}

export default function SpendPieChart({ data, title, valueFormatter }: SpendPieChartProps) {
  const fmt = (v: unknown) =>
    valueFormatter && typeof v === 'number' ? valueFormatter(v) : String(v)

  return (
    <div>
      {title && <h3 className="text-sm font-medium mb-3">{title}</h3>}
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="45%">
            {data.map((_, i) => (
              <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={v => fmt(v)} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
