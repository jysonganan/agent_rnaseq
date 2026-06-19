# TASK_FE_02 — Typed API Client & React Query Setup

## Goal
Create a typed API client module and React Query integration so all other frontend tasks can call FastAPI endpoints without writing raw `fetch` calls or duplicating auth logic.

## Requirements
- A base `apiFetch` function that:
  - Reads the API key from `AuthContext` and injects `Authorization: Bearer <key>` on every request
  - Targets `NEXT_PUBLIC_API_URL` (never hardcodes localhost)
  - Maps non-2xx responses to a typed `ApiError` (mirrors RFC 9457 Problem Details)
  - Retries on 5xx (up to 2 retries); does not retry on 4xx
- TypeScript interfaces for every API response shape defined in `docs/specs/api_contracts.md`
- Domain-specific API modules: `conversationsApi`, `runsApi`, `artifactsApi`, `genomesApi`
- A React Query `QueryClient` singleton configured with sane defaults
- A `ReactQueryProvider` wrapper component
- Custom hooks for common data fetching:
  - `useConversations()` — list conversations
  - `useConversation(id)` — single conversation + messages
  - `useRuns(filters?)` — list runs with optional status filter
  - `useRun(id)` — run detail with stages and artifacts
  - `useArtifactDownload(runId, artifactId)` — fetch presigned download URL

## Files to Create
| File | Purpose |
|---|---|
| `frontend/src/lib/types.ts` | All TypeScript interfaces matching API contracts |
| `frontend/src/lib/api.ts` | `apiFetch`, `conversationsApi`, `runsApi`, `artifactsApi`, `genomesApi` |
| `frontend/src/lib/errors.ts` | `ApiError` class with `status`, `title`, `detail` fields |
| `frontend/src/lib/query-client.ts` | `QueryClient` singleton |
| `frontend/src/providers/ReactQueryProvider.tsx` | `QueryClientProvider` wrapper |
| `frontend/src/hooks/useConversations.ts` | React Query hooks for conversations |
| `frontend/src/hooks/useRuns.ts` | React Query hooks for runs |
| `frontend/src/hooks/useArtifacts.ts` | React Query hook for artifacts |

## Key TypeScript Interfaces (in `types.ts`)
```typescript
// Mirror docs/specs/api_contracts.md exactly
interface Conversation { id: string; title: string; updated_at: string; created_at: string }
interface ChatMessage { id: string; conversation_id: string; role: "user" | "assistant" | "tool"; content: string; run_id: string | null; tool_name: string | null; tool_status: string | null; created_at: string }
interface Run { id: string; name: string; status: RunStatus; pipeline_type: string; created_at: string; started_at: string | null; completed_at: string | null }
interface RunDetail extends Run { genome: { id: string; name: string }; stages: Stage[]; artifacts: Artifact[] }
interface Stage { id: string; stage_name: string; status: StageStatus; tool_name: string; started_at: string | null; completed_at: string | null }
interface Artifact { id: string; artifact_type: string; path: string; file_size_bytes: number | null; created_at: string }
type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled"
type StageStatus = "pending" | "running" | "completed" | "failed" | "skipped"
```

## React Query Configuration
```typescript
// query-client.ts defaults
{
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => error instanceof ApiError && error.status >= 500 && failureCount < 2,
    }
  }
}
```

## Acceptance Criteria
- [ ] No `any` type annotations in any file in this task
- [ ] `ApiError` is thrown (not returned) on non-2xx responses; callers can `catch (e instanceof ApiError)`
- [ ] 401 responses trigger a callback (passed via context) to clear the stored API key
- [ ] All API modules are pure functions (no side effects beyond HTTP); hooks add React Query caching on top
- [ ] `useRun(id)` sets `refetchInterval: 3000` when run status is `pending` or `running`, and stops polling on terminal states
- [ ] `useRuns()` sets `refetchInterval: 5000` while any run in the list is non-terminal
- [ ] TypeScript compiles clean with `npx tsc --noEmit`

## Definition of Done
All acceptance criteria pass. No UI components yet — this task is pure data layer.

## Dependencies
TASK_FE_01 (scaffold must exist), TASK_FE_03 (AuthContext provides the key; mock it in tests).
