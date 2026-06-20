import { useQuery } from "@tanstack/react-query"
import { artifactsApi } from "@/lib/api"

const artifactKeys = {
  all: (runId: string) => ["artifacts", runId] as const,
  list: (runId: string, artifactType?: string) =>
    ["artifacts", runId, "list", artifactType] as const,
  download: (runId: string, artifactId: string) =>
    ["artifacts", runId, artifactId, "download"] as const,
}

export function useArtifacts(runId: string, artifactType?: string) {
  return useQuery({
    queryKey: artifactKeys.list(runId, artifactType),
    queryFn: () =>
      artifactsApi.list(runId, artifactType ? { artifact_type: artifactType } : undefined),
    enabled: Boolean(runId),
  })
}

export function useArtifactDownload(runId: string, artifactId: string) {
  return useQuery({
    queryKey: artifactKeys.download(runId, artifactId),
    queryFn: () => artifactsApi.download(runId, artifactId),
    enabled: false,
    staleTime: 30_000,
  })
}
