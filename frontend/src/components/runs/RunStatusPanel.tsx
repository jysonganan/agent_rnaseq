"use client"

import Link from "next/link"
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Ban,
  AlertCircle,
  ArrowLeft,
  CalendarDays,
} from "lucide-react"
import { useRun } from "@/hooks/useRuns"
import { StageProgressBar } from "./StageProgressBar"
import { StageTable } from "./StageTable"
import { ArtifactList } from "./ArtifactList"
import { RunLogTail } from "./RunLogTail"
import { CancelRunButton } from "./CancelRunButton"
import type { RunStatus } from "@/lib/types"

// ── Run-level status badge ────────────────────────────────────────────────────

interface RunStatusBadgeConfig {
  label: string
  className: string
  icon: React.ReactNode
}

function runStatusConfig(status: RunStatus): RunStatusBadgeConfig {
  switch (status) {
    case "pending":
      return {
        label: "Pending",
        className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
        icon: <Clock className="h-3 w-3" />,
      }
    case "running":
      return {
        label: "Running",
        className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
        icon: <Loader2 className="h-3 w-3 animate-spin" />,
      }
    case "completed":
      return {
        label: "Completed",
        className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        icon: <CheckCircle2 className="h-3 w-3" />,
      }
    case "failed":
      return {
        label: "Failed",
        className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
        icon: <AlertCircle className="h-3 w-3" />,
      }
    case "cancelled":
      return {
        label: "Cancelled",
        className: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
        icon: <Ban className="h-3 w-3" />,
      }
  }
}

function RunStatusBadge({ status }: { status: RunStatus }) {
  const cfg = runStatusConfig(status)
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${cfg.className}`}
    >
      {cfg.icon}
      {cfg.label}
    </span>
  )
}

// ── Timestamp row ─────────────────────────────────────────────────────────────

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

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="border-b pb-1 text-sm font-semibold">{title}</h2>
      {children}
    </section>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

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
      {/* Back link */}
      <Link
        href="/runs"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        All runs
      </Link>

      {/* Header */}
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

      {/* Progress */}
      {totalStages > 0 && (
        <Section title="Progress">
          <StageProgressBar completed={completedStages} total={totalStages} />
        </Section>
      )}

      {/* Stages */}
      <Section title="Stages">
        <StageTable stages={run.stages} />
      </Section>

      {/* Live logs — only while active */}
      {isActive && (
        <Section title="Live Logs">
          <RunLogTail runId={run.id} />
        </Section>
      )}

      {/* Artifacts */}
      <Section title="Artifacts">
        <ArtifactList runId={run.id} artifacts={run.artifacts} />
      </Section>
    </div>
  )
}
