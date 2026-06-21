import type { ChatMessage } from "@/lib/types"
import { UserMessage } from "./UserMessage"
import { AgentMessage } from "./AgentMessage"
import { ToolCallCard } from "./ToolCallCard"

interface Props {
  message: ChatMessage
}

export function MessageBubble({ message }: Props) {
  if (message.role === "user") {
    return <UserMessage content={message.content} />
  }

  if (message.role === "assistant") {
    return <AgentMessage content={message.content} />
  }

  // tool role — render as ToolCallCard
  const status =
    message.tool_status === "completed"
      ? "completed"
      : message.tool_status === "failed"
        ? "failed"
        : "running"

  return (
    <ToolCallCard
      toolName={message.tool_name ?? "tool"}
      status={status}
      summary={message.content || null}
    />
  )
}
