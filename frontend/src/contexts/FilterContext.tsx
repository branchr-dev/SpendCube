import { createContext, useContext, useReducer, ReactNode } from 'react'
import { FilterState, defaultFilters } from '@/types/filters'
import { ABCSegment } from '@/types/index'

export interface FilterContextValue {
  filters: FilterState
  updateFilter: (key: keyof FilterState, value: any) => void
  clearFilters: () => void
  toQueryParams: () => Record<string, string>
}

type FilterAction =
  | { type: 'SET_FILTER'; key: keyof FilterState; value: any }
  | { type: 'CLEAR_ALL' }

function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case 'SET_FILTER':
      return { ...state, [action.key]: action.value }
    case 'CLEAR_ALL':
      return defaultFilters()
    default:
      return state
  }
}

function initFromURLParams(): FilterState {
  const base = defaultFilters()
  if (typeof window === 'undefined') return base
  const params = new URLSearchParams(window.location.search)
  return {
    ...base,
    date_from: params.get('date_from') ?? base.date_from,
    date_to: params.get('date_to') ?? base.date_to,
    business_units: params.get('business_units')?.split(',').filter(Boolean) ?? base.business_units,
    category_l1s: params.get('category_l1s')?.split(',').filter(Boolean) ?? base.category_l1s,
    supplier_search: params.get('supplier_search') ?? base.supplier_search,
    legal_entities: params.get('legal_entities')?.split(',').filter(Boolean) ?? base.legal_entities,
    currencies: params.get('currencies')?.split(',').filter(Boolean) ?? base.currencies,
    countries: params.get('countries')?.split(',').filter(Boolean) ?? base.countries,
    categorisation_statuses:
      params.get('categorisation_statuses')?.split(',').filter(Boolean) ?? base.categorisation_statuses,
    abc_segments:
      (params.get('abc_segments')?.split(',').filter(Boolean) ?? base.abc_segments) as ABCSegment[],
    min_confidence: params.get('min_confidence') ? Number(params.get('min_confidence')) : base.min_confidence,
  }
}

const FilterContext = createContext<FilterContextValue | null>(null)

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, dispatch] = useReducer(filterReducer, undefined, initFromURLParams)

  function updateFilter(key: keyof FilterState, value: any) {
    dispatch({ type: 'SET_FILTER', key, value })
  }

  function clearFilters() {
    dispatch({ type: 'CLEAR_ALL' })
  }

  function toQueryParams(): Record<string, string> {
    const params: Record<string, string> = {}
    if (filters.date_from) params.date_from = filters.date_from
    if (filters.date_to) params.date_to = filters.date_to
    if (filters.business_units.length > 0) params.business_units = filters.business_units.join(',')
    if (filters.category_l1s.length > 0) params.category_l1s = filters.category_l1s.join(',')
    if (filters.supplier_search) params.supplier_search = filters.supplier_search
    if (filters.legal_entities.length > 0) params.legal_entities = filters.legal_entities.join(',')
    if (filters.currencies.length > 0) params.currencies = filters.currencies.join(',')
    if (filters.countries.length > 0) params.countries = filters.countries.join(',')
    if (filters.categorisation_statuses.length > 0)
      params.categorisation_statuses = filters.categorisation_statuses.join(',')
    if (filters.abc_segments.length > 0) params.abc_segments = filters.abc_segments.join(',')
    if (filters.min_confidence != null) params.min_confidence = String(filters.min_confidence)
    return params
  }

  return (
    <FilterContext.Provider value={{ filters, updateFilter, clearFilters, toQueryParams }}>
      {children}
    </FilterContext.Provider>
  )
}

export function useFilterContext(): FilterContextValue {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useFilterContext must be used within a FilterProvider')
  return ctx
}
