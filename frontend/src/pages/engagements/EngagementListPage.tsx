import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { format } from 'date-fns'
import { Plus } from 'lucide-react'
import { api } from '@/lib/api'
import type { Engagement } from '@/types'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

export default function EngagementListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: engagements, isLoading } = useQuery<Engagement[]>({
    queryKey: ['engagements'],
    queryFn: () => api.get('/api/engagements').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })

  function prefetchEngagement(id: string) {
    queryClient.prefetchQuery({
      queryKey: ['summary', id, {}],
      queryFn: () => api.get(`/api/engagements/${id}/cube/summary`).then(r => r.data),
      staleTime: 5 * 60 * 1000,
    })
    queryClient.prefetchQuery({
      queryKey: ['overview', id],
      queryFn: () => api.get(`/api/engagements/${id}/cube/overview`).then(r => r.data),
      staleTime: 10 * 60 * 1000,
    })
  }

  function openEngagement(id: string) {
    prefetchEngagement(id)
    navigate(`/engagements/${id}/overview`)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto max-w-5xl p-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold">SpendCube</h1>
            <p className="text-muted-foreground mt-1">Select an engagement to analyse</p>
          </div>
          <Button onClick={() => navigate('/engagements/new')}>
            <Plus className="mr-2 h-4 w-4" />
            New Engagement
          </Button>
        </div>

        {isLoading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-4 w-1/2 mt-1" />
                </CardHeader>
                <CardContent><Skeleton className="h-4 w-1/3" /></CardContent>
                <CardFooter><Skeleton className="h-9 w-20" /></CardFooter>
              </Card>
            ))}
          </div>
        )}

        {!isLoading && (!engagements || engagements.length === 0) && (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-lg">No engagements yet.</p>
            <p className="text-sm mt-1">Create your first engagement to get started.</p>
          </div>
        )}

        {!isLoading && engagements && engagements.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {engagements.map(eng => (
              <Card
                key={eng.id}
                className="flex flex-col cursor-pointer hover:shadow-md transition-shadow"
                onMouseEnter={() => eng.id && prefetchEngagement(eng.id)}
              >
                <CardHeader>
                  <CardTitle className="text-base">{eng.client_name}</CardTitle>
                  <CardDescription>{eng.engagement_title}</CardDescription>
                </CardHeader>
                <CardContent className="flex-1">
                  {eng.created_at && (
                    <p className="text-xs text-muted-foreground">
                      Created {format(new Date(eng.created_at), 'dd MMM yyyy')}
                    </p>
                  )}
                </CardContent>
                <CardFooter>
                  <Button size="sm" onClick={() => eng.id && openEngagement(eng.id)}>
                    Open
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
