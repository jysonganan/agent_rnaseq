import type { WsStatus } from "./types"

export type { WsStatus }

// Generic JSON frame — each hook interprets the shape based on the endpoint
export type JsonFrame = Record<string, unknown>

interface WsManagerOptions {
  /** Must not contain credentials (safety_policy 11.1); auth goes in the first frame. */
  url: string
  /** API key sent as the first frame on every (re)connect: {"type":"auth","api_key":...}. */
  apiKey: string
  onMessage: (frame: JsonFrame) => void
  onStatusChange: (status: WsStatus) => void
}

const MAX_RETRIES = 3

// Server close codes that a retry cannot fix (bad key, or resource not found / not owned).
const WS_CLOSE_UNAUTHORIZED = 4403
const WS_CLOSE_NOT_FOUND = 4404

export class WsManager {
  private ws: WebSocket | null = null
  private retryCount = 0
  private destroyed = false
  private retryTimer: ReturnType<typeof setTimeout> | null = null

  constructor(private readonly options: WsManagerOptions) {
    this.connect()
  }

  private connect() {
    if (this.destroyed) return
    this.options.onStatusChange("connecting")

    const ws = new WebSocket(this.options.url)
    this.ws = ws

    ws.onopen = () => {
      this.retryCount = 0
      ws.send(JSON.stringify({ type: "auth", api_key: this.options.apiKey }))
      this.options.onStatusChange("connected")
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const frame = JSON.parse(event.data as string) as JsonFrame
        this.options.onMessage(frame)
      } catch {
        // Silently drop unparseable frames
      }
    }

    ws.onclose = (event?: CloseEvent) => {
      if (this.destroyed) return
      const code = event?.code
      if (code === WS_CLOSE_UNAUTHORIZED || code === WS_CLOSE_NOT_FOUND) {
        this.options.onStatusChange("error")
        return
      }
      if (this.retryCount < MAX_RETRIES) {
        // Exponential back-off: 1 s, 2 s, 4 s
        const delayMs = Math.pow(2, this.retryCount) * 1000
        this.retryCount++
        this.retryTimer = setTimeout(() => this.connect(), delayMs)
      } else {
        this.options.onStatusChange("error")
      }
    }

    ws.onerror = () => {
      // onerror always fires before onclose; reconnect logic lives in onclose
    }
  }

  reconnect() {
    if (this.destroyed) return
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    this.retryCount = 0

    const state = this.ws?.readyState
    if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) {
      this.ws?.close()  // triggers onclose → connect()
    } else {
      this.connect()
    }
  }

  destroy() {
    this.destroyed = true
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    this.ws?.close()
  }
}

/** Convert http(s) base URL to ws(s) base URL. */
export function toWsBase(apiUrl: string): string {
  return apiUrl.replace(/^http/, "ws")
}
