# P0 Runtime Acceptance Design

> **Status:** Proposed — P0 foundation code is merged, but its household path
> is not yet demonstrable through `just run-server` plus `just run-robot`.

## Goal

Make the completed P0 contracts observable through the existing voice path
from an empty local database. A feature is accepted only when an operator can
run the server and robot, speak the documented scenarios, and observe the
correct response, safe denial, and audit outcome.

## Why this is a P0 closure task

`/transcribe` currently calls `process_text_turn` directly after STT. The
robot calls `/transcribe`; therefore it bypasses the P0.3 controller and the
P0.5-B2 household tools. `/chat` constructs the controller, but its public
adapter supplies an unknown actor. Existing offline tests prove the contracts,
not the end-to-end operator flow.

This design closes that gap. It does **not** start the P1 roadmap: there is no
speaker recognition, face evidence, generalized household onboarding, public
admin API, WorldState, or new perception capability.

## Acceptance definition

P0 is product-accepted only when all of these are true on a disposable local
database:

1. `just run-server` and classic `just run-robot` use the same controller
   decision path for a voice turn.
2. Without trusted local session evidence, a private family question is denied
   before any v4 read and reveals no protected value.
3. A short, confirmed local acceptance interview creates only the facts needed
   to exercise P0: one owner, children, active `child_of` relations, ISO birth
   dates, and multiple preferences.
4. A temporary explicit local manual session permits the owner to ask the
   supported self-child questions through the microphone and hear the
   deterministic result through Piper.
5. The operator can inspect an audit record proving tool authorization before
   the v4 read, with no child names, dates, preferences, or ages in audit
   metadata.
6. Repeating the run after `just reset-db` produces the same observable
   results.

## Architecture

### Slice R1 — voice-controller bridge

After STT, `/transcribe` creates the same typed text `CognitiveEvent` used by
`/chat`, resolves the active person through an adapter, and calls
`CognitiveController.handle`. The existing `process_text_turn` remains the
controller's generic-conversation delegate, so STT, TTS, response schema,
timings, and the WAV contract remain unchanged.

With no trusted evidence the adapter returns `unknown`. This is the default
for every normal robot run. It must prove two live cases before R2 begins:

- “¿Qué día es hoy?” follows the deterministic calendar path.
- “¿Cómo se llaman mis hijos?” is denied without calling the household reader.

Classic `/transcribe` is the acceptance target because `ROBOT_STREAMING` is
off by default. Streaming remains unchanged and is explicitly out of this
closure scope; the runbook requires it to remain disabled during acceptance.

### Slice R2 — confirmed local acceptance interview

R2 is a bounded test-data interview, not the P1 household onboarding product.
Iroko collects only the values required by P0 acceptance: owner display name,
children names, each child birth date, and one or more owner preferences. Each
answer becomes a typed candidate. No candidate is a durable family truth merely
because it was spoken or extracted by a model.

At the end, Iroko presents a summary. A local operator then performs an
explicit confirmation outside spoken language. That local confirmation creates
the owner role and the minimal v4 entities, relations, literals, consent state,
and audit record. A rejected or interrupted interview writes no accepted
household truth.

The implementation must reuse the existing v4 predicate registry,
repositories, owner bootstrap, policy evaluator, audit writer, and
`IdentitySessionRegistry`. It must not write legacy v3 facts as the source of
truth for this acceptance flow.

### Temporary manual session

After local confirmation, the operator explicitly selects the confirmed owner
for one short-lived acceptance session. The robot sends only an opaque session
token; the server resolves that token to existing manual evidence. The token is
not a person ID, is never derived from voice/text/face, is not logged, expires,
and is rejected when absent or expired.

The session mechanism is local acceptance infrastructure only:

- default off;
- permitted only when the server is loopback-bound;
- requires an explicit operator action after local confirmation;
- has a bounded lifetime and an explicit clear operation;
- must not create an HTTP identity, consent, or owner-bootstrap API.

When the session is absent, expired, or cleared, `/transcribe` returns to
`unknown` and the protected path remains denied.

## Operator scenarios

| Scenario | Spoken input | Required result |
|---|---|---|
| Empty start | First interaction after reset | Guided acceptance interview; no invented household data. |
| Candidate review | Interview complete | Iroko summarizes pending owner, children, dates, and preferences. |
| Local confirmation | Operator confirms outside voice | Minimal v4 data, owner role, consent, and audit record exist. |
| Supported result | “¿Cómo se llaman mis hijos?” | Exactly the confirmed child names, through STT/controller/tools/TTS. |
| Supported count | “¿Cuántos hijos tengo?” | Deterministic count matching active v4 relations. |
| Routing guard | “¿Qué día es hoy?” | Current date; never an age or family answer. |
| Unsupported guard | “¿Qué hora es?” | Safe unavailable/unknown response until a time tool is deliberately added. |
| Privacy guard | Session absent or cleared, then child question | No protected value and no v4 read. |

## Evidence required for completion

The implementation plan must require all of the following:

- observed RED/GREEN unit and integration tests for each new boundary;
- an HTTP integration test for `/transcribe` proving it invokes the controller;
- a disposable-DB acceptance test proving interview confirmation, session
  expiry, allowed family answer, denied family answer, and audit ordering;
- an operator run recorded with `just reset-db`, `just services`, `just
  run-server`, and `just run-robot` using the runbook;
- transcript, returned `llm_response`, and audible Piper response checked
  against each documented scenario;
- `just lint`, `just typecheck`, `just test`, `just audit`, `just check`,
  `git diff --check`, and green GitHub CI.

Passing tests alone never completes this work. A wrong live answer fails the
slice even if every automated check is green.

## Non-goals and stop conditions

- No P1 general onboarding, speaker recognition, face identity, identity
  fusion, WorldState, scene graph, semantic retrieval, cloud, or hardware
  action.
- No persistent biometric data, public identity field, public consent field,
  public admin endpoint, cloud provider, new dependency, or audio schema
  change.
- Stop for an ADR if the local session cannot remain loopback-only and
  time-bounded, if confirmation requires a public admin API, if the v4 write
  needs an unapproved migration, or if the `/transcribe` contract must break.

## Proposed delivery order

1. R1 voice-controller bridge and live safe-routing runbook checkpoint.
2. R2 confirmed interview, local temporary session, and supported family QA.
3. P0 closure evidence only after the complete operator run is recorded.

P1 remains unstarted until these three items are accepted.
