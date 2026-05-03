import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { Skeleton } from '@/components/ui/skeleton'

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="space-y-2 w-64">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
  )
}

export default function ProtectedRoute() {
  const { session, loading } = useAuth()

  if (loading) return <LoadingSpinner />
  if (!session) return <Navigate to="/login" replace />
  return <Outlet />
}
