# TASK_FE_07 — Run Status Panel

## Goal
Build the run detail view: per-stage progress bars, a live status display while the run is active, and artifact download links when the run completes.

## Requirements
- Route: `/runs/[run_id]`
- Fetches run detail via `GET /runs/{run_id}` (uses `useRun(id)` hook with auto-polling)
- `RunStatusPanel` component:
  - Run name, status badge, pipeline type, created/started/completed timestamps
  - Progress bar: `completed_stages / total_stages` as a fraction
  - Per-stage table: stage name, tool name, status badge, started_at, completed_at
  - Artifact section: grouped by artifact type, each with size and download button
- Polling: while run status is `pending` or `running`, refresh every 3 s
- Log stream: when run is active, optionally show last 20 log lines from `useRunLogStream`
- Cancel button: shown only when status is `pending` or `running`; calls `POST /runs/{id}/cancel`

## Files to Create
| File | Purpose |
|---|---|
| `frontend/src/app/runs/[run_id]/page.tsx` | Route page |
| `frontend/src/components/runs/RunStatusPanel.tsx` | Full status panel |
| `frontend/src/components/runs/StageProgressBar.tsx` | Overall progress bar (fraction complete) |
| `frontend/src/components/runs/StageTable.tsx` | Per-stage table rows |
| `frontend/src/components/runs/StageStatusBadge.tsx` | Badge: pending / running / completed / failed / skipped |
| `frontend/src/components/runs/ArtifactList.tsx` | Grouped artifact list |
| `frontend/src/components/runs/ArtifactDownloadLink.tsx` | Calls `/artifacts/{id}/download`, opens URL |
| `frontend/src/components/runs/RunLogTail.tsx` | Last N log lines from useRunLogStream |
| `frontend/src/components/runs/CancelRunButton.tsx` | Confirm-then-cancel button |

## Stage Status Badge Colors
| Status | Color |
|---|---|
| pending | gray |
| running | blue (animated pulse) |
| completed | green |
| failed | red |
| skipped | yellow |

## Artifact Download Flow
```
User clicks download →
  GET /runs/{run_id}/artifacts/{artifact_id}/download
  → { download_url, expires_in_seconds }
  → window.open(download_url, '_blank')
```
If the response takes >2 s, show a loading spinner on the button.

## Acceptance Criteria
- [ ] Run metadata (name, status, timestamps) renders correctly from API response
- [ ] Progress bar reflects `stages.filter(s => s.status === 'completed').length / stages.length`
- [ ] Each stage row shows correct status badge with appropriate color
- [ ] Running stage has animated pulse badge
- [ ] `useRun(id)` polls every 3 s while status is `pending` or `running`; polling stops on terminal status
- [ ] Artifact download button opens the presigned URL in a new tab
- [ ] Download button shows spinner during the presigned URL fetch
- [ ] Cancel button is visible only for `pending` / `running` runs
- [ ] Cancel button shows confirmation dialog (shadcn/ui `AlertDialog`) before calling API
- [ ] Log tail shows last 20 lines from WS stream while run is active
- [ ] TypeScript strict: no `any`

## Definition of Done
All acceptance criteria pass. Tested with a `dry_run=True` run from the demo notebook: status panel reflects stage completions in real time.

## Dependencies
TASK_FE_01–TASK_FE_04, TASK_FE_06 (log stream hook).
