// Server component — exports generateStaticParams without "use client".
// All interactive state lives in ConversationPageClient.
import { ConversationPageClient } from "@/components/chat/ConversationPageClient"

// Static export requires ≥1 param; real IDs are resolved client-side at runtime.
export const generateStaticParams = async () => [{ conversation_id: "_" }]

export default function ConversationPage({
  params: { conversation_id },
}: {
  params: { conversation_id: string }
}) {
  return <ConversationPageClient conversationId={conversation_id} />
}
