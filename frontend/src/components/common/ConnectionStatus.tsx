import { WifiOff, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { WsStatus } from "@/lib/types"

interface Props {
  status: WsStatus
  onReconnect?: () => void
}

export function ConnectionStatus({ status, onReconnect }: Props) {
  if (status === "connected") return null

  return (
    <div
      className={
        status === "connecting"
          ? "flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
          : "flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive"
      }
      role="status"
    >
      {status === "connecting" && (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>Connecting to agent stream…</span>
        </>
      )}
      {status === "error" && (
        <>
          <WifiOff className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1">Connection lost. Live updates paused.</span>
          {onReconnect && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onReconnect}
              className="h-5 px-2 text-xs"
            >
              Reconnect
            </Button>
          )}
        </>
      )}
    </div>
  )
}
