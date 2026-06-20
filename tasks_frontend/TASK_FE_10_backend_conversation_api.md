# TASK_FE_10 — Backend: Conversation API Endpoints

## Goal
Add the `Conversation` and `ChatMessage` DB models and all `/conversations` REST endpoints and the `/ws/conversations/{id}/stream` WebSocket endpoint to the FastAPI backend. Add `OrchestratorAgent.dispatch_from_chat()`.

## Requirements
- New SQLAlchemy models: `Conversation`, `ChatMessage` (per `docs/specs/data_models.md` entities 12–13)
  - `Conversation` has `deleted_at` for soft-delete support
  - `AnalysisRun` gains nullable `conversation_id` and `triggering_message_id` FKs (audit trail)
- New Pydantic schemas: `ConversationCreate`, `ConversationRead`, `ChatMessageRead`, `SendMessageRequest` (content: str, min_length=1, max_length=4000), `SendMessageResponse`
- New API router: `src/api/routers/conversations.py` with all endpoints in `docs/specs/api_contracts.md` Conversations section (including `DELETE /conversations/{id}`)
- New WebSocket handler: `src/api/websocket/conversation_stream.py` — subscribes to Redis pub/sub channel `conv:{conversation_id}` and forwards frames to the browser; unsubscribes cleanly on WS disconnect
- `OrchestratorAgent.dispatch_from_chat(input: ChatDispatchInput) -> ChatDispatchOutput` (per `docs/specs/tool_contracts.md` section 12) with streaming completions (`stream=True`)
- Redis pub/sub channel naming: `conv:{conversation_id}` for conversation stream, `run:{run_id}` for run log stream (existing)
- arq job: `process_chat_message(conversation_id, message_id, api_key_id)` — calls `dispatch_from_chat()` and publishes events to Redis
- Rate limiting: `POST /conversations/{id}/messages` enforces 10 requests/minute per API key (same limit as `POST /runs`)
- CORS middleware: allow `http://localhost:3000` in development (controlled by `CORS_ALLOW_ORIGINS` env var)

## Files to Create/Edit
| File | Action | Purpose |
|---|---|---|
| `src/db/models.py` | Edit | Add `Conversation`, `ChatMessage` ORM models |
| `src/schemas/conversation.py` | Create | Pydantic schemas for conversations and messages |
| `src/api/routers/conversations.py` | Create | REST endpoints: CRUD + message POST |
| `src/api/websocket/conversation_stream.py` | Create | WS `/ws/conversations/{id}/stream` |
| `src/agents/orchestrator.py` | Edit | Add `dispatch_from_chat()` method |
| `src/workers/tasks.py` | Edit | Add `process_chat_message` arq task |
| `src/api/main.py` | Edit | Register conversations router and WS route |
| `docs/specs/data_models.md` | (already updated by planner) | — |
| `docs/specs/api_contracts.md` | (already updated by planner) | — |

## Conversation Router Endpoints
```
POST   /conversations
GET    /conversations
GET    /conversations/{conversation_id}
GET    /conversations/{conversation_id}/messages
POST   /conversations/{conversation_id}/messages
```
All require `Authorization: Bearer <key>` and scope responses to the caller's API key (`created_by` FK).

## `dispatch_from_chat` Behaviour
See `docs/specs/tool_contracts.md` section 12 for the full contract. Key constraints:
- MUST query DB for available samples and genomes before calling LLM; pass them as structured list in system prompt
- LLM MUST select sample_ids and genome_id from provided UUID lists only; re-validate all IDs against DB after selection
- MUST use `stream=True` completions; publish each token chunk as a `token` frame to Redis before accumulating
- MUST NOT write LLM-generated numerical values to `AnalysisRun.run_config`
- MUST set `AnalysisRun.conversation_id` and `AnalysisRun.triggering_message_id` for runs created via chat
- Publish frames to Redis as JSON: `{ "type": "token"|"tool_call"|"stage_update"|"done"|"error", "payload": {...} }`
- `tool_call` frame `summary` field MUST be a JSON excerpt of the validated `ToolOutput` Pydantic model, not LLM prose
- Write `ChatMessage(role=assistant)` to DB only after the full response is accumulated and `done` frame has been published (atomic commit; no partial writes)
- Sanitize agent response content before writing to `ChatMessage.content` (strip file paths, credentials, raw stderr per safety_policy.md Rule 11.6)

## Redis Channel Lifecycle
- `conv:{conversation_id}` channel: pub/sub channels are transient in Redis — they exist only while there are active subscribers. No explicit cleanup is needed. The WS handler unsubscribes on disconnect, which removes the subscriber. If no client is connected when frames are published, frames are silently dropped (no persistence).
- On WS reconnect, the client must call `GET /conversations/{id}/messages` to catch up on messages committed to DB during disconnection; missed in-flight frames are not replayed.

## WebSocket Auth
The `/ws/conversations/{id}/stream` endpoint receives the API key as `?api_key=<key>`. The handler must:
1. Validate the key against `APIKey` table (same as REST middleware).
2. Verify the conversation belongs to that key's `id`.
3. Subscribe to `conv:{conversation_id}` Redis channel.
4. Forward all frames to the WebSocket client.
5. Unsubscribe and close cleanly on WS disconnect.

## Acceptance Criteria
- [ ] `POST /conversations` returns 201 with `id`, `title: "New conversation"`, `created_at`
- [ ] `DELETE /conversations/{id}` sets `deleted_at`; conversation no longer appears in `GET /conversations`
- [ ] `GET /conversations` returns only conversations owned by caller's key, excluding soft-deleted
- [ ] `POST /conversations/{id}/messages` with `content` > 4000 chars returns 422
- [ ] `POST /conversations/{id}/messages` with blank `content` returns 422
- [ ] `POST /conversations/{id}/messages` with valid content: creates `ChatMessage(role=user)`, enqueues arq task, returns 202 with `message_id` and `run_id` (null if clarification needed)
- [ ] `POST /conversations/{id}/messages` on first message updates `Conversation.title` to first 60 chars of content
- [ ] `GET /conversations/{id}/messages` returns messages in chronological order
- [ ] WS `/ws/conversations/{id}/stream` rejects with 403 if `api_key` param is missing or invalid
- [ ] WS forwards all Redis frames for the conversation in order
- [ ] WS unsubscribes from Redis channel cleanly on client disconnect
- [ ] `dispatch_from_chat()` queries DB for samples and genomes before calling LLM; passes lists in system prompt
- [ ] `dispatch_from_chat()` rejects a hallucinated sample UUID (not in DB) with `ToolValidationError` before creating `AnalysisRun`
- [ ] `dispatch_from_chat()` with a resolvable intent creates `AnalysisRun` with `conversation_id` and `triggering_message_id` set
- [ ] `dispatch_from_chat()` with an ambiguous intent returns `needs_clarification=True` and no `run_id`; no `AnalysisRun` created
- [ ] Assistant `ChatMessage` is written to DB only after `done` frame is published; crash before `done` leaves no partial record
- [ ] `tool_call` WS frames have `summary` derived from `ToolOutput` Pydantic model, not LLM text
- [ ] `ChatMessage.content` for assistant messages contains no raw file paths or credentials (automated assertion)
- [ ] `POST /conversations/{id}/messages` rate-limited to 10/minute per API key; returns 429 on excess
- [ ] CORS allows `http://localhost:3000` in dev; blocked in prod for non-matching origins
- [ ] Pydantic validation error on malformed request body returns 422
- [ ] New ORM models have Alembic migration generated

## Definition of Done
All acceptance criteria pass. Integration tests (`pytest tests/ -v`) cover: create conversation, send resolvable message (dry_run=True), send ambiguous message, WS stream receives frames in correct order.

## Dependencies
TASK_09_agent_layer_core (OrchestratorAgent base exists), TASK_11_fastapi_service (router registration pattern), TASK_13_aws_integration (arq worker exists). All existing backend tasks must be complete.

## Safety Checklist
- [ ] No LLM-generated numerics in `AnalysisRun.run_config`
- [ ] `ChatMessage.content` sanitized before DB write (no file paths, credentials, raw stderr)
- [ ] sample_ids and genome_id resolved from DB-provided lists, never from LLM free text
- [ ] All selected resource IDs re-validated against DB before RunConfig construction
- [ ] WS auth validated before channel subscription
- [ ] API key never logged or included in error responses
- [ ] `AnalysisRun.conversation_id` and `triggering_message_id` set for chat-originated runs
- [ ] `ChatMessage(role=assistant)` committed atomically after `done` frame; no partial writes
