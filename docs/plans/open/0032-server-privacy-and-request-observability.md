# Server Privacy and Request Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`. Execute this plan only when it
> is the explicitly authorized `NOW` item.

**Goal:** Remove raw domestic content from server/robot logs and add an
additive request correlation header without changing HTTP bodies.

**Architecture:** A pure-ASGI middleware owns request timing/correlation. A
logging filter reads a `ContextVar`; application paths emit metadata only.

**Tech Stack:** Python 3.12, FastAPI/Starlette ASGI, stdlib logging,
`contextvars`, pytest.

**Spec:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md)

## Global constraints

- Preserve all HTTP bodies, paths, status codes, audio, and streaming events.
- Request ID is context only; never identity or authorization.
- Do not add a logging dependency or `BaseHTTPMiddleware`.
- Remove raw content at DEBUG as well as INFO.
- The sentinel tests run through the shared `client` fixture, which is
  `scope="session"` and mutates the `settings` singleton (`memory_enabled`) for
  the whole run. Narrow that fixture's scope and restore state per test before
  asserting on captured logs — otherwise a sentinel can leak between tests and
  the assertions prove nothing. Plan 0043 recorded this gap.

## Permitted files

- `server/src/server/request_context.py` (new)
- `server/src/server/main.py`
- `server/src/server/logging_setup.py`
- `server/src/server/pipeline.py`
- `server/src/server/text_turn.py`
- `server/src/server/routers/transcribe.py`
- `server/src/server/streaming_render.py`
- `server/src/server/vision/describe.py`
- `server/src/server/stt.py`
- `server/src/server/memory/semantic.py`
- `server/src/server/memory/normalize.py`
- `server/src/server/memory/declarative.py`
- `server/src/server/memory/consolidation.py`
- `server/src/server/memory/context.py`
- `server/src/server/memory/relations.py`
- `server/src/server/vision/faces.py`
- `robot/src/robot/app.py`
- `robot/src/robot/app_streaming.py`
- `robot/src/robot/server_client.py`
- `tests/conftest.py`
- Focused tests under `tests/unit/` and `tests/integration/`

No persistence, schema, authentication, upload, or response-body change is in
scope.

## Interfaces

```python
request_id_var: ContextVar[str | None]


def current_request_id() -> str | None: ...


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None: ...
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...
```

Inbound `X-Request-ID` is preserved only when it parses as a UUID. Otherwise a
new UUID4 is generated. The response always includes `X-Request-ID`.

## Task 1: Prove the privacy leak and request-ID contract

- [ ] Add focused tests using unique sentinel values for transcript, LLM
  response, spoken sentence, PIN/token, and visual description. Exercise the
  existing classic and streaming paths with fake model boundaries and assert
  no sentinel appears in `caplog.text`.
- [ ] Add middleware tests proving generated UUID, preservation of a valid
  UUID, replacement of malformed/oversized input, response header insertion,
  and ContextVar reset after request completion.
- [ ] Run:

  ```powershell
  uv run pytest -n0 tests/unit/test_request_context.py tests/integration/test_sensitive_logging.py -q
  ```

  Expected before implementation: privacy/request-context assertions fail for
  the verified log sites and missing middleware.

## Task 2: Implement request context

- [ ] Create the pure-ASGI middleware. Wrap `send` to capture HTTP status and
  append the header before `http.response.start`; record monotonic duration;
  reset the ContextVar token in `finally`.
- [ ] Extend the existing formatter/filter so application records include
  `request_id` or `-` outside a request.
- [ ] Register the middleware without changing existing middleware order that
  affects response behavior.
- [ ] Emit one metadata-only completion event containing method, path, status,
  and duration. Do not log query/body/header values.

## Task 3: Redact application logs

- [ ] Replace every verified raw server/robot content log with event name,
  byte/character count, duration, and outcome.
- [ ] The confirmed sites at the time of writing, all at INFO:
  - `pipeline.py:90` — `STT heard: %r`, the full transcript
  - `text_turn.py:214` — `LLM response: %r`, the full model reply
  - `streaming_render.py:67` — `Stream sentence synthesized: %r`, the spoken
    sentence
  - `memory/semantic.py:176` — `query=%r`, the user's search text
  - `memory/normalize.py` — entity names and fact subjects at several lines
  - `routers/transcribe.py:367` — the first 60 characters of the transcript
  - `robot/app_streaming.py` — `Heard:` and `Speaking:` lines

  The first three were observed live in Plan 0043's acceptance run. Treat this
  list as a starting point, not a boundary — the sweep below is authoritative.
- [ ] The authoritative sweep, run during execution, found seven further sites
  that the original file list did not cover. They leak more than the known
  ones: household members' names and facts about them, written on every
  consolidation.
  - `memory/declarative.py:110,134` — the inserted or merged entity's name
  - `memory/declarative.py:195` — a fact's predicate and object value
  - `memory/consolidation.py:208` — `ent.name`, a person's name
  - `memory/consolidation.py:239` — `fact.subject`, a person's name
  - `memory/context.py:77` — `user_text[:40]`, the user's literal words
  - `memory/relations.py:102` — `text[:40]`, the user's literal words
  - `vision/faces.py:209` — the enrolled `label`, a household member's name
    written beside the row holding their face embedding. The most sensitive
    pairing found by the sweep.

  Those four modules were added to the permitted files above with Pipec's
  explicit authorization on 2026-09-02, because Task 3 declares this sweep
  authoritative while the original list would have blocked it, and because the
  completion criteria below cannot honestly be met while they remain.
- [ ] Scan all runtime code, not only the original sites:

  ```powershell
  rg -n "logger\.(debug|info|warning|error|exception)" server/src robot/src
  ```

- [ ] Rerun the focused tests and observe GREEN.
- [ ] Run `just lint`, `just typecheck`, `just test`, and `git diff --check`.

## Rollback

Revert this PR as one unit. It adds no schema/configuration migration and no
wire-body change.

## Completion criteria

- Sentinels never appear in captured logs at any configured level.
- Every HTTP response carries one valid request ID.
- Request context does not leak across sequential/concurrent requests.
- Existing HTTP/stream contract tests remain green.
- Independent review confirms no raw domestic content remains in runtime logs.

## Execution notes

Executed 2026-09-02 on branch `feat/0032-privacy-and-request-observability`,
strictly test-first: every one of the 24 new tests was watched failing against
real code before any production line changed, and each failed by printing the
sentinel it was written to catch.

### Redacted sites

Fourteen in total. The seven the plan named, plus seven the authoritative sweep
found:

| Site | Was leaking | Now logs |
|---|---|---|
| `pipeline.py:90` | the full transcript | `STT transcribed N chars` |
| `text_turn.py:214` | the full model reply | `LLM produced N chars` |
| `streaming_render.py:67` | each spoken sentence | `N chars`, duration, chunk |
| `memory/semantic.py:176` | the user's search words | `N chars`, top_k, hits |
| `memory/normalize.py` (7 sites) | entity names, fact subjects and objects | a `reason` marker |
| `routers/transcribe.py:367` | 60 chars of transcript | `N chars` |
| `stt.py:109` | each segment's spoken words (DEBUG) | segment timings and `N chars` |
| `memory/declarative.py:110,134` | the stored entity's name | type and id |
| `memory/declarative.py:195` | a fact's predicate and object value | predicate and `N chars` |
| `memory/consolidation.py:208,239` | a person's name inside a warning | the exception class |
| `memory/context.py:77` | the user's literal words | counts and `N chars` |
| `memory/relations.py:102` | the user's literal words | predicates, counts, `N chars` |
| `vision/faces.py:209` | the enrolled person's name | profile and entity ids |
| `robot/app.py`, `app_streaming.py`, `server_client.py` | heard and spoken text | character counts |

`vision/faces.py` was the most sensitive: a household member's name written
next to the row holding their face embedding.

### Deliberately left alone

- `llm.py:79,85` pass a `json.JSONDecodeError` to `%s`. Its `__str__` reports
  the message and position, never the document, so no model output escapes.
- `characters/__init__.py` logs profile and character names. Those come from
  configuration, not from the household.
- Identifiers (`person=`, `entity=`, `profile=`) stay: they are the correlation
  keys that replace content, and they resolve to a name only for someone who
  already has database access.

### Request correlation

`request_context.py` adds a pure-ASGI middleware — deliberately not
`BaseHTTPMiddleware`, which buffers the response body and would break the
NDJSON stream. It generates a UUID per request, preserves an inbound
`X-Request-ID` only when it parses as a UUID (the header is client-controlled),
stamps it on every response, and resets the `ContextVar` in `finally` so a
failed turn cannot bind its id to the next one. `RequestIdFilter` puts the id
on every record reaching a handler; the console format now carries it.

ASGI types are declared locally rather than imported from Starlette, so this
adds no new direct dependency.

Uvicorn's own access log is left in place: disabling it belongs to Plan 0038,
which owns the Uvicorn runtime configuration.

### Scope change

Four memory modules plus `vision/faces.py` were added to the permitted files
during execution with Pipec's explicit authorization. Task 3 declares the sweep
authoritative while the original file list would have blocked it, and the
completion criteria could not honestly have been met otherwise.

### Fixture isolation

`tests/conftest.py`'s `client` fixture moved from `scope="session"` to function
scope. It mutates the `settings` singleton, so at session scope one test's
captured logs could bleed into another's assertions — which would have made
these privacy assertions meaningless. Plan 0043 recorded the gap.

One existing test (`test_robot_app_streaming.py`) asserted that the robot
*logs* the spoken sentence, encoding the leak as expected behaviour. It now
asserts the opposite.

### Verification

- `just test` — **953 passed** (929 before, 24 added)
- `just lint` — clean
- `just typecheck` — mypy (90 files) and pyright, 0 errors
- `just audit` — Ruff S and pip-audit, no known vulnerabilities
- `just check` — all 17 hooks
- Real voice-turn acceptance: **pending Pipec**.
