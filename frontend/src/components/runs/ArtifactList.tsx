import type { Artifact } from "@/lib/types"
import { ArtifactDownloadLink } from "./ArtifactDownloadLink"

function formatBytes(bytes: number | null): string {
  if (bytes === null) return ""
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

interface Props {
  runId: string
  artifacts: Artifact[]
}

export function ArtifactList({ runId, artifacts }: Props) {
  if (artifacts.length === 0) {
    return <p className="text-sm text-muted-foreground">No artifacts yet.</p>
  }

  const grouped = artifacts.reduce<Record<string, Artifact[]>>((acc, a) => {
    ;(acc[a.artifact_type] ??= []).push(a)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {Object.entries(grouped).map(([type, items]) => (
        <div key={type}>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {type.replace(/_/g, " ")}
          </h4>
          <ul className="space-y-1.5">
            {items.map((artifact) => {
              const fileName = artifact.path.split("/").pop() ?? artifact.id
              return (
                <li
                  key={artifact.id}
                  className="flex items-center justify-between gap-3 rounded-md border bg-muted/20 px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs">{fileName}</p>
                    {artifact.file_size_bytes !== null && (
                      <p className="text-xs text-muted-foreground">
                        {formatBytes(artifact.file_size_bytes)}
                      </p>
                    )}
                  </div>
                  <ArtifactDownloadLink runId={runId} artifactId={artifact.id} />
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}
