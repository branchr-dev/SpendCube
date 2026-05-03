import { useState } from 'react'

export type DrilldownLevel = 'overview' | 'category_l1' | 'category_l2' | 'supplier' | 'transaction'

export interface DrilldownState {
  level: DrilldownLevel
  category_l1?: string
  category_l2?: string
  supplier_id?: string
  supplier_name?: string
}

function defaultState(): DrilldownState {
  return { level: 'overview' }
}

export function useDrilldown(): {
  state: DrilldownState
  drillTo: (level: DrilldownLevel, context: Partial<DrilldownState>) => void
  drillUp: () => void
  reset: () => void
  isFiltered: boolean
} {
  const [history, setHistory] = useState<DrilldownState[]>([defaultState()])

  const state = history[history.length - 1]

  function drillTo(level: DrilldownLevel, context: Partial<DrilldownState>) {
    setHistory(prev => [...prev, { level, ...context }])
  }

  function drillUp() {
    setHistory(prev => (prev.length > 1 ? prev.slice(0, -1) : prev))
  }

  function reset() {
    setHistory([defaultState()])
  }

  return { state, drillTo, drillUp, reset, isFiltered: state.level !== 'overview' }
}
