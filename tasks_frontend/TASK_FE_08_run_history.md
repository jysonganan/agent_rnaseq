# TASK_FE_08 — Run History View

## Goal
Build a paginated list of past analysis runs with status filtering, so users can find and navigate to any previous run.

## Requirements
- Route: `/runs`
- Fetches `GET /runs` with optional `status` and `project_id` query params
- Paginated: 20 runs per page, "Load more" button (or URL-based pagination with `?page=`)
- Filter dropdown: All / Pending / Running / Completed / Failed / Cancelled
- Each run row shows: run name, status badge, pipeline type, created_at, completed_at (or "in progress")
- Click on row navigates to `/runs/[run_id]`
- Empty state message when no runs match
- `useRuns()` polls every 5 s if any run in the current page is non-terminal

## Files to Create
| File | Purpose |
|---|---|
| `frontend/src/app/runs/page.tsx` | Route page with filter state |
| `frontend/src/components/runs/RunList.tsx` | Scrollable list of RunListItem |
| `frontend/src/components/runs/RunListItem.tsx` | Single run row |
| `frontend/src/components/runs/RunStatusBadge.tsx` | Reusable status badge (shared with RunStatusPanel) |
| `frontend/src/components/runs/RunFilters.tsx` | Status filter dropdown + project filter input |

## Run List Item Layout
```
┌─────────────────────────────────────────────────────────┐
│ ctrl_vs_treatment_v1              [completed] bulk_rnaseq │
│ Created 2026-06-18 14:32  ·  Completed 2026-06-18 15:01  │
└─────────────────────────────────────────────────────────┘
```

## Acceptance Criteria
- [ ] `GET /runs` is called with correct `status` query param when filter is set
- [ ] "All" filter sends no `status` param
- [ ] Run rows display all required fields
- [ ] Clicking a row navigates to `/runs/[run_id]`
- [ ] "Load more" button appears when total > displayed count; appends next 20 runs
- [ ] Empty state ("No runs found") shown when API returns 0 results
- [ ] `useRuns()` stops polling when all visible runs are in terminal states
- [ ] `RunStatusBadge` is importable from `components/runs/RunStatusBadge.tsx` (used by both this task and TASK_FE_07)
- [ ] TypeScript strict: no `any`

## Definition of Done
All acceptance criteria pass. Verified with ≥2 runs in the database (one completed, one failed) from the demo setup.

## Dependencies
TASK_FE_01–TASK_FE_04.
