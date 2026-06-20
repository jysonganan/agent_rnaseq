"use client"

import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useAuth } from "@/hooks/useAuth"
import { validateApiKey } from "@/lib/api"

export function ApiKeyModal() {
  const { setApiKey } = useAuth()
  const [value, setValue] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!value.trim()) return
    setError(null)
    setIsLoading(true)
    try {
      const result = await validateApiKey(value.trim())
      if (result === "valid") {
        setApiKey(value.trim())
      } else if (result === "invalid") {
        setError("Invalid API key. Please try again.")
      } else {
        setError("Cannot reach server. Check the API URL.")
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Dialog
      open
      // Controlled open — onOpenChange is a no-op to keep modal locked
      onOpenChange={() => undefined}
    >
      <DialogContent
        className="sm:max-w-md"
        // Prevent closing by clicking outside or pressing Escape
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
        // Hide the built-in close button via aria-hidden so it can't be
        // activated while the key is unset
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Connect to agent_rnaseq</DialogTitle>
          <DialogDescription>
            Enter your API key to access the RNA-seq analysis service.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          <Input
            type="password"
            placeholder="API key"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={isLoading}
            autoComplete="off"
            autoFocus
            aria-label="API key"
          />

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" disabled={isLoading || !value.trim()}>
            {isLoading ? "Connecting…" : "Connect"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
