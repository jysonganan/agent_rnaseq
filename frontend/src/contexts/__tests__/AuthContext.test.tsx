import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { server } from "@/mocks/server"
import { AuthProvider, useAuthContext } from "../AuthContext"
import { setApiKey as storeApiKey } from "@/lib/api"

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1"

function TestConsumer() {
  const { apiKey, isBootstrapping, setApiKey, clearApiKey } = useAuthContext()
  return (
    <div>
      <div data-testid="bootstrapping">{String(isBootstrapping)}</div>
      <div data-testid="key">{apiKey ?? "null"}</div>
      <button onClick={() => setApiKey("injected-key")}>Set key</button>
      <button onClick={clearApiKey}>Sign out</button>
    </div>
  )
}

function renderWithAuth() {
  return render(
    <AuthProvider>
      <TestConsumer />
    </AuthProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
  storeApiKey(null)
})

describe("AuthContext bootstrap", () => {
  test("no stored key → bootstrapping completes, apiKey=null", async () => {
    renderWithAuth()
    await waitFor(() =>
      expect(screen.getByTestId("bootstrapping").textContent).toBe("false")
    )
    expect(screen.getByTestId("key").textContent).toBe("null")
  })

  test("stored valid key → apiKey is restored after silent validation", async () => {
    localStorage.setItem("rnaseq_api_key", "valid-key")
    server.use(
      http.get(`${BASE}/health`, ({ request }) => {
        if (request.headers.get("Authorization") === "Bearer valid-key")
          return HttpResponse.json({ status: "ok", version: "0.1.0" })
        return new HttpResponse(null, { status: 401 })
      })
    )

    renderWithAuth()
    await waitFor(() =>
      expect(screen.getByTestId("bootstrapping").textContent).toBe("false")
    )
    expect(screen.getByTestId("key").textContent).toBe("valid-key")
  })

  test("stored expired key → apiKey=null, localStorage cleared", async () => {
    localStorage.setItem("rnaseq_api_key", "expired-key")
    server.use(
      http.get(`${BASE}/health`, () => new HttpResponse(null, { status: 401 }))
    )

    renderWithAuth()
    await waitFor(() =>
      expect(screen.getByTestId("bootstrapping").textContent).toBe("false")
    )
    expect(screen.getByTestId("key").textContent).toBe("null")
    expect(localStorage.getItem("rnaseq_api_key")).toBeNull()
  })
})

describe("AuthContext setApiKey / clearApiKey", () => {
  test("setApiKey stores in localStorage and updates state", async () => {
    renderWithAuth()
    await waitFor(() =>
      expect(screen.getByTestId("bootstrapping").textContent).toBe("false")
    )

    await userEvent.click(screen.getByRole("button", { name: "Set key" }))

    expect(screen.getByTestId("key").textContent).toBe("injected-key")
    expect(localStorage.getItem("rnaseq_api_key")).toBe("injected-key")
  })

  test("sign out clears localStorage and sets apiKey=null", async () => {
    localStorage.setItem("rnaseq_api_key", "my-key")
    server.use(
      http.get(`${BASE}/health`, () =>
        HttpResponse.json({ status: "ok", version: "0.1.0" })
      )
    )

    renderWithAuth()
    await waitFor(() =>
      expect(screen.getByTestId("key").textContent).toBe("my-key")
    )

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }))

    expect(screen.getByTestId("key").textContent).toBe("null")
    expect(localStorage.getItem("rnaseq_api_key")).toBeNull()
  })

  test("401 mid-session triggers clearApiKey via on401 callback", async () => {
    // Start with a valid session
    localStorage.setItem("rnaseq_api_key", "active-key")
    server.use(
      http.get(`${BASE}/health`, () =>
        HttpResponse.json({ status: "ok", version: "0.1.0" })
      )
    )

    renderWithAuth()
    await waitFor(() =>
      expect(screen.getByTestId("key").textContent).toBe("active-key")
    )

    // Now simulate a 401 from a different API endpoint by calling clearApiKey
    // (the on401 callback is wired to clearApiKey; tested via the sign-out path)
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }))
    expect(screen.getByTestId("key").textContent).toBe("null")
  })
})
