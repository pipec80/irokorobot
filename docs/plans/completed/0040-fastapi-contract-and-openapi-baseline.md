# FastAPI Contract and OpenAPI Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development`, `fastapi`, and
> `superpowers:verification-before-completion`.

**Goal:** Make the actual HTTP surface typed, dependency-driven where useful,
and accurately represented by generated OpenAPI without breaking clients.

**Architecture:** Typed FastAPI dependencies expose lifecycle resources at the
HTTP boundary. Existing wire error bodies remain compatible. Health and
readiness have distinct cheap semantics.

**Tech Stack:** FastAPI, Pydantic V2, OpenAPI, pytest.

**Spec:** Accepted ADR
[0010](../../adr/0010-fastapi-asgi-runtime-baseline.md).

## Permitted files

- `server/src/server/dependencies.py` (new)
- `server/src/server/openapi.py` (new if metadata warrants separation)
- `server/src/server/main.py`
- `server/src/server/routers/`
- Existing request/response schema modules
- `server/src/server/stt.py`, `tts.py`, `db.py` only for side-effect-free
  readiness state probes
- Focused API/OpenAPI tests

No URL version prefix, universal replacement error envelope, CORS, OAuth2,
domain import of FastAPI, or streaming transport migration is allowed.

`create_app()` is explicitly out of scope unless the `settings` singleton
migrates in the same slice. 24 modules import it at module level, so a factory
that accepts a `Settings` argument while those imports remain would only appear
injectable — and tests would then rely on configurability that does not exist.
Either both land together or neither does; ADR 0010 records this.

## Interfaces

```python
ResourcesDep = Annotated[AppResources, Depends(get_resources)]
OwnerUnlockServiceDep = Annotated[OwnerUnlockService, Depends(get_owner_unlock_service)]
IdentityTokenDep = Annotated[str | None, Security(owner_identity_header)]
```

The optional security scheme name is `OwnerIdentityToken`, header
`X-Iroko-Identity-Token`, `auto_error=False`.

## Task 1: Lock current and target OpenAPI

- [ ] Add tests asserting every existing core route remains present, operation
  IDs are unique, installed server package version is advertised, and every
  operation has tag/summary/typed success response.
- [ ] Assert the optional API-key header appears in
  `components.securitySchemes` without making public endpoints require it.
- [ ] Assert `/docs`, `/redoc`, and `/openapi.json` return 200.
- [ ] Observe RED for missing metadata/security/readiness.

## Task 2: Add focused dependencies

- [ ] Resolve `AppResources` from `request.app.state` with a typed accessor.
- [ ] Replace HTTP-layer imports of the owner service with dependency aliases.
- [ ] Use `app.dependency_overrides` in tests instead of new deep monkeypatches.
- [ ] Do not wrap pure settings/constants in dependencies unless a router truly
  needs application-specific state.

## Task 3: Document existing error contracts

- [ ] Add reusable response documentation for current `detail`-based 4xx/5xx
  shapes and privacy-safe validation responses.
- [ ] Centralize unexpected exception handling only if tests prove internal
  details are currently exposed; return a generic detail and request header ID.
- [ ] Do not remove `detail` or require robot/client migration in this plan.

## Task 4: Split liveness/readiness

- [ ] Preserve `/health` fields consumed by the robot and keep it cheap.
- [ ] Add `/ready`: 503 outside successful lifespan or when a mandatory local
  resource is unavailable; 200 during successful lifespan.
- [ ] Add side-effect-free `is_loaded`/`is_open` probes only; never load a model
  or call Ollama/VLM from a health endpoint.
- [ ] Disabled optional vision does not make the server unready.

## Task 5: Complete generated metadata

- [ ] Use `importlib.metadata.version("server")` for FastAPI version metadata.
- [ ] Add System/Auth/Chat/Audio/Vision tag metadata and concise summaries.
- [ ] Document existing uploads, status codes, and streaming media type
  accurately; do not maintain manual OpenAPI YAML.
- [ ] Run focused API/OpenAPI tests, then repository gates.

## Rollback

Dependencies/metadata/readiness are separate commits. Revert the responsible
commit while preserving existing paths/bodies.

## Completion criteria

- OpenAPI matches runtime routes, schemas, media types, and security input.
- Dependency overrides replace HTTP service globals.
- `/health` and `/ready` semantics are tested and cheap.
- Existing server and robot contract suites pass unchanged.

## Execution notes

### The `Dependencies`/`metadata`/`readiness` commit split from the plan's own
### Rollback note wasn't practical — landed as one commit instead

`auth.py` and `transcribe.py` each needed both Task 2's dependency wiring
(`owner_unlock_service` as an injected parameter) and Task 3's `responses=`
documentation in the same edit pass, with no clean git boundary between
them — Task 3's `responses=error_responses(...)` decorators reference
`server.schemas.error_responses`, so any commit carrying that reference
needs `schemas.py`'s new `ErrorResponse`/`error_responses` in the same
commit too, which pulled Task 5's schema work in behind it. Trying to force
a 3-way split would have meant either a broken intermediate commit (an
import that doesn't resolve yet) or hand-splitting diffs hunk-by-hunk for
marginal revert-granularity benefit on a documentation-only, no-wire-change
plan. Landed as one commit; the plan's own real safety property — "revert
while preserving existing paths/bodies" — holds for the whole commit, since
nothing in it changes a URL, request/response body, or status code.

### A real, pre-existing gap found by Task 1's own RED tests

Before this plan, `app.openapi()["info"]["version"]` was a hand-maintained
literal (`"0.2.0"`) that had already drifted from `server/pyproject.toml`'s
real `0.1.0` — proof that a hardcoded version string rots quietly. Fixed
with `importlib.metadata.version("server")`, which cannot drift because
it reads the installed package's own metadata.

### `POST /auth/owner/face/revoke`'s 204 needed a carve-out in the RED test

Task 1's "every operation has a typed success response" test initially
required `content` on every declared 2xx — `face/revoke` legitimately
returns `204 No Content` with no body at all (Plan 0029's original design).
Fixed the test's own assertion to skip schema-content checks on `204`
specifically, rather than either loosening the check for everyone or adding
a body the endpoint was never meant to carry.

### `/ready`'s probes are genuinely side-effect-free, verified twice

`stt.is_loaded()`/`tts.is_loaded()`/`db.is_open()` each just read a
module-level `None`-or-not flag — never trigger a load or open. Verified at
two levels: `tests/unit/test_readiness_probes.py` proves the real function
bodies reflect real module state (via `monkeypatch.setattr` on the private
`_model`/`_voice`/`_conn` globals themselves), and
`tests/integration/test_ready_endpoint.py` proves `/ready`'s branching logic
by mocking the probe functions — deliberately fast and deterministic, never
loading a real Whisper/Piper model or opening a real DB connection in the
CI-gate path. `MEMORY_ENABLED=false` skips the DB probe entirely, matching
the plan's "disabled optional [resource] does not make the server unready"
requirement (stated there for vision; applied here to the same principle
for the DB, which is optional under the same flag).

### Task 3's "centralize unexpected exception handling" bullet needed no code

Wrote a regression-guard test first
(`test_an_unexpected_exception_never_leaks_internal_detail`) forcing a
genuinely unexpected `RuntimeError` deep in `/transcribe`'s call graph and
asserting the response body never echoes the exception message, its type
name, or a traceback. It already passed against current code — FastAPI's
default unhandled-exception path returns a bare `"Internal Server Error"`
in production (no `debug=True` anywhere in this app) — so per the plan's own
conditional ("only if tests prove internal details are currently exposed"),
no fix was needed. The `X-Request-ID` header this bullet also wanted was
already present on every response via Plan 0032's `RequestContextMiddleware`.

### Verification

- `rg`-style manual survey of every `HTTPException(status_code=...)` call
  site across the four routers confirmed the exact non-422 code set per
  route before writing `_EXPECTED_ERROR_CODES` in the RED test — every code
  a route can genuinely raise now has a documented `{"detail": str}` shape
  via the shared `ErrorResponse`/`error_responses()` helper.
- `uv run pyright server/src robot/src tests` — 0 errors.
- `uv run mypy --config-file=pyproject.toml server/src robot/src` — Success,
  92 source files.
- `just lint` (`ruff check .` + `ruff format --check .`) — clean.
- `just audit` — clean, no known vulnerabilities.
- `uv run pytest -m "not slow and not hardware and not eval"` — **1039
  passed**, 9 deselected (1019 baseline + 20 new: 9 in
  `test_api_contract.py`, 8 in `test_ready_endpoint.py`, 3 in
  `test_readiness_probes.py`).
- `git diff --check` — clean.
- Real-runtime acceptance: this plan only adds typed dependencies, OpenAPI
  metadata, and a new read-only `/ready` probe endpoint — no change to the
  voice/vision/memory hot path's request or response bodies. No live voice
  turn was required; `just run-server` reachability of `/ready`,
  `/health`, and `/docs` is the acceptance signal for this plan.
