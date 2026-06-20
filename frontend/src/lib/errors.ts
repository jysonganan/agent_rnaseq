import type { ApiProblemDetail } from "./types"

export class ApiError extends Error {
  readonly status: number
  readonly title: string
  readonly detail: string
  readonly instance: string | undefined

  constructor(status: number, body: ApiProblemDetail | string) {
    const title =
      typeof body === "string"
        ? body || `HTTP ${status}`
        : body.title || `HTTP ${status}`
    super(title)
    this.name = "ApiError"
    this.status = status
    this.title = title
    this.detail =
      typeof body === "string" ? body : (body.detail ?? "")
    this.instance =
      typeof body === "object" ? body.instance : undefined
  }
}
