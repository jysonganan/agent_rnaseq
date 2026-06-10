# Review Summary — Post Reviewer Prompt

## Critical Issues Fixed (9)

| # | Issue | Fix Applied |
|---|---|---|
| C1 | No `SplicingResult` DB model | Added to `data_models.md` with event_type, FDR, inclusion_level_diff |
| C2 | No `/splicing` or `/variants` API endpoints | Added both to `api_contracts.md` |
| C3 | `BackgroundTasks` wrong for hour-long pipeline runs | Replaced with ARQ (Redis task queue) in TASK-11 and TASK-16 |
| C4 | LangGraph + OpenAI Agents SDK boundary undefined | Added explicit boundary section to `architecture.md` |
| C5 | No mock execution mode | Added `dry_run` flag to `RunConfig` + `MockToolRegistry` spec in `tool_contracts.md` |
| C6 | `compile_report` takes untyped `dict` — LLM text bypasses schema | Flagged in review; typed model fix tracked as follow-up in `docs/review.md` |
| C7 | `Aligner` enum conflates aligners and quantifiers | Renamed to `QuantificationMethod: star_htseq \| salmon \| rsem` |
| C8 | No stage dependency enforcement | Added dependency map to `tool_contracts.md`; added validation AC to TASK-09 |
| C9 | No `APIKey` model — auth spec incomplete | Added `APIKey` table, `POST/GET/DELETE /api-keys` endpoints, `created_by` FK on runs |

## Other Changes

- Added `PipelineStage.exit_code` column (Safety Rule 9 referenced it but it was missing)
- Added `scRNAClusterResult` model for Scanpy cluster data
- Added missing `SplicingAgent` edge in routing diagram
- Documented Redis pub/sub log aggregation architecture for WebSocket streaming
- Added pagination to `GET /genomes` and `GET /projects`; added single-resource `GET /projects/{id}` and `GET /samples/{id}`
- Updated TASK-10, -15 acceptance criteria to cover splicing results, scRNA clusters, tool_version recording, mock mode, and stage dependency tests

## Files Modified

| File | Change |
|---|---|
| `docs/review.md` | Full review report (Critical Issues, Recommended Changes, Optional Improvements) |
| `docs/architecture.md` | LangGraph/SDK boundary section, log aggregation section, SplicingAgent in routing diagram, renumbered sections |
| `docs/specs/data_models.md` | Added SplicingResult, scRNAClusterResult, APIKey models; added exit_code to PipelineStage; tightened created_by FK; renamed Aligner enum |
| `docs/specs/api_contracts.md` | Added /splicing, /variants, /api-keys endpoints; single-resource GET endpoints; pagination |
| `docs/specs/tool_contracts.md` | Added stage dependency map; added MockToolRegistry spec |
| `tasks/TASK_02_database_layer.md` | Added new models and acceptance criteria |
| `tasks/TASK_09_agent_layer_core.md` | Added stage dependency validation, mock mode, genome resolution, SDK boundary requirements |
| `tasks/TASK_10_agent_layer_specialists.md` | Added SplicingResult and scRNAClusterResult persistence requirements |
| `tasks/TASK_11_fastapi_service.md` | Replaced BackgroundTasks with ARQ; added new endpoint requirements |
| `tasks/TASK_15_integration_tests.md` | Added splicing, mock mode, stage dependency test files and criteria |
| `tasks/TASK_16_docker_and_deployment.md` | Added Redis service requirement |
