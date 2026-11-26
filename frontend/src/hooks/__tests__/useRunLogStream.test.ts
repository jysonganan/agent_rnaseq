import { renderHook, act } from "@testing-library/react"
import { setApiKey } from "@/lib/api"
import { useRunLogStream } from "@/hooks/useRunLogStream"

// ---------------------------------------------------------------------------
// MockWebSocket (same pattern as useConversationStream tests)
// ---------------------------------------------------------------------------
class MockWebSocket {
  static instances: MockWebSocket[] = []

  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e?: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []
  readyState = 0

  constructor(public readonly url: string) {
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }

  receive(data: string) {
    this.onmessage?.({ data })
  }

  send(data: string) {
    this.sent.push(data)
  }

  close(code?: number) {
    this.readyState = 3
    this.onclose?.(code === undefined ? undefined : { code })
  }

  static readonly OPEN = 1
  static readonly CONNECTING = 0
  static readonly CLOSING = 2
  static readonly CLOSED = 3
}

const originalWebSocket = global.WebSocket

beforeEach(() => {
  MockWebSocket.instances = []
  // @ts-expect-error – replacing global WebSocket with test double
  global.WebSocket = MockWebSocket
  setApiKey("test-key")
})

afterEach(() => {
  global.WebSocket = originalWebSocket
  setApiKey(null)
  jest.useRealTimers()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

it("connects without the API key in the URL", () => {
  renderHook(() => useRunLogStream("run-1"))

  expect(MockWebSocket.instances).toHaveLength(1)
  const url = MockWebSocket.instances[0].url
  expect(url).toContain("/ws/runs/run-1/logs")
  expect(url).not.toContain("api_key")
  expect(url).not.toContain("test-key")
})

it("sends the API key as the first frame on open", () => {
  renderHook(() => useRunLogStream("run-1"))

  expect(MockWebSocket.instances[0].sent).toHaveLength(0)
  act(() => MockWebSocket.instances[0].open())

  expect(MockWebSocket.instances[0].sent).toHaveLength(1)
  expect(JSON.parse(MockWebSocket.instances[0].sent[0])).toEqual({
    type: "auth",
    api_key: "test-key",
  })
})

it("re-sends the auth frame after reconnecting", () => {
  jest.useFakeTimers()
  renderHook(() => useRunLogStream("run-1"))

  act(() => MockWebSocket.instances[0].open())
  act(() => MockWebSocket.instances[0].close())
  act(() => jest.advanceTimersByTime(1000))
  act(() => MockWebSocket.instances[1].open())

  expect(JSON.parse(MockWebSocket.instances[1].sent[0])).toMatchObject({ type: "auth" })
})

it.each([4403, 4404])("does not retry after server close code %i", (code) => {
  jest.useFakeTimers()
  const { result } = renderHook(() => useRunLogStream("run-1"))

  act(() => MockWebSocket.instances[0].open())
  act(() => MockWebSocket.instances[0].close(code))
  act(() => jest.advanceTimersByTime(10000))

  expect(MockWebSocket.instances).toHaveLength(1)
  expect(result.current.status).toBe("error")
})

it("status becomes 'connected' after WS opens", () => {
  const { result } = renderHook(() => useRunLogStream("run-1"))

  act(() => MockWebSocket.instances[0].open())

  expect(result.current.status).toBe("connected")
})

it("accumulates log frames in the logs array", () => {
  const { result } = renderHook(() => useRunLogStream("run-1"))

  const frame1 = {
    ts: "2026-01-01T00:00:00Z",
    level: "info",
    stage: "qc",
    agent: "qc_agent",
    message: "FastQC started",
  }
  const frame2 = {
    ts: "2026-01-01T00:01:00Z",
    level: "info",
    stage: "alignment",
    agent: "alignment_agent",
    message: "STAR alignment complete",
  }

  act(() => {
    MockWebSocket.instances[0].open()
    MockWebSocket.instances[0].receive(JSON.stringify(frame1))
    MockWebSocket.instances[0].receive(JSON.stringify(frame2))
  })

  expect(result.current.logs).toHaveLength(2)
  expect(result.current.logs[0]).toMatchObject({ stage: "qc", message: "FastQC started" })
  expect(result.current.logs[1]).toMatchObject({ stage: "alignment" })
})

it("closes the WebSocket cleanly on unmount", () => {
  const { unmount } = renderHook(() => useRunLogStream("run-1"))

  act(() => MockWebSocket.instances[0].open())

  unmount()

  expect(MockWebSocket.instances[0].readyState).toBe(3)
})

it("does not connect when runId is null", () => {
  renderHook(() => useRunLogStream(null))
  expect(MockWebSocket.instances).toHaveLength(0)
})

it("sets status to 'error' after 3 failed reconnects", () => {
  jest.useFakeTimers()
  const { result } = renderHook(() => useRunLogStream("run-2"))

  act(() => MockWebSocket.instances[0].close())
  act(() => jest.advanceTimersByTime(1000))
  act(() => MockWebSocket.instances[1].close())
  act(() => jest.advanceTimersByTime(2000))
  act(() => MockWebSocket.instances[2].close())
  act(() => jest.advanceTimersByTime(4000))
  act(() => MockWebSocket.instances[3].close())

  expect(result.current.status).toBe("error")
})
