import { useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as XLSX from 'xlsx'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import KpiCard from '@/components/dashboard/KpiCard'
import RecommendationCard from '@/components/dashboard/RecommendationCard'
import { api } from '@/lib/api'
import type { Recommendation, PortfolioSummary, Engagement } from '@/types'

type Confidence = 'ALL' | 'HIGH' | 'MEDIUM' | 'LOW'

interface RecommendationsResponse {
  recommendations: Recommendation[]
  portfolio_summary: PortfolioSummary
}

export default function RecommendationsPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [confidenceFilter, setConfidenceFilter] = useState<Confidence>('ALL')

  const { data, isLoading, error } = useQuery<RecommendationsResponse>({
    queryKey: ['recommendations', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/recommendations`).then(r => r.data),
    enabled: !!engagementId,
    retry: false,
  })

  const { data: engagements = [] } = useQuery<Engagement[]>({
    queryKey: ['engagements'],
    queryFn: () => api.get('/api/engagements').then(r => r.data),
  })
  const engagement = engagements.find(e => e.id === engagementId)

  const runMutation = useMutation({
    mutationFn: () =>
      api.post(`/api/engagements/${engagementId}/recommendations/run`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recommendations', engagementId] })
    },
  })

  const is404 = (error as { response?: { status?: number } } | null)?.response?.status === 404

  const recommendations = data?.recommendations ?? []
  const portfolio = data?.portfolio_summary

  const filtered = useMemo(
    () =>
      confidenceFilter === 'ALL'
        ? recommendations
        : recommendations.filter(r => r.confidence === confidenceFilter),
    [recommendations, confidenceFilter],
  )

  const leverTabs = useMemo(() => {
    const seen = new Set<string>()
    const levers: string[] = []
    for (const r of recommendations) {
      const lever = r.lever ?? 'OTHER'
      if (!seen.has(lever)) {
        seen.add(lever)
        levers.push(lever)
      }
    }
    return levers
  }, [recommendations])

  function exportToExcel() {
    const clientName = (engagement?.client_name ?? engagementId ?? 'client')
      .replace(/[^a-zA-Z0-9_-]/g, '_')
    const date = new Date().toISOString().slice(0, 10)
    const rows = recommendations.map(r => ({
      Type: r.type ?? '',
      Context: r.context ?? '',
      'Estimated Impact AUD': r.estimated_impact_aud ?? 0,
      Confidence: r.confidence ?? '',
      Lever: r.lever ?? '',
      Action: r.action ?? '',
      'Baseline Spend': r.baseline_spend ?? 0,
      'Addressability %': r.addressability_pct != null ? r.addressability_pct : '',
      'Addressable Baseline': r.addressable_baseline ?? 0,
      'Saving %': r.saving_pct != null ? r.saving_pct : '',
      Narrative: r.narrative ?? '',
    }))
    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Recommendations')
    XLSX.writeFile(wb, `spendcube_recommendations_${clientName}_${date}.xlsx`)
  }

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      </div>
    )
  }

  if (is404) {
    return (
      <div className="p-6 flex flex-col items-center gap-4 text-center mt-12">
        <p className="text-muted-foreground">
          No recommendations have been generated yet for this engagement.
        </p>
        <Button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
          {runMutation.isPending ? 'Running…' : 'Run Recommendations Engine'}
        </Button>
        {runMutation.isError && (
          <p className="text-sm text-red-600">
            Failed to run recommendations engine. Please try again.
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Recommendations</h1>
        <Button
          variant="outline"
          onClick={exportToExcel}
          disabled={recommendations.length === 0}
        >
          Export to Excel
        </Button>
      </div>

      {portfolio && (
        <div className="grid grid-cols-4 gap-4">
          <KpiCard
            label="Total Identified Savings"
            value={portfolio.total_identified_savings ?? 0}
            valueType="currency"
          />
          <KpiCard
            label="Savings as % of Spend"
            value={(portfolio.savings_as_pct_of_spend ?? 0) * 100}
            valueType="pct"
          />
          <KpiCard
            label="Recommendation Count"
            value={portfolio.recommendation_count ?? 0}
            valueType="number"
          />
          <div className="flex items-center justify-center rounded-lg border bg-card">
            <div className="text-center p-4">
              <div className="text-sm text-muted-foreground mb-2">Sanity Check</div>
              {portfolio.sanity_check_passed ? (
                <Badge className="bg-green-100 text-green-800 border-green-200 text-sm px-3 py-1">
                  Passed
                </Badge>
              ) : (
                <Badge className="bg-red-100 text-red-800 border-red-200 text-sm px-3 py-1">
                  Warning — review results
                </Badge>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-muted-foreground">Confidence:</span>
        {(['ALL', 'HIGH', 'MEDIUM', 'LOW'] as Confidence[]).map(c => (
          <button
            key={c}
            onClick={() => setConfidenceFilter(c)}
            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
              confidenceFilter === c
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {leverTabs.length === 0 ? (
        <p className="text-muted-foreground">No recommendations available.</p>
      ) : (
        <Tabs defaultValue={leverTabs[0]}>
          <TabsList>
            {leverTabs.map(lever => {
              const count = recommendations.filter(r => (r.lever ?? 'OTHER') === lever).length
              return (
                <TabsTrigger key={lever} value={lever}>
                  {lever.replace(/_/g, ' ')} ({count})
                </TabsTrigger>
              )
            })}
          </TabsList>
          {leverTabs.map(lever => {
            const leverRecs = filtered
              .filter(r => (r.lever ?? 'OTHER') === lever)
              .sort((a, b) => (b.estimated_impact_aud ?? 0) - (a.estimated_impact_aud ?? 0))
            return (
              <TabsContent key={lever} value={lever} className="space-y-3 mt-4">
                {leverRecs.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    No {lever.replace(/_/g, ' ').toLowerCase()} recommendations match the current
                    filter.
                  </p>
                ) : (
                  leverRecs.map((rec, i) => <RecommendationCard key={i} rec={rec} />)
                )}
              </TabsContent>
            )
          })}
        </Tabs>
      )}
    </div>
  )
}
