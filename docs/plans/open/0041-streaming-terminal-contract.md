# Streaming Terminal Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`. Review server producer and
> robot consumer together.

**Goal:** Guarantee that every started line-delimited stream ends in exactly
one typed `done` or privacy-safe `error` event.

**Architecture:** Preserve the existing media type and successful event order.
Convert only post-header failures to an in-band terminal event. Pre-stream
validation remains an HTTP error.

**Tech Stack:** FastAPI/Starlette `StreamingResponse`, Pydantic discriminated
events, robot async HTTP client, pytest.

**Spec:** Proposed ADR
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

No change to `/transcribe`, media type, JSON framing, successful event fields,
STT/controller semantics, or TTS audio contract is allowed.

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
- Existing success order/media type remains unchanged.
- Robot safely handles `error`, truncation, and illegal post-terminal events.
