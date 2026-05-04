import { NavLink, Outlet, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart3,
  Tag,
  Building2,
  CreditCard,
  ShieldCheck,
  Lightbulb,
  ClipboardList,
  LogOut,
  UploadCloud,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/formatters'
import type { Engagement, OverviewData } from '@/types'

const navItems = [
  { to: 'overview', label: 'Overview', icon: BarChart3 },
  { to: 'recommendations', label: 'Recommendations', icon: Lightbulb },
  { to: 'category', label: 'Category', icon: Tag },
  { to: 'supplier', label: 'Supplier', icon: Building2 },
  { to: 'payment-terms', label: 'Payment Terms', icon: CreditCard },
  { to: 'quality', label: 'Data Quality', icon: ShieldCheck },
  { to: 'upload', label: 'Upload Data', icon: UploadCloud },
]

export default function Layout() {
  const { user, signOut } = useAuth()
  const { id } = useParams()
  const base = `/engagements/${id}`

  const { data: engagement } = useQuery<Engagement>({
    queryKey: ['engagement', id],
    queryFn: () => api.get(`/api/engagements/${id}`).then(r => r.data),
    enabled: !!id,
  })

  const { data: sidebarOverview } = useQuery<OverviewData>({
    queryKey: ['sidebar-overview', id],
    queryFn: () => api.get(`/api/engagements/${id}/cube/overview`).then(r => r.data),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  })

  return (
    <div className="flex h-screen bg-background">
      <aside className="w-64 border-r bg-card flex flex-col">
        <div className="p-4 border-b">
          <h1 className="font-semibold text-sm">SpendCube</h1>
          {engagement?.client_name && (
            <p className="text-xs text-muted-foreground mt-0.5">{engagement.client_name}</p>
          )}
          {sidebarOverview?.total_spend != null && (
            <>
              <p className="text-base font-bold text-foreground/80 mt-2">{formatCurrency(sidebarOverview.total_spend, sidebarOverview.currency_label ?? 'AUD')}</p>
              <p className="text-xs text-muted-foreground">Total Spend</p>
              {sidebarOverview?.data_freshness && <p className='text-xs text-muted-foreground mt-0.5'>{formatDate(sidebarOverview.data_freshness)}</p>}
            </>
          )}
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={`${base}/${to}`}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
          {engagement?.is_admin && (
            <NavLink
              to={`${base}/admin/review`}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`
              }
            >
              <ClipboardList className="h-4 w-4" />
              Review Workstation
            </NavLink>
          )}
        </nav>
        <div className="p-4 border-t space-y-2">
          {user?.email && (
            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
          )}
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={signOut}>
            <LogOut className="h-4 w-4 mr-2" />
            Logout
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
