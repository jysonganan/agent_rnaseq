// Stub — conversation thread implemented in TASK_FE_05
// Static export requires at least one param; real IDs come from the API at runtime.
export const generateStaticParams = async () => [{ conversation_id: "_" }]

interface Props {
  params: { conversation_id: string }
}

export default function ConversationPage({ params }: Props) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="text-center space-y-2">
        <h1 className="text-xl font-semibold">Conversation</h1>
        <p className="text-sm text-muted-foreground font-mono">{params.conversation_id}</p>
        <p className="text-xs text-muted-foreground">
          Chat thread — implemented in TASK_FE_05
        </p>
      </div>
    </div>
  )
}
