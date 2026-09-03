# Uvicorn Runtime Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`.

**Goal:** Make the one-process ASGI runtime explicit, safe without an assumed
supervisor, and testable as configuration.

**Architecture:** Pydantic validates immutable runtime invariants; a pure
kwargs builder supplies Uvicorn; target capacity remains measured evidence,
not an arbitrary scale-up.

**Tech Stack:** Pydantic Settings, Uvicorn, pytest.

**Spec:** Accepted ADRs
[0010](../../adr/0010-fastapi-asgi-runtime-baseline.md) and
[0013](../../adr/0013-local-http-network-posture.md).

## Permitted files

- `server/src/server/settings.py`
- `server/src/server/main.py`
- `.env.example`
- `tests/unit/test_settings.py`
- `tests/unit/test_main_lifespan.py` or a focused Uvicorn-config test
- `server/README.md` only for runtime configuration

No systemd unit, LAN enablement, multiple workers, CORS, TLS redirect, proxy
deployment, or load-test dependency is in scope.

## Interfaces

```python
def build_uvicorn_kwargs(runtime_settings: Settings) -> dict[str, object]: ...
```

Defaults: one worker, no reload, loopback, proxy headers false, server header
false, keep-alive 5 seconds, graceful shutdown 30 seconds, maximum requests
unset. Preserve current concurrency until target measurement supports a new
default; document it as uncalibrated rather than silently changing 100 to 8.

## Task 1: Write RED invariant tests

- [x] Prove `Settings(uvicorn_workers=2)` fails validation.
- [x] Prove port and positive timeout bounds.
- [x] Prove kwargs disable reload/proxy/server header and leave
  `limit_max_requests` unset by default.
- [x] Prove no forwarded address is trusted when proxy headers are false.

## Task 2: Implement constrained settings and builder

- [x] Use `Literal[1]` for workers and constrained fields for port/timeouts.
- [x] Change `uvicorn_max_requests` to `PositiveInt | None = None`; update
  `.env.example` by removing the active 1000-request value.
- [x] Pass explicit graceful timeout and retain the default TCP backlog.
- [x] Keep access logging unchanged until Plan 0032's request middleware is
  confirmed merged; then disable duplicate Uvicorn access logs.

## Task 3: Document capacity policy

- [x] State that Uvicorn returns 503 at its concurrency limit and terminates at
  maximum requests; neither option creates capacity.
- [x] Document a manual measurement matrix at concurrency 2, 4, 8, and current
  default using the real target, without committing a guessed production
  number.
- [x] Document that maximum-request recycling requires a verified supervisor.

## Task 4: Verify

- [x] Run focused settings/Uvicorn tests, `just lint`, `just typecheck`,
  `just test`, and `git diff --check`.

## Upstream runtime guidance

The official FastAPI skill recommends running through the `fastapi` CLI —
`fastapi run` for production, `fastapi dev` for local reload — with the
entrypoint declared in `pyproject.toml`:

```toml
[tool.fastapi]
entrypoint = "server.main:app"
```

Today `server.main:main()` calls `uvicorn.run()` directly with explicit flags
(workers, proxy headers, concurrency, keep-alive, max requests). That is not
wrong, and it is what makes those flags reviewable in code — which is this
plan's whole point.

- [x] Decide explicitly, and record the reason: keep `uvicorn.run()` and its
  visible flags, or move to `fastapi run` and express the same limits through
  its options. Do not adopt the CLI merely because it is the upstream default;
  the single-worker invariant and the concurrency limits must remain explicit
  and testable either way.

  **Decision: keep `uvicorn.run()`.** See execution notes.

## Standing bump risk

- [x] Record in the plan's execution notes that `pyproject.toml` sets
  `filterwarnings = ["error"]`, so every dependency bump is a suite-wide event —
  and that the net has a hole: warnings raised while importing `conftest.py`
  fire before pytest installs its catcher and pass unnoticed. Plan 0043 found
  one live instance (`starlette.testclient` with `httpx`, deprecated in favour
  of `httpx2`). Migrating the test client is a dev-dependency decision that
  belongs here, not in a privacy or upload plan.

  Investigated fixing it directly — see execution notes for why it was
  reverted rather than kept.

## Rollback

Reverting restores prior process settings. If a deployment intentionally sets
`UVICORN_MAX_REQUESTS`, remove that override before rollback to avoid relying
on absent supervisor behavior.

## Completion criteria

- Invalid worker/runtime settings fail at startup.
- Default server no longer self-terminates after 1000 requests.
- One-worker/local/proxy invariants are tested.
- No unmeasured concurrency number is presented as calibrated production
  capacity.

## Execution notes

Executed 2026-09-03 on branch `feat/0038-uvicorn-runtime-baseline`,
test-first throughout.

### `Literal[1]` broke real `.env` loading — a genuine RED the plan's own
### interface didn't anticipate

The first GREEN attempt (typing `uvicorn_workers: Literal[1] = 1`) crashed
importing the real app: `.env` sets `UVICORN_WORKERS=1` as a string, and
`pydantic-settings`'s env-var parser only auto-coerces a *plain* `int` field
from its string source — it decides how to parse by the field's outer type,
and `Literal` isn't `int`, so `"1"` reached validation unconverted and failed
against the literal `1`. Caught immediately because `tests/conftest.py`
imports the real `server.main:app`, which constructs the real module-level
`settings` — every test in the suite would have failed on collection, not
just the new ones. Fixed with a `field_validator(mode="before")` that parses
a string env value to `int` before the `Literal` check runs. This is the
kind of gap TDD is supposed to catch before it reaches `main`, and it did.

### The `httpx2` fix works, and then breaks something one file outside this
### plan's scope

Confirmed the standing-bump-risk finding is real and fixable: `httpx2` is a
real, published package; `starlette.testclient.TestClient` already tries
`import httpx2 as httpx` first and only falls back (with the warning) to
`httpx`. `uv add --group dev httpx2` made the warning disappear with zero
code changes, and neither `deptry` invocation objected (root dev-group
dependencies aren't in either workspace member's own dependency graph, so
deptry never sees an "unused" `httpx2`).

But `pyright` then failed for real: once `httpx2` is installed,
`TestClient.post()`/`.get()` return `httpx2.Response` instead of
`httpx.Response` — a different, structurally-similar but nominally distinct
class — and six call sites across five integration test files (none of them
`server/src`, `server/main.py`, or the settings/uvicorn test files this plan
is permitted to touch) have their own helper functions typed
`-> httpx.Response`, now a real type mismatch.

Reverted (`uv remove --group dev httpx2`; confirmed `git diff --stat
pyproject.toml uv.lock` is empty — the revert left no residual change).
Fixing the six annotations belongs to whichever plan next touches those
five files, or its own narrow follow-up — not a scope expansion smuggled
into a runtime-config plan through a dev dependency. The finding itself
stays recorded here, and the fix (`uv add --group dev httpx2`, then update
the six `-> httpx.Response` annotations) is now a known, already-diagnosed
five-minute task for whoever picks it up next.

### Decision: keep `uvicorn.run()`, not `fastapi run`

`fastapi run`'s CLI does not expose the specific flags this project actually
depends on for its safety invariants: `access_log=False` (redundant once
Plan 0032's `RequestContextMiddleware` logs every request), a custom
`log_config=None` handoff to the already-configured `dictConfig`, and the
exact `limit_max_requests`/`limit_concurrency`/timeout tuning
`build_uvicorn_kwargs` now makes directly testable. Migrating would trade a
reviewable, unit-tested Python function for CLI flags outside test reach,
for no capability this project needs. `uvicorn.run()` stays.

### `build_uvicorn_kwargs` needed one `type: ignore`, not a `TypedDict`

The plan's own interface specifies `-> dict[str, object]` verbatim.
Unpacking that into `uvicorn.run(**kwargs)` is a real type mismatch — every
one of `uvicorn.run`'s ~30 parameters has its own specific type, and
`object` can't statically satisfy any of them. A `TypedDict` matching
`uvicorn.run`'s signature would resolve it precisely but duplicates a
signature this project doesn't own and would need to track across every
`uvicorn` upgrade. Used one explained `# type: ignore[arg-type]` at the
single call site instead; `build_uvicorn_kwargs` itself is fully
unit-tested, so the dict's actual *contents* are still verified — only the
unpack's static shape is unchecked.

### Pipec's own `.env` still has the old value

`.env.example` no longer ships `UVICORN_MAX_REQUESTS`, but `.env` is
untracked and out of this plan's permitted files — Pipec's real local `.env`
still sets `UVICORN_MAX_REQUESTS=1000`, which will keep overriding the new
`None` default until he removes or comments out that line himself.

### Verification

- `just lint`, `just typecheck` (mypy 90 files, pyright 0 errors) — clean
- `pytest -m "not slow and not hardware and not eval" --cov-fail-under=80` —
  **1015 passed** (997 + 18 new: 8 in `test_uvicorn_config.py`, 6 in
  `test_settings.py`, existing `test_main_lifespan.py` tests unchanged), 9
  deselected, **89.77% coverage**
- `just check` — clean
- `git diff --check` — clean
- Real acceptance: not directly exercised as a live voice/auth turn — the
  change is process-startup and runtime-flag configuration, not a request
  code path. `just run-server` starting successfully and staying up (not
  self-terminating at a request count, no longer possible to hit anyway
  since the old ceiling was 1000) is the acceptance signal available here.
