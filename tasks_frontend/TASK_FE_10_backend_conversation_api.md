# TASK_FE_10 — Backend: Conversation API Endpoints

## Goal
Add the `Conversation` and `ChatMessage` DB models and all `/conversations` REST endpoints and the `/ws/conversations/{id}/stream` WebSocket endpoint to the FastAPI backend. Add `OrchestratorAgent.dispatch_from_chat()`.

## Requirements
- New SQLAlchemy models: `Conversation`, `ChatMessage` (per `docs/specs/data_models.md` entities 12–13)
- New Pydantic schemas: `ConversationCreate`, `ConversationRead`, `ChatMessageRead`, `SendMessageRequest`, `SendMessageResponse`
- New API router: `src/api/routers/conversations.py` with all endpoints in `docs/specs/api_contracts.md` Conversations section
- New WebSocket handler: `src/api/websocket/conversation_stream.py` — subscribes to Redis pub/sub channel `conv:{conversation_id}` and forwards frames to the browser
- `OrchestratorAgent.dispatch_from_chat(input: ChatDispatchInput) -> ChatDispatchOutput` (per `docs/specs/tool_contracts.md` section 12)
- Redis pub/sub channel naming: `conv:{conversation_id}` for conversation stream, `run:{run_id}` for run log stream (existing)
- arq job: `process_chat_message(conversation_id, message_id, api_key_id)` — calls `dispatch_from_chat()` and publishes events to Redis

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
- MUST Pydantic-validate all parameters before creating `AnalysisRun`
- MUST NOT write LLM-generated numerical values to `AnalysisRun.run_config`
- Publish frames to Redis as JSON: `{ "type": "token"|"tool_call"|"stage_update"|"done"|"error", "payload": {...} }`
- Sanitize agent response content before writing to `ChatMessage.content` (strip file paths, credentials, raw stderr per safety_policy.md Rule 11.6)

## WebSocket Auth
The `/ws/conversations/{id}/stream` endpoint receives the API key as `?api_key=<key>`. The handler must:
1. Validate the key against `APIKey` table (same as REST middleware).
2. Verify the conversation belongs to that key's `id`.
3. Subscribe to `conv:{conversation_id}` Redis channel.
4. Forward all frames to the WebSocket client.
5. Unsubscribe and close cleanly on WS disconnect.

## Acceptance Criteria
- [ ] `POST /conversations` returns 201 with `id`, `title`, `created_at`
- [ ] `GET /conversations` returns only conversations created by the caller's API key
- [ ] `POST /conversations/{id}/messages` with valid content: creates `ChatMessage(role=user)`, enqueues arq task, returns 202 with `message_id` and `run_id` (null if clarification needed)
- [ ] `GET /conversations/{id}/messages` returns messages in chronological order
- [ ] WS `/ws/conversations/{id}/stream` rejects with 403 if `api_key` param is missing or invalid
- [ ] WS forwards all Redis frames for the conversation in order
- [ ] `dispatch_from_chat()` with a resolvable intent creates `AnalysisRun` and returns `run_id`
- [ ] `dispatch_from_chat()` with an ambiguous intent returns `needs_clarification=True` and no `run_id`
- [ ] `ChatMessage.content` for assistant messages contains no raw file paths or credentials (automated assertion in tests)
- [ ] Pydantic validation error on malformed `POST /conversations/{id}/messages` body returns 422
- [ ] New ORM models have Alembic migration generated

## Definition of Done
All acceptance criteria pass. Integration tests (`pytest tests/ -v`) cover: create conversation, send resolvable message (dry_run=True), send ambiguous message, WS stream receives frames in correct order.

## Dependencies
TASK_09_agent_layer_core (OrchestratorAgent base exists), TASK_11_fastapi_service (router registration pattern), TASK_13_aws_integration (arq worker exists). All existing backend tasks must be complete.

## Safety Checklist
- [ ] No LLM-generated numerics in `AnalysisRun.run_config`
- [ ] `ChatMessage.content` sanitized before DB write
- [ ] WS auth validated before channel subscription
- [ ] API key never logged or included in error responses
