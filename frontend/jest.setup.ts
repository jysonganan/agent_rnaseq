import "@testing-library/jest-dom"
import { server } from "./src/mocks/server"

process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000"

beforeAll(() => server.listen({ onUnhandledRequest: "warn" }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
