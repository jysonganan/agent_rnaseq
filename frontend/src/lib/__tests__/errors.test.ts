import { ApiError } from "../errors"
import { setApiKey, setOn401Callback, conversationsApi } from "../api"
import { server } from "@/mocks/server"
import { http, HttpResponse } from "msw"

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1"

beforeEach(() => setApiKey("test-key"))
afterEach(() => {
  setApiKey(null)
  setOn401Callback(() => undefined)
})

describe("ApiError", () => {
  test("captures status, title, and detail from RFC 9457 body", () => {
    const err = new ApiError(422, {
      type: "https://api.example.com/errors/validation",
      title: "Validation Error",
      status: 422,
      detail: "content must be at most 4000 characters",
    })

    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(422)
    expect(err.title).toBe("Validation Error")
    expect(err.detail).toBe("content must be at most 4000 characters")
    expect(err.message).toBe("Validation Error")
  })

  test("handles string body gracefully", () => {
    const err = new ApiError(500, "Internal Server Error")
    expect(err.status).toBe(500)
    expect(err.title).toBe("Internal Server Error")
    expect(err.detail).toBe("Internal Server Error")
  })

  test("uses HTTP status fallback when title is empty", () => {
    const err = new ApiError(404, { type: "", title: "", status: 404, detail: "not found" })
    expect(err.title).toBe("HTTP 404")
  })

  test("is instanceof Error", () => {
    const err = new ApiError(400, "Bad Request")
    expect(err).toBeInstanceOf(Error)
  })
})

describe("401 triggers on401 callback", () => {
  test("calls the registered callback on 401 response from apiFetch", async () => {
    const onUnauthorized = jest.fn()
    setOn401Callback(onUnauthorized)

    server.use(
      http.get(`${BASE}/conversations`, () =>
        new HttpResponse(
          JSON.stringify({
            type: "about:blank",
            title: "Unauthorized",
            status: 401,
            detail: "Invalid API key",
          }),
          {
            status: 401,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )

    await expect(conversationsApi.list()).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  test("ApiError from 401 has correct status", async () => {
    setOn401Callback(() => undefined)

    server.use(
      http.get(`${BASE}/conversations`, () =>
        new HttpResponse(
          JSON.stringify({
            type: "about:blank",
            title: "Unauthorized",
            status: 401,
            detail: "Invalid API key",
          }),
          {
            status: 401,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )

    let caughtError: unknown
    try {
      await conversationsApi.list()
    } catch (e) {
      caughtError = e
    }

    expect(caughtError).toBeInstanceOf(ApiError)
    expect((caughtError as ApiError).status).toBe(401)
  })
})
