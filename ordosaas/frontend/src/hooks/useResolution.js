import { useQuery } from '@tanstack/react-query'

import { getGantt } from '../api/resolutions'
import { usePolling } from './usePolling'

export function useResolution(resolutionId) {
  const { data: resolution, isLoading } = usePolling(resolutionId)
  const status = resolution?.status
  const isCompleted = ['completed', 'partial'].includes(status)
  const isRunning = ['pending', 'running'].includes(status)

  const { data: ganttData } = useQuery({
    queryKey: ['gantt', resolutionId],
    queryFn: () => getGantt(resolutionId, { include_setups: true, include_windows: true }),
    enabled: isCompleted,
  })

  return {
    resolution,
    ganttData,
    isLoading,
    isRunning,
    isCompleted,
    progress: resolution?.progress_pct || 0,
  }
}
