import { useState } from 'react'
import { FilterState, defaultFilters } from '@/types/filters'

export function useFilters() {
  const [filters, setFilters] = useState<FilterState>(defaultFilters())

  function updateFilter<K extends keyof FilterState>(key: K, value: FilterState[K]) {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  function clearFilters() {
    setFilters(defaultFilters())
  }

  function toQueryParams(): Record<string, string> {
    const params: Record<string, string> = {}
    if (filters.date_from) params.date_from = filters.date_from
    if (filters.date_to) params.date_to = filters.date_to
    if (filters.business_units.length > 0) params.business_units = filters.business_units.join(',')
    if (filters.category_l1s.length > 0) params.category_l1s = filters.category_l1s.join(',')
    if (filters.supplier_search) params.supplier_search = filters.supplier_search
    return params
  }

  return { filters, updateFilter, clearFilters, toQueryParams }
}
