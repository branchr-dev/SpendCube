import { ABCSegment } from '@/types/index'

type ABCInputRow = { id: string; name: string; spend: number }
type ABCOutputRow<T> = T & { abc_segment: ABCSegment; cumulative_pct: number }

export function calculateABCSegments<T extends ABCInputRow>(rows: T[]): ABCOutputRow<T>[] {
  const sorted = [...rows].sort((a, b) => b.spend - a.spend)
  const totalSpend = sorted.reduce((sum, r) => sum + r.spend, 0)
  let cumulative = 0
  return sorted.map(row => {
    cumulative += row.spend
    const cumulative_pct = totalSpend > 0 ? cumulative / totalSpend : 0
    let abc_segment: ABCSegment
    if (cumulative_pct <= 0.80) abc_segment = 'A'
    else if (cumulative_pct <= 0.95) abc_segment = 'B'
    else abc_segment = 'C'
    return { ...row, abc_segment, cumulative_pct }
  })
}

export function calculateSpendConcentration(
  rows: { spend: number }[],
  topN: number
): { top_n_spend: number; top_n_pct: number; total_spend: number } {
  const sorted = [...rows].sort((a, b) => b.spend - a.spend)
  const total_spend = sorted.reduce((sum, r) => sum + r.spend, 0)
  const top_n_spend = sorted.slice(0, topN).reduce((sum, r) => sum + r.spend, 0)
  return {
    top_n_spend,
    top_n_pct: total_spend > 0 ? top_n_spend / total_spend : 0,
    total_spend,
  }
}

export function getTopN<T extends { spend?: number; total_spend?: number }>(rows: T[], n: number): T[] {
  return [...rows]
    .sort((a, b) => (b.spend ?? b.total_spend ?? 0) - (a.spend ?? a.total_spend ?? 0))
    .slice(0, n)
}

export function calculateTailSpendMetrics(rows: { id: string; spend: number }[]): {
  tail_supplier_count: number
  tail_spend: number
  tail_pct: number
  core_supplier_count: number
} {
  const sorted = [...rows].sort((a, b) => b.spend - a.spend)
  const totalSpend = sorted.reduce((sum, r) => sum + r.spend, 0)
  let coreSpend = 0
  let coreCount = 0
  for (const row of sorted) {
    if (totalSpend > 0 && coreSpend / totalSpend >= 0.80) break
    coreSpend += row.spend
    coreCount++
  }
  const tailSpend = totalSpend - coreSpend
  return {
    tail_supplier_count: sorted.length - coreCount,
    tail_spend: tailSpend,
    tail_pct: totalSpend > 0 ? tailSpend / totalSpend : 0,
    core_supplier_count: coreCount,
  }
}

export function formatSpendSummary(
  totalSpend: number,
  currency: string
): { formatted: string; millions: number; billions: number; scale: 'K' | 'M' | 'B' } {
  const billions = totalSpend / 1_000_000_000
  const millions = totalSpend / 1_000_000
  const thousands = totalSpend / 1_000
  if (Math.abs(billions) >= 1) {
    return { formatted: `${currency}${billions.toFixed(1)}B`, millions, billions, scale: 'B' }
  }
  if (Math.abs(millions) >= 1) {
    return { formatted: `${currency}${millions.toFixed(1)}M`, millions, billions, scale: 'M' }
  }
  return { formatted: `${currency}${thousands.toFixed(1)}K`, millions, billions, scale: 'K' }
}
