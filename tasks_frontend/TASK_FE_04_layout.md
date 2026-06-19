# TASK_FE_04 — App Router Layout & Navigation

## Goal
Create the root application layout with a navigation sidebar and route stubs for all views. This establishes the navigational skeleton that all content tasks (FE_05–FE_09) will fill in.

## Requirements
- Root `layout.tsx` wraps all routes with `ReactQueryProvider` and `AuthContext`
- `AuthGuard` wraps the main content area (not the root layout itself, to avoid flash)
- Left sidebar: fixed width on desktop, collapsible on mobile (shadcn/ui `Sheet` for mobile drawer)
- Sidebar sections:
  - App logo / name at top
  - "New Chat" button
  - Scrollable conversation history list (uses `useConversations()`)
  - Divider
  - Nav links: Chat, Runs, Browser
  - "Sign out" button at bottom
- Active route highlighted in sidebar nav
- All routes are stubs (render placeholder `<h1>` text) except layout

## Files to Create
| File | Purpose |
|---|---|
| `frontend/src/app/layout.tsx` | Root layout: providers + AuthGuard + Sidebar + content area |
| `frontend/src/app/page.tsx` | Root `/` → redirect to `/chat` |
| `frontend/src/app/chat/page.tsx` | `/chat` stub — "New conversation" blank state |
| `frontend/src/app/chat/[conversation_id]/page.tsx` | Conversation thread stub |
| `frontend/src/app/runs/page.tsx` | Run history stub |
| `frontend/src/app/runs/[run_id]/page.tsx` | Run detail stub |
| `frontend/src/app/browser/page.tsx` | Genome browser / visualization stub |
| `frontend/src/components/layout/Sidebar.tsx` | Full sidebar component |
| `frontend/src/components/layout/NavLink.tsx` | Styled nav link with active-state highlight |
| `frontend/src/components/layout/MobileHeader.tsx` | Mobile top bar with hamburger button |

## Sidebar Layout
```
┌────────────────────┐
│  🧬 agent_rnaseq  │  ← App name / logo
│  [+ New Chat]      │  ← Button → POST /conversations
├────────────────────┤
│  Recent Chats      │  ← Section header
│  › DE analysis …  │  ← Conversation list (useConversations)
│  › QC bulk run …  │
│  …                 │
├────────────────────┤
│  [Chat]            │  ← NavLink /chat (active if /chat/*)
│  [Runs]            │  ← NavLink /runs
│  [Browser]         │  ← NavLink /browser
├────────────────────┤
│  [Sign out]        │  ← clearApiKey()
└────────────────────┘
```

## Acceptance Criteria
- [ ] `npm run build` succeeds with all route files present
- [ ] Root `/` redirects to `/chat` (using `next/navigation redirect`)
- [ ] Sidebar renders correctly on desktop (≥768px)
- [ ] On mobile (<768px), sidebar is hidden; hamburger button opens it as a Sheet
- [ ] Active route link is visually distinct (bold or background highlight)
- [ ] "New Chat" button calls `POST /conversations` and navigates to `/chat/{new_id}`
- [ ] Conversation list shows the 20 most recent conversations from `useConversations()`
- [ ] "Sign out" button calls `clearApiKey()` and redirects to root (triggers auth modal)
- [ ] TypeScript strict: no `any`

## Definition of Done
All acceptance criteria pass. Route stubs render without errors. Navigation works between all routes.

## Dependencies
TASK_FE_01, TASK_FE_02, TASK_FE_03.
