import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft } from 'lucide-react'
import { api } from '@/lib/api'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function NewEngagementPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    client_name: '',
    engagement_title: 'Procurement Spend Diagnostic',
    currency_label: 'AUD',
    llm_dry_run: true,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const response = await api.post('/api/engagements', { ...form, name: form.client_name })
      if (response.status === 201 && response.data?.id) {
        navigate(`/engagements/${response.data.id}/upload`)
      }
    } catch (err: unknown) {
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          'Failed to create engagement'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        <Button
          variant="ghost"
          size="sm"
          className="mb-4"
          onClick={() => navigate('/engagements')}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        <Card>
          <CardHeader>
            <CardTitle>New Engagement</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="client_name">Client Name *</Label>
                <Input
                  id="client_name"
                  value={form.client_name}
                  onChange={e => setForm(f => ({ ...f, client_name: e.target.value }))}
                  required
                  disabled={loading}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="engagement_title">Engagement Title *</Label>
                <Input
                  id="engagement_title"
                  value={form.engagement_title}
                  onChange={e => setForm(f => ({ ...f, engagement_title: e.target.value }))}
                  required
                  disabled={loading}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="currency_label">Currency Label</Label>
                <Input
                  id="currency_label"
                  value={form.currency_label}
                  onChange={e => setForm(f => ({ ...f, currency_label: e.target.value }))}
                  disabled={loading}
                />
              </div>
              <div className="flex items-start gap-3">
                <Switch
                  id="llm_dry_run"
                  checked={form.llm_dry_run}
                  onCheckedChange={v => setForm(f => ({ ...f, llm_dry_run: v }))}
                  disabled={loading}
                />
                <div className="space-y-1">
                  <Label htmlFor="llm_dry_run" className="cursor-pointer">
                    LLM Dry Run
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Disable only when Anthropic API key is configured on the server
                  </p>
                </div>
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Creating...' : 'Create Engagement'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
