"use client"
import { useEffect, useRef, useState, useCallback } from "react"
import { WsManager, toWsBase } from "@/lib/websocket"
import { getApiKey } from "@/lib/api"
import type { WsStatus, RunLogFrame } from "@/lib/types"

interface UseRunLogStreamResult {
  status: WsStatus
  logs: RunLogFrame[]
  reconnect: () => void
}

export function useRunLogStream(runId: string | null): UseRunLogStreamResult {
  const [status, setStatus] = useState<WsStatus>("connecting")
  const [logs, setLogs] = useState<RunLogFrame[]>([])
  const managerRef = useRef<WsManager | null>(null)

  useEffect(() => {
    if (!runId || runId === "_") {
      setStatus("connected")
      return
    }

    const apiKey = getApiKey()
    if (!apiKey) return

    const wsBase = toWsBase(
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
    )
    const url = `${wsBase}/ws/runs/${runId}/logs?api_key=${apiKey}`

    const manager = new WsManager({
      url,
      onStatusChange: setStatus,
      onMessage: (raw) => {
        setLogs((prev) => [...prev, raw as unknown as RunLogFrame])
      },
    })

    managerRef.current = manager
    return () => {
      manager.destroy()
      managerRef.current = null
    }
  }, [runId])

  const reconnect = useCallback(() => {
    managerRef.current?.reconnect()
  }, [])

  return { status, logs, reconnect }
}
