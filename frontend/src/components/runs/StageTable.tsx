import type { Stage } from "@/lib/types"
import { StageStatusBadge } from "./StageStatusBadge"

function formatDate(dt: string | null): string {
  if (!dt) return "—"
  return new Date(dt).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

interface Props {
  stages: Stage[]
}

export function StageTable({ stages }: Props) {
  if (stages.length === 0) {
    return <p className="text-sm text-muted-foreground">No stages recorded yet.</p>
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/30">
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Stage</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Tool</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Started</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Completed</th>
          </tr>
        </thead>
        <tbody>
          {stages.map((stage) => (
            <tr key={stage.id} className="border-b last:border-0 hover:bg-muted/20">
              <td className="px-3 py-2 font-mono text-xs">
                {stage.stage_name.replace(/_/g, " ")}
              </td>
              <td className="px-3 py-2 text-muted-foreground">{stage.tool_name}</td>
              <td className="px-3 py-2">
                <StageStatusBadge status={stage.status} />
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {formatDate(stage.started_at)}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {formatDate(stage.completed_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
