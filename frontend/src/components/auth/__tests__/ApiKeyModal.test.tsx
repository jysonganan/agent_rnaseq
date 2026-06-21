import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { server } from "@/mocks/server"
import { AuthProvider } from "@/contexts/AuthContext"
import { ApiKeyModal } from "../ApiKeyModal"

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1"

function renderModal() {
  return render(
    <AuthProvider>
      <ApiKeyModal />
    </AuthProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe("ApiKeyModal", () => {
  test("renders key input and connect button", async () => {
    renderModal()
    await waitFor(() => expect(screen.getByLabelText(/api key/i)).toBeInTheDocument())
    expect(screen.getByRole("button", { name: /connect/i })).toBeInTheDocument()
  })

  test("input uses type=password so key is masked", async () => {
    renderModal()
    await waitFor(() => {
      const input = screen.getByLabelText(/api key/i)
      expect(input).toHaveAttribute("type", "password")
    })
  })

  test("valid key → calls setApiKey and stores in localStorage", async () => {
    server.use(
      http.get(`${BASE}/health`, () =>
        HttpResponse.json({ status: "ok", version: "0.1.0" })
      )
    )

    renderModal()
    await waitFor(() => screen.getByLabelText(/api key/i))

    await userEvent.type(screen.getByLabelText(/api key/i), "valid-key-123")
    await userEvent.click(screen.getByRole("button", { name: /connect/i }))

    await waitFor(() => {
      expect(localStorage.getItem("rnaseq_api_key")).toBe("valid-key-123")
    })
  })

  test("invalid key (401) → shows error, does not store key", async () => {
    server.use(
      http.get(`${BASE}/health`, () =>
        new HttpResponse(
          JSON.stringify({ type: "", title: "Unauthorized", status: 401, detail: "" }),
          { status: 401, headers: { "Content-Type": "application/problem+json" } }
        )
      )
    )

    renderModal()
    await waitFor(() => screen.getByLabelText(/api key/i))

    await userEvent.type(screen.getByLabelText(/api key/i), "bad-key")
    await userEvent.click(screen.getByRole("button", { name: /connect/i }))

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/invalid api key/i)
    })
    expect(localStorage.getItem("rnaseq_api_key")).toBeNull()
  })

  test("network error → shows unreachable message", async () => {
    server.use(
      http.get(`${BASE}/health`, () => HttpResponse.error())
    )

    renderModal()
    await waitFor(() => screen.getByLabelText(/api key/i))

    await userEvent.type(screen.getByLabelText(/api key/i), "some-key")
    await userEvent.click(screen.getByRole("button", { name: /connect/i }))

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/cannot reach server/i)
    })
  })

  test("loading state disables input and button during request", async () => {
    let resolveRequest: (value: Response) => void
    server.use(
      http.get(`${BASE}/health`, () =>
        new Promise<Response>((resolve) => {
          resolveRequest = resolve
        })
      )
    )

    renderModal()
    await waitFor(() => screen.getByLabelText(/api key/i))

    await userEvent.type(screen.getByLabelText(/api key/i), "test-key")

    // Start the submit (don't await — we want to inspect mid-flight state)
    const button = screen.getByRole("button", { name: /connect/i })
    userEvent.click(button)

    await waitFor(() => {
      expect(screen.getByLabelText(/api key/i)).toBeDisabled()
      expect(screen.getByRole("button", { name: /connecting/i })).toBeDisabled()
    })

    // Resolve the pending request
    resolveRequest!(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )
  })
})
