import { Treemap, ResponsiveContainer } from 'recharts'
import { CHART_COLORS } from './constants'

interface TreemapItem {
  name: string
  value: number
  color?: string
  [key: string]: unknown
}

interface SpendTreemapProps {
  data: TreemapItem[]
  title: string
  valueFormatter?: (v: number) => string
  onCellClick?: (name: string) => void
}

interface CustomContentProps {
  x?: number
  y?: number
  width?: number
  height?: number
  name?: string
  value?: number
  index?: number
  root?: { children?: TreemapItem[] }
}

function CustomContent({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  name = '',
  value = 0,
  index = 0,
  root,
  valueFormatter,
}: CustomContentProps & { valueFormatter?: (v: number) => string }) {
  const items = root?.children ?? []
  const item = items[index]
  const fill = item?.color ?? CHART_COLORS[index % CHART_COLORS.length]
  const showLabel = width > 60 && height > 40
  const truncated = name.length > 16 ? name.slice(0, 16) + '…' : name
  const formatted = valueFormatter ? valueFormatter(value) : String(value)
  const cx = x + width / 2
  const cy = y + height / 2

  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#fff" strokeWidth={2} />
      {showLabel && (
        <>
          <text
            x={cx}
            y={cy - 7}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="#fff"
            fontSize={11}
          >
            {truncated}
          </text>
          <text
            x={cx}
            y={cy + 7}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="#fff"
            fontSize={11}
          >
            {formatted}
          </text>
        </>
      )}
    </g>
  )
}

export default function SpendTreemap({
  data,
  title,
  valueFormatter,
  onCellClick,
}: SpendTreemapProps) {
  const isEmpty = data.length === 0 || data.every(d => d.value === 0)

  return (
    <div>
      <h3 className="section-header">{title}</h3>
      {isEmpty ? (
        <div className="flex items-center justify-center h-80 text-muted-foreground text-sm">
          No data available
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <Treemap
            data={data}
            dataKey="value"
            onClick={
              onCellClick
                ? (payload: { name?: string }) => {
                    if (payload?.name) onCellClick(payload.name)
                  }
                : undefined
            }
            style={onCellClick ? { cursor: 'pointer' } : undefined}
            content={
              <CustomContent valueFormatter={valueFormatter} />
            }
          />
        </ResponsiveContainer>
      )}
    </div>
  )
}
