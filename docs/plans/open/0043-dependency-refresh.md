# Dependency Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:verification-before-completion`. Execute this plan only when it
> is the explicitly authorized `NOW` item.

**Goal:** Bring the workspace lock to the latest stable resolution so the
server-production capsule (Plans 0032-0042) is designed against the runtime it
will actually ship on, not against a lock frozen in June.

**Architecture:** No architectural change. This plan moves versions and repairs
whatever the move breaks. It is transversal, so it runs before Plan 0032.

**Tech Stack:** uv workspace, Python 3.12, pytest.

**Spec:** [`server-production-baseline.md`](../../architecture/server-production-baseline.md)

## Why this runs before 0032

Two queued children change design depending on the outcome:

- Plan 0034 planned a hand-written raw body limit because `starlette 1.3.1`
  has no native one. Starlette 1.6.0 does. Refreshing first removes that work.
- Plan 0038 must record the real Uvicorn version and its runtime flags.

Writing eleven plans against a stale base and then moving the base is the more
expensive order.

## Verified starting point

At `846014d`, `uv pip list --outdated` reports 53 outdated packages. The ones
that matter:

| Package | Locked | Latest |
|---|---|---|
| fastapi | 0.141.1 | 0.141.1 — already current |
| starlette | 1.3.1 | 1.6.0 |
| uvicorn | 0.52.1 | 0.52.4 |
| pydantic | 2.13.4 | 2.13.5 |

`numpy`, `onnxruntime`, `opencv-python`, `insightface`, `piper-tts`,
`faster-whisper`, `httpx`, `aiosqlite` and `python-multipart` are already at
their latest release.

Starlette lags for no technical reason: `fastapi 0.141.1` requires
`starlette>=0.46.0` and `sse-starlette 3.4.8` requires `starlette>=0.49.1`.
Neither declares an upper bound, and the workspace root sets
`resolution = "highest"`, so `uv lock --upgrade` moves it without editing a
single specifier.

`robot 0.1.0 -> 0.1.4` in the outdated listing is a false positive: an
unrelated PyPI package shares the name of the editable workspace member.

## Permitted files

- `uv.lock`
- `server/pyproject.toml`, `robot/pyproject.toml` — only if a specifier
  genuinely blocks an upgrade
- Mechanical deprecation fixes under `server/src`, `robot/src`, `tests/`
- `docs/architecture/server-production-baseline.md` — verified version block
- Execution notes inside this plan only

No feature, schema, wire-contract, or behavior change is in scope. Suppressing
a warning instead of migrating the call is out of scope.

## Task 1: Refresh and measure

- [ ] `uv lock --upgrade`
- [ ] `uv sync --all-packages --all-groups`
- [ ] Record the resulting version diff in this plan as evidence.
- [ ] Run the COMPLETE suite, not CI's deterministic selection:

  ```powershell
  just test
  just check
  just typecheck
  just audit
  ```

`filterwarnings = ["error"]` turns any new `DeprecationWarning` across 53
packages into a suite failure. That is the expected primary failure class and
it is mechanical to repair.

## Task 2: Repair by failure class

- [ ] **Deprecation:** migrate the call site. Never add a new filter —
  `filterwarnings=error` is the net that surfaced this and it is not touched.
- [ ] **Starlette 1.3.1 -> 1.6.0:** the largest surface change (multipart,
  streaming, `TestClient`). Watch
  `tests/integration/test_transcribe_stream*.py`, the multipart upload tests,
  and every `TestClient` construction.
- [ ] **Real regression:** pin that one package with the reason written into
  the specifier and continue. A justified pin is acceptable; a stale lock is
  not.
- [ ] Re-run the full gate and observe GREEN.

## Task 3: Real-runtime acceptance

Mandatory. No automated test covers it: `av`, `ctranslate2` and
`huggingface-hub` form the Whisper chain, and model tests are marked `slow` and
excluded from CI, so a speech-quality regression would pass green.

- [ ] Pipec runs `just run-server` + `just run-robot` and confirms one complete
  voice turn: speak -> transcribe -> LLM -> TTS -> audio plays.
- [ ] Record the outcome here.

## Rollback

Revert the PR to restore `uv.lock`. No schema migration, no wire change, no
data rollback.

## Completion criteria

- The lock resolves to latest stable except for pins whose reason is written
  into the specifier.
- `just check`, `just typecheck`, `just audit` and the complete `just test`
  pass.
- No new warning filter was added.
- One real voice turn confirmed by Pipec and recorded above.
- The verified version block in `server-production-baseline.md` matches the
  merged lock.

## Execution notes

Executed 2026-09-02 on branch `chore/0043-dependency-refresh`.

### Task 1 — refresh

`uv lock --upgrade` + `uv sync --all-packages --all-groups` moved 50 packages
and removed 3 (`setuptools`, `shellingham`, `typer` — transitive only). 130
installed packages before, 127 after. The relevant moves:

| Package | From | To |
|---|---|---|
| starlette | 1.3.1 | 1.6.0 |
| uvicorn | 0.52.1 | 0.52.4 |
| pydantic | 2.13.4 | 2.13.5 |
| av | 17.0.1 | 18.1.0 |
| ctranslate2 | 4.7.1 | 4.8.2 |
| huggingface-hub | 1.12.0 | 1.29.0 |
| numpy, onnxruntime, opencv-python, insightface, piper-tts, faster-whisper, httpx, aiosqlite, python-multipart, fastapi | unchanged | already latest |

Full evidence: `just test` **929 passed** in 111.66s, `just typecheck`
(mypy 89 files + pyright) clean, `just audit` (Ruff S + pip-audit) clean,
`just check` all 17 hooks pass.

### Task 2 — repairs

None required. Zero test failures and zero new `DeprecationWarning` surfaced
by the suite. No pin was added; no warning filter was added.

Remaining `uv pip list --outdated` entries after the refresh:

- `pydantic-core 2.46.5 -> 2.48.0` — pinned by `pydantic 2.13.5`, which
  requires an exact core version. Not actionable independently.
- `robot 0.1.0 -> 0.1.4` — false positive, unrelated PyPI package sharing the
  editable workspace member's name.

### Finding 1: Starlette 1.6.0 body limit, verified behavior

`starlette/middleware/body_limit.py` exists and works. Measured directly, not
assumed:

- `FastAPI(...)` does **not** accept `max_body_size`; only
  `Starlette.__init__` does. Registration must be
  `app.add_middleware(RequestBodyLimitMiddleware, max_body_size=...)`.
- It is genuinely route-aware. A nested responder overrides
  `MAX_BODY_SIZE_SCOPE_KEY`, so a global budget plus a larger per-route budget
  is expressible — which is what the baseline requires for the route carrying
  both audio and a face frame.
- It rejects on `Content-Length` before reading and again on accumulated bytes
  during receive, so oversized bodies never reach application memory.
- **It answers `413` as `text/plain` with the body `Content Too Large`**, not
  as the JSON `{"detail": ...}` the current handlers emit. That is a wire
  difference the robot client can observe.

Consequence for Plan 0034: the hand-written ASGI limit is unnecessary, but the
413 response shape becomes an explicit decision in that plan, not an incidental
side effect.

### Finding 2: import-time deprecations escape `filterwarnings = ["error"]`

`import fastapi.testclient` emits:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is
deprecated; install `httpx2` instead.
```

The suite stays green because `tests/conftest.py:8` imports `TestClient` at
module level, which runs before pytest installs its warning catcher. The
`filterwarnings = ["error"]` net therefore does not cover import-time warnings
from conftest — a real blind spot in the project's upgrade safety net, not a
one-off.

Out of scope here (migrating the test client to `httpx2` is a dev-dependency
change with its own blast radius). Recorded so Plan 0032, which already touches
`tests/conftest.py`, and Plan 0038, which owns bump risk, can act on it.

### Task 3 — real-runtime acceptance

_Pending: Pipec runs `just run-server` + `just run-robot` and confirms one
complete voice turn. The Whisper chain (`av`, `ctranslate2`,
`huggingface-hub`) moved, and model tests are `slow`/CI-excluded, so a speech
regression would not appear above._
