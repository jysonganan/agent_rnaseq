import { CheckCircle2, Clock, Loader2, Ban, AlertCircle } from "lucide-react"
import type { RunStatus } from "@/lib/types"

interface Config {
  label: string
  className: string
  icon: React.ReactNode
}

function config(status: RunStatus): Config {
  switch (status) {
    case "pending":
      return {
        label: "Pending",
        className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
        icon: <Clock className="h-3 w-3" />,
      }
    case "running":
      return {
        label: "Running",
        className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
        icon: <Loader2 className="h-3 w-3 animate-spin" />,
      }
    case "completed":
      return {
        label: "Completed",
        className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        icon: <CheckCircle2 className="h-3 w-3" />,
      }
    case "failed":
      return {
        label: "Failed",
        className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
        icon: <AlertCircle className="h-3 w-3" />,
      }
    case "cancelled":
      return {
        label: "Cancelled",
        className: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
        icon: <Ban className="h-3 w-3" />,
      }
  }
}

interface Props {
  status: RunStatus
}

export function RunStatusBadge({ status }: Props) {
  const { label, className, icon } = config(status)
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}
    >
      {icon}
      {label}
    </span>
  )
}
