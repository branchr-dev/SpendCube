export function formatCurrency(value: number, currency = 'AUD'): string {
  const rounded = Math.round(value)
  const formatted = rounded.toLocaleString('en-AU')
  if (currency === 'AUD') return `$${formatted}`
  return `${currency} ${formatted}`
}

export function formatPct(value: number): string {
  return `${value.toFixed(1)}%`
}

export function formatNumber(value: number): string {
  return Math.round(value).toLocaleString('en-AU')
}

export function formatDate(isoStr: string): string {
  const date = new Date(isoStr)
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatMonth(isoStr: string): string {
  const date = new Date(isoStr)
  return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}
