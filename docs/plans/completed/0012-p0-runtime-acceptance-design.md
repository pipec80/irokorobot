# P0 Runtime Acceptance Design

> **Status:** Partially implemented historical design — Plan 0013 completed
> the classic voice bridge. Plan 0014 must close public-route policy parity
> before R1 can be operator-accepted. The R2 personal identity/session design
> below is superseded as an implementation target by ADR 0006 and Plan 0015;
> it is not a P0 exit criterion.

## Goal

Make the completed P0 contracts observable through the existing voice path
from an empty local database. A feature is accepted only when an operator can
run the server and robot, speak the documented scenarios, and observe the
correct response, safe denial, and audit outcome. This proves the `personal`
profile foundation; it does not onboard a family product.

## Why this is a P0 closure task

The robot calls public audio routes while the P0 controller and policy were
first proven through isolated tests and `/chat`. Plan 0013 brought classic
`/transcribe` through the controller with an unknown actor. The remaining
streaming and visual dialogue gaps are recorded separately in Plan 0014.
Existing offline tests prove contracts, not the end-to-end operator flow.

The R1 portion of this design closes that gap. It does **not** start the P1
roadmap: there is no speaker recognition, face evidence, generalized household
onboarding, public admin API, WorldState, or new perception capability.

> **R2 archival notice:** The following R2 text records an earlier acceptance
> concept. It must not be implemented as P0 work. Local personal
> administration, consented face/voice evidence, fusion, and personal
> acceptance now belong to the post-P0 personal-companion design in
> [Plan 0015](../open/0015-personal-companion-design.md), under
> [ADR 0006](../../adr/0006-personal-and-family-companion-profiles.md).

## Historical R1/R2 acceptance definition (superseded for P0)

The following six-item definition is retained to preserve the original R2
acceptance concept. P0 closure now requires the bounded public-route hardening
plans and R1 operator evidence only. The former R2 criteria are P1 design input
and require a future Ready plan under Plan 0015.

The former proposal considered P0 product-accepted only when all of these were
true on a disposable local database:

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

Classic `/transcribe` is the first acceptance target because `ROBOT_STREAMING`
is off by default. Until Plan 0014 is complete, streaming and visual dialogue
remain disabled in the P0 runbook.

### Slice R2 — confirmed local personal acceptance interview

R2 is a bounded test-data interview, not the P1 general onboarding product.
Iroko collects only the values required by P0 acceptance: one personal owner,
children names, each child birth date, and one or more owner preferences. Each
answer becomes a typed candidate. No candidate is durable truth merely because
it was spoken or extracted by a model.

At the end, Iroko presents a summary. A local operator then performs an
explicit confirmation outside spoken language. That local confirmation creates
the owner role, minimal v4 entities/relations/literals, an acceptance-only
scoped consent decision, and an audit record. It does not implement persistent
consent UX; that belongs to later family onboarding. A rejected or interrupted
interview writes no accepted household truth.

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
| Local confirmation | Operator confirms outside voice | Minimal v4 data, owner role, scoped acceptance consent, and audit record exist. |
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
