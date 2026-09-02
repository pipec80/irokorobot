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
