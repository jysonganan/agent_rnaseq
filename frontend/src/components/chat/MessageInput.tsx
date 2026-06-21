"use client"
import { useEffect, useRef, type KeyboardEvent } from "react"
import { Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const MAX_CHARS = 4000

interface Props {
  value: string
  onChange: (value: string) => void
  onSubmit: (content: string) => void
  disabled?: boolean
  placeholder?: string
}

export function MessageInput({
  value,
  onChange,
  onSubmit,
  disabled = false,
  placeholder = "Message the agent…",
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea to fit content
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [value])

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="border-t bg-background p-4">
      <div
        className={cn(
          "flex items-end gap-2 rounded-xl border bg-muted/30 px-3 py-2",
          "focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1"
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          rows={1}
          aria-label="Message input"
          className={cn(
            "flex-1 resize-none bg-transparent text-sm outline-none",
            "placeholder:text-muted-foreground",
            "min-h-[24px] overflow-y-auto",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        />
        <Button
          size="icon"
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          aria-label="Send message"
          className="h-8 w-8 shrink-0"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
      {value.length > MAX_CHARS * 0.9 && (
        <p className="mt-1 text-right text-xs text-muted-foreground">
          {value.length} / {MAX_CHARS}
        </p>
      )}
    </div>
  )
}
