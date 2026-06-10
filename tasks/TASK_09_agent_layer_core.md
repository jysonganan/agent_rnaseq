# TASK-09: Agent Layer — Orchestrator & LangGraph State Machine

## Goal
Implement the Orchestrator agent and LangGraph `StateGraph` that routes between specialist sub-agents. This is the core routing engine for the pipeline.

## Requirements
- `RunState` and `StageState` typed LangGraph state schemas.
- `StateGraph` with nodes for each pipeline stage + conditional edges for routing.
- `OrchestratorAgent` using OpenAI Agents SDK: parses `RunConfig` from user message, validates it, dispatches to graph.
- LangGraph checkpointing: state snapshots persisted to DB (`AnalysisRun.agent_state`).
- Agent can resume an interrupted run from checkpoint.
- Intent parser: LLM extracts `RunConfig` from natural language, result validated by Pydantic before use.

## Files to Create
```
src/agents/
  __init__.py
  state.py             # RunState, StageState TypedDict for LangGraph
  orchestrator.py      # OrchestratorAgent: intent parsing, RunConfig validation, graph dispatch
  router.py            # LangGraph StateGraph definition + conditional edge logic
  base_agent.py        # BaseStageAgent: common interface, tool call wrapper, DB stage record management
tests/agents/
  __init__.py
  test_orchestrator.py
  test_router.py
  test_state.py
```

## Files to Edit
- `pyproject.toml` — add langgraph, openai-agents-sdk dependencies.
- `src/config.py` — add `OPENAI_API_KEY` setting.

## Acceptance Criteria
- [ ] `StateGraph` compiles without error and contains nodes for all 9 pipeline stages.
- [ ] Given `RunConfig` with `stages=["qc", "alignment"]`, router transitions QC → Alignment → END.
- [ ] Given `RunConfig` with `stages=["qc"]`, router goes QC → END without entering alignment node.
- [ ] Interrupted graph resumes from correct stage using DB checkpoint.
- [ ] `OrchestratorAgent` rejects LLM-extracted `RunConfig` with invalid `alpha` value before dispatching.
- [ ] `OrchestratorAgent` rejects `genome_id` that doesn't exist in DB.
- [ ] All LangGraph state transitions are unit tested with mocked sub-agent nodes.
- [ ] No LLM API calls made in unit tests (all mocked).

## Definition of Done
`pytest tests/agents/` green with all LLM calls mocked.
