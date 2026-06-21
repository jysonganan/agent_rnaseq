"use client"

import Link from "next/link"
import { XCircle, Loader2, ArrowLeft, CalendarDays } from "lucide-react"
import { useRun } from "@/hooks/useRuns"
import { RunStatusBadge } from "./RunStatusBadge"
import { StageProgressBar } from "./StageProgressBar"
import { StageTable } from "./StageTable"
import { ArtifactList } from "./ArtifactList"
import { RunLogTail } from "./RunLogTail"
import { CancelRunButton } from "./CancelRunButton"
import { StreamlitEmbed } from "@/components/visualization/StreamlitEmbed"
import type { RunStatus } from "@/lib/types"

function Ts({ label, value }: { label: string; value: string | null }) {
  if (!value) return null
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <CalendarDays className="h-3 w-3 shrink-0" />
      <span className="font-medium">{label}:</span>
      <time dateTime={value}>
        {new Date(value).toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })}
      </time>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="border-b pb-1 text-sm font-semibold">{title}</h2>
      {children}
    </section>
  )
}

const ACTIVE_STATUSES: RunStatus[] = ["pending", "running"]

interface Props {
  runId: string
}

export function RunStatusPanel({ runId }: Props) {
  const { data: run, isLoading, isError } = useRun(runId === "_" ? "" : runId)

  if (runId === "_") {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        No run selected.
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading run…
      </div>
    )
  }

  if (isError || !run) {
    return (
      <div className="flex h-full items-center justify-center gap-2 p-8 text-sm text-destructive">
        <XCircle className="h-4 w-4" />
        Failed to load run.
      </div>
    )
  }

  const isActive = ACTIVE_STATUSES.includes(run.status)
  const completedStages = run.stages.filter((s) => s.status === "completed").length
  const totalStages = run.stages.length

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <Link
        href="/runs"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        All runs
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <h1 className="text-xl font-semibold">{run.name}</h1>
          <div className="flex flex-wrap items-center gap-2">
            <RunStatusBadge status={run.status} />
            <span className="text-xs text-muted-foreground">
              {run.pipeline_type.replace(/_/g, " ")}
            </span>
            {run.genome && (
              <span className="text-xs text-muted-foreground">· {run.genome.name}</span>
            )}
          </div>
          <div className="flex flex-col gap-0.5">
            <Ts label="Created" value={run.created_at} />
            <Ts label="Started" value={run.started_at} />
            <Ts label="Completed" value={run.completed_at} />
          </div>
        </div>
        {isActive && <CancelRunButton runId={run.id} runName={run.name} />}
      </div>

      {totalStages > 0 && (
        <Section title="Progress">
          <StageProgressBar completed={completedStages} total={totalStages} />
        </Section>
      )}

      <Section title="Stages">
        <StageTable stages={run.stages} />
      </Section>

      {isActive && (
        <Section title="Live Logs">
          <RunLogTail runId={run.id} />
        </Section>
      )}

      <Section title="Artifacts">
        <ArtifactList runId={run.id} artifacts={run.artifacts} />
      </Section>

      {/* Mini Streamlit embed — only when a streamlit_data artifact exists */}
      {run.artifacts.some((a) => a.artifact_type === "streamlit_data") && (
        <Section title="Visualization">
          <StreamlitEmbed height={500} />
        </Section>
      )}
    </div>
  )
}
