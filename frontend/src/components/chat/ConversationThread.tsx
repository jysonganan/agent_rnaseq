"use client"
import { useEffect, useRef } from "react"
import type { ChatMessage } from "@/lib/types"
import { MessageBubble } from "./MessageBubble"
import { ThinkingIndicator } from "./ThinkingIndicator"

interface Props {
  messages: ChatMessage[]
  isStreaming?: boolean
}

export function ConversationThread({ messages, isStreaming = false }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isStreaming])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.length === 0 && !isStreaming && (
        <p className="text-center text-sm text-muted-foreground pt-8">
          No messages yet.
        </p>
      )}
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      {isStreaming && <ThinkingIndicator />}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  )
}
