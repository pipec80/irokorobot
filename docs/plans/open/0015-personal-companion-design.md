# Plan 0015: Personal companion design

- **Status:** Reference only — approved product design, not directly executable
- **Opened:** 2026-08-20
- **Last design revision:** 2026-09-08 (CM-0 / Plan 0046 closed; status sync only)
- **Execution authority:** none; work requires one numbered `Ready` plan at a
  time

## Purpose

Define the path from the accepted cognitive foundation to a trustworthy
personal companion, then to a privacy-preserving family companion. This plan
stays open because PC-3 through PC-6 and CM-1 through CM-7 contain real work.
CM-0 closed 2026-09-08 (Plan 0046 — a benchmark and a measured RED baseline,
not longitudinal memory); PC-3A has a queued design and no executable plan.

It is an umbrella and product-acceptance reference. Do not implement it as one
batch and do not infer a future plan number from it.

## Product model

Iroko has one cognitive architecture configured along two independent axes, as
accepted in [ADR 0014](../../adr/0014-orthogonal-social-and-responsibility-profiles.md):

```text
Profile social:       personal | family
Responsibility:       companion | care | education
```

The active delivery target is `personal + companion`. `family` follows only
after personal acceptance. `care` and `education` are future responsibilities,
not current modes or promises, and will require their own ADRs, capabilities,
policies, outcomes/feedback contracts and acceptance evidence.

The axes do not create separate brains. They reuse the same typed controller,
identity, authorization, memory and local-provider boundaries. Identity never
grants permission, and an owner/admin never inherits another adult's private
data.

## Current evidence

### Closed foundations

- P0 cognitive foundation and combined runtime acceptance are complete.
- PC-1 owner-authenticated structured memory is complete through Plans
  [0025](../completed/0025-personal-owner-bootstrap-and-pin-setup.md)–[0028](../completed/0028-owner-authenticated-memory-runtime-acceptance.md).
- PC-2 consented face evidence is implemented by
  [Plan 0029](../completed/0029-consented-local-face-evidence.md), and its
  real-camera calibration closed provisionally through
  [Plan 0030](../completed/0030-real-camera-face-acceptance.md).
- The server-production baseline in Plans 0031–0045 is closed, with the
  second-audit follow-up
  [Plan 0048](../completed/0048-fastapi-baseline-final-hardening.md) closed
  2026-09-07.

The PC-2 calibration remains explicitly provisional because it measured only
three unrelated impostor identities. It does not solve liveness: a photograph
can still authenticate. PC-4 owns multimodal conflict and anti-spoofing policy.

### Work that remains open

- **PC-3:** consented speaker enrollment and calibrated speaker evidence;
- **PC-4:** conservative multimodal identity fusion and recovery;
- **P2.2 / CM-1…CM-7:** authorized, corrigible and forgettable longitudinal
  conversational memory (CM-0, the benchmark and RED baseline, is closed);
- **PC-5:** integrated personal-companion acceptance through the real PC path;
- **PC-6:** family profile, onboarding, selective privacy and recipient-only
  household data.

[Plan 0046](../completed/0046-reproducible-longitudinal-memory-baseline.md)
closed CM-0 on 2026-09-08 (benchmark GREEN, measured baseline RED at `ac43c58`).
[Plan 0047](0047-speaker-evidence-calibration-study.md) preserves the reviewed
PC-3A calibration design in `Queued` and is not executable until its
backend/dependency readiness gate is resolved and approved. There is no
physical `docs/plans/NOW.md`; the operational board is
[`docs/plans/README.md`](../README.md#operational-board).

## The verified memory gap

Iroko does not currently have one coherent longitudinal conversation path:

```text
protected household query
  -> identity -> authorization -> V4 memory -> deterministic response

generic conversation
  -> legacy text_turn -> legacy/semantic memory -> LLM
```

The current controller passes only message and conversation ID into the legacy
turn. The legacy turn enables durable memory only for `MANUAL` evidence; face
and local unlock do not enable its history, fact retrieval, vector search or
consolidation. Consolidation writes through legacy APIs, while semantic search
does not yet filter person, visibility, sensitivity, validity or authorization
and has no relevance threshold.

The manual-evidence barrier prevents some accidental disclosure, but it is not
a complete authorization model. Passing `active_person` directly into the LLM
would widen risk rather than close the gap.

The required delivery sequence and exact code seams are canonical in
[conversational-memory-delivery-map.md](../../roadmap/conversational-memory-delivery-map.md).

## Target memory behavior

Longitudinal memory is part of PC-5, not optional post-acceptance polish. The
canonical lifecycle is:

```text
conversation/perception
  -> candidate
  -> subject and source attribution
  -> sensitivity and retention classification
  -> accept | confirm | reject
  -> canonical V4-backed memory
  -> authorized retrieval
  -> evidenced response
  -> correction, history or complete forgetting
```

Automatic extraction proposes; it does not establish personal truth. The LLM
may verbalize authorized evidence but does not decide which conflicting memory
is true or visible.

Every durable item must support subject, assertor, source, temporal validity,
truth status, visibility, sensitivity, consent, retention, correction lineage
and deletion of derived embeddings/summaries. See
[memory-and-world-state.md](../../architecture/memory-and-world-state.md).

## Delivery stages

### PC-1 — Owner-authenticated memory MVP — complete

One fresh local unlock permits exactly one authorized structured child query;
the unauthenticated pair discloses nothing. Classic and streaming runtime
acceptance passed on real microphone/speaker hardware.

### PC-2 — Consented local face evidence — complete, provisional calibration

Face evidence uses explicit consent, the typed identity contract and the same
authorization boundary as PIN. Enrollment cannot choose an arbitrary subject,
revocation purges biometric rows, and PIN remains an independent recovery path.

### PC-3 — Speaker evidence — unstarted; PC-3A plan queued

Add a local speaker-verification adapter with explicit enrollment, consent,
revocation and a calibrated threshold. STT and VAD do not identify speakers.
Voice evidence must fail unknown on missing, low-quality or unavailable input;
it must never grant capabilities directly.

**Gate:** a versioned genuine/impostor dataset and real turns establish false
accept/reject behavior, backend-failure posture and revocation. No household
member's real voice may enter the repository.

Plan 0047 deliberately covers only the calibration study. Even a provisional
PASS leaves production enrollment, revocation and trusted evidence for a
future PC-3B plan.

### PC-4 — Conservative identity fusion — unstarted

Combine face, speaker and temporary administrative/session evidence through
typed deterministic policy. Agreement may strengthen a result; conflict must
produce `ambiguous`, never silently select the owner. Multiple visible people,
replay/spoof concerns, expiry and provider failure require explicit outcomes.

**Gate:** agreement, disagreement, one-signal absence, ambiguity, expiry,
replay/spoof cases and recovery are measured without weakening protected-data
authorization.

### P2.2 / CM-0…CM-7 — Longitudinal memory — CM-0 closed

Execute the staged portfolio from benchmark RED through authorized actor
propagation, candidate promotion to V4, protected episodes, pre-prompt
retrieval, correction/forgetting and real longitudinal acceptance.

Plan 0046 delivered CM-0 (closed 2026-09-08): the benchmark software finished
GREEN and recorded a measured product baseline that is honestly RED
(`ac43c58`, exit 1 — single-turn extraction is the only live seam and scores
below par, every other operation is `unsupported`). It implemented no CM-1
capability and changed no runtime memory. CM-1…CM-7 remain unplanned and wait
for PC-3 and PC-4.

**Gate:** the canonical evaluation proves `aprendo -> reinicio -> recuerdo ->
corrijo -> reinicio -> recuerdo la verdad vigente -> olvido -> no revelo`.
See
[longitudinal-conversational-memory-evaluation.md](../../architecture/longitudinal-conversational-memory-evaluation.md).

### PC-5 — Integrated personal companion acceptance — unstarted

Prove the complete `personal + companion` experience with `just run-server`
and `just run-robot`: voice, face/speaker evidence, authorized structured and
longitudinal memory, on-demand scene understanding, deterministic claims,
local LLM degradation and audible Piper output.

**Gate:** Pipec completes approved scenarios; an unknown or unauthorized actor
cannot read protected data; memory survives restarts, respects corrections and
can be forgotten; every transcript records literal STT, route, identity
evidence class, policy decision, response, audible output and audit result.

### PC-6 — Family profile — unstarted

Extend the accepted core to multiple household members with reviewable
onboarding, role/capability policy, consent and data separation. Shared,
personal and `recipient_only` data remain distinct. A recado is sensitive
temporal data delivered only to its confirmed authorized recipient, not generic
memory or household RAG.

Unknown visitors may converse generally. Unknown is not synonymous with
threat, and recognition is not authorization.

**Gate:** two adults and at least one restricted/unknown actor demonstrate
isolated personal memory, permitted shared data, recipient-only delivery,
correction, revocation and non-disclosure through the real path.

## Ordering

```text
PC-1 complete
  -> PC-2 complete (provisional calibration)
  -> CM-0 reproducible RED baseline (Plan 0046 closed 2026-09-08)
  -> PC-3A speaker calibration (Plan 0047 queued) <- current cursor
  -> PC-3B speaker runtime evidence
  -> PC-4 identity fusion
  -> P2.2 / CM-1..CM-7 longitudinal memory
  -> PC-5 personal companion acceptance
  -> PC-6 family profile
```

CM-0, the reproducible benchmark, is closed (Plan 0046, 2026-09-08): it created
the RED evidence needed to prevent implementation by intuition. The next product
slice is PC-3A. Plan 0047 is numbered only to preserve the next reviewed
handoff; its `Queued` status and readiness gate prevent premature execution.

## Non-goals

- implement PC-3 through PC-6 in this document;
- add a cloud runtime, agent framework, microservice or new database;
- train model weights or add JAX;
- treat face, voice, names in text or local network origin as authorization;
- store every conversation or observation permanently;
- claim nursing, clinical monitoring or autonomous education;
- change the server/robot HTTP boundary or audio contract.

## Exit condition for this umbrella

Plan 0015 closes only when PC-3, PC-4, CM-0…CM-7, PC-5 and PC-6 have each been
delivered by bounded plans with their own tests and real acceptance evidence,
or when a later accepted ADR explicitly removes one of those outcomes from the
product target.
