"use client"
import { useEffect, useRef, useState, useCallback } from "react"
import { WsManager, toWsBase } from "@/lib/websocket"
import { getApiKey } from "@/lib/api"
import type {
  WsStatus,
  WsFrame,
  TokenPayload,
  ToolCallPayload,
  StageUpdatePayload,
  DonePayload,
  WsErrorPayload,
} from "@/lib/types"

interface ConversationStreamCallbacks {
  onToken?: (messageId: string, token: string) => void
  onToolCall?: (payload: ToolCallPayload) => void
  onStageUpdate?: (payload: StageUpdatePayload) => void
  onDone?: (payload: DonePayload) => void
  onError?: (payload: WsErrorPayload) => void
}

interface UseConversationStreamResult {
  status: WsStatus
  reconnect: () => void
}

export function useConversationStream(
  conversationId: string | null,
  callbacks?: ConversationStreamCallbacks
): UseConversationStreamResult {
  const [status, setStatus] = useState<WsStatus>("connecting")
  const managerRef = useRef<WsManager | null>(null)

  // Keep callbacks in a ref so the effect closure doesn't go stale
  const callbacksRef = useRef(callbacks)
  useEffect(() => {
    callbacksRef.current = callbacks
  }, [callbacks])

  useEffect(() => {
    // Don't connect for null or static-export placeholder IDs
    if (!conversationId || conversationId === "_") {
      setStatus("connected")  // neutral state — no WS needed
      return
    }

    const apiKey = getApiKey()
    if (!apiKey) return

    const wsBase = toWsBase(
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
    )
    // API key is in the URL per safety_policy 11.5 (WS-only exception, WSS in prod)
    const url = `${wsBase}/ws/conversations/${conversationId}/stream?api_key=${apiKey}`

    const manager = new WsManager({
      url,
      onStatusChange: setStatus,
      onMessage: (raw) => {
        const frame = raw as unknown as WsFrame
        const cb = callbacksRef.current
        switch (frame.type) {
          case "token":
            cb?.onToken?.(
              (frame.payload as TokenPayload).message_id,
              (frame.payload as TokenPayload).token
            )
            break
          case "tool_call":
            cb?.onToolCall?.(frame.payload as ToolCallPayload)
            break
          case "stage_update":
            cb?.onStageUpdate?.(frame.payload as StageUpdatePayload)
            break
          case "done":
            cb?.onDone?.(frame.payload as DonePayload)
            break
          case "error":
            cb?.onError?.(frame.payload as WsErrorPayload)
            break
        }
      },
    })

    managerRef.current = manager
    return () => {
      manager.destroy()
      managerRef.current = null
    }
  }, [conversationId])

  const reconnect = useCallback(() => {
    managerRef.current?.reconnect()
  }, [])

  return { status, reconnect }
}
