import { useQuery } from '@tanstack/react-query'

import { getResolution } from '../api/resolutions'

const TERMINAL = ['completed', 'failed', 'cancelled', 'partial']

export function usePolling(resolutionId, { enabled = true, interval = 2000 } = {}) {
  return useQuery({
    queryKey: ['resolution', resolutionId],
    queryFn: () => getResolution(resolutionId),
    enabled: enabled && !!resolutionId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && TERMINAL.includes(status) ? false : interval
    },
  })
}
