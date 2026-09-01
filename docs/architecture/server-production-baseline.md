# Iroko server production baseline

- **Status:** Target architecture; implementation queued behind Plan 0030
- **Audited commit:** `7d68641`
- **Audit date:** 2026-08-31
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

Plan 0030 remains the only `NOW` item. Plan 0031 is a reference umbrella and
is never executed as a batch. Plan 0032 becomes `NOW` only after Plan 0030
closes and Pipec explicitly authorizes it.

The proposed ADRs 0010-0013 record decisions for review. They are not accepted
authority until their status is explicitly changed after review.

## Verified baseline

At the audited commit:

- `just lint`, `just typecheck`, `just test`, and `just audit` pass.
- The complete test suite passes with 929 tests.
- The deterministic `not slow` selection passes with 920 tests and 88.39%
  combined server/robot coverage.
- FastAPI is `0.141.1`, Starlette is `1.3.1`, and Uvicorn is `0.52.1`.
- The server uses one Uvicorn worker and binds to loopback by default.
- Server and robot share only HTTP/audio/stream contracts.

The audit also verified these gaps:

- Audio, image, and face-frame uploads are fully read before the semantic
  size check.
- No raw ASGI request-body limit is installed.
- One process-global `aiosqlite.Connection` is shared by multi-await write
  transactions without coroutine transaction ownership.
- The unused outbox has no consumer and commits separately from domain
  mutation.
- Normal server and robot logs contain transcript, model-response, spoken
  sentence, or visual-description content in several paths.
- PIN shape validation occurs below the HTTP schema and may escape as an
  internal error; concurrent unlock attempts can race the limiter.
- Ollama, VLM, and embedding paths construct outbound HTTP clients per call.
- `/health` is liveness-like but its documentation overstates readiness.
- Uvicorn stops after the configured maximum request count even though no
  verified supervisor is part of the current runtime contract.
- CI excludes useful local integration/API tests and overrides coverage to
  zero, despite the deterministic suite already exceeding 80%.

These findings are evidence at the audited commit, not eternal facts.

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
- Native FastAPI JSON Lines is adopted only through an explicit coordinated
  contract migration, not to maximize framework feature count.

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
