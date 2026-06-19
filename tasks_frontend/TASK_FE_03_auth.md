# TASK_FE_03 — API Key Authentication

## Goal
Implement the API key authentication flow: a modal prompts for the key on first visit, validates it against the backend, stores it in localStorage, and provides an `AuthContext` that all other components consume.

## Requirements
- `AuthContext` exposes: `apiKey: string | null`, `setApiKey(key)`, `clearApiKey()`
- `ApiKeyModal` is shown when `apiKey` is null; blocks rendering of all other UI
- Validation: `GET /health` with `Authorization: Bearer <key>`; 200 = valid, anything else = invalid
- Valid key stored in `localStorage['rnaseq_api_key']`
- On page reload, stored key is read from localStorage and validated against `/health` before restoring session (re-validates silently; if 401, clears key and shows modal)
- Any 401 response from any API call triggers `clearApiKey()` automatically (hooked into `apiFetch`)
- "Sign out" button (in Sidebar, added in TASK_FE_04) calls `clearApiKey()`
- Key never appears in URL params, POST bodies, or logged to console

## Files to Create
| File | Purpose |
|---|---|
| `frontend/src/contexts/AuthContext.tsx` | Context + provider; reads/writes localStorage |
| `frontend/src/hooks/useAuth.ts` | Convenience hook: `const { apiKey, setApiKey, clearApiKey } = useAuth()` |
| `frontend/src/components/auth/ApiKeyModal.tsx` | Modal dialog using shadcn/ui `Dialog` |
| `frontend/src/components/auth/AuthGuard.tsx` | Wraps children; renders `ApiKeyModal` if no key |

## ApiKeyModal Behaviour
1. Text input for the API key (type=password, so browser doesn't autofill or log).
2. Submit button labeled "Connect".
3. On submit: calls `GET /health` with the entered key.
4. Loading state while request is in flight; input and button disabled.
5. On 200: calls `setApiKey(key)`, closes modal.
6. On non-200: shows inline error "Invalid API key. Please try again." Key is not stored.
7. Network error: shows "Cannot reach server. Check the API URL."

## AuthContext Bootstrap (on app load)
```
1. Read localStorage['rnaseq_api_key']
2. If null → set apiKey=null (modal will show)
3. If present → validate via GET /health silently
   - 200 → set apiKey=storedKey (modal stays hidden)
   - non-200 → clearApiKey(), set apiKey=null (modal shows)
```

## Acceptance Criteria
- [ ] First visit (no localStorage key) shows `ApiKeyModal` before any content
- [ ] Entering a valid key (mocked 200 response in tests) stores it and hides the modal
- [ ] Entering an invalid key (mocked 401) shows error, does not store
- [ ] Reloading page with a valid stored key skips the modal (after silent re-validation)
- [ ] Reloading with an expired/revoked key (mocked 401 on validation) shows modal
- [ ] Any 401 from a non-health endpoint triggers modal re-display
- [ ] Sign out clears localStorage and shows modal
- [ ] Key is never visible in network URLs (only in Authorization header)
- [ ] TypeScript strict: no `any`

## Definition of Done
All acceptance criteria pass. Unit tests cover: valid key flow, invalid key flow, 401-mid-session flow, sign-out flow (mock `fetch` or use `msw`).

## Dependencies
TASK_FE_01 (scaffold), TASK_FE_02 (apiFetch needs AuthContext; wire together here).

## Security Notes
- Per `docs/specs/safety_policy.md` Rule 11.1: key never in URL except WSS `?api_key=` param.
- `ApiKeyModal` input uses `type="password"` to prevent browser history capture.
- Do not log the key value at any log level.
