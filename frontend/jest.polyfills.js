// Polyfills for msw v2 in jest-environment-jsdom.
// jsdom doesn't expose these Node.js globals; undici and msw interceptors need them.
const { TextDecoder, TextEncoder } = require("node:util")
const { ReadableStream, TransformStream, WritableStream } = require("node:stream/web")
const { MessageChannel, MessagePort, BroadcastChannel } = require("node:worker_threads")

const nodePairs = [
  ["TextDecoder", TextDecoder],
  ["TextEncoder", TextEncoder],
  ["ReadableStream", ReadableStream],
  ["TransformStream", TransformStream],
  ["WritableStream", WritableStream],
  ["MessageChannel", MessageChannel],
  ["MessagePort", MessagePort],
  ["BroadcastChannel", BroadcastChannel],
]

for (const [name, value] of nodePairs) {
  Object.defineProperty(globalThis, name, { writable: true, configurable: true, value })
}

const { fetch, Request, Response, Headers, FormData } = require("undici")

// configurable:true so msw interceptors can patch Request/Response
Object.defineProperty(globalThis, "fetch", { writable: true, configurable: true, value: fetch })
Object.defineProperty(globalThis, "Request", { writable: true, configurable: true, value: Request })
Object.defineProperty(globalThis, "Response", { writable: true, configurable: true, value: Response })
Object.defineProperty(globalThis, "Headers", { writable: true, configurable: true, value: Headers })
Object.defineProperty(globalThis, "FormData", { writable: true, configurable: true, value: FormData })
