# Upload and Multipart Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development`, `fastapi`, and
> `superpowers:verification-before-completion`.

**Goal:** Reject oversized or structurally unsafe audio/image requests before
unbounded application reads or model processing.

**Architecture:** Combine Starlette's native raw route budgets with reusable
per-file bounded reads and the existing media validators. Plan 0043 already
resolved the dependency question this plan used to open with.

**Tech Stack:** FastAPI 0.141.1, Starlette 1.6.0
(`RequestBodyLimitMiddleware`), Pydantic settings, UploadFile, existing
WAV/image libraries, pytest.

**Spec:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md)

## Permitted files

- `server/pyproject.toml`, `uv.lock` — only to promote Starlette to a direct
  dependency and drop unused `sse-starlette`; no version move (Plan 0043 owns that)
- `server/src/server/settings.py`, `.env.example`
- `server/src/server/uploads.py` (new)
- `server/src/server/main.py`
- `server/src/server/routers/transcribe.py`
- `server/src/server/routers/vision.py`
- `server/src/server/routers/auth.py`
- Existing audio/image validation modules only if a RED test proves a missing
  structural limit
- Focused settings/upload/API tests

No endpoint path, required response field, model, face policy, or successful
audio format may change.

## Locked limits model

Use separate positive settings:

```python
max_audio_upload_bytes: int
max_image_upload_bytes: int
max_image_pixels: int
max_audio_duration_s: int
```

Keep the existing 10 MiB value as the initial audio semantic limit. Derive or
configure route body budgets so `/transcribe` can carry one valid audio file
plus one valid optional frame and multipart overhead. Do not impose an 11 MiB
global ceiling on that combined route.

## Task 1: Adopt the native body limit

Plan 0043 already moved the lock to `starlette 1.6.0` and measured the API
directly, so no dependency work opens this plan. The measured facts:

- `starlette.middleware.body_limit.RequestBodyLimitMiddleware(app,
  max_body_size)` exists. A hand-written ASGI limiter is unnecessary.
- `FastAPI(...)` does **not** accept `max_body_size` — only
  `Starlette.__init__` does. Register it with
  `app.add_middleware(RequestBodyLimitMiddleware, max_body_size=...)`.
- It is genuinely route-aware: a nested responder overrides
  `MAX_BODY_SIZE_SCOPE_KEY`, so a modest global budget plus a larger budget on
  the audio+frame route is expressible. This is what satisfies the baseline's
  rule against a fixed global ceiling.
- It rejects on `Content-Length` before reading and again on accumulated bytes
  during receive, so an oversized body never reaches application memory.

- [ ] Add Starlette as a direct `server` dependency, since server code now
  imports its middleware by name; remove unused `sse-starlette` after `rg`
  confirms no runtime import.
- [ ] **Decide the 413 body shape explicitly.** The middleware answers
  `text/plain` with `Content Too Large`, while the current handlers answer JSON
  `{"detail": ...}`. The robot client can observe the difference. Either keep
  the plain-text default and update `robot/` in this same slice, or install an
  exception handler that restores the JSON shape. Do not let this be decided by
  accident.
- [ ] Run:

  ```powershell
  uv lock --check
  uv sync --locked --all-packages --all-groups
  uv run pytest -n0 tests/integration/test_health_endpoint.py tests/integration/test_transcribe_validation.py -q
  ```

## Task 2: Write RED boundary tests

- [ ] Add tests for raw body over route budget, audio `limit + 1`, image
  `limit + 1`, audio+frame within combined budget, audio+frame over combined
  budget, empty file, excessive multipart fields/files, malformed multipart,
  false MIME, truncated WAV/image, excessive duration, and excessive decoded
  image pixels.
- [ ] In every rejection test, assert STT/VLM/face decoder boundary was not
  called when rejection can occur earlier.
- [ ] Observe RED with the focused API suite.

## Task 3: Implement bounded uploads

Create:

```python
async def read_limited_upload(upload: UploadFile, *, limit: int) -> bytes:
    """Read at most limit + 1 bytes from an untrusted upload."""
```

- [ ] Reject known `upload.size > limit` before read, then perform exactly one
  `await upload.read(limit + 1)` and reject excess/empty data.
- [ ] Centralize deterministic error mapping while preserving existing public
  `detail` compatibility.
- [ ] Apply it to audio, optional transcribe frame, vision endpoints, and owner
  face image upload.
- [ ] Enforce raw budgets through `RequestBodyLimitMiddleware` and keep
  byte-level media validation after MIME precheck.
- [ ] Record the untrusted-`filename` convention in code: `UploadFile.filename`
  is client-controlled metadata and never determines a path. No upload is
  persisted today, so this is a written convention with a test asserting the
  filename is not used to build a path — not a refactor.

## Task 4: Verify

- [ ] Run focused RED/GREEN tests, `just lint`, `just typecheck`, `just test`,
  `just audit`, `uv lock --check`, and `git diff --check`.
- [ ] Manually inspect OpenAPI upload content types; do not claim MIME proves
  file safety.

## Rollback

Revert the PR as one unit; the dependency move already landed and closed in
Plan 0043, so there is no upgrade to unwind here. Reverting restores the old
limits and requires no data rollback.

## Completion criteria

- No endpoint performs an unbounded `UploadFile.read()`.
- Raw and per-file limits reject before model work.
- A valid audio+frame request is not rejected by a too-small global budget.
- WAV/image structural constraints and all existing success contracts pass.
