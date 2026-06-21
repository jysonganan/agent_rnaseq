# TASK_FE_05 — Chat View (Conversation Thread)

## Goal
Build the full chat interface: a scrollable conversation thread showing user messages and agent responses, with Markdown rendering and a message input box.

## Requirements
- Route: `/chat/[conversation_id]`
- On mount: fetch conversation history via `GET /conversations/{id}/messages`
- Conversation thread: scrollable list of message bubbles (user / assistant / tool roles)
- User messages: right-aligned, plain text, gray bubble
- Assistant messages: left-aligned, Markdown-rendered via `react-markdown`, white bubble
- Tool messages: left-aligned, collapsible `ToolCallCard` (see TASK_FE_06)
- Message input: `<textarea>` at bottom; Submit on Enter (Shift+Enter for newline); disabled while agent is responding
- On submit:
  1. Optimistically append the user message bubble
  2. `POST /conversations/{id}/messages` with `{ content }`
  3. Disable input and show "Agent is thinking…" indicator
  4. WebSocket stream (TASK_FE_06) delivers agent response tokens and tool events
- Scroll to bottom on new messages (smooth scroll)
- `/chat` (no conversation_id): show blank state with prompt examples and "Start a new conversation" CTA
- Blank state prompt examples (hardcoded):
  - "Run DE analysis comparing treatment vs control on my bulk RNA-seq samples"
  - "Run QC on all samples in project XYZ"
  - "Show me the top pathways from the last completed run"

## Files to Create
| File | Purpose |
|---|---|
| `frontend/src/app/chat/[conversation_id]/page.tsx` | Route page — fetches conversation, renders thread |
| `frontend/src/app/chat/page.tsx` | Blank state + example prompts |
| `frontend/src/components/chat/ConversationThread.tsx` | Scrollable message list |
| `frontend/src/components/chat/MessageBubble.tsx` | Container: dispatches to UserMessage/AgentMessage/ToolCallCard |
| `frontend/src/components/chat/UserMessage.tsx` | Right-aligned plain text bubble |
| `frontend/src/components/chat/AgentMessage.tsx` | Left-aligned Markdown bubble |
| `frontend/src/components/chat/MessageInput.tsx` | Textarea + submit button |
| `frontend/src/components/chat/ThinkingIndicator.tsx` | Animated "…" indicator while streaming |

## Markdown Rendering Rules (per safety_policy.md Rule 11.2)
```typescript
// Allowed elements only — no raw HTML passthrough
const allowedElements = [
  'p', 'br', 'strong', 'em', 'code', 'pre',
  'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a'
]
// <a> hrefs must start with https:// or mailto:
// Never use rehypeRaw plugin
```

## Acceptance Criteria
- [ ] Conversation history loads on mount from `GET /conversations/{id}/messages`
- [ ] User messages appear right-aligned, agent messages left-aligned
- [ ] `react-markdown` renders **bold**, *italic*, `code`, lists, and tables correctly
- [ ] No `<script>` or `<iframe>` tags can be injected via Markdown content
- [ ] Thread scrolls to bottom on each new message
- [ ] Input is disabled while agent is responding (i.e., while WebSocket is streaming)
- [ ] Pressing Enter submits; Shift+Enter inserts newline
- [ ] Empty input (whitespace only) does not submit
- [ ] Blank `/chat` route shows example prompts; clicking one pre-fills the input
- [ ] TypeScript strict: no `any`

## Definition of Done
All acceptance criteria pass. Tested manually: send a message, observe optimistic user bubble, observe streaming agent response rendering incrementally via WS (TASK_FE_06 must be complete for full streaming test; stub with static fixture response before that).

## Dependencies
TASK_FE_01, TASK_FE_02, TASK_FE_03, TASK_FE_04. TASK_FE_06 required for streaming; this task can use a mock/static response for initial implementation.

## Package Dependencies to Add
```
react-markdown
remark-gfm        # GitHub-flavored Markdown (tables, strikethrough)
```
