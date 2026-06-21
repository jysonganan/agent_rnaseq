"use client"
import { useState, useCallback } from "react"
import { useConversationMessages, useSendMessage } from "@/hooks/useConversations"
import { ConversationThread } from "./ConversationThread"
import { MessageInput } from "./MessageInput"
import type { ChatMessage } from "@/lib/types"

interface Props {
  conversationId: string
}

export function ConversationPageClient({ conversationId }: Props) {
  const [inputValue, setInputValue] = useState("")
  const [optimisticMsg, setOptimisticMsg] = useState<ChatMessage | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)

  const { data } = useConversationMessages(conversationId)
  const sendMessage = useSendMessage(conversationId)

  // Merge server messages with any pending optimistic message.
  // Remove optimistic once the server's list already contains a matching user turn.
  const serverMessages = data?.messages ?? []
  const messages: ChatMessage[] =
    optimisticMsg &&
    !serverMessages.some(
      (m) => m.role === "user" && m.content === optimisticMsg.content
    )
      ? [...serverMessages, optimisticMsg]
      : serverMessages

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

      try {
        await sendMessage.mutateAsync(content)
        // WS streaming wired in TASK_FE_06; stop indicator after API ack for now.
      } catch {
        setOptimisticMsg(null)
      } finally {
        setIsStreaming(false)
        // useSendMessage.onSuccess invalidates the messages query; the re-fetch
        // brings the real user turn, which dedupes the optimistic message above.
      }
    },
    [conversationId, sendMessage]
  )

  return (
    <div className="flex h-full flex-col">
      <ConversationThread messages={messages} isStreaming={isStreaming} />
      <MessageInput
        value={inputValue}
        onChange={setInputValue}
        onSubmit={handleSend}
        disabled={isStreaming}
      />
    </div>
  )
}
