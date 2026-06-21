import type { StageStatus } from "@/lib/types"

interface Props {
  status: StageStatus
}

const CONFIG: Record<StageStatus, { label: string; className: string; pulse?: boolean }> = {
  pending: {
    label: "pending",
    className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  },
  running: {
    label: "running",
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
    pulse: true,
  },
  completed: {
    label: "completed",
    className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  },
  failed: {
    label: "failed",
    className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  skipped: {
    label: "skipped",
    className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
}

export function StageStatusBadge({ status }: Props) {
  const cfg = CONFIG[status] ?? CONFIG.pending
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${cfg.className}`}
    >
      {cfg.pulse && (
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" />
        </span>
      )}
      {cfg.label}
    </span>
  )
}
