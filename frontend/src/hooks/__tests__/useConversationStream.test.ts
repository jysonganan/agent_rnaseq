import { renderHook, act } from "@testing-library/react"
import { setApiKey } from "@/lib/api"
import { useConversationStream } from "@/hooks/useConversationStream"

// ---------------------------------------------------------------------------
// MockWebSocket — deterministic WebSocket substitute for unit tests
// ---------------------------------------------------------------------------
class MockWebSocket {
  static instances: MockWebSocket[] = []

  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  readyState = 0  // CONNECTING

  constructor(public readonly url: string) {
    MockWebSocket.instances.push(this)
  }

  // Test helper: simulate successful connection
  open() {
    this.readyState = 1
    this.onopen?.()
  }

  // Test helper: server sends a text frame
  receive(data: string) {
    this.onmessage?.({ data })
  }

  // Test helper: connection closed
  close() {
    this.readyState = 3
    this.onclose?.()
  }

  // Expose OPEN constant so WsManager can reference WebSocket.OPEN
  static readonly OPEN = 1
  static readonly CONNECTING = 0
  static readonly CLOSING = 2
  static readonly CLOSED = 3
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------
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

it("connects with the correct URL including api_key param", () => {
  renderHook(() => useConversationStream("conv-1"))

  expect(MockWebSocket.instances.length).toBe(1)
  const url = MockWebSocket.instances[0].url
  expect(url).toContain("/ws/conversations/conv-1/stream")
  expect(url).toContain("api_key=test-key")
})

it("status becomes 'connected' after WS opens", () => {
  const { result } = renderHook(() => useConversationStream("conv-1"))

  act(() => MockWebSocket.instances[0].open())

  expect(result.current.status).toBe("connected")
})

it("dispatches token frames to onToken callback", () => {
  const onToken = jest.fn()
  renderHook(() => useConversationStream("conv-1", { onToken }))

  act(() => {
    MockWebSocket.instances[0].open()
    MockWebSocket.instances[0].receive(
      JSON.stringify({ type: "token", payload: { message_id: "m1", token: "Hello " } })
    )
    MockWebSocket.instances[0].receive(
      JSON.stringify({ type: "token", payload: { message_id: "m1", token: "world" } })
    )
  })

  expect(onToken).toHaveBeenCalledTimes(2)
  expect(onToken).toHaveBeenNthCalledWith(1, "m1", "Hello ")
  expect(onToken).toHaveBeenNthCalledWith(2, "m1", "world")
})

it("dispatches done frame to onDone callback", () => {
  const onDone = jest.fn()
  renderHook(() => useConversationStream("conv-1", { onDone }))

  act(() => {
    MockWebSocket.instances[0].open()
    MockWebSocket.instances[0].receive(
      JSON.stringify({ type: "done", payload: { message_id: "m1", run_id: null } })
    )
  })

  expect(onDone).toHaveBeenCalledWith({ message_id: "m1", run_id: null })
})

it("dispatches tool_call frames to onToolCall callback", () => {
  const onToolCall = jest.fn()
  renderHook(() => useConversationStream("conv-1", { onToolCall }))

  const payload = {
    message_id: "m1",
    tool_name: "run_deseq2",
    status: "running",
    summary: null,
  }

  act(() => {
    MockWebSocket.instances[0].open()
    MockWebSocket.instances[0].receive(
      JSON.stringify({ type: "tool_call", payload })
    )
  })

  expect(onToolCall).toHaveBeenCalledWith(payload)
})

it("reconnects with exponential back-off and sets status='error' after 3 retries", () => {
  jest.useFakeTimers()
  const { result } = renderHook(() => useConversationStream("conv-2"))

  // Initial connection attempt (instance 0 exists, in CONNECTING state)
  expect(MockWebSocket.instances).toHaveLength(1)

  // Simulate immediate close (connection refused)
  act(() => MockWebSocket.instances[0].close())

  // After 1s delay, first retry
  act(() => jest.advanceTimersByTime(1000))
  expect(MockWebSocket.instances).toHaveLength(2)

  // Second close
  act(() => MockWebSocket.instances[1].close())

  // After 2s delay, second retry
  act(() => jest.advanceTimersByTime(2000))
  expect(MockWebSocket.instances).toHaveLength(3)

  // Third close
  act(() => MockWebSocket.instances[2].close())

  // After 4s delay, third retry
  act(() => jest.advanceTimersByTime(4000))
  expect(MockWebSocket.instances).toHaveLength(4)

  // Fourth close → no more retries, status = "error"
  act(() => MockWebSocket.instances[3].close())

  expect(result.current.status).toBe("error")
})

it("closes the WebSocket cleanly on unmount", () => {
  const { unmount } = renderHook(() => useConversationStream("conv-3"))

  act(() => MockWebSocket.instances[0].open())

  unmount()

  // The ws was closed (readyState 3 = CLOSED)
  expect(MockWebSocket.instances[0].readyState).toBe(3)
})

it("does not connect when conversationId is null", () => {
  renderHook(() => useConversationStream(null))
  expect(MockWebSocket.instances).toHaveLength(0)
})

it("does not connect when conversationId is the static placeholder '_'", () => {
  renderHook(() => useConversationStream("_"))
  expect(MockWebSocket.instances).toHaveLength(0)
})
