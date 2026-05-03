export interface FilterState {
  date_from?: string
  date_to?: string
  business_units: string[]
  category_l1s: string[]
  supplier_search: string
}

export interface FilterOptions {
  business_units: string[]
  category_l1s: string[]
}

export function defaultFilters(): FilterState {
  return {
    date_from: undefined,
    date_to: undefined,
    business_units: [],
    category_l1s: [],
    supplier_search: '',
  }
}
