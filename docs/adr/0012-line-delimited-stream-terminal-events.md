# 0012 — Require a terminal event in the line-delimited stream

- **Status:** Accepted
- **Date:** 2026-08-31
- **Accepted:** 2026-09-02
- **Corrected:** 2026-09-02 — the Context wrongly stated FastAPI had no
  JSON Lines support. It does. The decision is unchanged; only the
  reasoning behind it is now factual.

## Context

The server and robot currently exchange line-delimited JSON events for
incremental transcription/emotion/audio output. The robot validates ordering
and treats EOF without `done` as failure. If TTS or another stage fails after
headers are sent, HTTP status can no longer represent the failure and the
stream may end only by truncation.

FastAPI does support JSON Lines natively, measured on the pinned `0.141.1`: a
path operation declaring `-> AsyncIterable[Model]` and yielding models streams
`application/jsonl`, serialized by Pydantic and documented in OpenAPI. It is a
return-type convention rather than a response class, which is why an earlier
revision of this ADR wrongly claimed the capability was absent. The project's
own discriminated event union works under it unchanged.

The current transport is nonetheless `StreamingResponse` with
`media_type="application/x-ndjson"`, hand-serialized. Adopting the native form
would change the media type on a wire the robot already parses with
`aiter_lines()` and validates for event ordering, so it is a coordinated
producer/consumer migration, not a local refactor.

## Decision

Preserve the accepted line-delimited transport initially. Extend its typed
event union with a privacy-safe terminal `error` event. Every started stream
ends with exactly one `done` or `error`, followed by EOF. Errors detectable
before streaming starts remain ordinary non-200 HTTP responses.

Server and robot changes ship and test together. Migration to the native JSON
Lines media type requires its own explicit compatibility decision; Plan 0041
evaluates it with the measured evidence rather than assuming it is unavailable.

## Alternatives considered

- **Treat truncation as the only error signal:** workable but less diagnosable
  and harder to distinguish from transport loss.
- **Migrate immediately to native JSON Lines:** deferred, not rejected on
  capability grounds. It is available and would replace hand-serialization with
  typed, documented output; it is deferred only because it changes the media
  type for a live client and belongs in one reviewed producer/consumer slice.
- **Use SSE or WebSockets:** rejected because the current one-way request stream
  already fits the product and robot client.

## Consequences

### Positive

- Post-header failures have deterministic protocol semantics.
- The robot can report retryability without exposing private internal details.
- Existing successful event ordering remains stable.

### Negative

- Producer and consumer must change in one reviewed slice.
- Older clients must continue treating an unknown terminal event safely during
  any deployment transition.

## Review

Review when independently versioned clients exist or a new transport replaces
the current HTTP line stream.
