import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { type ReactNode } from "react"
import { useConversations } from "../useConversations"
import { setApiKey } from "@/lib/api"

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

beforeEach(() => setApiKey("test-key"))
afterEach(() => setApiKey(null))

test("useConversations returns the mocked conversation list", async () => {
  const { result } = renderHook(() => useConversations(), {
    wrapper: makeWrapper(),
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))

  const conversations = result.current.data?.conversations
  expect(conversations).toHaveLength(2)
  expect(conversations?.[0].title).toBe("RNA-seq bulk analysis")
  expect(conversations?.[1].title).toBe("Single-cell clustering")
})

test("useConversations total matches fixture", async () => {
  const { result } = renderHook(() => useConversations(), {
    wrapper: makeWrapper(),
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data?.total).toBe(2)
})
