# TASK_FE_06 — WebSocket Hooks & Tool Call Cards

## Goal
Implement real-time streaming of agent events (response tokens, tool calls, stage updates) from the FastAPI WebSocket endpoints, and render them as interactive cards in the chat thread.

## Requirements
- `useConversationStream(conversationId)`: connects to `WS /ws/conversations/{id}/stream?api_key=<key>`
- `useRunLogStream(runId)`: connects to `WS /ws/runs/{id}/logs?api_key=<key>`
- Both hooks:
  - Connect on mount, disconnect on unmount
  - Exponential back-off reconnect: 1 s, 2 s, 4 s — then stop and mark `status: "error"`
  - Expose: `{ status: "connecting" | "connected" | "error", messages: WsFrame[] }`
- `useConversationStream` handles frame types (see `docs/specs/api_contracts.md`):
  - `token` → calls `onToken(token: string)` callback to append to current agent message
  - `tool_call` → calls `onToolCall(payload)` to create/update `ToolCallCard`
  - `stage_update` → calls `onStageUpdate(payload)` to update `StageProgressIndicator`
  - `done` → marks streaming complete, re-enables input
  - `error` → shows error banner in thread
- `ToolCallCard` component:
  - Shows: tool name (monospace), status badge (running / completed / failed), collapsible output summary
  - Running: animated spinner
  - Completed: green check, summary text
  - Failed: red X, error message
- `StageProgressIndicator`: compact inline pill showing current stage name and status

## Files to Create
| File | Purpose |
|---|---|
| `frontend/src/hooks/useConversationStream.ts` | WS hook for conversation agent stream |
| `frontend/src/hooks/useRunLogStream.ts` | WS hook for run log stream |
| `frontend/src/lib/websocket.ts` | Low-level WS connection manager (used by both hooks) |
| `frontend/src/components/chat/ToolCallCard.tsx` | Tool invocation card |
| `frontend/src/components/chat/StageProgressIndicator.tsx` | Inline stage status pill |
| `frontend/src/components/common/ConnectionStatus.tsx` | Dot indicator: connected/disconnected/error |

## WebSocket Frame Types
```typescript
// In types.ts (added by this task)
type WsFrameType = "token" | "tool_call" | "stage_update" | "done" | "error"

interface WsFrame {
  type: WsFrameType
  payload: TokenPayload | ToolCallPayload | StageUpdatePayload | DonePayload | ErrorPayload
}

interface TokenPayload    { message_id: string; token: string }
interface ToolCallPayload { message_id: string; tool_name: string; status: string; summary: string | null }
interface StageUpdatePayload { run_id: string; stage_name: string; status: string }
interface DonePayload     { message_id: string; run_id: string | null }
interface ErrorPayload    { message: string }
```

## Reconnect Strategy
```
attempt 1 → wait 1s → reconnect
attempt 2 → wait 2s → reconnect
attempt 3 → wait 4s → reconnect
attempt 4 → set status="error", stop trying
```
Show `ConnectionStatus` indicator in chat thread when disconnected or errored.

## Acceptance Criteria
- [ ] `useConversationStream` connects to the correct URL with `?api_key=` param
- [ ] Token frames accumulate in the current agent message bubble (streaming effect)
- [ ] ToolCallCard shows spinner for `running`, check for `completed`, X for `failed`
- [ ] ToolCallCard output summary is collapsible (click to expand)
- [ ] StageProgressIndicator updates correctly from `stage_update` frames
- [ ] On `done` frame, input is re-enabled and streaming indicator disappears
- [ ] On WS disconnect, reconnect attempt uses exponential back-off
- [ ] After 3 failed reconnects, error state is shown; user can click "Reconnect" to try again
- [ ] WS closes cleanly on component unmount (no memory leaks)
- [ ] API key never logged to console
- [ ] TypeScript strict: no `any`

## Mock WebSocket Testing
Unit tests for WebSocket hooks must not require a live FastAPI server. Use msw v2's WebSocket handler support:

```typescript
// In frontend/src/mocks/handlers.ts (added by this task)
import { ws } from 'msw'

export const conversationStreamHandler = ws(
  `${process.env.NEXT_PUBLIC_API_URL}/ws/conversations/:id/stream`,
  ({ client }) => {
    // Emit fixture frames on connection
    client.send(JSON.stringify({ type: 'token', payload: { message_id: 'uuid', token: 'Hello' } }))
    client.send(JSON.stringify({ type: 'done', payload: { message_id: 'uuid', run_id: null } }))
  }
)
```

**Acceptance Criteria (added):**
- [ ] Jest test for `useConversationStream`: mock WS server emits token + done frames; hook accumulates tokens and sets status to "connected" then back to idle after done
- [ ] Jest test for reconnect back-off: mock WS server closes immediately on connect; verify hook attempts 3 reconnects with increasing delays, then sets `status: "error"`
- [ ] Jest test for unmount cleanup: verify WS is closed on unmount (no open handle warning in Jest)

## Definition of Done
All acceptance criteria (including mock WS tests) pass. End-to-end tested with a running FastAPI server.

## Dependencies
TASK_FE_01, TASK_FE_02, TASK_FE_03, TASK_FE_05.
