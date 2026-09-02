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
