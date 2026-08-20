# Personal companion design — Iroko and Pipec

> **Status:** Product direction approved. The immediate spine is
> [Plan 0024](0024-owner-authenticated-memory-mvp-design.md), decomposed into
> executable Plans 0025–0028. The portfolio awaits Pipec's review; no production
> implementation has started. Face, voice, fusion, and visual-companion slices
> remain later work.

## Objective

Make Iroko useful as Pipec's secure local companion as soon as possible,
without discarding the existing cognitive, memory, policy, STT, TTS, or vision
foundations. The first proof is deliberately visceral: authenticated Pipec asks
who his children are and hears “Máximo y Dominga”; a request without valid
authentication receives no protected names or hints.

This is the `personal` profile from
[ADR 0006](../adr/0006-personal-and-family-companion-profiles.md). The same
architecture later supports a family/multiple-person profile with stricter
per-person privacy; this slice does not build that later product.

## Governing decisions

- [ADR 0007](../adr/0007-first-boot-and-default-posture.md) keeps explicit
  first boot, owner-before-household ordering, completion state, and local
  recovery.
- [ADR 0008](../adr/0008-progressive-owner-authentication.md) supersedes
  automatic owner-by-local-channel presumption. Authentication is fresh,
  expiring evidence, never a persistent global boolean.
- Identity, authentication, and authorization remain separate. Protected
  memory is authorized before it is retrieved.

## Delivery path

### PC-1 — Owner-authenticated memory MVP

Execute the approved design in
[Plan 0024](0024-owner-authenticated-memory-mvp-design.md) through its bounded
portfolio: [setup](0025-personal-owner-bootstrap-and-pin-setup.md),
[classic authenticated turn](0026-one-use-owner-authenticated-classic-turn.md),
[streaming parity](0027-one-use-owner-streaming-parity.md), and
[runtime acceptance](0028-owner-authenticated-memory-runtime-acceptance.md).

The delivery order is fixed:

1. connect first boot, owner bootstrap, and confirmed child relationships;
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

Pipec reviews Plans [0025](0025-personal-owner-bootstrap-and-pin-setup.md),
[0026](0026-one-use-owner-authenticated-classic-turn.md),
[0027](0027-one-use-owner-streaming-parity.md), and
[0028](0028-owner-authenticated-memory-runtime-acceptance.md). If approved,
implementation starts with Plan 0025 only, on a feature branch, with its
observed RED/GREEN evidence and review gate. Approval does not collapse the
four plans into one change.
