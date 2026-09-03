# Streaming Terminal Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`. Review server producer and
> robot consumer together.

**Goal:** Guarantee that every started line-delimited stream ends in exactly
one typed `done` or privacy-safe `error` event.

**Architecture:** Preserve the existing media type and successful event order.
Convert only post-header failures to an in-band terminal event. Pre-stream
validation remains an HTTP error. Adopting FastAPI's native JSON Lines support
is evaluated in Task 0 and decided explicitly — it is available, contrary to an
earlier revision of ADR 0012.

**Tech Stack:** FastAPI/Starlette `StreamingResponse`, Pydantic discriminated
events, robot async HTTP client, pytest.

**Spec:** Accepted ADR
[0012](../../adr/0012-line-delimited-stream-terminal-events.md).

## Permitted files

- `server/src/server/schemas_streaming.py`
- `server/src/server/streaming.py`
- `server/src/server/streaming_render.py`
- `server/src/server/routers/transcribe.py`
- `robot/src/robot/stream_events.py`
- `robot/src/robot/stream_validation.py`
- `robot/src/robot/server_client.py`
- `robot/src/robot/app_streaming.py`
- Focused server/robot stream tests

No change to `/transcribe`, successful event fields, STT/controller semantics,
or the TTS audio contract is allowed. The stream's media type and framing may
change only through Task 0's explicit decision, with the robot updated in the
same slice.

## Interface

```python
class StreamErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    detail: str
    retryable: bool = False
```

The event union includes existing text/emotion/audio/done plus error. Detail is
fixed client-safe text and never includes provider exception/model response.

## Task 0: Decide on native JSON Lines, with evidence

An earlier revision of ADR 0012 claimed FastAPI had no JSON Lines support and
this plan inherited that error. Measured on the pinned `fastapi 0.141.1`:

```python
@router.post("/transcribe/stream")
async def transcribe_stream(...) -> AsyncIterable[StreamEvent]:
    yield StreamTextHeardEvent(value=...)
```

streams `application/jsonl`, serialized by Pydantic and documented in OpenAPI.
The project's existing discriminated union
(`text_heard | emotion | audio | done`) was verified working under it unchanged.

What adoption would buy:

- hand-built newline-joined `model_dump_json()` output disappears from
  `streaming.py` and `streaming_render.py`;
- the event union appears in OpenAPI, so `/docs` finally describes what the
  stream emits — today it claims a plain JSON response;
- one terminal-event rule to enforce, in typed code rather than string
  assembly.

What it costs:

- the media type changes from `application/x-ndjson` to `application/jsonl`;
  the robot parses with `aiter_lines()` and validates event order, so producer
  and consumer must move together;
- `StreamingResponse` is returned directly today, which the official guidance
  advises against, but the current code also branches between two generators
  before streaming — that branching must survive the rewrite;
- errors detectable before the first byte must still produce a non-200
  response, which is harder to guarantee once the endpoint is a generator.

- [ ] Prototype the migration behind a test and measure whether the pre-stream
  `413`/`422` paths still return real HTTP errors.
- [ ] If they do, migrate in this plan and record the media-type change as a
  coordinated contract move. If they do not, keep `application/x-ndjson`,
  record the blocking reason here, and open the question in Plan 0042.
- [ ] Either way the terminal-event work below proceeds; it does not depend on
  the outcome.

## Task 1: Write producer/consumer RED tests

- [ ] Success sequence ends `done`, then EOF.
- [ ] TTS failure after text/emotion emits one `error`, then EOF, with no
  subsequent `done`.
- [ ] EOF without terminal is rejected by robot.
- [ ] Event after either terminal is rejected.
- [ ] Pre-stream oversized/invalid/no-speech failure remains non-200 JSON and
  never starts a 200 stream.
- [ ] Unknown error code is still safely representable by the robot.

## Task 2: Implement server terminal error

- [ ] Add the model and serialize it with the same one-object-per-line helper
  as current events.
- [ ] Catch only failures occurring after headers at the narrow render/pipeline
  boundary; log exception class/request ID and emit stable code/detail.
- [ ] Preserve cancellation and client disconnect; do not emit into a cancelled
  transport.
- [ ] Enforce one terminal in server-side validation/helpers.

## Task 3: Implement robot handling

- [ ] Parse `error` into a typed event and make terminal-state validation accept
  `done | error` exactly once.
- [ ] Map error to existing robot failure/retry UI/state without speaking or
  logging private detail.
- [ ] Preserve failure on truncated EOF for compatibility with older/broken
  servers.

## Task 4: Verify

- [ ] Run all stream unit/integration tests, `just lint`, `just typecheck`,
  `just test`, and `git diff --check`.
- [ ] Run a repeatable real `just run-server` + `just run-robot` success stream;
  a synthetic injected TTS failure is sufficient for the error branch.

## Rollback

Server and robot changes form one coordinated PR/commit boundary. Revert both;
older truncation detection remains functional.

## Completion criteria

- Exactly one terminal event exists for every started stream.
- Existing success event order remains unchanged.
- The media type either stays `application/x-ndjson` or moves to
  `application/jsonl` with the robot updated in the same slice — never
  drifts unrecorded.
- Robot safely handles `error`, truncation, and illegal post-terminal events.

## Execution notes

### Task 0: measured, decided — stays `application/x-ndjson`

Confirmed with a throwaway prototype (not committed) that FastAPI 0.141.1
does stream `application/jsonl` from a plain `async def ... -> AsyncIterator[Model]`
path operation with a discriminated union, exactly as ADR 0012 states — the
media type, per-line serialization, and OpenAPI `itemSchema` all work.

The blocking finding is in the OTHER half of Task 0's own test: **a
pre-first-yield `HTTPException` no longer produces a clean HTTP error once
the endpoint itself is the generator.** Reproduced directly:

```python
@app.post("/stream")
async def stream(fail: bool = False) -> AsyncIterator[EventA]:
    if fail:
        raise HTTPException(status_code=422, detail="bad input before streaming")
    yield EventA(value="hello")
```

Posting with `fail=true` does not return a 422 — it raises
`RuntimeError: Caught handled exception, but response already started.`
FastAPI's `_async_stream_jsonl` opens the streaming response and enters the
task group as soon as `async for item in gen` begins, which happens before
the generator function's own body runs its first line — so *any* exception
raised before the first `yield`, including today's `413`/`422` validation
that legitimately happens deep inside `transcribe_stream` (after STT, after
deciding the response plan), would stop being a clean pre-stream HTTP
error.

`transcribe_stream` today is a **regular** `async def` that does all
pre-stream work synchronously and only constructs
`StreamingResponse(stream_pipeline(...))` at the very end — that pattern is
what keeps `413`/`422` as real HTTP errors (confirmed still true after this
plan's changes by the untouched, still-passing
`test_transcribe_stream_resilience.py`). Migrating to native JSON Lines
would require collapsing that "prepare synchronously, then decide to
stream" shape into the generator itself, which breaks exactly the
regression Task 0 asked to measure for.

**Decision: keep `application/x-ndjson`.** Per Task 0's own instruction,
this is recorded here as the blocking reason, and the native-JSON-Lines
question is left open for Plan 0042. The terminal-event work (Tasks 1-4)
does not depend on this outcome and proceeded unchanged.

### Design: one wrapper at the router boundary, not scattered try/excepts

`streaming.guarantee_terminal_event()` wraps both `stream_pipeline(...)` and
`stream_response_plan(...)` at their `StreamingResponse(...)` call sites in
`routers/transcribe.py` — the single "narrow render/pipeline boundary" Task
2 asks for. It classifies exactly two cases (`TTSError` → `tts_failed`,
retryable; anything else → generic `internal_error`, not retryable) and
never touches `asyncio.CancelledError` — which is not an `Exception`
subclass, so Python's own `except Exception` already never catches it; no
explicit re-raise needed, just documented.

This meant `stream_response_plan()` (the deterministic-plan path, e.g.
"what day is it") needed **zero direct changes** — it had no TTS-failure
handling of its own before this plan, a real pre-existing gap the wrapper
closes for free by being applied uniformly to every stream producer instead
of patched into each one individually. `stream_pipeline()`'s own
`except TTSError: ...; raise` also needed no behavior change — it still
logs its operational metrics line and re-raises exactly as before; the
wrapper is what now catches that re-raised exception one level up and turns
it into the terminal `error` event instead of letting it truncate the ASGI
connection.

A defensive third branch: if a wrapped generator ever completes normally
without having yielded any `done`/`error`-typed line (an orchestration bug
neither of the above two branches would catch), the wrapper still emits one
`internal_error` event rather than silently closing the stream — verified
by `test_a_generator_that_ends_without_any_terminal_still_gets_one`.

### Robot: reused the existing failure state, no new state machine

`StreamValidationState` gained a fourth outcome (`error_seen`, alongside
`emotion_seen`/`audio_chunks`/`done_seen`) — unlike `done`, an `error`
terminal never requires `audio_chunks >= 1` first (a TTS failure can
legitimately happen on the very first sentence, before any audio has
played). `_audio_chunks()` in `app_streaming.py` raises the existing
`ServerError` when it accumulates a terminal `ErrorEvent`, which propagates
through `play_wav_stream()`'s already-documented "re-raises whatever
`chunks` raises" contract straight into `on_speaking_stream()`'s existing
`except (ServerError, NoSpeechError)` branch — `RobotState.ERROR`, no new
state, no new retry UI, per the plan's own "map error to existing
robot failure/retry UI/state" instruction. `error.detail` is logged (it is
fixed, client-safe text by the server-side contract, safe to log) but never
spoken — no TTS call happens on the robot side at all, so "never speak
private detail" holds by construction, not by a special case.

### Verification

- `uv run pyright server/src robot/src tests` — 0 errors.
- `uv run mypy --config-file=pyproject.toml server/src robot/src` — Success,
  92 source files.
- `just lint` — clean.
- `just audit` — clean, no known vulnerabilities.
- `uv run pytest -m "not slow and not hardware and not eval"` — **1059
  passed**, 9 deselected (1039 baseline + 20 new: 3 schema, 3 robot
  `stream_events`, 5 robot `stream_validation`, 3 robot `app_streaming`, 5
  server wrapper unit tests, 1 HTTP-level integration test).
- `git diff --check` — clean.
- `test_transcribe_stream_resilience.py`'s three pre-stream-error tests
  (`test_stream_stt_failure_returns_500`,
  `test_stream_empty_transcript_returns_422`,
  `test_stream_empty_audio_returns_422`) pass unchanged — direct proof the
  413/422/500 pre-stream contract this plan explicitly must not break is
  intact.
- Real-runtime acceptance (Pipec, 2026-09-03, `just run-server` +
  `just run-robot`, PR #111 already merged at the time): two full voice
  turns through `guarantee_terminal_event`'s new code path both completed
  successfully — `outcome=ok`, spoken audio, `done` event, no regression.
  The synthetic-TTS-failure branch of Task 4 was explicitly deferred by
  Pipec's own choice — the HTTP-level `test_stream_http_tts_failure_
  ends_in_one_error_event_not_done` test plus the five direct
  `guarantee_terminal_event` unit tests already exercise that path in
  depth (including the exact "no provider text/exception leaks" and
  "no `done` after `error`" invariants a live run could only re-confirm,
  not add new coverage to).
