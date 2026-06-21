import type { ChatMessage } from "@/lib/types"
import { UserMessage } from "./UserMessage"
import { AgentMessage } from "./AgentMessage"

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

  // tool role — ToolCallCard implemented in TASK_FE_06
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-lg border bg-muted/50 px-3 py-2 text-xs font-mono text-muted-foreground">
        <span className="font-semibold">{message.tool_name ?? "tool"}</span>
        {message.tool_status && (
          <span className="ml-2 capitalize">[{message.tool_status}]</span>
        )}
        {message.content && (
          <p className="mt-1 truncate opacity-70">{message.content}</p>
        )}
      </div>
    </div>
  )
}
