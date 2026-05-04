import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { RecommendationConfig } from '@/types'

export default function useRecommendationConfig(engagementId: string | undefined) {
  const queryClient = useQueryClient()

  const { data: config, isLoading } = useQuery<RecommendationConfig>({
    queryKey: ['rec-config', engagementId],
    queryFn: () =>
      api.get(`/api/engagements/${engagementId}/recommendations/config`).then(r => r.data),
    enabled: !!engagementId,
    retry: false,
  })

  const { mutateAsync: patchConfig, isPending: isSaving } = useMutation({
    mutationFn: (updates: Partial<RecommendationConfig>) =>
      api.patch(`/api/engagements/${engagementId}/recommendations/config`, updates).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rec-config', engagementId] }),
  })

  const saveConfig = async (updates: Partial<RecommendationConfig>) => {
    await patchConfig(updates)
  }

  return { config, isLoading, saveConfig, isSaving }
}
