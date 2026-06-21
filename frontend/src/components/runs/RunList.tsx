import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { RunListItem } from "./RunListItem"
import type { Run } from "@/lib/types"

interface Props {
  runs: Run[]
  total: number
  isLoading: boolean
  onLoadMore: () => void
}

export function RunList({ runs, total, isLoading, onLoadMore }: Props) {
  if (isLoading && runs.length === 0) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading runs…
      </div>
    )
  }

  if (runs.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
        No runs found.
      </div>
    )
  }

  const hasMore = total > runs.length

  return (
    <div className="space-y-3">
      {runs.map((run) => (
        <RunListItem key={run.id} run={run} />
      ))}
      {hasMore && (
        <div className="pt-2 text-center">
          <Button variant="outline" size="sm" onClick={onLoadMore} disabled={isLoading}>
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                Loading…
              </>
            ) : (
              "Load more"
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
