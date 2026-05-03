import { ABCSegment } from './index'

export interface FilterState {
  date_from?: string
  date_to?: string
  business_units: string[]
  category_l1s: string[]
  supplier_search: string
  legal_entities: string[]
  currencies: string[]
  countries: string[]
  categorisation_statuses: string[]
  abc_segments: ABCSegment[]
  min_confidence?: number
}

export interface FilterOptions {
  business_units: string[]
  category_l1s: string[]
  legal_entities: string[]
  currencies: string[]
  countries: string[]
}

export function defaultFilters(): FilterState {
  return {
    date_from: undefined,
    date_to: undefined,
    business_units: [],
    category_l1s: [],
    supplier_search: '',
    legal_entities: [],
    currencies: [],
    countries: [],
    categorisation_statuses: [],
    abc_segments: [],
    min_confidence: undefined,
  }
}
