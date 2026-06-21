"use client"

import { useState } from "react"
import { Loader2 } from "lucide-react"

interface StreamlitEmbedProps {
  height?: number
}

export function StreamlitEmbed({ height = 700 }: StreamlitEmbedProps) {
  const [loaded, setLoaded] = useState(false)
  const streamlitUrl = process.env.NEXT_PUBLIC_STREAMLIT_URL

  if (!streamlitUrl) {
    return (
      <div
        className="flex items-center justify-center rounded-md border bg-muted/20 text-sm text-muted-foreground"
        style={{ height }}
      >
        <div className="text-center space-y-1">
          <p>Streamlit not configured.</p>
          <p className="text-xs">
            Set <code className="rounded bg-muted px-1">NEXT_PUBLIC_STREAMLIT_URL</code> to enable.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative w-full overflow-hidden rounded-md border" style={{ height }}>
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}
      <iframe
        src={streamlitUrl}
        className="h-full w-full"
        sandbox="allow-scripts allow-same-origin allow-forms"
        title="Streamlit visualization"
        onLoad={() => setLoaded(true)}
      />
    </div>
  )
}
