import { RunStatusPanel } from "@/components/runs/RunStatusPanel"

export const generateStaticParams = async () => [{ run_id: "_" }]

interface Props {
  params: { run_id: string }
}

export default function RunDetailPage({ params }: Props) {
  return <RunStatusPanel runId={params.run_id} />
}
