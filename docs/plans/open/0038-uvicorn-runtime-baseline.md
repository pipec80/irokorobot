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

**Spec:** Proposed ADRs
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

- [ ] Prove `Settings(uvicorn_workers=2)` fails validation.
- [ ] Prove port and positive timeout bounds.
- [ ] Prove kwargs disable reload/proxy/server header and leave
  `limit_max_requests` unset by default.
- [ ] Prove no forwarded address is trusted when proxy headers are false.

## Task 2: Implement constrained settings and builder

- [ ] Use `Literal[1]` for workers and constrained fields for port/timeouts.
- [ ] Change `uvicorn_max_requests` to `PositiveInt | None = None`; update
  `.env.example` by removing the active 1000-request value.
- [ ] Pass explicit graceful timeout and retain the default TCP backlog.
- [ ] Keep access logging unchanged until Plan 0032's request middleware is
  confirmed merged; then disable duplicate Uvicorn access logs.

## Task 3: Document capacity policy

- [ ] State that Uvicorn returns 503 at its concurrency limit and terminates at
  maximum requests; neither option creates capacity.
- [ ] Document a manual measurement matrix at concurrency 2, 4, 8, and current
  default using the real target, without committing a guessed production
  number.
- [ ] Document that maximum-request recycling requires a verified supervisor.

## Task 4: Verify

- [ ] Run focused settings/Uvicorn tests, `just lint`, `just typecheck`,
  `just test`, and `git diff --check`.

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
