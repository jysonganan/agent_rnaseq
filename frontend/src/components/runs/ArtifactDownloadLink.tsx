"use client"

import { useState } from "react"
import { Download, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { artifactsApi } from "@/lib/api"

interface Props {
  runId: string
  artifactId: string
  label?: string
}

export function ArtifactDownloadLink({ runId, artifactId, label = "Download" }: Props) {
  const [loading, setLoading] = useState(false)

  async function handleClick() {
    setLoading(true)
    try {
      const { download_url } = await artifactsApi.download(runId, artifactId)
      window.open(download_url, "_blank", "noopener,noreferrer")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleClick}
      disabled={loading}
      className="h-7 gap-1.5 text-xs"
    >
      {loading ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <Download className="h-3 w-3" />
      )}
      {label}
    </Button>
  )
}
