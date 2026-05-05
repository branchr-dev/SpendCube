import { useState, useRef, useCallback } from 'react'
import type { AxiosProgressEvent } from 'axios'
import { api } from '@/lib/api'
import type { PipelineJob } from '@/types'

interface FileInfo {
  name: string
  size: number
  rowCountEstimate: number
}

interface IngestionState {
  step: 1 | 2 | 3
  jobId: string | null
  filePath: string | null
  columns: string[]
  fileInfo: FileInfo | null
  columnMapping: Record<string, string>
  jobStatus: PipelineJob | null
  uploading: boolean
  uploadProgress: number
  uploadError: string | null
  pollError: string | null
}

const INITIAL_STATE: IngestionState = {
  step: 1,
  jobId: null,
  filePath: null,
  columns: [],
  fileInfo: null,
  columnMapping: {},
  jobStatus: null,
  uploading: false,
  uploadProgress: 0,
  uploadError: null,
  pollError: null,
}

export function useIngestion(engagementId: string) {
  const [state, setState] = useState<IngestionState>(INITIAL_STATE)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const latestStateRef = useRef(state)
  latestStateRef.current = state

  const uploadFile = useCallback(async (file: File) => {
    setState(s => ({ ...s, uploading: true, uploadProgress: 0, uploadError: null }))
    const formData = new FormData()
    formData.append('file', file)
    try {
      const { data } = await api.post(
        `/api/engagements/${engagementId}/ingest/upload`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (e: AxiosProgressEvent) => {
            if (e.total) {
              setState(s => ({
                ...s,
                uploadProgress: Math.round((e.loaded / e.total!) * 100),
              }))
            }
          },
        }
      )
      setState(s => ({
        ...s,
        uploading: false,
        uploadProgress: 100,
        jobId: data.job_id,
        filePath: data.file_path,
        columns: data.columns ?? [],
        fileInfo: {
          name: file.name,
          size: file.size,
          rowCountEstimate: data.row_count_estimate ?? 0,
        },
      }))
    } catch (err: unknown) {
      setState(s => ({
        ...s,
        uploading: false,
        uploadProgress: 0,
        uploadError:
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          'Upload failed',
      }))
      throw err
    }
  }, [engagementId])

  const runPipeline = useCallback(async (mapping: Record<string, string>) => {
    const { jobId, filePath } = latestStateRef.current
    setState(s => ({ ...s, columnMapping: mapping }))
    // POST first — only advance to step 3 after the job is confirmed queued
    await api.post(`/api/engagements/${engagementId}/ingest/run`, {
      job_id: jobId,
      file_path: filePath,
      column_mapping: mapping,
    })
    setState(s => ({ ...s, step: 3 }))
  }, [engagementId])

  const startPolling = useCallback((jobId: string) => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    let consecutiveErrors = 0

    const poll = async () => {
      try {
        const { data } = await api.get(
          `/api/engagements/${engagementId}/ingest/status/${jobId}`
        )
        consecutiveErrors = 0
        setState(s => ({ ...s, jobStatus: data, pollError: null }))
        if (data.status === 'done' || data.status === 'failed') {
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
        }
      } catch {
        consecutiveErrors++
        if (consecutiveErrors >= 4) {
          setState(s => ({
            ...s,
            pollError: 'Cannot reach the server — the pipeline may still be running.',
          }))
        }
      }
    }

    // Immediate first poll, then every 3 s
    poll()
    intervalRef.current = setInterval(poll, 3000)
  }, [engagementId])

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const setStep = useCallback((step: 1 | 2 | 3) => {
    setState(s => ({ ...s, step }))
  }, [])

  const reset = useCallback(() => {
    stopPolling()
    setState(INITIAL_STATE)
  }, [stopPolling])

  return {
    ...state,
    uploadFile,
    runPipeline,
    startPolling,
    stopPolling,
    setStep,
    reset,
  }
}
