# Official FastAPI Conventions Implementation Plan

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

- [ ] Write a RED test asserting the chat UI is served and that an API route
  sharing its prefix still wins.
- [ ] Replace the mount with `app.frontend()`.
- [ ] Confirm `GET /` still returns the UI and every API route is unaffected.

## Task 2: Move prefixes and tags onto the routers

All five routers declare `tags` only, and each path operation repeats the full
path (`@router.post("/auth/owner/unlock")`). Upstream prefers `APIRouter(prefix=...,
tags=...)` with relative paths.

- [ ] Add a test pinning the exact current URL of every route, from
  `app.routes`, before touching anything. It must keep passing.
- [ ] Move each router to `prefix` + relative paths. `system.py` has no common
  prefix and stays as it is.
- [ ] `transcribe.py` serves `/transcribe` and `/transcribe/stream`; a prefix of
  `/transcribe` with `""` and `/stream` is only worth it if it stays readable.
  If it does not, leave it and record why.

## Task 3: Drop redundant `response_model`

Three path operations declare `response_model=` **and** the same return type
(`auth.py:67,202`, `chat.py:54`). Upstream: prefer the return type; use
`response_model` only when the public schema differs from what the function
returns. Here they are identical, so the parameter is noise.

- [ ] Assert the OpenAPI schema for those three routes before and after; it
  must be byte-identical.
- [ ] Remove the redundant `response_model=`.
- [ ] Leave any case where the two genuinely differ, and comment why.

## Task 4: Correct the async rule

`.claude/rules/fastapi.md` states "all endpoints must be async". Upstream says
the opposite: use `async def` only when the body is genuinely non-blocking, and
prefer `def` — which FastAPI runs in a threadpool — when in doubt.

Every current endpoint is legitimately async, so no code changes. The rule
itself is what misleads.

- [ ] Rewrite the rule to match upstream, keeping the project's own addition:
  CPU-bound work goes to a bounded executor via
  `run_in_executor_with_context`, never inline in an `async def`.
- [ ] Add the same correction to `CLAUDE.md`/`AGENTS.md` if they restate it.

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

- [ ] `uv add --group dev httpx2` (already confirmed: silences the warning
  with zero code changes, and neither workspace member's `deptry` run
  objects — root dev-group deps aren't in either member's own dependency
  graph).
- [ ] Fix the resulting `pyright` break: once `httpx2` is installed,
  `TestClient.post()`/`.get()` return `httpx2.Response` instead of
  `httpx.Response` — a different, structurally similar but nominally
  distinct class. Six call sites across the five files listed under
  "Permitted files" have their own helper functions typed
  `-> httpx.Response`; update those six annotations to match (import
  `httpx2` there, or use a `Response` alias — whichever reads clearer in
  context).
- [ ] Confirm `just typecheck` and `just test` are clean afterward, and that
  the `StarletteDeprecationWarning` no longer appears anywhere in a full
  `just test` run.

## Task 6: Quieter logging when Ollama is unreachable

Found during Plan 0039's real-runtime acceptance (2026-09-03): with Ollama
down, a voice turn correctly speaks the fallback phrase (P0-C6 — never
silent) but `logger.error(..., exc_info=True)` also prints a full multi-frame
httpx/httpcore traceback (`server/src/server/streaming.py:209`,
`server/src/server/text_turn.py:229`) for what is an expected, already-handled
operational condition (the local model server isn't up), not a code defect.
Pre-existing behavior, not introduced by Plan 0039 — recorded here so it
isn't lost, per the standing "fix everything found" policy.

- [ ] Write a RED test asserting a connection-refused Ollama failure logs at
  `WARNING` (or `ERROR` without `exc_info`) with a short, actionable message —
  never a full traceback — while still correctly speaking the fallback
  phrase and returning the same response contract.
- [ ] Distinguish "Ollama unreachable" (`httpx.ConnectError`/
  `httpx.ConnectTimeout`) from a genuinely unexpected failure (malformed
  response, unknown exception) — only the latter still deserves
  `exc_info=True`.
- [ ] Apply the same fix to both call sites (`streaming.py`'s streaming path
  and `text_turn.py`'s classic path) so the two paths stay consistent.

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
