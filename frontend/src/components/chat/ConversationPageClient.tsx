"use client"
import { useState, useCallback, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useConversationMessages, useSendMessage, conversationKeys } from "@/hooks/useConversations"
import { useConversationStream } from "@/hooks/useConversationStream"
import { ConversationThread } from "./ConversationThread"
import { MessageInput } from "./MessageInput"
import type {
  ChatMessage,
  ToolCallPayload,
  StageUpdatePayload,
  DonePayload,
  WsErrorPayload,
} from "@/lib/types"

interface Props {
  conversationId: string
}

export function ConversationPageClient({ conversationId }: Props) {
  const qc = useQueryClient()
  const [inputValue, setInputValue] = useState("")
  const [optimisticMsg, setOptimisticMsg] = useState<ChatMessage | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)

  // Real-time streaming state
  const streamingContentRef = useRef("")
  const [streamingContent, setStreamingContent] = useState("")
  const [toolCalls, setToolCalls] = useState<ToolCallPayload[]>([])
  const [currentStage, setCurrentStage] = useState<StageUpdatePayload | null>(null)

  const { data } = useConversationMessages(conversationId)
  const sendMessage = useSendMessage(conversationId)

  // Merge server messages with any pending optimistic message
  const serverMessages = data?.messages ?? []
  const messages: ChatMessage[] =
    optimisticMsg &&
    !serverMessages.some(
      (m) => m.role === "user" && m.content === optimisticMsg.content
    )
      ? [...serverMessages, optimisticMsg]
      : serverMessages

  // Stable callbacks for the WS hook (via useCallback; refs in the hook avoid stale closures)
  const handleToken = useCallback((_messageId: string, token: string) => {
    setIsStreaming(true)
    streamingContentRef.current += token
    setStreamingContent(streamingContentRef.current)
  }, [])

  const handleToolCall = useCallback((payload: ToolCallPayload) => {
    setToolCalls((prev) => {
      const key = `${payload.message_id}-${payload.tool_name}`
      const existing = prev.findIndex(
        (tc) => `${tc.message_id}-${tc.tool_name}` === key
      )
      if (existing >= 0) {
        const next = [...prev]
        next[existing] = payload
        return next
      }
      return [...prev, payload]
    })
  }, [])

  const handleStageUpdate = useCallback((payload: StageUpdatePayload) => {
    setCurrentStage(payload)
  }, [])

  const handleDone = useCallback(
    (_payload: DonePayload) => {
      setIsStreaming(false)
      setOptimisticMsg(null)
      streamingContentRef.current = ""
      setStreamingContent("")
      setToolCalls([])
      setCurrentStage(null)
      // Re-fetch settled messages so the agent response appears in the thread
      qc.invalidateQueries({ queryKey: conversationKeys.messages(conversationId) })
    },
    [conversationId, qc]
  )

  const handleWsError = useCallback((_payload: WsErrorPayload) => {
    setIsStreaming(false)
  }, [])

  const { status: wsStatus, reconnect } = useConversationStream(conversationId, {
    onToken: handleToken,
    onToolCall: handleToolCall,
    onStageUpdate: handleStageUpdate,
    onDone: handleDone,
    onError: handleWsError,
  })

  const handleSend = useCallback(
    async (content: string) => {
      const temp: ChatMessage = {
        id: `optimistic-${Date.now()}`,
        conversation_id: conversationId,
        role: "user",
        content,
        run_id: null,
        tool_name: null,
        tool_status: null,
        created_at: new Date().toISOString(),
      }
      setOptimisticMsg(temp)
      setInputValue("")
      setIsStreaming(true)
      // Reset streaming content for the new turn
      streamingContentRef.current = ""
      setStreamingContent("")
      setToolCalls([])
      setCurrentStage(null)

      try {
        await sendMessage.mutateAsync(content)
        // isStreaming stays true until the WS done frame arrives
      } catch {
        setOptimisticMsg(null)
        setIsStreaming(false)
      }
    },
    [conversationId, sendMessage]
  )

  return (
    <div className="flex h-full flex-col">
      <ConversationThread
        messages={messages}
        isStreaming={isStreaming}
        streamingContent={streamingContent}
        toolCalls={toolCalls}
        currentStage={currentStage}
        wsStatus={wsStatus}
        onReconnect={reconnect}
      />
      <MessageInput
        value={inputValue}
        onChange={setInputValue}
        onSubmit={handleSend}
        disabled={isStreaming}
      />
    </div>
  )
}
