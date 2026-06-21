"use client"
import { useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { FlaskConical } from "lucide-react"
import { MessageInput } from "@/components/chat/MessageInput"
import { useCreateConversation } from "@/hooks/useConversations"
import { conversationsApi } from "@/lib/api"

const EXAMPLE_PROMPTS = [
  "Run DE analysis comparing treatment vs control on my bulk RNA-seq samples",
  "Run QC on all samples in project XYZ",
  "Show me the top pathways from the last completed run",
]

export default function ChatPage() {
  const [inputValue, setInputValue] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const router = useRouter()
  const createConversation = useCreateConversation()

  const handleSubmit = useCallback(
    async (content: string) => {
      setIsSubmitting(true)
      try {
        const conv = await createConversation.mutateAsync(undefined)
        await conversationsApi.sendMessage(conv.id, content)
        router.push(`/chat/${conv.id}`)
      } finally {
        setIsSubmitting(false)
      }
    },
    [createConversation, router]
  )

  return (
    <div className="flex h-full flex-col">
      {/* Centered blank state */}
      <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
        <div className="flex flex-col items-center gap-2 text-center">
          <FlaskConical className="h-10 w-10 text-primary" />
          <h1 className="text-2xl font-semibold">RNA-seq Analysis Agent</h1>
          <p className="text-sm text-muted-foreground max-w-xs">
            Describe your analysis in plain English. The agent will build and
            run the pipeline for you.
          </p>
        </div>

        {/* Example prompts */}
        <div className="flex w-full max-w-xl flex-col gap-3">
          {EXAMPLE_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => setInputValue(prompt)}
              className="rounded-xl border bg-card px-4 py-3 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Message input */}
      <div className="w-full max-w-2xl mx-auto px-4 pb-4">
        <MessageInput
          value={inputValue}
          onChange={setInputValue}
          onSubmit={handleSubmit}
          disabled={isSubmitting}
          placeholder="Start a new conversation…"
        />
      </div>
    </div>
  )
}
