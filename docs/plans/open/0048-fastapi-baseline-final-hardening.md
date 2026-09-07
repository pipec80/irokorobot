# FastAPI Production Baseline — Final Hardening Plan

> **Status:** Ready. Authorized by Pipec on 2026-09-07 as the single `NOW`
> item, following a second independent audit of `server/src/server` after
> the 0031 capsule (0032–0045) closed.

> **For agentic workers:** REQUIRED SUB-SKILLS: `superpowers:test-driven-development`,
> `fastapi`, `superpowers:verification-before-completion`. Execute this plan
> only while it is the explicitly authorized `NOW` item. Implement exactly
> the tasks below; if evidence contradicts the plan, stop and report the
> conflict instead of redesigning.

**Goal:** Close the four small, real gaps the second audit found on top of
the already-professional server baseline, so the "how should FastAPI do
this?" phase ends and future PRs build features *on* the server instead of
*on the server itself*.

**Architecture:** No new abstraction, no dependency, no wire change to any
existing field. Each task either adds a validation bound that was missing,
makes an existing guarantee actually hold, or corrects documentation to
match the code. Uvicorn concurrency calibration is explicitly **out of
scope** — it needs measurement on real target hardware and gets its own
`perf(...)` plan.

**Tech Stack:** FastAPI 0.141.x, Starlette 1.6.x, Pydantic 2.13.x, pytest,
`aiosqlite`. Same pinned versions as Plan 0044.

**Spec:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md),
plus the upstream skill at `.claude/skills/fastapi`.

## Why this plan exists

The capsule was audited a second time, independently, against the merged
code. The verdict: the baseline is professional, every original P0 is
closed, and general infrastructure refactors should stop. Four bounded
edges remain, none urgent, all verifiable:

1. Free-text request fields (`chat` message, `vision/respond` text,
   `vision/enroll` name) have `min_length` but no `max_length`. The raw
   ASGI body limit (`main.py`) caps total bytes (~15 MB), but 15 MB of
   *valid* text still reaches Pydantic → tokenization → Ollama. This is a
   different bound from the body limit.
2. `streaming.guarantee_terminal_event()` promises "exactly one terminal
   event, then EOF" but does not hold it: `saw_terminal` is reassigned per
   line instead of latched, and neither `except` branch checks it. A
   producer that yields `done` then raises emits `done` + `error` (two
   terminals); a producer that yields `done` then another line emits
   `done`, that line, then a spurious `error`.
3. `POST /transcribe/stream`'s generated OpenAPI `200` says
   `application/json` with an empty schema. The runtime contract is
   `application/x-ndjson` with a known set of line events.
4. `system.py`'s `GET /health` docstring claims it returns ok "when the
   server is up **and models are loaded**" — it checks neither; only
   `/ready` does. `create_app()` reads the module-global `settings`
   singleton, so `lifespan` behaviour (worker check, `MEMORY_ENABLED`,
   startup) cannot be driven by an injected `Settings` for test isolation.

This plan is **not** a licence to apply every audit suggestion. Items
deliberately excluded are under non-goals.

## Permitted files

- `server/src/server/cognition/response_plan.py` — Task 1 (shared bound
  constant + `TextTurnPayload.message`)
- `server/src/server/schemas_chat.py` — Task 1 (`ChatRequest.message`)
- `server/src/server/routers/vision.py` — Task 1 (`text`, `name` `Form`
  bounds)
- `server/src/server/streaming.py` — Task 2 (`guarantee_terminal_event`)
- `server/src/server/routers/transcribe.py` — Task 3 (`/transcribe/stream`
  `responses=` / `response_class`)
- `server/src/server/schemas_streaming.py` — Task 3 only, if a documented
  `200` schema needs a union/example (no field change to existing events)
- `server/src/server/routers/system.py` — Task 4 (`/health` docstring)
- `server/src/server/main.py` — Task 4 (`create_app(app_settings=None)`,
  `app.state.settings`, `lifespan` reads it)
- Focused tests under `tests/unit/` and `tests/integration/`:
  `test_stream_terminal_event.py`, `test_chat_endpoint.py`,
  `test_vision_dialog.py`, `test_openapi_contract.py` /
  `test_api_contract.py`, `test_transcribe_stream.py`,
  `test_app_lifecycle.py`, `test_health_endpoint.py`
- `server/README.md` — only if a wording line needs to track a change here
- `docs/architecture/current-state.md` — one row on closure
- `docs/plans/README.md`, `docs/plans/open/README.md` — board + index
- `.env.example` — only if Task 1 introduces a configurable bound (it does
  not by default — see Task 1)

No change to any URL, status code, existing response field, audio contract,
or existing streaming event. Every route answers at the same path with the
same operationId afterwards — proven by the Plan 0040 route-pinning test.

## Task 1: Semantic `max_length` on free-text request fields

`ChatRequest.message`, `TextTurnPayload.message`, and the `vision/respond`
`text` / `vision/enroll` `name` `Form` params accept unbounded valid text.

- [ ] RED: add to `test_chat_endpoint.py::test_chat_rejects_invalid_payloads`
  a case `("x" * (MAX + 1), "web-primary")` → expect `422`. Watch it fail
  (currently `200`/`500`).
- [ ] RED: add to `test_vision_dialog.py` a case posting a `text` form
  field one char over the bound → expect `422`. Watch it fail.
- [ ] Define ONE module constant `MAX_TURN_MESSAGE_CHARS = 4000` in
  `response_plan.py` (the canonical turn-message model already lives
  there), with a comment stating it is the *semantic* bound and the raw
  ASGI body limit in `main.py` is the outer one. A plain constant, not a
  `Settings` field — it follows the existing `_CONVERSATION_ID_PATTERN` /
  `max_length=64` convention in the same layer, and Pydantic `Field`
  constraints must be literals. If Pipec later wants it tunable, that is a
  separate change.
- [ ] Apply `max_length=MAX_TURN_MESSAGE_CHARS` to `TextTurnPayload.message`
  and `ChatRequest.message` (importing the constant into `schemas_chat.py`).
- [ ] Apply `Form(max_length=MAX_TURN_MESSAGE_CHARS, ...)` to
  `vision/respond`'s `text`, and `Form(max_length=200, ...)` to
  `vision/enroll`'s `name` (a person name; the endpoint still 503s and
  discards it, but the multipart contract stays honest).
- [ ] GREEN: both new cases pass; the added `maxLength` shows in the
  generated OpenAPI (additive only). Full suite unchanged otherwise.
- [ ] Confirm `4000` is a deliberate value: it is ~4× the longest plausible
  spoken turn and ~700 words typed — comfortably a conversational turn,
  far below what wastes tokenization/LLM time. Record the reasoning in the
  execution notes if Pipec wants a different number.

## Task 2: Make `guarantee_terminal_event` actually guarantee one terminal

- [ ] RED: add to `test_stream_terminal_event.py`:
  - `test_done_then_producer_exception_emits_only_done` — producer yields
    `done` then raises `RuntimeError`; assert output ends at `done`, no
    `error` line.
  - `test_tts_error_after_done_appends_no_second_terminal` — producer
    yields `done` then raises `TTSError`; assert only `done`.
  - `test_a_line_after_done_is_dropped_not_forwarded` — producer yields
    `done` then an `audio` line; assert output ends at `done`, no trailing
    line, no spurious `error`.
  - `test_error_then_producer_exception_emits_only_error` — producer yields
    an `error` line then raises; assert only that one `error`.
  Watch each fail for the right reason against today's code.
- [ ] Fix `guarantee_terminal_event`:
  - latch: `saw_terminal` becomes `True` and stays `True` (never
    reassigned back to `False`);
  - once `saw_terminal` is `True`, stop forwarding producer lines (drain
    the generator so its own cleanup runs, but yield nothing more) and log
    one `logger.error(...)` naming the producer-contract violation;
  - both `except` branches: if `saw_terminal` is already `True`, log and
    `return` without emitting a second terminal;
  - guard the `json.loads(line)` parse (`except (ValueError, TypeError)`)
    so a non-JSON producer line is forwarded-but-not-terminal instead of
    crashing into the generic `error` path.
- [ ] Keep the existing five tests green unchanged — the normal path, the
  single-`TTSError`, the single-unexpected-exception, the cancellation
  passthrough, and the no-terminal-at-all case must all still pass.
- [ ] GREEN: all new + existing tests pass.

## Task 3: Document the `/transcribe/stream` 200 as NDJSON in OpenAPI

Keep the manual `StreamingResponse(...)` return (Plan 0041/0044 decision —
a pre-stream `HTTPException` must still become a real 413/422/500). Only
correct the generated schema.

- [ ] RED: add `test_openapi_contract.py::test_transcribe_stream_200_is_documented_ndjson`:
  ```python
  op = app.openapi()["paths"]["/transcribe/stream"]["post"]
  content = op["responses"]["200"]["content"]
  assert "application/x-ndjson" in content
  assert "application/json" not in content
  ```
  Watch it fail (today: only `application/json`, empty schema).
- [ ] Give the route an explicit `200` in its `responses=` dict describing
  the NDJSON stream and its line events (`text_heard`, `emotion`, `audio`,
  `done`, `error`), and drive the media type to `application/x-ndjson`
  only — the cleanest way on the pinned FastAPI is a
  `class NDJSONStreamingResponse(StreamingResponse): media_type = "application/x-ndjson"`
  passed as `response_class=` on the decorator (docs only; the handler
  still returns its own response object for the error-handling reason
  above). Verify with a throwaway probe that `response_class=` alone
  removes the bogus `application/json` 200 entry before committing to it;
  if it does not, fall back to an explicit `responses={200: {...}}` that
  overwrites `content`.
- [ ] The documented `200` schema references the streaming event union
  (`schemas_streaming.StreamEvent`) so `/docs` shows the real line shapes.
- [ ] GREEN: the new test passes; `test_every_operation_has_tag_summary_and_typed_response`
  and every other contract test still pass; route path/method/operationId
  unchanged (route-pinning test green).

## Task 4: Correct `/health` wording and make `create_app` settings-injectable

- [ ] `system.py`: rewrite `health()`'s docstring to state exactly what it
  does — "200 whenever the HTTP process is accepting requests; it checks
  neither models nor the database — use `GET /ready` for that." No code
  change to the handler.
- [ ] RED: add `test_app_lifecycle.py::test_create_app_accepts_an_injected_settings`
  — `create_app(Settings(memory_enabled=False))` then drive `lifespan` on
  that instance with `stt.preload`/`tts.preload` patched, and assert
  `open_db` is never called (e.g. monkeypatch `main.open_db` to fail).
  Watch it fail (`create_app` takes no argument today).
- [ ] `main.py`:
  - `def create_app(app_settings: Settings | None = None) -> FastAPI:` with
    `cfg = app_settings or settings`;
  - `configure_logging(cfg)`; store `new_app.state.settings = cfg`;
  - `lifespan` reads `_app.state.settings` for the worker-count check, the
    `memory_enabled` branch, and the startup log line — nothing else;
  - `build_uvicorn_kwargs` already takes `Settings` as a parameter — leave
    it;
  - module-level `app = create_app()` stays (uses the global default).
- [ ] Scope guard: this task touches `main.py` only. Other modules
  (`db.py`, `logging_setup.py`, `retention.py`, `stt.py`, `tts.py`, the
  dependency aliases) keep reading the global `settings` — a full
  settings-injection refactor is a **non-goal** (see below). The win here
  is real and contained: `create_app(Settings(memory_enabled=False))` /
  `create_app(Settings(vision_enabled=True))` / a custom worker count now
  produce genuinely different lifespan behaviour without mutating globals,
  which is the isolation case the audit named.
- [ ] Keep `test_main_lifespan.py` and the existing
  `test_app_lifecycle.py` tests green — they patch attributes on the
  shared global `settings`, and `main.app.state.settings is settings`, so
  they are unaffected.
- [ ] GREEN: new test passes; lifecycle + lifespan suites green.

## Non-goals

Deliberately excluded, with the reason:

- **Uvicorn concurrency calibration** (`UVICORN_LIMIT_CONCURRENCY=100`) —
  needs p50/p95/RAM/queueing measurement on the real homelab hardware, not
  a guessed literal. Its own `perf(server): calibrate runtime concurrency`
  plan.
- **Full `Settings` dependency injection** across `db.py`, `retention.py`,
  `stt.py`, `tts.py`, etc. — the audit itself says not to block features
  on this; Task 4 does the contained part only.
- **Moving `owner_unlock_service` construction into the lifespan** — Plan
  0040 wired it deliberately as a singleton into `AppResources`; changing
  that is its own decision, not hardening.
- **`TrustedHostMiddleware`** — only meaningful once `SERVER_HOST=0.0.0.0`;
  add it with the LAN-exposure change and its allowed-host list, not now.
- **Migrating the stream to native FastAPI JSON Lines** — measured and
  deferred in Plan 0041; a pre-stream `HTTPException` must still surface as
  a real status code.
- **Making `MAX_TURN_MESSAGE_CHARS` a `Settings` field** — a constant
  matches the layer's existing convention; promote it only on request.

## Verification

Run before claiming done, in this order:

```powershell
uv lock --check
just lint
just typecheck
just test
just audit
just check
uv build --all-packages
git diff --check
```

Plus the exact deterministic CI coverage command:

```powershell
uv run pytest -m "not slow and not hardware and not eval" `
  --cov=server/src --cov=robot/src --cov-report=term --cov-fail-under=80
```

## Completion criteria

- Every free-text request field has a `max_length`; an over-length body /
  form field returns `422` (proven by new tests).
- `guarantee_terminal_event` emits exactly one terminal event in every
  case, including `done`-then-raise and `done`-then-extra-line (proven by
  new tests); all five original tests still pass.
- `/transcribe/stream`'s OpenAPI `200` is `application/x-ndjson` with the
  documented line events and no `application/json`.
- `GET /health`'s docstring matches what it actually checks.
- `create_app(Settings(...))` produces isolated lifespan behaviour with no
  global mutation; `main.py` is the only production file changed for it.
- All gates above pass; coverage ≥ 80%.
- No URL, status code, existing field, or existing streaming event
  changed — route-pinning and OpenAPI contract tests green.

## Real runtime acceptance

Decide with Pipec at closure. Likely **not applicable** — no hot-path
request/response body or streaming event changes; the automated HTTP-level
suite (route pinning, OpenAPI diff, new 422 cases, new terminal-invariant
tests) proves the behaviour a live turn could only re-confirm. If Pipec
wants a live turn anyway: one classic `/transcribe` and one
`/transcribe/stream` turn, outcomes/timings only, no transcripts.

## Rollback

Revert the PR as one unit. No schema, dependency, or wire change; every
existing field and event is untouched.

## Closure

One squash-merged PR (`chore(server): close FastAPI production baseline`).
On merge: move this file to `completed/`, update the board and
`current-state.md`, and record that the "how should FastAPI do this?" phase
is closed — the standing convention for any new endpoint becomes: Pydantic
contract → thin router → typed `Depends` → domain/service → typed response
→ known errors → OpenAPI → API tests → CI.
