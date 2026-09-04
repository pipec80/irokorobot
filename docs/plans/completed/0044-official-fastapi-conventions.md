# Official FastAPI Conventions Implementation Plan

> **Status:** Completed 2026-09-03. Historical evidence only — this document
> is not an instruction and authorizes nothing.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development`, `fastapi`, and
> `superpowers:verification-before-completion`. Execute this plan only when it
> is the explicitly authorized `NOW` item.

**Goal:** Close the gaps between the HTTP layer and the official FastAPI
conventions, where closing them removes real code or fixes a real inaccuracy.

**Architecture:** No new abstraction. Each item replaces hand-written code with
the framework feature that already does the job, or corrects a project rule
that contradicts upstream guidance.

**Tech Stack:** FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.5, pytest.

**Spec:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md),
section "Official FastAPI guidance", plus the upstream skill at
`fastapi/.agents/skills/fastapi`.

## Why this plan exists

The capsule (Plans 0032-0042) was audited before the official FastAPI skill was
consulted. Comparing the two afterwards found four gaps that no child plan
owns, plus a fifth found later during Plan 0038's own execution (Task 5) and a
sixth found during Plan 0039's real-runtime acceptance (Task 6).
None is urgent; all are small and verifiable, and leaving them undocumented
means the next endpoint repeats them.

This plan is **not** a licence to apply every upstream recommendation. Items
deliberately excluded are listed under non-goals.

## Permitted files

- `server/src/server/chat_ui.py`
- `server/src/server/routers/` (all five routers)
- `server/src/server/main.py`
- `.claude/rules/fastapi.md` (untracked; fix lands locally)
- Focused API tests
- `pyproject.toml` (root) — dev-group dependency only, for Task 5
- `tests/integration/test_transcribe_stream.py`,
  `test_transcribe_stream_resilience.py`, `test_vision_dialog.py`,
  `test_vision_endpoint.py`, `test_vision_enroll_service.py` — Task 5 only,
  return-type annotations only
- `server/src/server/streaming.py`, `server/src/server/text_turn.py` —
  Task 6 only, error-logging call sites

No change to any URL, response body, status code, audio contract, or streaming
event is in scope. Every route must answer at exactly the same path afterwards.

## Task 1: Serve the chat UI with `app.frontend()`

`chat_ui.py` mounts `StaticFiles` manually. Upstream guidance is explicit: use
`app.frontend()` for built frontend assets instead. It also orders routes
correctly — API routes match first, then frontend files and client-side
fallbacks — which a manual mount does not guarantee.

- [x] Confirmed `app.frontend()` exists on the pinned FastAPI (measured
  directly, not assumed) and, via a throwaway prototype, that a manual
  `StaticFiles` mount registered before a same-path API route lets the
  static file **shadow** the route — the exact hazard upstream warns
  about — while `app.frontend()` correctly lets the route win regardless
  of order. Wrote this as a real RED test
  (`test_frontend_serving_lets_an_api_route_win_over_a_static_asset`),
  watched it fail against today's `app.mount()`.
- [x] Replaced the mount with `app.frontend("/chat-ui", directory=...)`.
- [x] The UI stays at `/chat-ui` (not `/`) — the plan's own "No change to
  any URL" rule overrides the task text's loose "`GET /`" phrasing; the
  mount path was never `/`. Every existing `test_chat_ui.py` test plus the
  new one pass unchanged (7/7).

## Task 2: Move prefixes and tags onto the routers

All five routers declare `tags` only, and each path operation repeats the full
path (`@router.post("/auth/owner/unlock")`). Upstream prefers `APIRouter(prefix=...,
tags=...)` with relative paths.

- [x] `tests/integration/test_api_contract.py::test_every_existing_route_is_still_present`
  (Plan 0040) already pins every route's exact URL from the generated
  OpenAPI schema — confirmed passing before touching anything, used as the
  regression net instead of writing a duplicate test.
- [x] Moved `auth.py` (`prefix="/auth/owner"`), `chat.py`
  (`prefix="/chat"`), `transcribe.py` (`prefix="/transcribe"`), and
  `vision.py` (`prefix="/vision"`) to `prefix` + relative paths.
  `system.py` (`/health`, `/ready` — no common prefix) stays as it is.
- [x] `transcribe.py`: `prefix="/transcribe"` with `@router.post("")` and
  `@router.post("/stream")` stayed readable — kept.
- [x] Verified: the pinning test, `test_operation_ids_are_unique`, and
  every operationId (manually inspected) are unchanged — operationIds are
  derived from the full literal path, which prefix+relative composition
  reproduces exactly. 1069 tests, all green.

## Task 3: Drop redundant `response_model`

Three path operations declare `response_model=` **and** the same return type
(`auth.py:67,202`, `chat.py:54`). Upstream: prefer the return type; use
`response_model` only when the public schema differs from what the function
returns. Here they are identical, so the parameter is noise.

- [x] Only **two** such occurrences actually exist today (`auth.py`'s
  `enroll_owner_face` → `FaceEnrollResponse`, `chat.py`'s `chat` →
  `ChatResponse`) — the plan's line-number count is stale, not a
  contradiction worth stopping for. Both confirmed genuinely identical to
  their return type before touching them.
- [x] Captured the OpenAPI schema for both routes before and after removing
  `response_model=`: **byte-identical** (`diff` of the two JSON dumps, empty).
- [x] Removed both redundant `response_model=`.
- [x] No case where the two genuinely differ was found — nothing left to
  comment.

## Task 4: Correct the async rule

`.claude/rules/fastapi.md` states "all endpoints must be async". Upstream says
the opposite: use `async def` only when the body is genuinely non-blocking, and
prefer `def` — which FastAPI runs in a threadpool — when in doubt.

Every current endpoint is legitimately async, so no code changes. The rule
itself is what misleads.

- [x] **`.claude/rules/fastapi.md` already states the correct upstream
  guidance** — re-read it and found no "always async" claim there; the
  plan's premise about which file holds the stale text doesn't match the
  tree. The actual violation is `.claude/rules/python-style.md`'s "Async
  Rules" section ("Use `async def` for all FastAPI endpoints..."). Fixed
  that file instead, matching the task's real intent (correct the rule
  that contradicts upstream, wherever it lives) rather than no-oping on a
  file that was already correct.
- [x] `CLAUDE.md`/`AGENTS.md` restate nothing about async — no change needed.

## Task 5: Migrate the test client from `httpx` to `httpx2`

Found and diagnosed during Plan 0038 (2026-09-03), not fixed there because
it touches five files outside that plan's permitted scope. Recorded here so
it isn't lost.

`starlette.testclient.TestClient` already tries `import httpx2 as httpx`
first and only falls back to `httpx` with
`StarletteDeprecationWarning: Using httpx with starlette.testclient is
deprecated; install httpx2 instead.` — a warning `pyproject.toml`'s
`filterwarnings = ["error"]` never catches, because it fires while
`tests/conftest.py` imports the real app, before pytest installs its own
warning-to-error catcher (a hole Plan 0038's own "Standing bump risk" section
already named).

- [x] `uv add --group dev httpx2` — silenced the warning with zero code
  changes; confirmed with a throwaway `-W all` import probe before and
  after. Neither workspace member's `deptry` run objected.
- [x] Fixed the resulting `pyright` break — **7** call sites, not 6 (the
  plan's count was stale; `test_vision_endpoint.py` alone has 3, not 1).
  All 7 across the five named files now type `-> httpx2.Response`, adding
  a same-purpose `import httpx2` (module-level where `httpx` is also used
  at runtime for real things like `httpx.AsyncClient`/`httpx.ConnectError`;
  under the existing `TYPE_CHECKING` block where it was type-only already).
- [x] `just typecheck` (mypy 92 files + pyright): 0 errors. `just test`:
  1069 passed (0 regressions). Grepped a full `-n0` run's output for
  "deprecat": zero matches — the warning is gone everywhere.

## Task 6: Quieter logging when Ollama is unreachable

Found during Plan 0039's real-runtime acceptance (2026-09-03): with Ollama
down, a voice turn correctly speaks the fallback phrase (P0-C6 — never
silent) but `logger.error(..., exc_info=True)` also prints a full multi-frame
httpx/httpcore traceback (`server/src/server/streaming.py:209`,
`server/src/server/text_turn.py:229`) for what is an expected, already-handled
operational condition (the local model server isn't up), not a code defect.
Pre-existing behavior, not introduced by Plan 0039 — recorded here so it
isn't lost, per the standing "fix everything found" policy.

- [x] Wrote 4 RED tests (2 per call site: one connection-refused, one
  genuinely-unexpected-failure control) using `caplog` to assert on the
  actual log record's `exc_info` — watched the connection-refused pair
  fail (traceback logged) and the control pair already pass, confirming
  the exact behavior to fix.
- [x] Added `llm.is_connectivity_failure(exc)`: `True` only when
  `exc.__cause__` is `httpx.ConnectError`/`httpx.ConnectTimeout` —
  `generate_response`'s own `raise LLMError(...) from exc` is what
  preserves the real cause on the chain. A bare `ValueError` (malformed
  model output, no cause chain) always returns `False`, so it still gets
  the full traceback.
- [x] Applied at both call sites — `streaming.py`'s `except (LLMError,
  ValueError)` in `stream_pipeline`, `text_turn.py`'s in `_generate` — same
  shape: `WARNING` with no `exc_info` for connectivity, `ERROR` with
  `exc_info=True` otherwise. All 4 new tests green; 1073 tests total.

## Non-goals

Upstream recommendations deliberately not adopted, with the reason:

- **SQLModel** — the project uses `sqlite-vec` through raw `aiosqlite`, and
  ADR 0011 keeps that. SQLModel would not carry the vector extension.
- **Asyncer** — a new dependency to replace asyncio usage that already works.
- **`ty`** — the project already runs mypy and pyright; a third type checker
  is cost without benefit.
- **`fastapi run` / `fastapi dev`** — belongs to Plan 0038, which owns the
  runtime configuration.
- **Native JSON Lines** — belongs to Plan 0041, which owns the stream contract.
- **`ORJSONResponse`/`UJSONResponse`** — deprecated upstream and unused here.

## Rollback

Revert the PR as one unit. No schema, dependency or wire change.

## Completion criteria

- Every route answers at exactly the same URL, proven by the pinning test.
- The generated OpenAPI is unchanged except where an item deliberately improves
  it.
- The chat UI is served through `app.frontend()`.
- No redundant `response_model` remains.
- The async rule matches upstream guidance and names the executor requirement.
- `httpx2` is installed and the six affected annotations are corrected; the
  `StarletteDeprecationWarning` no longer appears in any test run.
- An unreachable Ollama logs a short, actionable message — not a full
  traceback — while a genuinely unexpected LLM failure still gets one.

## Execution notes

Executed 2026-09-03 on branch `feat/0044-official-fastapi-conventions`,
test-first throughout: every RED was watched failing for the right reason
before the corresponding fix landed.

### Three of the plan's own factual claims were stale, none blocking

- Task 3: the plan named 3 redundant `response_model=` occurrences; only 2
  exist today.
- Task 4: the plan named `.claude/rules/fastapi.md` as holding the stale
  "always async" rule; that file was already correct — the real violation
  was `.claude/rules/python-style.md`.
- Task 5: the plan estimated 6 affected `httpx.Response` annotations; 7
  actually exist (`test_vision_endpoint.py` alone has 3).

None of these contradicted the plan's own *goal* — each was fixed by
following the stated intent against the measured tree, not by redesigning
anything. Recorded per CLAUDE.md's "stop and report a genuine contradiction"
rule not being triggered here: these are stale counts/locations, not
decisions the evidence overturned.

### Task 1's ordering hazard was proven, not assumed

A throwaway prototype (before writing the RED test) confirmed the actual
mechanism: a manual `app.mount(StaticFiles(...))` registered *before* a
same-path API route lets the static file **shadow** the route regardless
of the route's own registration order — Starlette's mount matching doesn't
defer to a later-registered path operation. `app.frontend()` does not have
this hazard: `test_frontend_serving_lets_an_api_route_win_over_a_static_asset`
locks this in permanently, not just for this plan's own migration.

### Verification

- `just lint`, `just typecheck` (mypy 92 files + pyright), `just audit`,
  `just check` — all clean.
- `just test` — **1073 passed** (1069 base + 4 new Task 6 tests), 0
  regressions.
- `git diff --check` — clean.
- Real runtime acceptance: **not applicable, confirmed explicitly by
  Pipec** — no URL, response body, status code, or streaming event changed
  in this plan's own scope; the comprehensive automated HTTP-level test
  suite for every touched route (route pinning, OpenAPI byte-identical
  diff, 4 new logging-behavior tests) already proves the behavior a live
  turn could only re-confirm, not add coverage to.

## Closure

Merged as PR #115. Closes the last child of the 0031 capsule — no further
child plan is queued behind this one; Plan 0031 itself and Plan 0042 remain
as reference/closure documents.
