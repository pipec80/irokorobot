# Application Lifecycle and HTTP Resources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development`, `fastapi`, and
> `superpowers:verification-before-completion`.

**Goal:** Make FastAPI composition and cleanup explicit and reuse outbound
HTTP resources without pretending the whole runtime has injectable settings.

**Architecture:** `create_app()` composes metadata/middleware/routers and a
failure-safe lifespan. A focused resource object owns HTTPX and the owner
unlock service; existing DB ownership from Plans 0035-0036 is integrated only
through its proven lifecycle interface.

**Tech Stack:** FastAPI lifespan, `AsyncExitStack`, HTTPX, pytest.

**Spec:** Accepted ADR
[0010](../../adr/0010-fastapi-asgi-runtime-baseline.md).

## Permitted files

- `server/src/server/main.py`
- `server/src/server/resources.py` (new)
- `server/src/server/logging_setup.py`
- `server/src/server/llm_transport.py`
- `server/src/server/llm.py`
- `server/src/server/llm_streaming.py`
- `server/src/server/text_turn.py`
- `server/src/server/vision/describe.py`
- `server/src/server/memory/embeddings.py`
- Minimal callers/routers required to pass the resource
- Focused lifecycle/transport tests and fixtures

No settings-wide dependency rewrite, STT/TTS behavior change, API body change,
or new HTTP dependency is allowed.

## Interfaces

```python
@dataclass(slots=True)
class AppResources:
    http_client: httpx.AsyncClient
    owner_unlock_service: OwnerUnlockService


def create_app() -> FastAPI: ...
```

`create_app()` intentionally takes no `Settings` argument in this slice. A
future injectable-settings change must first migrate every affected global
consumer and prove behavior, not only `app.state`.

## Task 1: Prove lifecycle behavior with RED tests

- [ ] Importing `server.main` must not create log directories or outbound HTTP
  clients.
- [ ] Entering/exiting `TestClient(app)` creates/closes resources exactly once.
- [ ] A forced startup failure after client creation closes the client and any
  already-open DB/background resources.
- [ ] `app.state.ready` is false before/after lifespan and true only during a
  successful lifespan.

## Task 2: Compose the factory and owned lifespan

- [ ] Move logging side effects behind `configure_logging(settings)`.
- [ ] Create the resource dataclass and store one instance on `app.state`.
- [ ] Use `AsyncExitStack` or equivalent registered callbacks in reverse
  ownership order; preserve current preload/DB/retention startup semantics.
- [ ] Keep `app = create_app()` and console `main()` interfaces.
- [ ] Do not add STT/TTS shutdown/recreation unless a focused RED test proves
  the current executor prevents the required lifecycle.

## Task 3: Reuse outbound HTTP resources

- [ ] Add HTTPX `MockTransport` tests proving two LLM/VLM/embedding operations
  use the injected lifecycle client and no hot path constructs a client.
- [ ] Configure explicit connect/write/pool/read timeouts and bounded
  connections. Preserve longer inference-specific read deadlines at request
  level where necessary.
- [ ] Propagate the client through application collaborators without importing
  FastAPI into domain modules.
- [ ] Do not catch `asyncio.CancelledError` as an ordinary provider failure.

## Task 4: Verify

- [ ] Run:

  ```powershell
  rg -n "httpx\.AsyncClient\(" server/src/server
  ```

  Expected: lifecycle/resource construction only.
- [ ] Run focused lifespan/transport tests, `just lint`, `just typecheck`,
  `just test`, `just audit`, and `git diff --check`.

## Rollback

Keep factory/lifespan composition and HTTP-client propagation as separate
commits. Revert transport reuse first if provider behavior regresses; no data
migration is involved.

## Completion criteria

- Partial startup failure releases acquired resources.
- Hot inference paths reuse owned HTTP transport.
- Import has no new filesystem/network/model side effect.
- No test claims settings isolation that runtime consumers do not implement.

## Execution notes

### The true file footprint is much larger than the literal "Permitted files" list

Before writing any code, traced every `httpx.AsyncClient(` construction site
(`llm_transport.py` ×2, `memory/embeddings.py`, `vision/describe.py`) and
every transitive caller via `grep`. Making `client: httpx.AsyncClient` a
required, non-optional parameter — with zero internal fallback construction
anywhere in the call graph — is the only design that satisfies Task 4's grep
verification (`rg -n "httpx\.AsyncClient\(" server/src/server` must find
exactly one hit, in `main.py`'s lifespan). That requirement propagates the
parameter through 12 production files beyond the plan's named list:
`memory/consolidation.py`, `memory/semantic.py`, `memory/context.py`,
`vision/perception.py`, `routers/vision.py`, `streaming.py`, plus the two
routers not named at all (`routers/chat.py`, `routers/transcribe.py`). All of
this is covered by the plan's own "Minimal callers/routers required to pass
the resource" clause — each touch is exactly threading one parameter through,
nothing more.

### `app.state.resources` must be set before preload, not after

The first `lifespan()` draft assigned `app.state.resources` only after
`stt.preload()`/`tts.preload()` succeeded. That fails the Task 1 RED test for
a startup failure after client creation: if `tts.preload()` raises, the test
needs `app.state.resources.http_client.is_closed` to be `True`, which
requires `app.state.resources` to already exist. Fixed by assigning it
immediately after `http_client` enters the `AsyncExitStack`, before any
preload call — a startup failure downstream still leaves the client
reachable for cleanup.

### `memory/embeddings.py` had a real, pre-existing timeout inconsistency

`embed()`'s Ollama call used a hardcoded `timeout=30.0` — every other Ollama
call site in the codebase uses `settings.ollama_timeout_s`. Fixed as part of
threading the client through this file, with an inline comment explaining
why (Plan 0038 gave every other site a configurable timeout; this one was
missed).

### `vision.perceive()` is confirmed dead code, not newly introduced

`perceive()` (as opposed to `perceive_scene()`) has zero production callers
today. This matches an existing project record: face-recognition perception
was disconnected 2026-08-10 in PR #31; reconnecting it is future work under
P1.2. Still updated for signature consistency with `perceive_scene()`, but
its disconnection is not a new finding from this plan.

### Task 3's own instruction: rewrite `test_llm_transport.py` with `MockTransport`

The plan explicitly calls out that the previous pattern — monkeypatching the
`httpx.AsyncClient` constructor itself — is incompatible with an injected
client. Rewrote the file to build a real `httpx.AsyncClient(transport=
httpx.MockTransport(handler))` per test instead, matching the plan's stated
intent for Task 3's RED coverage.

### Real bug found only by running the full suite, not by static checks

`tests/conftest.py`'s `client` fixture (a synchronous `TestClient`) never
enters the app's lifespan — by design, so Whisper/Piper stay unloaded in
fast unit/integration tests. Before this plan, no router read
`app.state.resources`, so that was harmless. After Task 3, every endpoint
depending on `ResourcesDep` (`/transcribe`, `/transcribe/stream`, `/chat`,
`/vision/describe`, `/vision/respond`) started returning 500
(`AttributeError: 'State' object has no attribute 'resources'`) the moment a
test exercised it through this fixture.

`uv run pyright`/`mypy` stayed clean throughout — `Depends(get_resources)`
resolves at request time, not at type-check time, so nothing about this gap
is visible statically. It only surfaced once the full `just test` gate ran
(31 failures, all `AttributeError` or a stale-mock-signature symptom of the
same root cause), which is exactly why Task 4 requires running the real test
suite and not just lint/typecheck before declaring the plan done.

Fixed by having the `client` fixture construct a lightweight `AppResources`
itself (a real, unconnected `httpx.AsyncClient` plus the existing
`owner_unlock_service` singleton) and assign it to `app.state.resources`
before yielding — no lifespan, no Whisper/Piper load, but `ResourcesDep`
resolves correctly. The identical gap existed in two files' own local
`ASGITransport` client helpers (`test_chat_endpoint.py`,
`test_face_authenticated_turn.py`, which build their own async client instead
of using the shared fixture) — fixed the same way in each. A new shared
`http_client` fixture (a real `httpx.AsyncClient`, closed via `async with`)
was added for tests that inject a client directly into a function under a
mocked backend.

### Timeout/Limits design

Client-level defaults (`connect=5.0, read=10.0, write=10.0, pool=5.0`,
`max_connections=10, max_keepalive_connections=5`) are deliberately modest —
they're for the shared client's general behavior, not Ollama inference. Every
Ollama-calling site still passes its own `timeout=settings.ollama_timeout_s`
as a **per-request** override on `client.post(...)`/`client.stream(...)`,
preserving today's generous per-call Ollama timeout without making the whole
shared client wait that long by default on every request.

### Verification

- `rg -n "httpx\.AsyncClient\(" server/src/server` — exactly one real
  construction site (`main.py`'s lifespan); the only other hit is a docstring
  mention in `resources.py`.
- `uv run pyright server/src robot/src tests` — 0 errors, 0 warnings.
- `uv run mypy --config-file=pyproject.toml server/src robot/src` — Success,
  91 source files.
- `just lint` (`ruff check .` + `ruff format --check .`) — clean.
- `just audit` (bandit via `ruff check --select S` + `pip-audit --local`) —
  clean, no known vulnerabilities.
- `uv run pytest -m "not slow and not hardware and not eval"` — **1019
  passed**, 9 deselected (same baseline as before this plan; net zero test
  count change, since the fixes above corrected existing tests rather than
  adding new ones beyond `test_app_lifecycle.py`'s 4).
- `git diff --check` — clean.
- Two commits on the branch, matching the plan's own "Rollback" instruction:
  one for Task 1+2 (factory/lifespan composition), one for Task 3+4
  (HTTP-client propagation, including the test-fixture fixes it uncovered).
- Real-runtime acceptance (Pipec, 2026-09-03, `just run-server` +
  `just run-robot`): confirmed. The shared `httpx.AsyncClient` correctly
  reaches Ollama through the new lifecycle wiring — a full voice turn with
  Ollama up completed end-to-end (STT → LLM → TTS → audio played,
  `outcome=ok`). Two earlier turns, made while Ollama itself was still
  starting up, hit `httpx.ConnectError` and correctly spoke the fallback
  phrase instead of failing silently (P0-C6) — expected degradation, not a
  regression. STT, face recognition, and TTS all worked throughout. The
  verbose traceback logged for the expected "Ollama down" case was flagged
  as a quality-of-life gap and recorded as Plan 0044's new Task 6, not fixed
  here (out of this plan's scope).
