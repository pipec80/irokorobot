# Personal companion design — Iroko and Pipec

> **Status:** Product direction approved. The immediate spine is
> [Plan 0024](0024-owner-authenticated-memory-mvp-design.md), decomposed into
> executable Plans 0025–0028. All four are merged/executed (PR #56, PR #57,
> PR #64, and Plan 0028's 2026-08-21 real-hardware run). PC-1 is accepted:
> classic and streaming authenticated-owner flows are each confirmed 3x with
> real hardware. Existing foundations listed below are production code and
> must be reused. PC-2's code/test slice is merged —
> [Plan 0029](0029-consented-local-face-evidence.md), PR #73, 2026-08-25 — a
> protected turn resolves the owner from an in-request webcam frame through
> the same typed evidence and authorization contract the PIN uses, with the
> PIN kept as an independent recovery path. It has no liveness/anti-spoofing
> defense and no real-camera calibration yet; PC-2 itself is not accepted
> until that follow-up plan closes it. Voice, fusion, and visual-companion
> acceptance (PC-3 through PC-6) remain later work, not started.

## Objective

Make Iroko useful as Pipec's secure local companion as soon as possible,
without discarding the existing cognitive, memory, policy, STT, TTS, or vision
foundations. The first proof is deliberately visceral: authenticated Pipec asks
who his children are and hears “Máximo y Dominga”; a request without valid
authentication receives no protected names or hints.

This is the `personal` profile from
[ADR 0006](../../adr/0006-personal-and-family-companion-profiles.md). The same
architecture later supports a family/multiple-person profile with stricter
per-person privacy; this slice does not build that later product.

## Governing decisions

- [ADR 0007](../../adr/0007-first-boot-and-default-posture.md) keeps explicit
  first boot, owner-before-household ordering, completion state, and local
  recovery.
- [ADR 0008](../../adr/0008-progressive-owner-authentication.md) supersedes
  automatic owner-by-local-channel presumption. Authentication is fresh,
  expiring evidence, never a persistent global boolean.
- Identity, authentication, and authorization remain separate. Protected
  memory is authorized before it is retrieved.

## Existing foundation and reuse boundary

PC-1 is an integration slice, not a new brain. Current production code already
provides the typed controller, public-unknown channel adapters, authorization
and audit policy, v4 child relationships and child-name/count tools, a
process-local identity-session seam, onboarding slot/flag primitives, and the
real STT/Piper audio path. Local face perception also exists but is not wired
as authenticated request evidence.

Plans 0025–0028 must connect and harden those pieces. They must not introduce a
second controller, a second memory store, a second authorization system, or a
new RAG path for the structured question “¿quiénes son mis hijos?”. What is
missing is owner/PIN setup, one-use evidence propagation through classic and
streaming channels, and real allowed/denied runtime acceptance.

## Delivery path

### PC-1 — Owner-authenticated memory MVP

Execute the approved design in
[Plan 0024](0024-owner-authenticated-memory-mvp-design.md) through its bounded
portfolio: [setup](../completed/0025-personal-owner-bootstrap-and-pin-setup.md)
(merged), [classic authenticated turn](../completed/0026-one-use-owner-authenticated-classic-turn.md)
(merged), [streaming parity](../completed/0027-one-use-owner-streaming-parity.md) (merged), and
[runtime acceptance](../completed/0028-owner-authenticated-memory-runtime-acceptance.md)
(executed, PASS). PC-1 is complete.

The delivery order is fixed:

1. connect the minimal security bootstrap: owner, confirmed child
   relationships, and PIN, without claiming extended onboarding completion;
2. add an explicit local, short-lived, one-use unlock;
3. resolve that evidence into the existing `ActivePersonContext` seams;
4. authorize and invoke the existing structured child-name tool;
5. prove both allowed and denied paths through real microphone, STT,
   controller, Piper, and speaker output.

PC-1 does not require face or speaker recognition. Its limitation is explicit:
the local secret proves the unlock action, not the physical speaker. One-use
scope and short expiry make that acceptable for the first product proof.

### PC-2 — Consented local face evidence

Integrate the existing local face engine through the same typed evidence
contract. Enrollment is available only after explicit owner authentication and
subject consent. Store templates separately from generic facts; evaluate
unknown faces, false accepts/rejects, lighting, distance, expiry, deletion, and
backend failure on Pipec's actual camera. Face evidence never grants permission
directly.

**Code/test slice merged 2026-08-25** —
[Plan 0029](0029-consented-local-face-evidence.md), PR #73. Consent schema
with real purge on revoke, `FACE` as a trusted evidence source, a lazy
per-turn face resolver composed face-first/PIN-fallback, authenticated
enrollment/revocation endpoints, and the router/robot wiring — all behind
feature flags defaulting off. Not yet done: real-camera calibration (false
accept/reject rates, lighting, distance, glasses) and any liveness defense
— PC-2 is not accepted until a follow-up real-camera acceptance plan closes
that gap.

### PC-3 — Consented local speaker evidence

Add a real speaker-enrollment and verification adapter through the same
contract. STT and VAD are not voice identity. Evaluate changed voice, noise,
distance, microphone variation, replay risk, false accepts/rejects, expiry,
deletion, and backend failure. Raw audio stays ephemeral by default.

### PC-4 — Conservative fusion

Combine the one-use session, face, and voice evidence without creating a
second authorization system. Agreement may raise assurance; conflict is
`ambiguous`; absence or expiry is `unknown`. A local recovery method remains
available even when biometrics fail.

### PC-5 — Local visual companion acceptance

For “Iroko, ¿qué ves?”, keep specialized responsibilities separate:

```text
face adapter -> identity evidence
scene adapter -> current visual evidence
voice adapter -> speaker evidence
controller -> authentication + authorization + response plan
```

The VLM may describe current visual evidence, but does not name Pipec or grant
access. The text LLM receives typed, policy-approved results, not a raw frame.

### PC-6 — Family profile expansion

Only after the personal proof is stable, extend onboarding, visibility,
consent, and recipient privacy for multiple household members. A technical
owner/admin does not automatically receive another adult's private data.

## Product acceptance ladder

| Stage | Pipec | Request without valid authentication |
|---|---|---|
| One-use unlock | Hears “Máximo y Dominga” through the real audio path. | Receives a non-disclosing denial. |
| Face | Gets the same result from fresh consented face evidence. | Unknown/mismatch receives no names. |
| Voice | Gets the same result from calibrated speaker evidence. | Unknown/mismatch/replay receives no names. |
| Fusion | Non-conflicting evidence reduces friction. | Conflict becomes `ambiguous`, never best-score guessing. |

Every row must pass automated security/regression tests and repeated
`just run-server` plus `just run-robot` scenarios. Green `pytest` alone is not
product acceptance.

## Explicit non-goals for PC-1

- general web administration or family onboarding;
- a durable `authenticated = true` setting;
- assuming the owner from the PC, loopback, microphone, name, message, or LLM;
- face, voice, fingerprint, multi-factor fusion, or biometric enrollment;
- broad RAG, PDF ingestion, knowledge-graph redesign, or a new vector store;
- wake word, ROS2, physical autonomy, or TTS replacement.

## Next decision gate

Pipec reviewed and merged Plans
[0025](../completed/0025-personal-owner-bootstrap-and-pin-setup.md) (PR #56),
[0026](../completed/0026-one-use-owner-authenticated-classic-turn.md) (PR #57),
[0027](../completed/0027-one-use-owner-streaming-parity.md) (PR #64), and
[0028](../completed/0028-owner-authenticated-memory-runtime-acceptance.md)
(executed 2026-08-21), each on its own feature branch with observed
RED/GREEN evidence and a review gate. The same discipline applies to every
future plan: one plan per change, never collapsed.
