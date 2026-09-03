# Iroko server production baseline

- **Status:** Target architecture; children 0032–0041 closed, 0042 and 0044
  remain
- **Audited commit:** `7d68641` (original audit); see "Verified baseline" for
  the current state after the closed children
- **Audit date:** 2026-08-31; last status refresh 2026-09-03
- **Scope:** `server/` and only the minimum `robot/` changes required by a
  shared HTTP or streaming contract

## Purpose

This document is the durable source of truth for hardening Iroko's HTTP
server. It prevents future work from repeating a full FastAPI audit while
preserving the repository rule that executable code, tests, and current
configuration outrank a stale implementation snapshot.

"Use FastAPI completely" means using FastAPI, Starlette, Pydantic, HTTPX,
Uvicorn, and asyncio idiomatically for problems the server actually has. It
does not mean enabling every framework feature. The baseline remains small,
local-first, typed, and explicit.

Before executing any child plan, revalidate only its named assumptions and
permitted files against the current tree. A contradiction stops that child
plan; it does not reopen the entire server audit.

## Authority and execution

This target is subordinate to runtime `AGENTS.md`,
[`implementation-guardrails.md`](implementation-guardrails.md), accepted
ADRs, and immutable API/audio contracts. The executable decomposition lives
under [`docs/plans/open/`](../plans/open/README.md).

Plan 0031 is a reference umbrella and is never executed as a batch. Plan 0043
(dependency refresh) ran first, as designed, then 0032–0040 closed in order:
0032 (privacy/observability), 0033 (owner-unlock hardening), 0034
(upload/multipart security), 0035 (SQLite transaction owner), 0036 (SQLite
write migration and outbox removal), 0037 (deterministic CI baseline), 0038
(Uvicorn runtime baseline), 0039 (application lifecycle and HTTP resources),
0040 (FastAPI contract and OpenAPI baseline), 0041 (streaming terminal
contract). Plan 0042 is next; see the
[operational board](../plans/README.md#operational-board) for the current
`NOW`/`QUEUED` state — this document does not duplicate it.

ADRs 0010-0013 were reviewed and accepted on 2026-09-02, so the child plans may
cite them as authority.

## Verified baseline

At the original audited commit (`7d68641`, 2026-08-31):

- `just lint`, `just typecheck`, `just test`, and `just audit` pass.
- The complete test suite passes with 929 tests.
- The deterministic `not slow` selection passes with 920 tests and 88.39%
  combined server/robot coverage.
- FastAPI is `0.141.1`, Starlette is `1.6.0`, Uvicorn is `0.52.4`, and
  Pydantic is `2.13.5` (Plan 0043 refreshed the lock on 2026-09-02; FastAPI was
  already at its latest release).
- The server uses one Uvicorn worker and binds to loopback by default.
- Server and robot share only HTTP/audio/stream contracts.

After Plan 0037 closed (2026-09-03): the deterministic gate itself changed —
CI runs `not slow and not hardware and not eval` (not `not integration`) with
`--cov-fail-under=80`, and the local target is **1015 tests, 89.77%
coverage** (997 after 0032–0037, plus 18 from Plan 0038). Re-run
`pytest -m "not slow and not hardware and not eval" --cov=server/src
--cov=robot/src --cov-fail-under=80` for the current number at any later
commit — this document does not update opportunistically.

The original audit verified these gaps. Each is now marked with the child
plan that closed it, or left open:

- ~~Audio, image, and face-frame uploads are fully read before the semantic
  size check.~~ **Closed by Plan 0034** — a raw ASGI body-limit middleware
  plus per-file bounded reads.
- ~~No raw ASGI request-body limit is installed.~~ **Closed by Plan 0034** —
  `RequestBodyLimitMiddleware`.
- ~~One process-global `aiosqlite.Connection` is shared by multi-await write
  transactions without coroutine transaction ownership.~~ **Closed by Plans
  0035/0036** — `db.transaction()`, and every runtime repository write
  migrated onto it.
- ~~The unused outbox has no consumer and commits separately from domain
  mutation.~~ **Closed by Plan 0036** — the outbox writer is removed.
- ~~Normal server and robot logs contain transcript, model-response, spoken
  sentence, or visual-description content in several paths.~~ **Closed by
  Plan 0032** — fourteen log sites stopped writing household content.
- ~~PIN shape validation occurs below the HTTP schema and may escape as an
  internal error; concurrent unlock attempts can race the limiter.~~
  **Closed by Plan 0033.**
- ~~Ollama, VLM, and embedding paths construct outbound HTTP clients per
  call.~~ **Closed by Plan 0039** — a single lifespan-owned `httpx.AsyncClient`
  is threaded through every call site instead.
- ~~`/health` is liveness-like but its documentation overstates readiness.~~
  **Closed by Plan 0040** — `/health` stays a cheap liveness check; a new
  `GET /ready` reports the real, side-effect-free readiness state.
- ~~Uvicorn stops after the configured maximum request count even though no
  verified supervisor is part of the current runtime contract.~~ **Closed by
  Plan 0038** — `uvicorn_max_requests` defaults to unset.
- ~~CI excludes useful local integration/API tests and overrides coverage to
  zero, despite the deterministic suite already exceeding 80%.~~ **Closed by
  Plan 0037.**

These findings were evidence at the audited commit, not eternal facts — the
strikethrough entries above are now closed, not still-true findings.

Two framework capabilities were measured directly after the Plan 0043 refresh
and constrain the child plans:

- Starlette `1.6.0` provides `RequestBodyLimitMiddleware`, so the raw body
  limit does not need a hand-written middleware. `FastAPI(...)` does not accept
  `max_body_size`; it is registered with `add_middleware`. It rejects on
  `Content-Length` and on accumulated bytes, and it is route-aware. It answers
  `413` as `text/plain`, not as the JSON error shape the current handlers emit.
- FastAPI supports JSON Lines natively: a path operation declaring
  `-> AsyncIterable[Model]` and yielding models streams `application/jsonl`,
  serialized by Pydantic and documented in OpenAPI. It is a return-type
  convention, not a response class. The project's discriminated stream event
  union works under it unchanged. **Measured by Plan 0041's own Task 0
  prototype and not adopted**: once FastAPI owns the streaming response,
  a pre-first-yield `HTTPException` in a generator-endpoint no longer
  returns a clean HTTP error (`RuntimeError: Caught handled exception, but
  response already started.`) — a real blocker for `/transcribe/stream`'s
  "validate synchronously, then decide to stream" shape. `application/
  x-ndjson` stays the wire format; the migration question is left open for
  Plan 0042.

Two gaps in the project's own safety net were found after the original
audit; one is closed:

- ~~`tests/conftest.py` builds its `TestClient` fixture at `scope="session"`
  and mutates the `settings` singleton (`memory_enabled`) for the whole run,
  so test isolation depends on ordering.~~ **Closed by Plan 0032** — the
  `client` fixture is function-scoped, with the rationale recorded directly
  in its docstring.
- **Open**, diagnosed and scoped: `filterwarnings = ["error"]` does not cover
  import-time warnings raised while loading `conftest.py`. An active
  `StarletteDeprecationWarning` about `starlette.testclient` with `httpx`
  passes through the suite unnoticed. Plan 0038 confirmed the fix
  (`uv add --group dev httpx2`) works but also breaks six
  `-> httpx.Response` annotations across five integration test files outside
  that plan's scope — tracked as Plan 0044's Task 5.


## Architectural invariants

### Server and robot boundary

- The server remains a generic cognitive/audio API and never imports robot
  hardware or robot process concepts.
- The robot remains a generic HTTP/audio client and never imports STT, LLM,
  TTS, memory, or FastAPI internals.
- A shared wire-contract change updates and tests producer and consumer in the
  same bounded plan.
- `POST /transcribe` preserves its existing required response fields. Adding a
  field is allowed; removing or renaming one requires explicit approval.
- Every function touching audio documents and enforces WAV, 16 kHz, mono,
  int16.

### FastAPI boundary

- FastAPI owns routing, dependency resolution, HTTP validation, response
  filtering, exception translation, and generated OpenAPI.
- Routers are async HTTP adapters. They validate external input, resolve HTTP
  context, call application/domain collaborators, and shape output.
- Domain and persistence modules do not import FastAPI, `Depends`,
  `HTTPException`, `Request`, or response types.
- Use `Annotated` dependencies where they remove a real global or document a
  real security input. Do not create dependencies for pure functions merely
  for stylistic consistency.
- Request and response models are separate when their contracts differ.
- Request models reject unknown fields when silent acceptance would hide a
  client error.
- Response models are explicit on sensitive endpoints so internal fields
  cannot leak accidentally.
- OpenAPI is generated from code; no parallel handwritten specification is
  maintained.

### Application lifecycle

- Heavy resources are not created as import side effects.
- Lifespan owns resources that require create/use/close semantics.
- Cleanup is guaranteed on normal shutdown and partial startup failure.
- `create_app()` may compose the application, but it must not claim fully
  injectable settings while runtime modules still read the global settings
  singleton.
- Re-entrant STT/TTS executor lifecycle is introduced only if repeated
  application lifespans require it and tests demonstrate the need.

### HTTP clients

- Hot inference paths reuse lifecycle-owned HTTPX transport/client resources.
- Connect, pool, write, and inference-read timeouts are explicit.
- Different inference deadlines use request-level timeouts or focused
  transports, not an unbounded new client per request.
- Generic automatic retries are forbidden. A retry requires an idempotent
  operation and an explicitly transient failure class.
- Cancellation is propagated; it is not converted into a successful fallback.

### Upload and multipart security

The validation sequence is:

```text
raw request-body budget
  -> multipart part/file/field budgets
  -> per-file bounded read
  -> declared media-type precheck
  -> byte-level format validation
  -> structural limits
  -> model processing
```

- Raw-body limits are route-aware. A fixed 11 MiB global limit is invalid for
  a route that may legitimately carry both audio and a face frame.
- Audio and image limits are independent settings. The combined multipart
  budget includes every permitted part plus framing overhead.
- Upload reads consume at most `limit + 1` bytes in application memory.
- Client-provided media type and filename are untrusted metadata.
- WAV bytes must satisfy the immutable audio contract and a bounded duration.
- Images must decode successfully and satisfy explicit format, dimension, and
  total-pixel limits before model use.
- Original upload filenames never determine a persisted path.
- Malformed multipart, empty files, excessive fields, excessive files,
  truncated media, and oversized decoded images have deterministic tests.

### Errors and privacy

- Existing public error wire shapes remain compatible unless a dedicated
  contract migration is approved.
- PINs, identity tokens, transcripts, LLM output, spoken TTS sentences, raw
  visual descriptions, biometrics, request bodies, and household values are
  absent from logs at every normal log level.
- Logs may contain request ID, method, path, status, duration, byte/character
  counts, component, outcome, and exception class.
- Validation responses never echo the raw invalid PIN or token.
- Unexpected exceptions return generic client-safe details and retain the
  internal traceback only in protected logs.
- A request ID is an additive response header and correlation field; it never
  becomes identity, authorization, or a conversation identifier.

### Owner unlock

- The HTTP schema accepts only ASCII decimal PINs of 6-12 digits and keeps the
  value in `SecretStr`.
- Malformed shape is `422`; incorrect credential is `401`; authenticated but
  forbidden context is `403`; limiter rejection is `429`.
- One complete local PIN attempt is serialized so concurrent expensive
  verification cannot bypass the rolling limiter.
- Loopback is evaluated with IP-address semantics for IPv4 and IPv6.
- Successful token responses use `Cache-Control: no-store`; limiter responses
  expose `Retry-After` when the block duration is known.
- Face, voice, text, name, request ID, or conversation ID never authorizes an
  unlock.

### SQLite

- Keep SQLite and `aiosqlite`; do not introduce SQLAlchemy for this baseline.
- One connection may remain process-local only with explicit ownership for an
  entire write transaction.
- Repository code outside the transaction boundary does not call `BEGIN`,
  `commit`, or `rollback` after migration.
- Composite operations accept an active transaction/connection rather than
  acquiring a nested non-reentrant lock.
- Startup migrations remain startup-exclusive and are distinguished from
  ordinary runtime writes.
- Retention follows the same transaction discipline as request-driven writes.
- `busy_timeout` defends against external SQLite contention; it does not
  replace coroutine transaction ownership.
- The outbox has no current consumer and is removed from runtime writes. Its
  migration history may remain when deleting it would create greater risk.

### Health and streaming

- `/health` is cheap process liveness and retains fields consumed by the
  current robot client.
- `/ready` is optional until a supervisor/orchestrator needs it; when added it
  checks only cheap mandatory local state and never performs LLM/VLM inference.
- The accepted line-delimited streaming contract is preserved initially.
- A started stream ends with exactly one terminal `done` or `error` event,
  then EOF.
- Failures detectable before headers remain ordinary non-200 HTTP responses.
- Post-header failures are represented in-band without private details.
- Native FastAPI JSON Lines is available and is adopted only through an
  explicit coordinated contract migration, never as an unreviewed refactor.

### Uvicorn and network posture

- One worker is an explicit invariant while grants, models, DB ownership, and
  background jobs are process-local.
- Loopback is the secure default bind address.
- Reload is development-only.
- Proxy headers are disabled unless a named trusted reverse proxy is deployed.
- Trusted hosts are explicit when the server is exposed beyond loopback.
- CORS is absent until a concrete cross-origin browser client exists.
- HTTPS redirection is absent until the TLS termination topology is known.
- Application request logging owns access logs; duplicate Uvicorn access logs
  are disabled when request middleware is installed.
- Maximum-request recycling is disabled without a verified supervisor.
- Concurrency reflects measured STT/TTS/LLM/DB capacity, not HTTP's theoretical
  maximum.

### Official FastAPI guidance

The official FastAPI skill (`fastapi/.agents/skills/fastapi` upstream) is a
source for HTTP-layer conventions. Where it and this baseline differ, record
the reason rather than drifting silently:

- Dependencies use `Annotated[..., Depends(...)]` behind a reusable type alias;
  shared dependencies are declared on the `APIRouter`, along with its prefix
  and tags.
- A return type is preferred over `response_model`; `response_model` is for
  when the public schema differs from what the function returns.
- `async def` is for path operations whose body is genuinely non-blocking. A
  blocking body belongs in `def`, which FastAPI runs in a threadpool, or in an
  explicit executor. "Always async" is not the official recommendation.
- `app.frontend()` serves built frontend assets instead of a manual
  `StaticFiles` mount.
- `ORJSONResponse`/`UJSONResponse` are deprecated; neither is used here.
- SQLModel is the upstream database recommendation. It does not apply: this
  project uses `sqlite-vec` through raw `aiosqlite`, and ADR 0011 keeps that.
- Asyncer and `ty` are upstream tooling recommendations. Neither is adopted:
  the project already standardises on asyncio, mypy and pyright, and adding
  them would be change without a demonstrated need.

## Deliberate non-goals

This baseline does not introduce SQLAlchemy, Redis, Celery, Kafka, NATS,
Docker, Kubernetes, an API gateway, OAuth2/JWT, wildcard CORS, an external DI
container, generic retry middleware, manual OpenAPI YAML, generated SDKs,
custom docs frontend, or an OpenTelemetry backend.

It does not implement wake word, LiveKit, ROS2, Chatterbox, or emotion-driven
TTS modulation.

## Verification policy

Every child plan uses TDD for behavior changes and runs focused tests before
repository gates. The deterministic PR gate must include unit, API, and local
integration tests while excluding only slow models, real hardware, and
model-quality evaluations. Coverage remains at least 80% without production
omissions added solely to cross the threshold.

Automated tests are component/regression evidence. Changes affecting the real
voice path additionally require repeatable `just run-server` +
`just run-robot` scenarios before product acceptance is claimed.

## Review triggers

Revisit this baseline when any of the following becomes real:

- multiple independently deployed robot/client versions;
- LAN or public exposure through a reverse proxy;
- more than one Uvicorn worker;
- a second server process writing the same SQLite database;
- a durable outbox consumer or synchronization product requirement;
- a browser origin different from the API origin;
- measured capacity showing executor queues retain unacceptable payloads;
- a replacement transport such as WebRTC.
