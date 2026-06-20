# TASK_FE_09 — Visualization Panel (Streamlit Iframe & Genome Browser)

## Goal
Embed the Streamlit visualization app and the UCSC genome browser as iframes within the frontend, accessible from the `/browser` route and as a panel within run detail pages.

## Requirements
- Route: `/browser` — dedicated full-screen visualization page
- `StreamlitEmbed`: iframe pointing at `NEXT_PUBLIC_STREAMLIT_URL`
- `GenomeBrowserEmbed`: iframe pointing at UCSC genome browser for a given genome build + optional coordinates
- Both iframes must use correct `sandbox` attributes (per `docs/specs/safety_policy.md` Rule 11.4)
- `VisualizationPanel`: tab interface (Streamlit | Genome Browser) embedded in `/browser`
- Optional: mini `StreamlitEmbed` shown within `/runs/[run_id]` when run has a `streamlit_data` artifact
- Loading spinner while iframes are loading (`onLoad` handler)
- Fallback message if `NEXT_PUBLIC_STREAMLIT_URL` is not set or iframe returns an error

## Files to Create
| File | Purpose |
|---|---|
| `frontend/src/app/browser/page.tsx` | Route page with VisualizationPanel |
| `frontend/src/components/visualization/VisualizationPanel.tsx` | Tabs: Streamlit / Genome Browser |
| `frontend/src/components/visualization/StreamlitEmbed.tsx` | Streamlit iframe component |
| `frontend/src/components/visualization/GenomeBrowserEmbed.tsx` | UCSC browser iframe component |

## StreamlitEmbed Props
```typescript
interface StreamlitEmbedProps {
  height?: number        // default 700
}
```

**Note:** A `runId` prop was considered but removed. The current Streamlit app reads from static files on disk and does not accept `run_id` as a query parameter. Adding `?run_id=` would silently show the wrong data. Run-specific Streamlit filtering requires a backend change to the Streamlit app (out of scope for this task).

## GenomeBrowserEmbed Props
```typescript
interface GenomeBrowserEmbedProps {
  genomeBuild: string    // e.g. "hg38"
  coords?: string        // e.g. "chr17:7,674,220-7,675,000"
  height?: number        // default 600
}
```

The UCSC browser URL is constructed as:
```
https://genome.ucsc.edu/cgi-bin/hgTracks?db={build}&position={coords}
```
This URL is the only place in the frontend where a full URL is constructed (UCSC is a well-known public resource).

## Sandbox Attributes
```html
<!-- Streamlit (same-origin in dev, cross-origin in prod) -->
<iframe sandbox="allow-scripts allow-same-origin allow-forms" ...>

<!-- UCSC (always cross-origin) -->
<iframe sandbox="allow-scripts allow-forms" ...>
```
Neither iframe gets `allow-top-navigation` or `allow-popups-to-escape-sandbox`.

## Acceptance Criteria
- [ ] `/browser` renders `VisualizationPanel` with Streamlit and Genome Browser tabs
- [ ] `StreamlitEmbed` renders iframe pointing at `NEXT_PUBLIC_STREAMLIT_URL`
- [ ] Loading spinner shows while iframe is loading; hides on `onLoad`
- [ ] If `NEXT_PUBLIC_STREAMLIT_URL` is not set, shows "Streamlit not configured" message instead of blank iframe
- [ ] `GenomeBrowserEmbed` constructs correct UCSC URL for given build and coordinates
- [ ] Both iframes have correct `sandbox` attributes per security policy
- [ ] Neither iframe has `allow-top-navigation` in sandbox
- [ ] TypeScript strict: no `any`

## Definition of Done
All acceptance criteria pass. Verified manually: Streamlit embedded in `/browser` shows the DE/GSEA/QC dashboards from the demo run.

## Dependencies
TASK_FE_01–TASK_FE_04.

## Notes
- `NEXT_PUBLIC_STREAMLIT_URL` is `http://localhost:8501` in dev; the Docker Compose Streamlit service is accessible at that address.
- The UCSC genome browser is a public external URL; do not proxy it.
