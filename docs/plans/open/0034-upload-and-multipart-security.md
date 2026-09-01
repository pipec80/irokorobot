# Upload and Multipart Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development`, `fastapi`, and
> `superpowers:verification-before-completion`.

**Goal:** Reject oversized or structurally unsafe audio/image requests before
unbounded application reads or model processing.

**Architecture:** Resolve a compatible Starlette body-limit API in an isolated
dependency change, then combine raw route budgets with reusable per-file
bounded reads and existing media validators.

**Tech Stack:** FastAPI 0.141.x, compatible Starlette, Pydantic settings,
UploadFile, existing WAV/image libraries, pytest.

**Spec:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md)

## Permitted files

- `server/pyproject.toml`, `uv.lock`
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

## Task 1: Isolate Starlette compatibility

- [ ] Verify the selected body-limit API against official Starlette release
  notes and the FastAPI dependency range.
- [ ] Add Starlette as a direct dependency only because server code imports its
  middleware/API directly; remove unused `sse-starlette` after `rg` confirms no
  runtime import.
- [ ] Update only intended lock entries and run:

  ```powershell
  uv lock --check
  uv sync --locked --all-packages --all-groups
  uv run pytest -n0 tests/integration/test_health_endpoint.py tests/integration/test_transcribe_validation.py -q
  uv run pip-audit --local
  ```

- [ ] Stop if FastAPI/Starlette compatibility or existing contracts fail.

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
- [ ] Enforce raw budgets at ASGI/routing level and keep byte-level media
  validation after MIME precheck.

## Task 4: Verify

- [ ] Run focused RED/GREEN tests, `just lint`, `just typecheck`, `just test`,
  `just audit`, `uv lock --check`, and `git diff --check`.
- [ ] Manually inspect OpenAPI upload content types; do not claim MIME proves
  file safety.

## Rollback

Dependency upgrade and upload implementation must be separate commits so a
compatibility failure can revert the upgrade without reverting unrelated
security code. Reverting restores old limits; it requires no data rollback.

## Completion criteria

- No endpoint performs an unbounded `UploadFile.read()`.
- Raw and per-file limits reject before model work.
- A valid audio+frame request is not rejected by a too-small global budget.
- WAV/image structural constraints and all existing success contracts pass.
