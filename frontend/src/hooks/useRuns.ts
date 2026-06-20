import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { runsApi } from "@/lib/api"
import type { RunStatus } from "@/lib/types"

const TERMINAL_STATUSES: RunStatus[] = ["completed", "failed", "cancelled"]

interface RunListParams {
  status?: RunStatus
  conversation_id?: string
  limit?: number
  offset?: number
}

export const runKeys = {
  all: () => ["runs"] as const,
  list: (params?: RunListParams) => ["runs", "list", params] as const,
  detail: (id: string) => ["runs", id] as const,
}

export function useRuns(params?: RunListParams) {
  return useQuery({
    queryKey: runKeys.list(params),
    queryFn: () => runsApi.list(params),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 5_000
      const hasActive = data.runs.some(
        (r) => !TERMINAL_STATUSES.includes(r.status)
      )
      return hasActive ? 5_000 : false
    },
  })
}

export function useRun(id: string) {
  return useQuery({
    queryKey: runKeys.detail(id),
    queryFn: () => runsApi.get(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status || TERMINAL_STATUSES.includes(status)) return false
      return 3_000
    },
  })
}

export function useCancelRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => runsApi.cancel(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: runKeys.detail(id) })
      qc.invalidateQueries({ queryKey: runKeys.all() })
    },
  })
}
