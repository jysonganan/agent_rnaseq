// Stub — run detail implemented in TASK_FE_07
// Static export requires at least one param; real IDs come from the API at runtime.
export const generateStaticParams = async () => [{ run_id: "_" }]

interface Props {
  params: { run_id: string }
}

export default function RunDetailPage({ params }: Props) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="text-center space-y-2">
        <h1 className="text-xl font-semibold">Run Detail</h1>
        <p className="text-sm text-muted-foreground font-mono">{params.run_id}</p>
        <p className="text-xs text-muted-foreground">
          Stage progress + artifacts — implemented in TASK_FE_07
        </p>
      </div>
    </div>
  )
}
