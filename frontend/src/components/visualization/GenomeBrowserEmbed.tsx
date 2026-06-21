"use client"

import { useState } from "react"
import { Loader2 } from "lucide-react"

interface GenomeBrowserEmbedProps {
  genomeBuild: string
  coords?: string
  height?: number
}

export function GenomeBrowserEmbed({ genomeBuild, coords, height = 600 }: GenomeBrowserEmbedProps) {
  const [loaded, setLoaded] = useState(false)

  const params = new URLSearchParams({ db: genomeBuild })
  if (coords) params.set("position", coords)
  const src = `https://genome.ucsc.edu/cgi-bin/hgTracks?${params.toString()}`

  return (
    <div className="relative w-full overflow-hidden rounded-md border" style={{ height }}>
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}
      <iframe
        src={src}
        className="h-full w-full"
        sandbox="allow-scripts allow-forms"
        title="UCSC Genome Browser"
        onLoad={() => setLoaded(true)}
      />
    </div>
  )
}
