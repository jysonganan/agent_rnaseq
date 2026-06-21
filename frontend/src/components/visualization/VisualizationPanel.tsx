"use client"

import { useState } from "react"
import { BarChart2, Dna } from "lucide-react"
import { StreamlitEmbed } from "./StreamlitEmbed"
import { GenomeBrowserEmbed } from "./GenomeBrowserEmbed"

type Tab = "streamlit" | "genome"

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "streamlit", label: "Streamlit", icon: <BarChart2 className="h-3.5 w-3.5" /> },
  { id: "genome", label: "Genome Browser", icon: <Dna className="h-3.5 w-3.5" /> },
]

interface VisualizationPanelProps {
  defaultGenomeBuild?: string
  defaultCoords?: string
}

export function VisualizationPanel({
  defaultGenomeBuild = "hg38",
  defaultCoords,
}: VisualizationPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>("streamlit")
  const [coords, setCoords] = useState(defaultCoords ?? "")

  return (
    <div className="flex h-full flex-col p-6 space-y-4">
      <h1 className="text-xl font-semibold">Visualization</h1>

      {/* Tab bar */}
      <div className="flex gap-1 rounded-lg border bg-muted/30 p-1 w-fit">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={[
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              activeTab === tab.id
                ? "bg-background shadow-sm text-foreground"
                : "text-muted-foreground hover:text-foreground",
            ].join(" ")}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "streamlit" && (
        <div className="flex-1 min-h-0">
          <StreamlitEmbed height={680} />
        </div>
      )}

      {activeTab === "genome" && (
        <div className="flex-1 min-h-0 space-y-3">
          <div className="flex items-center gap-2">
            <label htmlFor="coords-input" className="text-sm font-medium text-muted-foreground">
              Position
            </label>
            <input
              id="coords-input"
              type="text"
              value={coords}
              onChange={(e) => setCoords(e.target.value)}
              placeholder="e.g. chr17:7,674,220-7,675,000"
              className="rounded-md border bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring w-72"
            />
          </div>
          <GenomeBrowserEmbed
            genomeBuild={defaultGenomeBuild}
            coords={coords || undefined}
            height={620}
          />
        </div>
      )}
    </div>
  )
}
