# Frontend Architecture Review

Reviewer: strict architecture review per `docs/prompts/04_reviewer_prompt_frontend.md`
Scope: CLAUDE.md, docs/architecture.md, docs/specs/*.md, tasks_frontend/*.md

---

## Critical Issues

### C1 — LLM Can Hallucinate Sample IDs
**Location:** `docs/specs/tool_contracts.md` Section 12, `docs/specs/safety_policy.md`

`dispatch_from_chat()` accepts a natural-language message and must produce a `RunConfig` including `sample_ids: list[UUID]`. The current spec does not require that these IDs come from a DB-provided list. An LLM could invent plausible-looking UUIDs from free text, bypassing the FK constraint only at DB insert time (which would raise an integrity error, not a safe validation failure).

**Fix:** The Orchestrator must query the `Sample` table for samples owned by the caller's projects before calling the LLM, and pass the available samples as a structured list in the system prompt. The LLM must select `sample_ids` from this list by exact UUID match only.

**Fixed in:** `docs/specs/tool_contracts.md` Section 12, `docs/specs/safety_policy.md` Rule 11.3

---

### C2 — `dispatch_from_chat()` Missing Streaming Completion Spec
**Location:** `docs/specs/tool_contracts.md` Section 12, `docs/architecture.md` Section 4

`docs/architecture.md` Section 4 states LangGraph nodes call `client.chat.completions.create()` directly but does not specify `stream=True`. Without streaming, no `token` frames can be published to Redis — the frontend receives nothing until the entire response is ready, then a single `done` frame. The token streaming UX (core feature of the chat UI) is silently broken.

**Fix:** Spec must require `stream=True` for the intent-parsing and response-generation calls inside `dispatch_from_chat()`. Each chunk from the streaming response is published as a `token` frame to the Redis `conv:{conversation_id}` channel as it arrives.

**Fixed in:** `docs/specs/tool_contracts.md` Section 12

---

### C3 — `ChatMessage(role=assistant)` Commit Timing Unspecified
**Location:** `tasks_frontend/TASK_FE_10_backend_conversation_api.md`

The arq worker calls `dispatch_from_chat()`, which streams tokens to Redis. The spec says it "Creates ChatMessage(role=assistant)" but does not say when. If the worker crashes mid-stream:
- The partial token stream has already been sent to the browser.
- No `ChatMessage` record exists in the DB.
- On page reload, the assistant turn is missing from history.

This is a data consistency gap.

**Fix:** The arq worker must accumulate streamed tokens in memory, then write a single `ChatMessage(role=assistant, content=<accumulated_text>)` after the `done` frame is published. If the worker crashes before the commit, the assistant message is absent from history (acceptable: user can re-send). The spec must state this explicitly.

**Fixed in:** `tasks_frontend/TASK_FE_10_backend_conversation_api.md`

---

### C4 — No Rate Limit on `POST /conversations/{id}/messages`
**Location:** `docs/specs/api_contracts.md` Rate Limits section

`POST /conversations/{id}/messages` triggers an LLM call and potentially a full pipeline run (same cost as `POST /runs`). Yet the Rate Limits section does not list this endpoint. The existing `POST /runs` limit is 10 requests/minute per API key.

**Fix:** Add `POST /conversations/{id}/messages: 10 requests/minute per API key` to the Rate Limits section.

**Fixed in:** `docs/specs/api_contracts.md`

---

### C5 — No Frontend Dev-Mode API Mocking
**Location:** `tasks_frontend/TASK_FE_02_api_client.md`

Frontend developers cannot run tasks FE_02 through FE_09 without a fully running FastAPI backend + Redis + arq worker + PostgreSQL. There is no Mock Service Worker (msw) setup specified. This is a development blocker for frontend-only work and a testing blocker for unit tests that need to mock API responses.

**Fix:** Add msw setup to TASK_FE_02. Create `frontend/src/mocks/` with handler stubs for all API endpoints and a `server.ts` for Node test environments.

**Fixed in:** `tasks_frontend/TASK_FE_02_api_client.md`

---

### C6 — Inconsistent WebSocket Authentication Between Endpoints
**Location:** `docs/specs/api_contracts.md`

`WS /ws/conversations/{id}/stream` specifies `?api_key=<key>` authentication. The existing `WS /ws/runs/{run_id}/logs` endpoint has no auth method documented at all. This inconsistency leaves the run log stream either unauthenticated (security hole) or using a different mechanism that isn't specified.

**Fix:** Add `?api_key=<key>` authentication to `WS /ws/runs/{run_id}/logs` spec to match the conversation stream. Both WebSocket endpoints must use the same auth pattern.

**Fixed in:** `docs/specs/api_contracts.md`

---

### C7 — `AnalysisRun` Has No Audit Trail Back to the Chat Message
**Location:** `docs/specs/data_models.md`

`ChatMessage.run_id` is an FK from message → run. But `AnalysisRun` has no FK back to the chat message or conversation that created it. Querying "which conversation triggered this run?" requires a reverse join through `ChatMessage`, which is fragile and expensive. More importantly, the existing audit log (Rule 7) does not record the user intent (chat message) that led to the run configuration.

**Fix:** Add nullable fields `conversation_id UUID FK → Conversation` and `triggering_message_id UUID FK → ChatMessage` to `AnalysisRun`. These are set only for runs created via chat; runs created via `POST /runs` leave them null.

**Fixed in:** `docs/specs/data_models.md`

---

## Recommended Changes

### R1 — `user_content` Max Length Not in API Contract
**Location:** `docs/specs/api_contracts.md` `POST /conversations/{id}/messages`

`tool_contracts.md` Section 12 specifies `user_content: str (max 4000 chars)` but the API contract for this endpoint does not state the `content` field max length. Implementers may miss this constraint.

**Fix:** Add `content` max 4000 characters to the request body spec.

**Fixed in:** `docs/specs/api_contracts.md`

---

### R2 — Conversation Title Update Behavior Unspecified
**Location:** `docs/specs/data_models.md`, `docs/specs/api_contracts.md`

`Conversation.title` says "Auto-generated from first user message (truncated to 60 chars)" but neither the data model nor the API contracts specify:
- What the initial title is when `POST /conversations` is called (before any message).
- When/how it is updated to the first-message-derived title.
- Whether `POST /conversations` `title` override takes precedence permanently.

**Fix:** Specify: initial title is `"New conversation"`; when the first `ChatMessage(role=user)` is committed, the backend updates `Conversation.title` to `user_content[:60]` unless an explicit title was provided at creation.

**Fixed in:** `docs/specs/data_models.md`

---

### R3 — `ToolCallCard.summary` Source Is Ambiguous (Rule 1 Risk)
**Location:** `docs/specs/api_contracts.md` (WS frame spec), `docs/specs/tool_contracts.md`

The `tool_call` WS frame has a `summary: string | null` field. It is unclear whether this string is:
a) A JSON subset of the validated `ToolOutput` Pydantic model (safe — deterministic).
b) LLM-generated prose describing the tool result (violates Rule 1 if it contains numerical values).

If (b), the LLM summarizing tool outputs into the `summary` field could include numbers like "aligned 94.2% of reads" — which are acceptable per Rule 1 ("LLMs may summarize validated results in natural language") but the summary must not itself be stored as a numerical DB value. The spec must clarify.

**Fix:** Specify that `tool_call.payload.summary` is a short JSON-serialized excerpt of the validated `ToolOutput` Pydantic model, not LLM-generated text. LLM prose summaries appear only in `token` frames (the `ChatMessage(role=assistant)` content).

**Fixed in:** `docs/specs/tool_contracts.md` Section 12

---

### R4 — CORS Configuration Not Mentioned Anywhere
**Location:** `tasks_frontend/TASK_FE_11_fastapi_static.md`

In development, the Next.js dev server runs on port 3000 and makes `fetch` requests to FastAPI on port 8000. Without CORS headers on FastAPI, all API requests from the browser will be blocked. No task or spec mentions adding `CORSMiddleware` to FastAPI.

**Fix:** Add CORS configuration to TASK_FE_11 (the integration task). FastAPI must allow `http://localhost:3000` in dev; in prod, `/app` is same-origin so no CORS is needed.

**Fixed in:** `tasks_frontend/TASK_FE_11_fastapi_static.md`

---

### R5 — Redis Channel Cleanup Not Specified
**Location:** `docs/architecture.md` Section 10.5, `tasks_frontend/TASK_FE_10_backend_conversation_api.md`

Redis pub/sub channels (`conv:{id}`, `run:{id}`) are created when a job starts and WS clients subscribe. There is no spec for:
- When channels are unsubscribed (on WS disconnect — but who removes the channel key?).
- What happens if a WS client reconnects mid-stream (it misses frames published during disconnection).
- Channel TTL / expiry policy for abandoned channels.

In long-running deployments, orphaned channel subscriptions accumulate memory in Redis.

**Fix:** Specify that the WS handler unsubscribes on disconnect; channels have no server-side TTL (Redis pub/sub channels are transient and disappear when the last subscriber leaves — this is correct default behavior, no extra cleanup needed). Add a note about missed frames on reconnect: the client should re-fetch history via `GET /conversations/{id}/messages` after reconnecting.

**Fixed in:** `tasks_frontend/TASK_FE_10_backend_conversation_api.md`

---

### R6 — Missing Test Infrastructure Spec for Frontend
**Location:** `tasks_frontend/TASK_FE_02_api_client.md`, `tasks_frontend/TASK_FE_06_websocket.md`

TASK_FE_02 and FE_06 reference "unit tests" and "mock fetch" but don't specify the test framework or toolchain. Without a specified setup, each developer makes different choices.

**Fix:**
- Specify: Jest + React Testing Library + msw for component/hook unit tests.
- Add `frontend/src/mocks/` directory to TASK_FE_02 scope.
- Add a `frontend/jest.config.ts` and `frontend/jest.setup.ts` to TASK_FE_01 scaffold.

**Fixed in:** `tasks_frontend/TASK_FE_01_scaffold.md`, `tasks_frontend/TASK_FE_02_api_client.md`

---

### R7 — `StreamlitEmbed` `runId` Prop Is an Integration Gap
**Location:** `tasks_frontend/TASK_FE_09_visualization.md`

`StreamlitEmbed` accepts a `runId` prop and appends `?run_id={runId}` to the Streamlit URL. However, the existing Streamlit app (`src/streamlit/`) reads from static files on disk — it has no mechanism to accept or respond to a `run_id` query param. The embed would silently show the wrong run's data.

**Fix:** Remove `runId` prop from `StreamlitEmbed` in the task spec. Instead, note that the Streamlit app must be extended (in a separate backend task) to accept `run_id` before this feature can work. Mark it as out of scope for TASK_FE_09; TASK_FE_09 embeds the Streamlit app without a run filter.

**Fixed in:** `tasks_frontend/TASK_FE_09_visualization.md`

---

### R8 — `DELETE /conversations/{id}` Endpoint Missing
**Location:** `docs/specs/api_contracts.md`

Users will want to delete chat history. Only GET and POST are defined for conversations. Without DELETE, the conversation list grows unboundedly and there is no user-facing way to clear history.

**Fix:** Add `DELETE /conversations/{id}` endpoint that soft-deletes the conversation (sets a `deleted_at` timestamp) and cascades to `ChatMessage` records. `GET /conversations` must filter out deleted conversations.

**Fixed in:** `docs/specs/api_contracts.md`, `docs/specs/data_models.md`

---

### R9 — `GET /runs/{run_id}` Response Missing `conversation_id`
**Location:** `docs/specs/api_contracts.md`

When viewing `/runs/[run_id]`, the frontend may want to link back to the conversation that triggered the run ("View in conversation"). This reverse link is impossible without `conversation_id` in the run detail response.

**Fix:** Add `conversation_id: string | null` and `triggering_message_id: string | null` to the `GET /runs/{run_id}` 200 response body.

**Fixed in:** `docs/specs/api_contracts.md`

---

### R10 — No Mock Mode for WebSocket in Frontend Tests
**Location:** `tasks_frontend/TASK_FE_06_websocket.md`

TASK_FE_06 says "Tested end-to-end with a running FastAPI server" for the Definition of Done. WebSocket hooks are untestable in isolation without a mock WS server. msw v2 supports WebSocket mocking; without it, the hooks can only be integration-tested.

**Fix:** Add mock WebSocket server setup (msw `ws` handler) to TASK_FE_06 acceptance criteria and test infrastructure.

**Fixed in:** `tasks_frontend/TASK_FE_06_websocket.md`

---

## Optional Improvements

### O1 — Database Indexes for `ChatMessage` Not Specified
`ChatMessage` will be the highest-volume table in the schema. Queries by `conversation_id` (for history) and `created_at` (for ordering) will be frequent. No indexes are specified in `data_models.md`.

**Suggestion:** Add composite index `(conversation_id, created_at)` to `ChatMessage`. Add index `(conversation_id)` to `Conversation` and `(created_by)` to `Conversation`.

---

### O2 — Accessibility Not Mentioned
None of the frontend tasks mention ARIA labels, keyboard navigation, focus management, or screen reader support. The chat input, conversation list, and run status table all require accessibility markup for production quality.

**Suggestion:** Add a one-line accessibility requirement to each UI task: "All interactive elements must have ARIA labels and be keyboard-accessible."

---

### O3 — OpenAI Agents SDK Version Not Pinned
CLAUDE.md lists "OpenAI Agents SDK" without a version. The SDK is pre-1.0 and changes rapidly. A version upgrade could break `dispatch_from_chat()`.

**Suggestion:** Pin the SDK version in `requirements.txt` / `pyproject.toml` and add a note in CLAUDE.md.

---

### O4 — No Visual Regression / Storybook Story Requirement
Components like `ToolCallCard`, `RunStatusPanel`, and `AgentMessage` have complex visual states. Without Storybook stories or snapshot tests, visual regressions are undetectable.

**Suggestion:** Add Storybook to TASK_FE_01 as an optional dev dependency, with a story per component added in each subsequent task.

---

### O5 — WebSocket Connection Limit for Production
No guidance on max concurrent WebSocket connections per server instance. At scale, each active run and conversation holds one WS connection open. A single ECS task with default settings can handle ~1000 concurrent WS connections; beyond that, scale-out is needed.

**Suggestion:** Add a note in `docs/architecture.md` Section 10.5 that production deployments should configure Uvicorn workers and set a max WS connection limit per instance.

---

### O6 — `useConversations()` Cache Invalidation Not Made Explicit
TASK_FE_04 says "Conversation list in sidebar shows 20 most recent" via `useConversations()`. But when "New Chat" creates a new conversation, the query cache must be invalidated to show the new entry. This invalidation pattern is mentioned in TASK_FE_02 comment but not in the task acceptance criteria where it matters (TASK_FE_04).

**Suggestion:** Add to TASK_FE_04 acceptance criteria: "After 'New Chat' POST /conversations, `['conversations']` React Query cache is invalidated and the new conversation appears in the sidebar without a page reload."

---

## Summary of Fixes Applied

All critical issues (C1–C7) and recommended changes (R1–R10) have been applied to the relevant spec and task files. No implementation code was written.

| Issue | File(s) Fixed |
|---|---|
| C1 — LLM sample_id hallucination | `tool_contracts.md`, `safety_policy.md` |
| C2 — Missing streaming spec | `tool_contracts.md` |
| C3 — ChatMessage commit timing | `TASK_FE_10` |
| C4 — Missing rate limit | `api_contracts.md` |
| C5 — No API mocking (msw) | `TASK_FE_01`, `TASK_FE_02` |
| C6 — WS auth inconsistency | `api_contracts.md` |
| C7 — Missing audit FK on AnalysisRun | `data_models.md`, `api_contracts.md` |
| R1 — content max length in API | `api_contracts.md` |
| R2 — title update behavior | `data_models.md` |
| R3 — ToolCallCard.summary source | `tool_contracts.md` |
| R4 — CORS missing | `TASK_FE_11` |
| R5 — Redis channel cleanup | `TASK_FE_10` |
| R6 — Test framework not specified | `TASK_FE_01`, `TASK_FE_02` |
| R7 — StreamlitEmbed runId gap | `TASK_FE_09` |
| R8 — DELETE /conversations missing | `api_contracts.md`, `data_models.md` |
| R9 — conversation_id in run response | `api_contracts.md` |
| R10 — No mock WS in tests | `TASK_FE_06` |
