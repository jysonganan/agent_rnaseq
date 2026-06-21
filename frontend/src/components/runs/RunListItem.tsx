import Link from "next/link"
import { RunStatusBadge } from "./RunStatusBadge"
import type { Run } from "@/lib/types"

function formatDate(dt: string | null): string {
  if (!dt) return "in progress"
  return new Date(dt).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

interface Props {
  run: Run
}

export function RunListItem({ run }: Props) {
  return (
    <Link
      href={`/runs/${run.id}`}
      className="block rounded-lg border bg-card p-4 transition-colors hover:bg-muted/40"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{run.name}</span>
        <div className="flex items-center gap-2">
          <RunStatusBadge status={run.status} />
          <span className="text-xs text-muted-foreground">
            {run.pipeline_type.replace(/_/g, " ")}
          </span>
        </div>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
        <span>Created {formatDate(run.created_at)}</span>
        <span>·</span>
        <span>
          {run.status === "completed" ? "Completed" : "Ended"} {formatDate(run.completed_at)}
        </span>
      </div>
    </Link>
  )
}
