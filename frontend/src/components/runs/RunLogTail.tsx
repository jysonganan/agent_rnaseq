"use client"

import { useEffect, useRef } from "react"
import { useRunLogStream } from "@/hooks/useRunLogStream"
import type { RunLogFrame } from "@/lib/types"

const MAX_LINES = 20

const LEVEL_CLASS: Record<RunLogFrame["level"], string> = {
  info:    "text-foreground",
  debug:   "text-muted-foreground",
  warning: "text-yellow-600 dark:text-yellow-400",
  error:   "text-destructive",
}

interface Props {
  runId: string
}

export function RunLogTail({ runId }: Props) {
  const { logs } = useRunLogStream(runId)
  const bottomRef = useRef<HTMLDivElement>(null)
  const visible = logs.slice(-MAX_LINES)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [visible.length])

  return (
    <div className="max-h-60 overflow-y-auto rounded-md border bg-muted/10 p-3 font-mono text-xs">
      {visible.length === 0 ? (
        <p className="text-muted-foreground">Waiting for log output…</p>
      ) : (
        visible.map((log, idx) => (
          <div key={idx} className="flex gap-2 leading-relaxed">
            <span className="shrink-0 text-muted-foreground">
              {new Date(log.ts).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            <span className="w-16 shrink-0 uppercase text-muted-foreground">{log.level}</span>
            <span className="w-20 shrink-0 truncate text-muted-foreground">{log.stage}</span>
            <span className={LEVEL_CLASS[log.level]}>{log.message}</span>
          </div>
        ))
      )}
      <div ref={bottomRef} />
    </div>
  )
}
