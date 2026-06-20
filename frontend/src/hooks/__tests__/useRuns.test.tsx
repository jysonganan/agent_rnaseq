import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import { type ReactNode } from "react"
import { useRun } from "../useRuns"
import { setApiKey } from "@/lib/api"
import { server } from "@/mocks/server"
import type { RunDetail } from "@/lib/types"

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1"

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

beforeEach(() => setApiKey("test-key"))
afterEach(() => setApiKey(null))

test("useRun returns data for a completed run", async () => {
  const { result } = renderHook(() => useRun("run-1"), {
    wrapper: makeWrapper(),
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data?.status).toBe("completed")
  expect(result.current.data?.id).toBe("run-1")
})

test("useRun polling stops when run is completed", async () => {
  const fetchSpy = jest.spyOn(global, "fetch")

  const { result } = renderHook(() => useRun("run-1"), {
    wrapper: makeWrapper(),
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data?.status).toBe("completed")

  const callCount = fetchSpy.mock.calls.length
  // After 100ms, there should be no additional fetches (polling stopped)
  await new Promise((r) => setTimeout(r, 100))
  expect(fetchSpy.mock.calls.length).toBe(callCount)

  fetchSpy.mockRestore()
})

test("useRun returns running status for an active run", async () => {
  server.use(
    http.get(`${BASE}/runs/run-active`, () =>
      HttpResponse.json<RunDetail>({
        id: "run-active",
        name: "active_run",
        status: "running",
        pipeline_type: "bulk_rnaseq",
        conversation_id: null,
        triggering_message_id: null,
        created_at: "2026-01-01T00:00:00Z",
        started_at: "2026-01-01T00:01:00Z",
        completed_at: null,
        genome: { id: "g1", name: "GRCh38" },
        stages: [],
        artifacts: [],
      })
    )
  )

  const { result } = renderHook(() => useRun("run-active"), {
    wrapper: makeWrapper(),
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data?.status).toBe("running")
})
