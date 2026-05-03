import { useState, useMemo } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { api } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/formatters'
import type { Engagement, CategoryRow, AuditLogEntry, CategoryOverride } from '@/types'

// ---------------------------------------------------------------------------
// Local types
// ---------------------------------------------------------------------------

interface SupplierQueueItem {
  id: string
  raw_supplier_name?: string
  canonical_supplier_id?: string
  match_method?: string
  confidence?: number
  review_status?: string
}

interface CategoryQueueItem {
  transaction_id?: string
  raw_supplier_name?: string
  canonical_supplier_id?: string
  base_amount?: number
  category_l1?: string
  category_l2?: string
  category_l3?: string
  category_confidence?: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ConfidenceBadge({ score }: { score: number }) {
  const pct = `${(score * 100).toFixed(0)}%`
  if (score >= 0.88) {
    return <Badge className="bg-green-100 text-green-800 border-green-200">{pct}</Badge>
  }
  if (score >= 0.70) {
    return <Badge className="bg-amber-100 text-amber-800 border-amber-200">{pct}</Badge>
  }
  return <Badge className="bg-red-100 text-red-800 border-red-200">{pct}</Badge>
}

const NONE = '__none__'

// ---------------------------------------------------------------------------
// Supplier Queue Tab
// ---------------------------------------------------------------------------

function SupplierQueueTab({
  engagementId,
}: {
  engagementId: string
}) {
  const queryClient = useQueryClient()

  const [overrideDialog, setOverrideDialog] = useState<{ matchId: string } | null>(null)
  const [overrideForm, setOverrideForm] = useState({ canonicalId: '', name: '' })

  const { data: queue = [], isLoading } = useQuery<SupplierQueueItem[]>({
    queryKey: ['supplier-queue', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/review/supplier-queue`).then(r => r.data),
    enabled: !!engagementId,
  })

  const approveMutation = useMutation({
    mutationFn: (matchId: string) =>
      api.post(`/api/engagements/${engagementId}/review/supplier/${matchId}/approve`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['supplier-queue', engagementId] })
      queryClient.invalidateQueries({ queryKey: ['audit-log', engagementId] })
      toast.success('Supplier match approved')
    },
    onError: () => toast.error('Failed to approve supplier match'),
  })

  const rejectMutation = useMutation({
    mutationFn: (matchId: string) =>
      api.post(`/api/engagements/${engagementId}/review/supplier/${matchId}/reject`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['supplier-queue', engagementId] })
      queryClient.invalidateQueries({ queryKey: ['audit-log', engagementId] })
      toast.success('Supplier match rejected')
    },
    onError: () => toast.error('Failed to reject supplier match'),
  })

  const overrideMutation = useMutation({
    mutationFn: ({ matchId, canonicalId, name }: { matchId: string; canonicalId: string; name: string }) =>
      api
        .post(`/api/engagements/${engagementId}/review/supplier/${matchId}/override`, {
          canonical_supplier_id: canonicalId,
          canonical_name: name,
        })
        .then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['supplier-queue', engagementId] })
      queryClient.invalidateQueries({ queryKey: ['audit-log', engagementId] })
      toast.success('Supplier override applied')
      setOverrideDialog(null)
      setOverrideForm({ canonicalId: '', name: '' })
    },
    onError: () => toast.error('Failed to apply supplier override'),
  })

  function openOverride(matchId: string) {
    setOverrideForm({ canonicalId: '', name: '' })
    setOverrideDialog({ matchId })
  }

  function submitOverride() {
    if (!overrideDialog) return
    if (!overrideForm.canonicalId.trim() || !overrideForm.name.trim()) {
      toast.error('Both Canonical ID and Name are required')
      return
    }
    overrideMutation.mutate({
      matchId: overrideDialog.matchId,
      canonicalId: overrideForm.canonicalId.trim(),
      name: overrideForm.name.trim(),
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-2 mt-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
      </div>
    )
  }

  return (
    <>
      {queue.length === 0 ? (
        <p className="text-muted-foreground text-sm mt-4">0 items pending</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Raw Supplier</TableHead>
              <TableHead>Matched To</TableHead>
              <TableHead>Method</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {queue.map(row => (
              <TableRow key={row.id}>
                <TableCell className="font-medium">{row.raw_supplier_name ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs">{row.canonical_supplier_id ?? '—'}</TableCell>
                <TableCell>{row.match_method ?? '—'}</TableCell>
                <TableCell>
                  {row.confidence != null ? (
                    <ConfidenceBadge score={row.confidence} />
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-green-700 border-green-200 hover:bg-green-50"
                      onClick={() => approveMutation.mutate(row.id)}
                      disabled={approveMutation.isPending}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-red-700 border-red-200 hover:bg-red-50"
                      onClick={() => rejectMutation.mutate(row.id)}
                      disabled={rejectMutation.isPending}
                    >
                      Reject
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => openOverride(row.id)}
                    >
                      Override
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!overrideDialog} onOpenChange={open => !open && setOverrideDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Override Supplier Match</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>New Canonical ID</Label>
              <Input
                value={overrideForm.canonicalId}
                onChange={e => setOverrideForm(f => ({ ...f, canonicalId: e.target.value }))}
                placeholder="e.g. abc123def456"
              />
            </div>
            <div className="space-y-1">
              <Label>New Name</Label>
              <Input
                value={overrideForm.name}
                onChange={e => setOverrideForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Acme Corporation"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOverrideDialog(null)}>
              Cancel
            </Button>
            <Button onClick={submitOverride} disabled={overrideMutation.isPending}>
              {overrideMutation.isPending ? 'Saving…' : 'Apply Override'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ---------------------------------------------------------------------------
// Category Override Dialog (shared by Category Queue and Override Rules tabs)
// ---------------------------------------------------------------------------

interface CatOverrideDialogProps {
  open: boolean
  onClose: () => void
  presetSupplierId?: string
  engagementId: string
  allCategories: CategoryRow[]
  onSuccess: () => void
}

function CatOverrideDialog({
  open,
  onClose,
  presetSupplierId,
  engagementId,
  allCategories,
  onSuccess,
}: CatOverrideDialogProps) {
  const [form, setForm] = useState({
    supplierId: presetSupplierId ?? '',
    glAccount: '',
    l1: '',
    l2: '',
    l3: '',
    reason: '',
  })

  // Reset form when dialog opens (and sync preset)
  const [lastOpen, setLastOpen] = useState(false)
  if (open && !lastOpen) {
    setLastOpen(true)
    setForm({ supplierId: presetSupplierId ?? '', glAccount: '', l1: '', l2: '', l3: '', reason: '' })
  }
  if (!open && lastOpen) {
    setLastOpen(false)
  }

  const l1Options = useMemo(
    () => [...new Set(allCategories.map(c => c.category_l1).filter((v): v is string => !!v))],
    [allCategories],
  )
  const l2Options = useMemo(
    () =>
      form.l1
        ? [...new Set(allCategories.filter(c => c.category_l1 === form.l1).map(c => c.category_l2).filter((v): v is string => !!v))]
        : [],
    [allCategories, form.l1],
  )
  const l3Options = useMemo(
    () =>
      form.l2
        ? [...new Set(allCategories.filter(c => c.category_l2 === form.l2).map(c => c.category_l3).filter((v): v is string => !!v))]
        : [],
    [allCategories, form.l2],
  )

  const mutation = useMutation({
    mutationFn: () =>
      api
        .post(`/api/engagements/${engagementId}/review/category-override`, {
          canonical_supplier_id: form.supplierId.trim() || undefined,
          gl_account: form.glAccount.trim() || undefined,
          override_l1: form.l1,
          override_l2: form.l2,
          override_l3: form.l3,
          reason: form.reason,
        })
        .then(r => r.data),
    onSuccess: () => {
      toast.success('Category override created')
      onSuccess()
      onClose()
    },
    onError: () => toast.error('Failed to create category override'),
  })

  function submit() {
    if (!form.supplierId.trim() && !form.glAccount.trim()) {
      toast.error('Provide a Supplier ID or GL Account')
      return
    }
    if (!form.l1 || !form.l2 || !form.l3) {
      toast.error('Select L1, L2, and L3 categories')
      return
    }
    if (!form.reason.trim()) {
      toast.error('Reason is required')
      return
    }
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={o => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Category Override</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Supplier ID (canonical_supplier_id)</Label>
            <Input
              value={form.supplierId}
              onChange={e => setForm(f => ({ ...f, supplierId: e.target.value }))}
              placeholder="Optional if GL Account provided"
            />
          </div>
          <div className="space-y-1">
            <Label>GL Account</Label>
            <Input
              value={form.glAccount}
              onChange={e => setForm(f => ({ ...f, glAccount: e.target.value }))}
              placeholder="Optional if Supplier ID provided"
            />
          </div>
          <div className="space-y-1">
            <Label>Category L1</Label>
            <Select
              value={form.l1 || NONE}
              onValueChange={v => setForm(f => ({ ...f, l1: v === NONE ? '' : v, l2: '', l3: '' }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select L1…" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>— Select L1 —</SelectItem>
                {l1Options.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Category L2</Label>
            <Select
              value={form.l2 || NONE}
              onValueChange={v => setForm(f => ({ ...f, l2: v === NONE ? '' : v, l3: '' }))}
              disabled={!form.l1}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select L2…" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>— Select L2 —</SelectItem>
                {l2Options.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Category L3</Label>
            <Select
              value={form.l3 || NONE}
              onValueChange={v => setForm(f => ({ ...f, l3: v === NONE ? '' : v }))}
              disabled={!form.l2}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select L3…" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>— Select L3 —</SelectItem>
                {l3Options.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Reason</Label>
            <textarea
              value={form.reason}
              onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
              className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Why is this override needed?"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Create Override'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Category Queue Tab
// ---------------------------------------------------------------------------

function CategoryQueueTab({
  engagementId,
  allCategories,
}: {
  engagementId: string
  allCategories: CategoryRow[]
}) {
  const queryClient = useQueryClient()
  const [overrideTarget, setOverrideTarget] = useState<CategoryQueueItem | null>(null)

  const { data: queue = [], isLoading } = useQuery<CategoryQueueItem[]>({
    queryKey: ['category-queue', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/review/category-queue`).then(r => r.data),
    enabled: !!engagementId,
  })

  if (isLoading) {
    return (
      <div className="space-y-2 mt-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
      </div>
    )
  }

  return (
    <>
      {queue.length === 0 ? (
        <p className="text-muted-foreground text-sm mt-4">0 items pending</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Supplier</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead>Current L1 / L2 / L3</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {queue.map((row, i) => (
              <TableRow key={row.transaction_id ?? i}>
                <TableCell className="font-medium">{row.raw_supplier_name ?? '—'}</TableCell>
                <TableCell className="text-right">
                  {row.base_amount != null ? formatCurrency(row.base_amount) : '—'}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {[row.category_l1, row.category_l2, row.category_l3].filter(Boolean).join(' / ') || '—'}
                </TableCell>
                <TableCell>
                  {row.category_confidence != null ? (
                    <ConfidenceBadge score={row.category_confidence} />
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell>
                  <Button size="sm" variant="outline" onClick={() => setOverrideTarget(row)}>
                    Override
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <CatOverrideDialog
        open={!!overrideTarget}
        onClose={() => setOverrideTarget(null)}
        presetSupplierId={overrideTarget?.canonical_supplier_id}
        engagementId={engagementId}
        allCategories={allCategories}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['category-queue', engagementId] })
          queryClient.invalidateQueries({ queryKey: ['category-overrides', engagementId] })
          queryClient.invalidateQueries({ queryKey: ['audit-log', engagementId] })
        }}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// Override Rules Tab
// ---------------------------------------------------------------------------

function OverrideRulesTab({
  engagementId,
  allCategories,
}: {
  engagementId: string
  allCategories: CategoryRow[]
}) {
  const queryClient = useQueryClient()
  const [addRuleOpen, setAddRuleOpen] = useState(false)

  const { data: overrides = [], isLoading } = useQuery<CategoryOverride[]>({
    queryKey: ['category-overrides', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/review/category-overrides`).then(r => r.data),
    enabled: !!engagementId,
  })

  const deleteMutation = useMutation({
    mutationFn: (overrideId: string) =>
      api
        .delete(`/api/engagements/${engagementId}/review/category-override/${overrideId}`)
        .then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['category-overrides', engagementId] })
      queryClient.invalidateQueries({ queryKey: ['audit-log', engagementId] })
      toast.success('Override rule deleted')
    },
    onError: () => toast.error('Failed to delete override rule'),
  })

  return (
    <>
      <div className="flex justify-end mt-2 mb-4">
        <Button onClick={() => setAddRuleOpen(true)}>Add Rule</Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
        </div>
      ) : overrides.length === 0 ? (
        <p className="text-muted-foreground text-sm">No override rules defined.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Matches</TableHead>
              <TableHead>L1 / L2 / L3</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {overrides.map(row => (
              <TableRow key={row.id}>
                <TableCell className="font-mono text-xs">
                  {row.canonical_supplier_id ?? row.gl_account ?? '—'}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {[row.override_l1, row.override_l2, row.override_l3].filter(Boolean).join(' / ') || '—'}
                </TableCell>
                <TableCell className="text-sm">{row.reason ?? '—'}</TableCell>
                <TableCell className="text-sm">
                  {row.created_at ? formatDate(row.created_at) : '—'}
                </TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-red-700 border-red-200 hover:bg-red-50"
                    onClick={() => row.id && deleteMutation.mutate(row.id)}
                    disabled={deleteMutation.isPending}
                  >
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <CatOverrideDialog
        open={addRuleOpen}
        onClose={() => setAddRuleOpen(false)}
        engagementId={engagementId}
        allCategories={allCategories}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['category-overrides', engagementId] })
          queryClient.invalidateQueries({ queryKey: ['audit-log', engagementId] })
        }}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// Audit Log Tab
// ---------------------------------------------------------------------------

function AuditLogTab({ engagementId }: { engagementId: string }) {
  const { data: entries = [], isLoading } = useQuery<AuditLogEntry[]>({
    queryKey: ['audit-log', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/review/audit-log`).then(r => r.data),
    enabled: !!engagementId,
  })

  if (isLoading) {
    return (
      <div className="space-y-2 mt-4">
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
      </div>
    )
  }

  return entries.length === 0 ? (
    <p className="text-muted-foreground text-sm mt-4">No audit entries yet.</p>
  ) : (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Timestamp</TableHead>
          <TableHead>Table</TableHead>
          <TableHead>Field</TableHead>
          <TableHead>Old Value</TableHead>
          <TableHead>New Value</TableHead>
          <TableHead>Changed By</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map(row => (
          <TableRow key={row.id}>
            <TableCell className="text-xs whitespace-nowrap">
              {row.changed_at ? formatDate(row.changed_at) : '—'}
            </TableCell>
            <TableCell className="text-xs">{row.table_name ?? '—'}</TableCell>
            <TableCell className="text-xs">{row.field_name ?? '—'}</TableCell>
            <TableCell className="text-xs max-w-[120px] truncate">{row.old_value ?? '—'}</TableCell>
            <TableCell className="text-xs max-w-[120px] truncate">{row.new_value ?? '—'}</TableCell>
            <TableCell className="text-xs">{row.changed_by ?? '—'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ReviewWorkstationPage() {
  const { id: engagementId } = useParams<{ id: string }>()

  const { data: engagement, isLoading: engagementLoading } = useQuery<Engagement>({
    queryKey: ['engagement', engagementId],
    queryFn: () => api.get(`/api/engagements/${engagementId}`).then(r => r.data),
    enabled: !!engagementId,
  })

  const { data: allCategories = [] } = useQuery<CategoryRow[]>({
    queryKey: ['cube-categories', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/cube/categories`).then(r => r.data),
    enabled: !!engagementId,
  })

  if (!engagementLoading && engagement !== undefined && !engagement.is_admin) {
    return <Navigate to="../overview" replace />
  }

  if (engagementLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded bg-amber-100 text-amber-800 text-xs font-medium mb-3">
          Internal use only — not for client viewing
        </div>
        <h1 className="text-xl font-semibold">Review Workstation</h1>
      </div>

      <Tabs defaultValue="supplier-queue">
        <TabsList>
          <TabsTrigger value="supplier-queue">Supplier Queue</TabsTrigger>
          <TabsTrigger value="category-queue">Category Queue</TabsTrigger>
          <TabsTrigger value="override-rules">Override Rules</TabsTrigger>
          <TabsTrigger value="audit-log">Audit Log</TabsTrigger>
        </TabsList>

        <TabsContent value="supplier-queue">
          <SupplierQueueTab engagementId={engagementId!} />
        </TabsContent>

        <TabsContent value="category-queue">
          <CategoryQueueTab engagementId={engagementId!} allCategories={allCategories} />
        </TabsContent>

        <TabsContent value="override-rules">
          <OverrideRulesTab engagementId={engagementId!} allCategories={allCategories} />
        </TabsContent>

        <TabsContent value="audit-log">
          <AuditLogTab engagementId={engagementId!} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
