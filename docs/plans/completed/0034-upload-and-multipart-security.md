# Upload and Multipart Security Implementation Plan

> **Status:** Completed 2026-09-02. Historical evidence only — this document
> is not an instruction and authorizes nothing.

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

- [x] Add Starlette as a direct `server` dependency, since server code now
  imports its middleware by name; remove unused `sse-starlette` after `rg`
  confirms no runtime import.
- [x] **Decide the 413 body shape explicitly.** The middleware answers
  `text/plain` with `Content Too Large`, while the current handlers answer JSON
  `{"detail": ...}`. The robot client can observe the difference. Either keep
  the plain-text default and update `robot/` in this same slice, or install an
  exception handler that restores the JSON shape. Do not let this be decided by
  accident.
- [x] Run:

  ```powershell
  uv lock --check
  uv sync --locked --all-packages --all-groups
  uv run pytest -n0 tests/integration/test_health_endpoint.py tests/integration/test_transcribe_validation.py -q
  ```

## Task 2: Write RED boundary tests

- [x] Add tests for raw body over route budget, audio `limit + 1`, image
  `limit + 1`, audio+frame within combined budget, audio+frame over combined
  budget, empty file, excessive multipart fields/files, malformed multipart,
  false MIME, truncated WAV/image, excessive duration, and excessive decoded
  image pixels.
- [x] In every rejection test, assert STT/VLM/face decoder boundary was not
  called when rejection can occur earlier.
- [x] Observe RED with the focused API suite.

## Task 3: Implement bounded uploads

Create:

```python
async def read_limited_upload(upload: UploadFile, *, limit: int) -> bytes:
    """Read at most limit + 1 bytes from an untrusted upload."""
```

- [x] Reject known `upload.size > limit` before read, then perform exactly one
  `await upload.read(limit + 1)` and reject excess/empty data.
- [x] Centralize deterministic error mapping while preserving existing public
  `detail` compatibility.
- [x] Apply it to audio, optional transcribe frame, vision endpoints, and owner
  face image upload.
- [x] Enforce raw budgets through `RequestBodyLimitMiddleware` and keep
  byte-level media validation after MIME precheck.
- [x] Record the untrusted-`filename` convention in code: `UploadFile.filename`
  is client-controlled metadata and never determines a path. No upload is
  persisted today, so this is a written convention with a test asserting the
  filename is not used to build a path — not a refactor.

## Task 4: Verify

- [x] Run focused RED/GREEN tests, `just lint`, `just typecheck`, `just test`,
  `just audit`, `uv lock --check`, and `git diff --check`.
- [x] Manually inspect OpenAPI upload content types; do not claim MIME proves
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

## Execution notes

Executed 2026-09-02 on branch `feat/0034-upload-and-multipart-security`,
test-first throughout: every new test was watched failing against real code —
for the correct reason, never a typo — before the matching production line
changed.

### `UploadFile.size` does not exist on this Starlette version

Task 3 assumed a "reject known `upload.size > limit` before read" pre-check.
Checked directly: `starlette.datastructures.UploadFile` on 1.6.0 exposes only
`close`, `content_type`, `read`, `seek`, `write` — no `size` attribute. The
bounded read (`read(limit + 1)`, reject if the result is longer than `limit`)
is the only mechanism; there is nothing to pre-check.

### The 413 body-shape question was already closed, by measurement

Plan 0043 already established that the robot's `server_client.py` reads only
`exc.response.status_code` on an `HTTPStatusError`, never the body. Verified
again here: none of its four call sites parse error JSON. So
`RequestBodyLimitMiddleware`'s default `text/plain` "Content Too Large" body
needed no wrapping handler — the risk the plan flagged does not apply to this
client.

### The middleware had to stay inside `RequestContextMiddleware`, not outside

Plan 0032 guarantees every response carries `X-Request-ID`. Starlette builds
`user_middleware` innermost-to-outermost in *reverse* registration order — the
last `add_middleware()` call becomes the outermost wrapper. Registering the
body limit after `RequestContextMiddleware` would have put it *outside* the
correlation layer, so a `413` would ship with no request id, breaking an
already-closed plan's own completion criterion. Registered between `GZip` and
`RequestContext` instead; verified directly against a live `TestClient` that a
`413` carries `X-Request-ID`.

### The raw-body test I first wrote proved nothing

The first version of the "raw body over budget" test sent an oversized
`audio` field alone. That field already exceeds its own
`max_audio_upload_bytes` per-file limit, so the per-file check in
`_read_audio_upload` would reject it with or without the new middleware — the
test passed for a reason unrelated to what it claimed to prove, which is the
kind of test that would have silently reported the middleware as tested when
it was not.

Replaced with a test that genuinely isolates the raw-body layer, and it found
a real gap: `face_authentication_enabled` defaults to `False`, and in that
state `transcribe`'s handler never calls `_read_optional_frame` at all — the
`frame` field is accepted by the signature but structurally never read by any
per-file check. Before this plan, an oversized `frame` field on that default
configuration was invisible to the application; nothing bounded it. Confirmed
by watching that exact scenario return `422` (from the audio path's normal
processing) instead of `413` before the middleware existed, then `413` after.

### A genuine gap in `validate_wav_contract`, not just a rename

Splitting `max_upload_bytes` into per-file settings was the trigger, but
duration itself was never checked before this plan: `validate_wav_contract`
verified channels, sample width, frame rate, and that at least one frame
existed — never how long the recording was. A format-perfect multi-hour WAV
passed every existing check. `max_duration_s` is now a required keyword
argument, not a default, so no caller can silently skip it.

### Ripple beyond the permitted files

Two call sites outside the plan's file list broke because they called the
changed functions with their old signatures: `scripts/client_test.py` (calls
`validate_wav_contract`) and `tests/unit/test_settings.py`/
`tests/unit/test_client_test_audio.py` (asserted/mocked the old setting name
and old signature). Fixed as mechanical signature updates, not new behavior —
same category as Plan 0033's `main.py` addition: required to make the
plan's own change consistent, not a scope expansion.

### Dependency move

`starlette` promoted to a direct `server` dependency (`>=1.6.0,<2.0.0`,
matching the version Plan 0043 already locked); `sse-starlette` removed after
confirming zero runtime imports, along with its now-pointless `deptry`
per-rule ignore. `uv add`/`uv remove` both hit a Windows file-lock on
`serve.exe` because Pipec's own `just run-server` was still running against
this working tree; resolved by Pipec stopping it, per this repo's rule that
local server processes are his to start and stop.

### OpenAPI manual inspection (Task 4)

`Body_transcribe_transcribe_post.frame` declares
`{"type": "string", "contentMediaType": "application/octet-stream"}`; every
other upload field declares only `{"type": "string"}`. OpenAPI does not encode
or enforce which MIME types a field accepts — confirming the plan's own
instruction not to claim MIME proves file safety. The real contract is the
magic-byte precheck plus the real decode this plan leaves untouched.

### Verification

- `just test` — **987 passed** (968 at Plan 0033's close, 19 added net)
- `just lint` — clean
- `just typecheck` — mypy (91 files) and pyright, 0 errors
- `just audit` — Ruff S and pip-audit, no known vulnerabilities
- `just check` — all 17 hooks
- Real acceptance: **PASS**, 2026-09-02 19:35–19:36. Three consecutive voice
  turns through `just run-server` + `just run-robot`, none rejected by any
  new limit: two ordinary turns (`stt=1581ms/1913ms`, `llm=14151ms/3443ms`,
  `outcome=ok`), and one face-authenticated turn exercising exactly the code
  this plan touched in `auth.py`/`vision/faces.py` —
  `status=identified role=owner`, the deterministic `get_children` tool
  firing (`stt=1749ms llm=0ms tts=108ms total=4909ms`). Pipec independently
  confirmed `/transcribe`, `/vision/*`, and the face-enroll endpoint all
  still resolve from `/docs`.

## Closure

Merged as PR #98. Real HTTP-path acceptance and the OpenAPI inspection both
recorded above. The capsule's next child is Plan 0035. Closing this plan does
not authorize it.
