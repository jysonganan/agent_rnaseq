import type { RunStatus } from "@/lib/types"

const STATUS_OPTIONS: { value: RunStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
]

interface Props {
  status: RunStatus | "all"
  onStatusChange: (status: RunStatus | "all") => void
}

export function RunFilters({ status, onStatusChange }: Props) {
  return (
    <div className="flex items-center gap-3">
      <label htmlFor="run-status-filter" className="text-sm font-medium text-muted-foreground">
        Status
      </label>
      <select
        id="run-status-filter"
        value={status}
        onChange={(e) => onStatusChange(e.target.value as RunStatus | "all")}
        className="rounded-md border bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  )
}
