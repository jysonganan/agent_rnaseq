# Terminal Prompts — Repo Review, WebSocket Auth, Per-Principal Ownership

Continues `terminal_prompts_03.md`. Chronological record of the user prompts issued after that
log was written. It covers a full repository review, the local versus cloud execution question,
and the first two security fixes from the review. Each prompt is quoted verbatim and followed by
what was implemented, what was added, and what remained to do or unsolved at that point.

---

## 1. Commit the previous prompt log

**Prompt**
> yes

**Outcome**: Committed `docs/prompts/terminal_prompts_03.md` as `0e0d374` and pushed `origin/main`.

---

## 2. Push the frontend branch

**Prompt**
> push add_frontend too

**Outcome**: `origin/add_frontend` fast-forwarded `eedda6c → 0e0d374`.

---

## 3. Thorough repository review

**Prompt**
> do a thorough review of the agent repo, and summarize what to be done and what haven't implemented, list what we can do next.

**Outcome**: The review was done in the session with no code changes. The test suite stood at
910 passed and 1 skipped, and CI was green. Validation levels L0 and L1 are confirmed; L2 and L3
have not been run.

**Fix these first**
1. The run-log WebSocket checked no API key.
2. API keys are sent in WebSocket URLs, which contradicts the `CLAUDE.md` frontend rule.
3. Any API key could see every run and project.
4. RSeQC never runs, because QC always comes before alignment.
5. Strandedness is fixed to `reverse` for HTSeq.
6. Alembic has a single `create_all` revision, so existing databases cannot be upgraded.

**Not implemented**
- Bioinformatics:
  - The GATK RNA-seq steps `MarkDuplicates` and `SplitNCigarReads` are missing.
  - Single-cell isn't in Nextflow.
  - The Streamlit single-cell page never gets data.
  - rMATS always runs on the worker.
- Execution:
  - Samples run one at a time.
  - Cancelling stops only the current sample.
  - There is no log streaming from Nextflow or Batch.
- Product:
  - There is no upload.
  - The frontend has no retry button or result tables.
  - The frontend isn't in CI.
  - Streamlit takes a local folder path.
- Docs:
  - "OpenAI Agents SDK" is named, but only the plain `openai` client is used.
  - The ECS and Kubernetes deployment docs have no infrastructure code.

**Suggested next steps**: security fixes, then correct science, then L2/L3 runs, then proper
migrations, then parallel samples, then the frontend, then single-cell and splicing in Nextflow,
then observability.

---

## 4. Is agent-driven execution local only?

**Prompt**
> and my follow up the agent-driven execution can only be local for now? and why not enable it for cloud also? what makes it only local?

**Outcome**: Explained with no code changes.
- **Runs created through `POST /runs`** can already use `nextflow` or `aws_batch`.
- **Chat-started runs are fixed to local.** `dispatch_from_chat` hard-codes
  `executor=Executor.local`. That line dates from TASK_FE_10, written before the other executors
  existed, and was never revisited.
- **Proposed design:**
  - The executor comes from the user or a `DEFAULT_EXECUTOR` setting, never from the LLM.
  - Prerequisites are checked before the run is created.
  - The executor is shown in the run plan, with a confirmation before anything is sent to AWS.
- **Caveat:** even an `aws_batch` run only sends the four heavy per-sample stages to Batch. The
  orchestrator and the lighter stages still run in the worker.

---

## 5. Save the review as a shareable doc

**Prompt**
> please aggregate the answers for my last 2 questions: thorough review of the repo, what to do, what not implemented and what next to do & the follow up: the agent-driven execution local and cloud. put them together in a sharable page or markdown file in the docs/

**Outcome**: Wrote `docs/review_post_executor_validation.md` with five sections: where things
stand, fix these first (findings #1–#7, where #7 is the chat executor limit), not implemented,
next steps, and local versus cloud execution.

---

## 6. Commit and push

**Prompt**
> commit and push it

**Outcome**: Committed as `fb25fbe` and pushed `origin/main`.

---

## 7. Push the frontend branch

**Prompt**
> push add_frontend too

**Outcome**: `origin/add_frontend` fast-forwarded `0e0d374 → fb25fbe`.

---

## 8. Fix finding #1 — run-log WebSocket authentication

**Prompt**
> okay fix the #1 finding: run-log websocket checks no API key issue

**Implemented / added**
- **The run-log WebSocket checks the key first.** `WS /ws/runs/{run_id}/logs` now validates the
  API key and run ownership before accepting the connection or subscribing to Redis.
  - Close `4403`: the key is missing, unknown, expired or revoked.
  - Close `4404`: the run id is malformed, unknown, or the run is owned by someone else. These
    cases can't be told apart, so run ids aren't revealed.
- **One shared key check.** New `active_api_key()` in `src/api/auth.py` is now used by REST and
  both WebSockets. The conversation stream's own copy of the check was removed.
- **Specs updated first:** close codes in `api_contracts.md`, and both sockets in
  `safety_policy.md` §11.5.
- **Tests:** 8 tests replace the 2 that connected with no key. 7 of them fail against the old
  handler. The suite stood at 916 passed and 1 skipped.

---

## 9. Commit and push

**Prompt**
> commit and push it

**Outcome**: Committed as `4d88340` and pushed. CI run 45324742877 was green on all four jobs:
Unit, Integration, Lint and Nextflow stub e2e.

---

## 10. Fix finding #3 — per-principal ownership and admin-only key management

**Prompt**
> go ahead

**Decisions (asked of the user)**
- What "owner" means: **per principal**. Each key belongs to a user or team, so key rotation
  keeps access to existing data.
- Lock down `/api-keys`: **yes, with an admin flag**.

**Implemented / added**
- **Schema** (specs first: `data_models.md`, `api_contracts.md` "Principals and ownership",
  `safety_policy.md` Rule 12):
  - `APIKey.principal` (indexed) and `APIKey.is_admin`.
  - Migration `0002_api_key_principal`, which only adds the columns when they are missing.
  - The migration was tested on a fresh database, on a downgrade followed by an upgrade, and on an
    old database. Existing keys get principal `default` and are not admin.
- **Query-level scoping** (`src/api/ownership.py`):
  - Projects, samples and runs (with their results, artifacts, cancel and retry) are scoped through
    `Project.owner`.
  - Conversations are scoped through the creating key's principal.
  - Both WebSockets use the same checks.
  - Another principal's ids return the same 404 as missing ids.
- **`POST /runs`:** the project must be owned by the caller, and every sample must belong to that
  project. Before this, a run could mix samples from any project.
- **`POST /projects`:** the server sets `owner` from the key's principal. A different `owner` in
  the request gets 403.
- **`/api-keys` is admin-only** (`require_admin`).
  - Creating a key accepts `principal` (defaults to the issuer's) and `is_admin`.
  - The list no longer includes revoked keys.
  - The name `bootstrap` is reserved.
- **`API_KEY_BOOTSTRAP` now works as the first admin key.** It was previously never read.
  - It is stored on first use, and concurrent first requests are handled safely.
  - It is disabled when the setting changes.
  - It is rejected if it is the placeholder value or shorter than 16 characters.
  - New setting `BOOTSTRAP_PRINCIPAL`, default `admin`.
- **Chat:**
  - The orchestrator only offers the LLM, and only accepts, samples from the caller's projects.
  - It asks which project to use when the selected samples span two projects.
- **Docs:** README access model and key setup (which also fixes `jq .key` to read `raw_key`),
  `.env.example`, the demo notebook's key, and the review doc (#3 marked fixed).
- **Tests:**
  - New `tests/api/test_ownership.py`, admin and bootstrap tests in `test_auth.py`, WebSocket
    principal tests, and chat isolation tests.
  - 33 of the new API tests fail against the old routers.
  - The suite stood at 960 passed and 1 skipped, and ruff was clean.

---

## 11. Commit and push

**Prompt**
> commit it and push it

**Outcome**: Committed as `74dfcaa` (32 files) and pushed `origin/main`. CI for this commit was
still running when this log was written.

---

## 12. Push the frontend branch

**Prompt**
> push add_frontend too

**Outcome**: `origin/add_frontend` fast-forwarded `fb25fbe → 74dfcaa`.

---

## 13. Prompt log (this document)

**Prompt**
> Also save my prompts (after the point you made terminal_prompts_03.md) and your final summary of what you implemented, added and things remain to do or unsolved each time -- save them as docs/prompts/terminal_prompts_04.md

**Outcome**: This file.

---

## Remaining / unsolved (as of this log)

**Deploying `74dfcaa` to an existing database**
- Run `alembic upgrade head`.
- Then set `principal` on existing API keys and `owner` on existing projects so they match.
  Otherwise existing keys won't see their projects.

**Security follow-ups**
- **#2:** API keys are still sent in WebSocket URLs. `safety_policy.md` §11.5 allows this over
  TLS, but the `CLAUDE.md` frontend rule forbids it. The conflict needs to be resolved, for
  example with a first-message or short-lived-token handshake.
- Any key can still register reference genomes, which are shared by everyone. This could be made
  admin-only.
- There is no frontend screen for managing keys; admins use curl.

**Science**
- **#4:** move RSeQC to a post-alignment QC step.
- **#5:** add a strandedness input, or detect it automatically.
- Add the GATK RNA-seq steps `MarkDuplicates` and `SplitNCigarReads`.

**Platform**
- **#6:** proper Alembic migrations. `0002` works around the `create_all` baseline; a real
  baseline and a CI check that models match migrations are still needed.
- **#7:** let chat choose the executor, set by the user or settings and never by the LLM.
- **L2/L3:** run the real-tools and AWS Batch validations, as the user (see
  `docs/testing/executor_e2e.md`).
- Run samples in parallel.
- Stream Nextflow and Batch logs.
- Add the single-cell and splicing workflows to Nextflow.

**Product**
- Upload via presigned URLs.
- Frontend: a retry button and result tables, and frontend lint, tests and build in CI.
- Streamlit: open results by run ID and read them from S3.

**Docs**
- Fix the "OpenAI Agents SDK" naming, or adopt the Agents SDK.
- The ECS and Kubernetes sections in `docs/deployment.md` have no infrastructure code.
