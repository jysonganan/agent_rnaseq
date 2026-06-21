"use client"
import { useState } from "react"
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"

interface Props {
  toolName: string
  status: "running" | "completed" | "failed"
  summary: string | null
}

export function ToolCallCard({ toolName, status, summary }: Props) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] space-y-1.5 rounded-lg border bg-muted/30 px-3 py-2.5 text-xs">
        {/* Header row: icon + tool name + status */}
        <div className="flex items-center gap-2">
          {status === "running" && (
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
          )}
          {status === "completed" && (
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green-500" />
          )}
          {status === "failed" && (
            <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
          )}
          <code className="font-mono font-semibold">{toolName}</code>
          <span
            className={cn(
              "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
              status === "running" && "bg-primary/10 text-primary",
              status === "completed" && "bg-green-500/10 text-green-600",
              status === "failed" && "bg-destructive/10 text-destructive"
            )}
          >
            {status}
          </span>
        </div>

        {/* Collapsible output summary */}
        {summary && (
          <div>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
              aria-expanded={expanded}
            >
              {expanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              <span>{expanded ? "Hide" : "Show"} output</span>
            </button>
            {expanded && (
              <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap rounded bg-muted p-2 text-[10px]">
                {summary}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
