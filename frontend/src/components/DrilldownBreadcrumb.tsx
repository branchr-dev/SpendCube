import { ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DrilldownLevel, DrilldownState } from '@/hooks/useDrilldown'

interface DrilldownBreadcrumbProps {
  state: DrilldownState
  drillTo: (level: DrilldownLevel, context: Partial<DrilldownState>) => void
  reset: () => void
}

export function DrilldownBreadcrumb({ state, drillTo, reset }: DrilldownBreadcrumbProps) {
  if (state.level === 'overview') return null

  const segments: { label: string; onClick: () => void }[] = [
    { label: 'Overview', onClick: reset },
  ]

  if (state.category_l1) {
    segments.push({
      label: state.category_l1,
      onClick: () => drillTo('category_l1', { category_l1: state.category_l1 }),
    })
  }

  if (state.category_l2) {
    segments.push({
      label: state.category_l2,
      onClick: () =>
        drillTo('category_l2', {
          category_l1: state.category_l1,
          category_l2: state.category_l2,
        }),
    })
  }

  if (state.supplier_name) {
    segments.push({
      label: state.supplier_name,
      onClick: () =>
        drillTo('supplier', {
          category_l1: state.category_l1,
          category_l2: state.category_l2,
          supplier_id: state.supplier_id,
          supplier_name: state.supplier_name,
        }),
    })
  }

  const lastIndex = segments.length - 1

  return (
    <nav className="flex items-center gap-1 text-sm text-muted-foreground">
      {segments.map((segment, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
          {i === lastIndex ? (
            <span className="font-medium text-foreground">{segment.label}</span>
          ) : (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-muted-foreground hover:text-foreground"
              onClick={segment.onClick}
            >
              {segment.label}
            </Button>
          )}
        </span>
      ))}
    </nav>
  )
}
