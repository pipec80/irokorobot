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
- `server/src/server/vision/describe.py`
- `server/src/server/stt.py`
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
