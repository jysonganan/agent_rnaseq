"use client"

import { useState } from "react"
import { useRuns } from "@/hooks/useRuns"
import { RunList } from "@/components/runs/RunList"
import { RunFilters } from "@/components/runs/RunFilters"
import type { RunStatus } from "@/lib/types"

const PAGE_SIZE = 20

export default function RunsPage() {
  const [statusFilter, setStatusFilter] = useState<RunStatus | "all">("all")
  const [limit, setLimit] = useState(PAGE_SIZE)

  const { data, isLoading } = useRuns({
    status: statusFilter === "all" ? undefined : statusFilter,
    limit,
  })

  function handleStatusChange(newStatus: RunStatus | "all") {
    setStatusFilter(newStatus)
    setLimit(PAGE_SIZE)
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Run History</h1>
        {data && (
          <span className="text-sm text-muted-foreground">
            {data.total} run{data.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <RunFilters status={statusFilter} onStatusChange={handleStatusChange} />

      <RunList
        runs={data?.runs ?? []}
        total={data?.total ?? 0}
        isLoading={isLoading}
        onLoadMore={() => setLimit((prev) => prev + PAGE_SIZE)}
      />
    </div>
  )
}
