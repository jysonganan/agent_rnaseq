# TASK_FE_01 — Frontend Scaffold

## Goal
Bootstrap the Next.js 14 (App Router) project with TypeScript, Tailwind CSS, shadcn/ui, and ESLint. This is the foundation all other frontend tasks build on.

## Requirements
- Next.js 14 with App Router and `output: 'export'` for static file generation
- TypeScript strict mode (`"strict": true`)
- Tailwind CSS v3
- shadcn/ui component library (pre-installs Button, Input, Card, Badge, Dialog, ScrollArea, Separator, Tooltip)
- ESLint with `eslint-config-next`
- `.env.example` documenting all required environment variables
- `next.config.ts` configures `basePath: '/app'` so the static build can be mounted under `/app` by FastAPI

## Files to Create
| File | Purpose |
|---|---|
| `frontend/package.json` | Dependencies and npm scripts (including `test` script) |
| `frontend/tsconfig.json` | TypeScript config, strict mode |
| `frontend/next.config.ts` | Next.js config: `output: 'export'`, `basePath: '/app'` |
| `frontend/tailwind.config.ts` | Tailwind config with shadcn/ui content paths |
| `frontend/postcss.config.js` | PostCSS for Tailwind |
| `frontend/components.json` | shadcn/ui registry config |
| `frontend/.eslintrc.json` | ESLint: next/core-web-vitals rules |
| `frontend/.env.example` | Documents `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_STREAMLIT_URL` |
| `frontend/src/app/layout.tsx` | Root layout: `<html>`, `<body>`, font, metadata |
| `frontend/src/app/page.tsx` | Root page: redirects to `/chat` |
| `frontend/src/app/globals.css` | Tailwind directives + shadcn/ui CSS variables |
| `frontend/src/components/ui/` | Auto-generated shadcn/ui component files |
| `frontend/jest.config.ts` | Jest config: jsdom environment, path aliases |
| `frontend/jest.setup.ts` | `@testing-library/jest-dom` setup |

## Test Infrastructure
Unit test stack: **Jest + React Testing Library + msw** (Mock Service Worker).
- `jest.config.ts` uses `next/jest` transformer and `jsdom` test environment.
- `jest.setup.ts` imports `@testing-library/jest-dom/extend-expect`.
- msw is configured in TASK_FE_02; this task only adds the Jest scaffolding.
- `npm test` runs `jest --passWithNoTests` (no tests yet at scaffold stage).

## Environment Variables
```
NEXT_PUBLIC_API_URL=http://localhost:8000      # FastAPI base URL (dev)
NEXT_PUBLIC_STREAMLIT_URL=http://localhost:8501 # Streamlit server URL
```

## Acceptance Criteria
- [ ] `cd frontend && npm install` completes without errors
- [ ] `npm run dev` starts dev server at `localhost:3000` with no compile errors
- [ ] `npm run build` produces `frontend/out/` directory (static export)
- [ ] `npm run lint` passes with zero warnings
- [ ] `npm test` exits 0 (no tests yet, but Jest runs cleanly)
- [ ] TypeScript: `npx tsc --noEmit` exits 0
- [ ] A sample page using `Button` from shadcn/ui renders correctly at `localhost:3000`
- [ ] Tailwind utility classes apply correctly (e.g., `bg-blue-500 text-white`)
- [ ] `basePath: '/app'` is set in next.config.ts

## Definition of Done
All acceptance criteria pass. CI runs `npm install`, `npm run lint`, and `npm run build` without errors. No implementation beyond scaffold files — no business logic yet.

## Dependencies
None — this is the first frontend task.

## Notes
- Do not set `output: 'export'` if it breaks dynamic routes during development; use `output: 'export'` only for production build. The dev server does not export.
- shadcn/ui uses CSS variables for theming; ensure `globals.css` includes the `:root` variable block from shadcn/ui init output.
