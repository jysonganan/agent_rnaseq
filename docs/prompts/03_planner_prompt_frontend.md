You are the architect/planner for adding front-end for this repo.

Review:

CLAUDE.md
docs/architecture.md
docs/specs/*.md
tasks/*.md
docs/*.md

You will add:

Chat UI:
- A chat interface where users describe what they want in natural language
  (e.g. "run DE analysis on these samples comparing treatment vs control")
  and the Orchestrator Agent interprets the request, selects tools and parameters,
  and launches the appropriate pipeline stages.
- Built with React / Next.js (TypeScript)
- Tailwind CSS for styling
- shadcn/ui component library
- React Query for server state management
- WebSocket client connects to FastAPI `/ws/runs/{run_id}/logs` to stream agent
  messages, tool call events, and stage progress back to the user in real time;
  FastAPI acts as the bridge between the frontend and the Orchestrator Agent
- Conversation thread UI: user messages, streaming agent responses, tool call cards
  showing tool name / status / summary
- Run status panel: live per-stage progress bar, artifact download links
- Markdown rendering for agent responses (react-markdown)
- Embedded Streamlit iframe for interactive visualization plots
- Authentication: API key entry on first load, stored in localStorage
- Routing: Next.js App Router (chat view, run history view, genome browser view)
- Build output served as static files by FastAPI under `/app` (or standalone Next.js server)

Do not implement application code yet.

Generate an implementation plan. 

Include:

1. High-level architecture.
2. Major components.
3. Tool interfaces.
4. Task breakdown.
5. Risks and assumptions.
6. Testing strategy.

Generate implementation tasks under tasks_frontend/.

Each task should:

- have clear scope,
- contain acceptance criteria,
- be independently testable,
- modify as few components as possible.
- Goal
- Requirements
- Files to create/edit
- Acceptance criteria
- Definition of Done

Modify or update if needed:

1. CLAUDE.md
2. docs/architecture.md
3. docs/specs/data_models.md
4. docs/specs/api_contracts.md
5. docs/specs/tool_contracts.md
6. docs/specs/safety_policy.md
