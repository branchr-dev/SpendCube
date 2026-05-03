import { useEffect, useRef, useState } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FilterState, FilterOptions, defaultFilters } from '@/types/filters'

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
}

export default function FilterBar({ filters, onChange, options }: FilterBarProps) {
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
      <Button variant="outline" size="sm" onClick={() => onChange(defaultFilters())}>
        Clear
      </Button>
    </div>
  )
}
