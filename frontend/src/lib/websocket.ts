import type { WsStatus } from "./types"

export type { WsStatus }

// Generic JSON frame — each hook interprets the shape based on the endpoint
export type JsonFrame = Record<string, unknown>

interface WsManagerOptions {
  url: string
  onMessage: (frame: JsonFrame) => void
  onStatusChange: (status: WsStatus) => void
}

const MAX_RETRIES = 3

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

    ws.onclose = () => {
      if (this.destroyed) return
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
