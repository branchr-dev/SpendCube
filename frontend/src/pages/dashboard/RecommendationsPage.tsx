import { useState, useMemo, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as XLSX from 'xlsx'
import {
  ScatterChart,
  Scatter,
  XAxis as RScatterXAxis,
  YAxis as RScatterYAxis,
  ZAxis,
  Tooltip as RScatterTooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { Settings } from 'lucide-react'
import useRecommendationConfig from '@/hooks/useRecommendationConfig'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import KpiCard from '@/components/dashboard/KpiCard'
import RecommendationCard from '@/components/dashboard/RecommendationCard'
import { SpendBarChart } from '@/components/charts'
import { CHART_COLORS, SEMANTIC_COLORS } from '@/components/charts/constants'
import { formatCurrency } from '@/lib/formatters'
import { api } from '@/lib/api'
import type { Recommendation, PortfolioSummary, Engagement } from '@/types'

type Confidence = 'ALL' | 'HIGH' | 'MEDIUM' | 'LOW'

interface RecommendationsResponse {
  recommendations: Recommendation[]
  portfolio_summary: PortfolioSummary
}

interface LeverSummary {
  lever: string
  totalImpact: number
  count: number
}

interface ScatterPoint {
  x: number
  y: number
  z: number
  label: string
  type: string
  impact: number
  lever: string
}

function PriorityMatrix({ recommendations }: { recommendations: Recommendation[] }) {
  const pointsByLever = useMemo(() => {
    const allPoints: ScatterPoint[] = recommendations.map(r => ({
      x: r.confidence === 'HIGH' ? 0.9 : r.confidence === 'MEDIUM' ? 0.6 : 0.3,
      y: r.estimated_impact_aud ?? 0,
      z: Math.max((r.addressable_baseline ?? 0) / 1000, 100),
      label: r.context ?? '',
      type: r.type ?? '',
      impact: r.estimated_impact_aud ?? 0,
      lever: r.lever ?? 'OTHER',
    }))
    const uniqueLevers = [...new Set(allPoints.map(p => p.lever))]
    return uniqueLevers.map((lever, leverIndex) => ({
      lever,
      leverIndex,
      points: allPoints.filter(p => p.lever === lever),
    }))
  }, [recommendations])

  if (recommendations.length === 0) return null

  return (
    <div className="border rounded-xl p-5 bg-card shadow-sm">
      <h3 className="section-header">Priority Matrix — Impact vs. Confidence</h3>
      <ResponsiveContainer width="100%" height={280}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 60 }}>
          <RScatterXAxis
            type="number"
            dataKey="x"
            domain={[0.2, 1.0]}
            ticks={[0.3, 0.6, 0.9]}
            tickFormatter={(v: number) => v === 0.3 ? 'Low' : v === 0.6 ? 'Medium' : 'High'}
            label={{ value: 'Confidence', position: 'insideBottom', offset: -5, fontSize: 11 }}
          />
          <RScatterYAxis
            type="number"
            dataKey="y"
            tickFormatter={(v: number) => formatCurrency(v)}
            label={{ value: 'Est. Savings', angle: -90, position: 'insideLeft', fontSize: 11 }}
          />
          <ZAxis type="number" dataKey="z" range={[40, 400]} />
          <RScatterTooltip
            content={({ payload }) => {
              if (!payload?.length) return null
              const d = payload[0].payload as ScatterPoint
              return (
                <div className="bg-background border rounded shadow p-2 text-xs space-y-1">
                  <div className="font-semibold">{d.label}</div>
                  <div>{d.type.replace(/_/g, ' ')}</div>
                  <div className="text-green-700 font-medium">{formatCurrency(d.impact)}</div>
                </div>
              )
            }}
          />
          {pointsByLever.map(({ lever, leverIndex, points }) => (
            <Scatter
              key={lever}
              name={lever.replace(/_/g, ' ')}
              data={points}
            >
              {points.map((_, i) => (
                <Cell key={i} fill={CHART_COLORS[leverIndex % CHART_COLORS.length]} />
              ))}
            </Scatter>
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function RecommendationsPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [confidenceFilter, setConfidenceFilter] = useState<Confidence>('ALL')
  const [selectedLever, setSelectedLever] = useState<string | null>(null)
  const [showConfig, setShowConfig] = useState(false)
  const { config: recConfig, saveConfig, isSaving } = useRecommendationConfig(engagementId)

  const [targetPaymentDays, setTargetPaymentDays] = useState<number>(0)
  const [wacc, setWacc] = useState<number>(0)
  const [consolidationThreshold, setConsolidationThreshold] = useState<number>(0)
  const [tailSpendAlertPct, setTailSpendAlertPct] = useState<number>(0)
  const [maverickAlertPct, setMaverickAlertPct] = useState<number>(0)
  const [competitiveTenderMinSpend, setCompetitiveTenderMinSpend] = useState<number>(0)
  const [contractCoverageGapMinSpend, setContractCoverageGapMinSpend] = useState<number>(0)
  const [concentrationThresholdPct, setConcentrationThresholdPct] = useState<number>(0)
  const [minDiscountOpportunity, setMinDiscountOpportunity] = useState<number>(0)

  useEffect(() => {
    if (!recConfig) return
    setTargetPaymentDays(recConfig.target_payment_days ?? 0)
    setWacc((recConfig.wacc ?? 0) * 100)
    setConsolidationThreshold(recConfig.consolidation_threshold ?? 0)
    setTailSpendAlertPct((recConfig.tail_spend_alert_pct ?? 0) * 100)
    setMaverickAlertPct((recConfig.maverick_alert_pct ?? 0) * 100)
    setCompetitiveTenderMinSpend(recConfig.competitive_tender_min_spend ?? 0)
    setContractCoverageGapMinSpend(recConfig.contract_coverage_gap_min_spend ?? 0)
    setConcentrationThresholdPct((recConfig.concentration_threshold_pct ?? 0) * 100)
    setMinDiscountOpportunity(recConfig.min_discount_opportunity ?? 0)
  }, [recConfig])

  const { data, isLoading, error } = useQuery<RecommendationsResponse>({
    queryKey: ['recommendations', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/recommendations`).then(r => r.data),
    enabled: !!engagementId,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const { data: engagements = [] } = useQuery<Engagement[]>({
    queryKey: ['engagements'],
    queryFn: () => api.get('/api/engagements').then(r => r.data),
    staleTime: 5 * 60 * 1000,
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

  const leverSummaries: LeverSummary[] = useMemo(() => {
    const map = new Map<string, { totalImpact: number; count: number }>()
    for (const r of recommendations) {
      const lever = r.lever ?? 'OTHER'
      const existing = map.get(lever) ?? { totalImpact: 0, count: 0 }
      map.set(lever, {
        totalImpact: existing.totalImpact + (r.estimated_impact_aud ?? 0),
        count: existing.count + 1,
      })
    }
    return Array.from(map.entries())
      .map(([lever, { totalImpact, count }]) => ({ lever, totalImpact, count }))
      .sort((a, b) => b.totalImpact - a.totalImpact)
  }, [recommendations])

  const displayedRecs = (
    selectedLever ? filtered.filter(r => (r.lever ?? 'OTHER') === selectedLever) : filtered
  ).sort((a, b) => (b.estimated_impact_aud ?? 0) - (a.estimated_impact_aud ?? 0))

  async function handleSaveConfig() {
    await saveConfig({
      target_payment_days: targetPaymentDays,
      wacc: wacc / 100,
      consolidation_threshold: consolidationThreshold,
      tail_spend_alert_pct: tailSpendAlertPct / 100,
      maverick_alert_pct: maverickAlertPct / 100,
      competitive_tender_min_spend: competitiveTenderMinSpend,
      contract_coverage_gap_min_spend: contractCoverageGapMinSpend,
      concentration_threshold_pct: concentrationThresholdPct / 100,
      min_discount_opportunity: minDiscountOpportunity,
    })
    runMutation.mutate()
  }

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
        <h1 className="text-2xl font-bold">Recommendations</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowConfig(p => !p)}>
            <Settings className="h-4 w-4 mr-2" />
            {showConfig ? 'Close Settings' : 'Configure'}
          </Button>
          <Button
            variant="outline"
            onClick={exportToExcel}
            disabled={recommendations.length === 0}
          >
            Export to Excel
          </Button>
        </div>
      </div>

      {portfolio && (
        <div className="text-center py-4 border rounded-xl bg-card shadow-sm">
          <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Total Identified Savings</p>
          <p className="text-5xl font-bold text-green-700">{formatCurrency(portfolio.total_identified_savings ?? 0)}</p>
        </div>
      )}

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
          <KpiCard
            label="Sanity Check"
            value={portfolio.sanity_check_passed ? 'Passed' : 'Review'}
            valueType="text"
            accentColor={portfolio.sanity_check_passed ? 'green' : 'risk'}
          />
        </div>
      )}

      {showConfig && (
        <div className="border rounded-xl p-5 bg-muted/30 space-y-4">
          <h3 className="text-sm font-semibold">Recommendation Thresholds</h3>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1">
              <Label htmlFor="target_payment_days">Target Payment Days</Label>
              <Input
                id="target_payment_days"
                type="number"
                value={targetPaymentDays}
                onChange={e => setTargetPaymentDays(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="wacc">WACC (%)</Label>
              <Input
                id="wacc"
                type="number"
                value={wacc}
                onChange={e => setWacc(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="consolidation_threshold">Consolidation Threshold (suppliers)</Label>
              <Input
                id="consolidation_threshold"
                type="number"
                value={consolidationThreshold}
                onChange={e => setConsolidationThreshold(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="tail_spend_alert_pct">Tail Spend Alert (%)</Label>
              <Input
                id="tail_spend_alert_pct"
                type="number"
                value={tailSpendAlertPct}
                onChange={e => setTailSpendAlertPct(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="maverick_alert_pct">Maverick Alert (%)</Label>
              <Input
                id="maverick_alert_pct"
                type="number"
                value={maverickAlertPct}
                onChange={e => setMaverickAlertPct(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="competitive_tender_min_spend">Competitive Tender Min Spend</Label>
              <Input
                id="competitive_tender_min_spend"
                type="number"
                value={competitiveTenderMinSpend}
                onChange={e => setCompetitiveTenderMinSpend(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="contract_coverage_gap_min_spend">Contract Coverage Gap Min Spend</Label>
              <Input
                id="contract_coverage_gap_min_spend"
                type="number"
                value={contractCoverageGapMinSpend}
                onChange={e => setContractCoverageGapMinSpend(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="concentration_threshold_pct">Concentration Threshold (%)</Label>
              <Input
                id="concentration_threshold_pct"
                type="number"
                value={concentrationThresholdPct}
                onChange={e => setConcentrationThresholdPct(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="min_discount_opportunity">Min Discount Opportunity</Label>
              <Input
                id="min_discount_opportunity"
                type="number"
                value={minDiscountOpportunity}
                onChange={e => setMinDiscountOpportunity(Number(e.target.value))}
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={() => setShowConfig(false)}>Cancel</Button>
            <Button onClick={handleSaveConfig} disabled={isSaving}>
              {isSaving ? 'Saving…' : 'Save & Regenerate'}
            </Button>
          </div>
        </div>
      )}

      <PriorityMatrix recommendations={recommendations} />

      {leverSummaries.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 px-1">
          {leverSummaries.map(({ lever }, i) => (
            <span key={lever} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span
                className="inline-block w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }}
              />
              {lever.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      )}

      {leverSummaries.length > 0 && (
        <div className="border rounded-xl p-5 bg-card shadow-sm">
          <SpendBarChart
            data={leverSummaries.map(l => ({ label: l.lever.replace(/_/g, ' '), value: l.totalImpact }))}
            title="Savings by Lever"
            horizontal={true}
            valueFormatter={v => formatCurrency(v)}
            showLabel={false}
            color={SEMANTIC_COLORS.opportunity}
          />
        </div>
      )}

      {leverSummaries.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {leverSummaries.map(({ lever, totalImpact, count }) => (
            <div
              key={lever}
              onClick={() => setSelectedLever(prev => prev === lever ? null : lever)}
              className={
                selectedLever === lever
                  ? 'border-2 border-primary bg-primary/5 rounded-xl p-4 cursor-pointer'
                  : 'border rounded-xl p-4 cursor-pointer hover:bg-muted/50'
              }
            >
              <div className="text-sm font-semibold">{lever.replace(/_/g, ' ')}</div>
              <div className="text-lg font-bold text-green-700">{formatCurrency(totalImpact)}</div>
              <div className="text-xs text-muted-foreground">{count} recommendations</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap pt-2 border-t">
        <span className="text-sm text-muted-foreground">Filter by confidence:</span>
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

      <div className="space-y-3">
        {displayedRecs.length === 0 ? (
          <p className="text-muted-foreground">No recommendations match the current filters.</p>
        ) : (
          (() => {
            const portfolioTotal = portfolio?.total_identified_savings ?? 0
            return displayedRecs.map((rec, i) => {
              const leverIndex = leverSummaries.findIndex(l => l.lever === (rec.lever ?? 'OTHER'))
              return (
                <RecommendationCard
                  key={i}
                  rec={rec}
                  portfolioTotal={portfolioTotal}
                  leverIndex={leverIndex >= 0 ? leverIndex : undefined}
                />
              )
            })
          })()
        )}
      </div>
    </div>
  )
}
