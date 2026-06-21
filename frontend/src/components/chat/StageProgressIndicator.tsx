import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react"

interface Props {
  stageName: string
  status: string
}

export function StageProgressIndicator({ stageName, status }: Props) {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-2 rounded-full border bg-muted/30 px-3 py-1 text-xs">
        {status === "running" && (
          <Loader2 className="h-3 w-3 animate-spin text-primary" />
        )}
        {status === "completed" && (
          <CheckCircle2 className="h-3 w-3 text-green-500" />
        )}
        {status === "failed" && (
          <XCircle className="h-3 w-3 text-destructive" />
        )}
        {status === "pending" && (
          <Clock className="h-3 w-3 text-muted-foreground" />
        )}
        <span className="capitalize">{stageName.replace(/_/g, " ")}</span>
        <span className="text-muted-foreground">{status}</span>
      </div>
    </div>
  )
}
