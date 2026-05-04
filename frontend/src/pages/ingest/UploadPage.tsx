import { useEffect, useCallback, useRef, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useParams, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Loader2, CheckCircle2, XCircle, Circle } from 'lucide-react'
import { useIngestion } from '@/hooks/useIngestion'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { PipelineJob } from '@/types'

const CANONICAL_FIELDS = [
  { key: 'supplier_name', label: 'Supplier Name', keyword: 'supplier' },
  { key: 'supplier_id', label: 'Supplier ID', keyword: 'supplier_id' },
  { key: 'invoice_number', label: 'Invoice Number', keyword: 'invoice' },
  { key: 'invoice_date', label: 'Invoice Date', keyword: 'date' },
  { key: 'amount', label: 'Amount', keyword: 'amount' },
  { key: 'currency', label: 'Currency', keyword: 'currency' },
  { key: 'gl_code', label: 'GL Code', keyword: 'gl' },
  { key: 'cost_centre', label: 'Cost Centre', keyword: 'cost' },
]

const PIPELINE_STAGES = [
  { key: 'ingesting', label: 'Ingesting Data' },
  { key: 'harmonising', label: 'Harmonising Suppliers' },
  { key: 'categorising', label: 'Categorising Spend' },
  { key: 'building_cube', label: 'Building Analytics Cube' },
  { key: 'recommendations', label: 'Generating Recommendations' },
]

type StageStatus = 'pending' | 'active' | 'done' | 'failed'

function getStageStatus(stageKey: string, jobStatus: PipelineJob | null): StageStatus {
  if (!jobStatus || jobStatus.status === 'queued') return 'pending'
  if (jobStatus.stage === 'promoting') {
    return stageKey === 'ingesting' ? 'done' : stageKey === 'harmonising' ? 'active' : 'pending'
  }
  const currentIdx = PIPELINE_STAGES.findIndex(s => s.key === jobStatus.stage)
  const thisIdx = PIPELINE_STAGES.findIndex(s => s.key === stageKey)
  if (jobStatus.status === 'done') return 'done'
  if (jobStatus.status === 'failed') {
    if (currentIdx >= 0 && thisIdx < currentIdx) return 'done'
    if (currentIdx >= 0 && thisIdx === currentIdx) return 'failed'
    return thisIdx === 0 ? 'failed' : 'pending'
  }
  // running / promoting (promoting maps to stage after ingesting)
  if (currentIdx < 0) return thisIdx === 0 ? 'active' : 'pending'
  if (thisIdx < currentIdx) return 'done'
  if (thisIdx === currentIdx) return 'active'
  return 'pending'
}

function StageIcon({ status }: { status: StageStatus }) {
  switch (status) {
    case 'active':
      return <Loader2 className="h-5 w-5 animate-spin text-primary" />
    case 'done':
      return <CheckCircle2 className="h-5 w-5 text-green-600" />
    case 'failed':
      return <XCircle className="h-5 w-5 text-destructive" />
    default:
      return <Circle className="h-5 w-5 text-muted-foreground" />
  }
}

const NONE_VALUE = '__none__'

export default function UploadPage() {
  const { id: engagementId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const ingestion = useIngestion(engagementId!)
  const [localMapping, setLocalMapping] = useState<Record<string, string>>({})
  const pollingStartedRef = useRef(false)
  const stopPollingRef = useRef(ingestion.stopPolling)
  stopPollingRef.current = ingestion.stopPolling

  // Auto-map columns when they arrive
  useEffect(() => {
    if (ingestion.columns.length > 0) {
      const auto: Record<string, string> = {}
      for (const field of CANONICAL_FIELDS) {
        const match = ingestion.columns.find(col =>
          col.toLowerCase().includes(field.keyword)
        )
        if (match) auto[field.key] = match
      }
      setLocalMapping(auto)
    }
  }, [ingestion.columns])

  // Start polling when step moves to 3
  useEffect(() => {
    if (ingestion.step === 3 && ingestion.jobId && !pollingStartedRef.current) {
      pollingStartedRef.current = true
      ingestion.startPolling(ingestion.jobId)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ingestion.step, ingestion.jobId])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { stopPollingRef.current() }
  }, [])

  const onDrop = useCallback(async (files: File[]) => {
    const file = files[0]
    if (!file) return
    try {
      await ingestion.uploadFile(file)
    } catch {
      toast.error('Failed to upload file')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ingestion.uploadFile])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    },
    multiple: false,
    disabled: ingestion.uploading || !!ingestion.fileInfo,
  })

  const handleStartProcessing = async () => {
    const filtered = Object.fromEntries(
      Object.entries(localMapping).filter(([, v]) => v && v !== NONE_VALUE)
    )
    try {
      await ingestion.runPipeline(filtered)
    } catch {
      toast.error('Failed to start pipeline')
    }
  }

  const handleTryAgain = () => {
    pollingStartedRef.current = false
    ingestion.reset()
    setLocalMapping({})
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Upload Data</h1>
        <p className="text-muted-foreground mt-1">
          Step {ingestion.step} of 3 —{' '}
          {ingestion.step === 1
            ? 'Upload File'
            : ingestion.step === 2
            ? 'Map Columns'
            : 'Processing'}
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex gap-2 mb-8">
        {[1, 2, 3].map(s => (
          <div
            key={s}
            className={`h-2 flex-1 rounded-full transition-colors ${
              s <= ingestion.step ? 'bg-primary' : 'bg-muted'
            }`}
          />
        ))}
      </div>

      {/* Step 1: Drop zone */}
      {ingestion.step === 1 && (
        <div className="space-y-6">
          <div
            {...getRootProps()}
            className={[
              'border-2 border-dashed rounded-lg p-12 text-center transition-colors',
              ingestion.fileInfo
                ? 'border-green-500 bg-green-50 cursor-default'
                : isDragActive
                ? 'border-primary bg-primary/5 cursor-copy'
                : ingestion.uploading
                ? 'border-muted cursor-not-allowed'
                : 'border-muted hover:border-primary hover:bg-muted/50 cursor-pointer',
            ].join(' ')}
          >
            <input {...getInputProps()} />
            {ingestion.fileInfo ? (
              <div className="space-y-1">
                <p className="font-medium">{ingestion.fileInfo.name}</p>
                <p className="text-sm text-muted-foreground">
                  ~{ingestion.fileInfo.rowCountEstimate.toLocaleString()} rows detected
                </p>
              </div>
            ) : isDragActive ? (
              <p className="text-primary font-medium">Drop the file here</p>
            ) : (
              <div className="space-y-2">
                <p className="font-medium">Drop a CSV or Excel file here</p>
                <p className="text-sm text-muted-foreground">or click to browse</p>
                <p className="text-xs text-muted-foreground">.csv and .xlsx accepted</p>
              </div>
            )}
          </div>

          {ingestion.uploading && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Uploading… {ingestion.uploadProgress}%
              </p>
              <Progress value={ingestion.uploadProgress} className="h-2" />
            </div>
          )}

          {ingestion.uploadError && (
            <p className="text-sm text-destructive">{ingestion.uploadError}</p>
          )}

          <Button
            className="w-full"
            disabled={!ingestion.fileInfo || ingestion.uploading}
            onClick={() => ingestion.setStep(2)}
          >
            Continue
          </Button>
        </div>
      )}

      {/* Step 2: Column mapping */}
      {ingestion.step === 2 && (
        <div className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Map the columns from your file to SpendCube's canonical fields. Unmatched fields will
            be skipped during ingestion.
          </p>
          <div className="rounded-lg border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left p-3 font-medium w-1/2">Canonical Field</th>
                  <th className="text-left p-3 font-medium w-1/2">Source Column</th>
                </tr>
              </thead>
              <tbody>
                {CANONICAL_FIELDS.map(field => (
                  <tr key={field.key} className="border-t">
                    <td className="p-3 font-medium">{field.label}</td>
                    <td className="p-3">
                      <Select
                        value={localMapping[field.key] ?? NONE_VALUE}
                        onValueChange={v =>
                          setLocalMapping(m => ({ ...m, [field.key]: v }))
                        }
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue placeholder="— not mapped —" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NONE_VALUE}>— not mapped —</SelectItem>
                          {ingestion.columns.map(col => (
                            <SelectItem key={col} value={col}>
                              {col}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => ingestion.setStep(1)}>
              Back
            </Button>
            <Button className="flex-1" onClick={handleStartProcessing}>
              Start Processing
            </Button>
          </div>
        </div>
      )}

      {/* Step 3: Pipeline progress */}
      {ingestion.step === 3 && (
        <div className="space-y-6">
          <div className="rounded-lg border p-6 space-y-4">
            {PIPELINE_STAGES.map(stage => {
              const status = getStageStatus(stage.key, ingestion.jobStatus)
              return (
                <div key={stage.key} className="flex items-center gap-3">
                  <StageIcon status={status} />
                  <span
                    className={status === 'pending' ? 'text-muted-foreground' : 'font-medium'}
                  >
                    {stage.label}
                  </span>
                </div>
              )
            })}
          </div>

          {(!ingestion.jobStatus || ingestion.jobStatus.status === 'queued') && (
            <p className="text-sm text-muted-foreground text-center">
              Starting pipeline…
            </p>
          )}

          {ingestion.jobStatus?.status === 'done' && (
            <div className="rounded-lg bg-green-50 border border-green-200 p-4 space-y-3">
              <p className="font-semibold text-green-800">Data processed successfully</p>
              <Button onClick={() => navigate(`/engagements/${engagementId}/overview`)}>
                View Dashboard
              </Button>
            </div>
          )}

          {ingestion.jobStatus?.status === 'failed' && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-4 space-y-3">
              <p className="font-semibold text-red-800">Processing failed</p>
              {ingestion.jobStatus.error_message && (
                <p className="text-sm text-red-700">{ingestion.jobStatus.error_message}</p>
              )}
              <Button variant="outline" onClick={handleTryAgain}>
                Try Again
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
