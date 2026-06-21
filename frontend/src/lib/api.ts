import { ApiError } from "./errors"
import type {
  HealthResponse,
  Genome,
  GenomesListResponse,
  Run,
  RunDetail,
  RunsListResponse,
  Artifact,
  ArtifactsListResponse,
  ArtifactDownloadResponse,
  Conversation,
  ConversationDetail,
  ConversationsListResponse,
  ChatMessage,
  MessagesListResponse,
  SendMessageResponse,
  RunStatus,
  ApiProblemDetail,
} from "./types"

// Module-level API key store. AuthContext (TASK_FE_03) wires this up;
// tests call setApiKey() directly.
let _apiKey: string | null = null
let _on401: (() => void) | null = null

export function setApiKey(key: string | null): void {
  _apiKey = key
}

export function getApiKey(): string | null {
  return _apiKey
}

export function setOn401Callback(cb: () => void): void {
  _on401 = cb
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined
  ) as [string, string | number][]
  if (entries.length === 0) return ""
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
  const url = `${baseUrl}/api/v1${path}`

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  }
  if (_apiKey) {
    headers["Authorization"] = `Bearer ${_apiKey}`
  }

  const response = await fetch(url, { ...init, headers })

  if (!response.ok) {
    if (response.status === 401) {
      _on401?.()
    }
    let body: ApiProblemDetail | string
    const contentType = response.headers.get("content-type") ?? ""
    if (contentType.includes("application/json") || contentType.includes("application/problem+json")) {
      body = (await response.json()) as ApiProblemDetail
    } else {
      body = await response.text()
    }
    throw new ApiError(response.status, body)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

// Health
export const healthApi = {
  get: (): Promise<HealthResponse> => apiFetch("/health"),
}

// Validates a candidate API key without persisting it to the module store.
// Used by AuthContext during bootstrap and by ApiKeyModal on submit.
export async function validateApiKey(
  key: string
): Promise<"valid" | "invalid" | "unreachable"> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
  try {
    const response = await fetch(`${baseUrl}/api/v1/health`, {
      headers: { Authorization: `Bearer ${key}` },
    })
    return response.ok ? "valid" : "invalid"
  } catch {
    return "unreachable"
  }
}

// Genomes
export const genomesApi = {
  list: (params?: { limit?: number; offset?: number }): Promise<GenomesListResponse> => {
    const q = params ? buildQuery(params) : ""
    return apiFetch(`/genomes${q}`)
  },
  get: (id: string): Promise<Genome> => apiFetch(`/genomes/${id}`),
}

// Runs
export const runsApi = {
  list: (params?: {
    status?: RunStatus
    conversation_id?: string
    limit?: number
    offset?: number
  }): Promise<RunsListResponse> => {
    const q = params ? buildQuery(params as Record<string, string | number | undefined>) : ""
    return apiFetch(`/runs${q}`)
  },
  get: (id: string): Promise<RunDetail> => apiFetch(`/runs/${id}`),
  cancel: (id: string): Promise<Run> =>
    apiFetch(`/runs/${id}/cancel`, { method: "POST" }),
}

// Artifacts
export const artifactsApi = {
  list: (
    runId: string,
    params?: { artifact_type?: string }
  ): Promise<ArtifactsListResponse> => {
    const q = params ? buildQuery(params) : ""
    return apiFetch(`/runs/${runId}/artifacts${q}`)
  },
  download: (runId: string, artifactId: string): Promise<ArtifactDownloadResponse> =>
    apiFetch(`/runs/${runId}/artifacts/${artifactId}/download`),
}

// Conversations
export const conversationsApi = {
  list: (params?: { limit?: number; offset?: number }): Promise<ConversationsListResponse> => {
    const q = params ? buildQuery(params) : ""
    return apiFetch(`/conversations${q}`)
  },
  create: (title?: string): Promise<Conversation> =>
    apiFetch("/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  get: (id: string): Promise<ConversationDetail> => apiFetch(`/conversations/${id}`),
  getMessages: (
    id: string,
    params?: { limit?: number; offset?: number }
  ): Promise<MessagesListResponse> => {
    const q = params ? buildQuery(params) : ""
    return apiFetch(`/conversations/${id}/messages${q}`)
  },
  sendMessage: (id: string, content: string): Promise<SendMessageResponse> =>
    apiFetch(`/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  delete: (id: string): Promise<void> =>
    apiFetch(`/conversations/${id}`, { method: "DELETE" }),
}

// Re-export types used by callers
export type {
  Conversation,
  ConversationDetail,
  ConversationsListResponse,
  ChatMessage,
  MessagesListResponse,
  SendMessageResponse,
  Run,
  RunDetail,
  RunsListResponse,
  Artifact,
  ArtifactsListResponse,
  ArtifactDownloadResponse,
  Genome,
}
