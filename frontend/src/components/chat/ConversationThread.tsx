"use client"
import { useEffect, useRef } from "react"
import type { ChatMessage, ToolCallPayload, StageUpdatePayload, WsStatus } from "@/lib/types"
import { MessageBubble } from "./MessageBubble"
import { ThinkingIndicator } from "./ThinkingIndicator"
import { AgentMessage } from "./AgentMessage"
import { ToolCallCard } from "./ToolCallCard"
import { StageProgressIndicator } from "./StageProgressIndicator"
import { ConnectionStatus } from "@/components/common/ConnectionStatus"

interface Props {
  messages: ChatMessage[]
  isStreaming?: boolean
  // Real-time streaming state from useConversationStream
  streamingContent?: string
  toolCalls?: ToolCallPayload[]
  currentStage?: StageUpdatePayload | null
  wsStatus?: WsStatus
  onReconnect?: () => void
}

export function ConversationThread({
  messages,
  isStreaming = false,
  streamingContent = "",
  toolCalls = [],
  currentStage = null,
  wsStatus,
  onReconnect,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isStreaming, streamingContent, toolCalls])

  const hasStreamingContent =
    isStreaming && (streamingContent || toolCalls.length > 0 || currentStage)

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {/* Connection status banner */}
      {wsStatus && wsStatus !== "connected" && (
        <ConnectionStatus status={wsStatus} onReconnect={onReconnect} />
      )}

      {messages.length === 0 && !isStreaming && (
        <p className="pt-8 text-center text-sm text-muted-foreground">
          No messages yet.
        </p>
      )}

      {/* Settled messages */}
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {/* Live streaming section */}
      {hasStreamingContent && (
        <>
          {/* Active tool calls from stream */}
          {toolCalls.map((tc) => (
            <ToolCallCard
              key={`${tc.message_id}-${tc.tool_name}`}
              toolName={tc.tool_name}
              status={
                tc.status === "completed"
                  ? "completed"
                  : tc.status === "failed"
                    ? "failed"
                    : "running"
              }
              summary={tc.summary}
            />
          ))}

          {/* Current pipeline stage */}
          {currentStage && (
            <StageProgressIndicator
              stageName={currentStage.stage_name}
              status={currentStage.status}
            />
          )}

          {/* Streaming agent response */}
          {streamingContent ? (
            <AgentMessage content={streamingContent} />
          ) : (
            <ThinkingIndicator />
          )}
        </>
      )}

      {/* Thinking indicator when streaming but no content yet */}
      {isStreaming && !hasStreamingContent && <ThinkingIndicator />}

      <div ref={bottomRef} aria-hidden="true" />
    </div>
  )
}
