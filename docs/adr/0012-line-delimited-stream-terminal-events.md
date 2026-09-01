# 0012 — Require a terminal event in the line-delimited stream

- **Status:** Proposed
- **Date:** 2026-08-31

## Context

The server and robot currently exchange line-delimited JSON events for
incremental transcription/emotion/audio output. The robot validates ordering
and treats EOF without `done` as failure. If TTS or another stage fails after
headers are sent, HTTP status can no longer represent the failure and the
stream may end only by truncation.

FastAPI now offers native JSON Lines support, but changing media type and
serialization solely to use a newer feature would create a coordinated wire
contract migration without resolving an unmet requirement by itself.

## Decision

Preserve the accepted line-delimited transport initially. Extend its typed
event union with a privacy-safe terminal `error` event. Every started stream
ends with exactly one `done` or `error`, followed by EOF. Errors detectable
before streaming starts remain ordinary non-200 HTTP responses.

Server and robot changes ship and test together. A later migration to native
FastAPI `application/jsonl` requires its own explicit compatibility decision.

## Alternatives considered

- **Treat truncation as the only error signal:** workable but less diagnosable
  and harder to distinguish from transport loss.
- **Migrate immediately to native JSON Lines:** rejected because framework
  feature adoption alone is not sufficient justification for a wire change.
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
