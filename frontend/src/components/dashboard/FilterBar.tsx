import { useEffect, useRef, useState } from 'react'
import { SlidersHorizontal, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FilterState, FilterOptions, defaultFilters } from '@/types/filters'
import type { ABCSegment } from '@/types'

interface MultiSelectProps {
  label: string
  options: string[]
  selected: string[]
  onChange: (v: string[]) => void
}

function MultiSelect({ label, options, selected, onChange }: MultiSelectProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function toggle(option: string) {
    if (selected.includes(option)) {
      onChange(selected.filter(s => s !== option))
    } else {
      onChange([...selected, option])
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm hover:bg-accent/50"
      >
        {selected.length === 0 ? `All ${label}` : `${selected.length} selected`}
      </button>
      {open && (
        <div className="absolute z-50 w-full mt-1 bg-background border rounded-md shadow-md max-h-48 overflow-auto">
          {options.map(opt => (
            <label
              key={opt}
              className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={() => toggle(opt)}
                className="h-4 w-4"
              />
              {opt}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

interface FilterBarProps {
  filters: FilterState
  onChange: (f: FilterState) => void
  options: FilterOptions
  showConfidenceFilter?: boolean
}

export default function FilterBar({ filters, onChange, options, showConfidenceFilter = false }: FilterBarProps) {
  const [expanded, setExpanded] = useState(false)
  const abcOptions: ABCSegment[] = options.abc_segments ?? []
  const catStatusOptions = options.categorisation_statuses ?? []

  const activePills: { label: string; onRemove: () => void }[] = []

  if (filters.date_from) {
    activePills.push({ label: 'From: ' + filters.date_from, onRemove: () => onChange({ ...filters, date_from: undefined }) })
  }
  if (filters.date_to) {
    activePills.push({ label: 'To: ' + filters.date_to, onRemove: () => onChange({ ...filters, date_to: undefined }) })
  }
  for (const bu of filters.business_units) {
    activePills.push({ label: bu, onRemove: () => onChange({ ...filters, business_units: filters.business_units.filter(v => v !== bu) }) })
  }
  for (const cat of filters.category_l1s) {
    activePills.push({ label: cat, onRemove: () => onChange({ ...filters, category_l1s: filters.category_l1s.filter(v => v !== cat) }) })
  }
  if (filters.supplier_search) {
    activePills.push({ label: 'Supplier: ' + filters.supplier_search, onRemove: () => onChange({ ...filters, supplier_search: '' }) })
  }
  for (const le of filters.legal_entities) {
    activePills.push({ label: le, onRemove: () => onChange({ ...filters, legal_entities: filters.legal_entities.filter(v => v !== le) }) })
  }
  for (const cur of filters.currencies) {
    activePills.push({ label: cur, onRemove: () => onChange({ ...filters, currencies: filters.currencies.filter(v => v !== cur) }) })
  }
  for (const country of filters.countries) {
    activePills.push({ label: country, onRemove: () => onChange({ ...filters, countries: filters.countries.filter(v => v !== country) }) })
  }
  for (const seg of filters.abc_segments) {
    activePills.push({ label: seg, onRemove: () => onChange({ ...filters, abc_segments: filters.abc_segments.filter(v => v !== seg) as ABCSegment[] }) })
  }

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 flex-wrap py-2">
        <Button variant="outline" size="sm" onClick={() => setExpanded(true)}>
          <SlidersHorizontal className="h-4 w-4 mr-1.5" />
          Filters
          {activePills.length > 0 && (
            <span className="ml-1 bg-primary text-primary-foreground rounded-full text-xs px-1.5">
              {activePills.length}
            </span>
          )}
        </Button>
        {activePills.map((pill, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 bg-muted text-muted-foreground text-xs rounded-full px-2.5 py-1"
          >
            {pill.label}
            <button onClick={pill.onRemove}>
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        {activePills.length > 0 && (
          <button
            className="text-xs text-muted-foreground underline ml-1"
            onClick={() => onChange(defaultFilters())}
          >
            Clear all
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-end gap-3 p-4 bg-muted/30 rounded-lg border">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">From</label>
        <Input
          type="date"
          value={filters.date_from ?? ''}
          onChange={e => onChange({ ...filters, date_from: e.target.value || undefined })}
          className="w-36"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">To</label>
        <Input
          type="date"
          value={filters.date_to ?? ''}
          onChange={e => onChange({ ...filters, date_to: e.target.value || undefined })}
          className="w-36"
        />
      </div>
      {options.business_units.length > 0 && (
        <div className="flex flex-col gap-1 min-w-40">
          <label className="text-xs text-muted-foreground">Business Unit</label>
          <MultiSelect
            label="Business Units"
            options={options.business_units}
            selected={filters.business_units}
            onChange={v => onChange({ ...filters, business_units: v })}
          />
        </div>
      )}
      {options.category_l1s.length > 0 && (
        <div className="flex flex-col gap-1 min-w-40">
          <label className="text-xs text-muted-foreground">Category</label>
          <MultiSelect
            label="Categories"
            options={options.category_l1s}
            selected={filters.category_l1s}
            onChange={v => onChange({ ...filters, category_l1s: v })}
          />
        </div>
      )}
      <div className="flex flex-col gap-1 min-w-44">
        <label className="text-xs text-muted-foreground">Supplier Search</label>
        <Input
          type="text"
          placeholder="Search suppliers..."
          value={filters.supplier_search}
          onChange={e => onChange({ ...filters, supplier_search: e.target.value })}
        />
      </div>
      {options.legal_entities.length > 0 && (
        <div className="flex flex-col gap-1 min-w-40">
          <label className="text-xs text-muted-foreground">Legal Entity</label>
          <MultiSelect
            label="Legal Entities"
            options={options.legal_entities}
            selected={filters.legal_entities}
            onChange={v => onChange({ ...filters, legal_entities: v })}
          />
        </div>
      )}
      {options.currencies.length > 0 && (
        <div className="flex flex-col gap-1 min-w-36">
          <label className="text-xs text-muted-foreground">Currency</label>
          <MultiSelect
            label="Currencies"
            options={options.currencies}
            selected={filters.currencies}
            onChange={v => onChange({ ...filters, currencies: v })}
          />
        </div>
      )}
      {options.countries.length > 0 && (
        <div className="flex flex-col gap-1 min-w-40">
          <label className="text-xs text-muted-foreground">Country</label>
          <MultiSelect
            label="Countries"
            options={options.countries}
            selected={filters.countries}
            onChange={v => onChange({ ...filters, countries: v })}
          />
        </div>
      )}
      {abcOptions.length > 0 && (
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">ABC Segment</label>
          <div className="flex items-center gap-2 h-9 px-1">
            {abcOptions.map(seg => (
              <label key={seg} className="flex items-center gap-1 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={filters.abc_segments.includes(seg)}
                  onChange={() => {
                    const next = filters.abc_segments.includes(seg)
                      ? filters.abc_segments.filter(s => s !== seg)
                      : [...filters.abc_segments, seg]
                    onChange({ ...filters, abc_segments: next as ABCSegment[] })
                  }}
                />
                {seg}
              </label>
            ))}
          </div>
        </div>
      )}
      {catStatusOptions.length > 0 && (
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Status</label>
          <div className="flex items-center gap-2 h-9 px-1">
            {['All', ...catStatusOptions].map(status => (
              <label key={status} className="flex items-center gap-1 text-sm cursor-pointer">
                <input
                  type="radio"
                  name="categorisation_status"
                  className="h-4 w-4"
                  checked={
                    status === 'All'
                      ? filters.categorisation_statuses.length === 0
                      : filters.categorisation_statuses[0] === status
                  }
                  onChange={() => {
                    onChange({
                      ...filters,
                      categorisation_statuses: status === 'All' ? [] : [status],
                    })
                  }}
                />
                {status}
              </label>
            ))}
          </div>
        </div>
      )}
      {showConfidenceFilter && (
        <div className="flex flex-col gap-1 min-w-44">
          <label className="text-xs text-muted-foreground">
            Min Confidence:{' '}
            {filters.min_confidence != null
              ? `${Math.round(filters.min_confidence * 100)}%`
              : 'Any'}
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={filters.min_confidence ?? 0}
            onChange={e => {
              const val = parseFloat(e.target.value)
              onChange({ ...filters, min_confidence: val === 0 ? undefined : val })
            }}
            className="h-9 w-full accent-primary"
          />
        </div>
      )}
      <Button variant="outline" size="sm" onClick={() => onChange(defaultFilters())}>
        Clear
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setExpanded(false)}>
        Close ↑
      </Button>
    </div>
  )
}
