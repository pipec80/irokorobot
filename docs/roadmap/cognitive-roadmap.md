# Cognitive roadmap

> **Status:** Canonical implementation order
>
> **Starting point:** [Current cognitive implementation](../architecture/current-state.md)
>
> **Personal-companion traceability:** [Delivery map](personal-companion-delivery-map.md)
>
> **Longitudinal-memory traceability:** [Delivery map](conversational-memory-delivery-map.md)
>
> **Rule:** Finish and verify one bounded plan before preparing or implementing
> the next. Priority does not authorize all work in a phase at once.

## Goal

Turn the existing conversational prototype into a trustworthy household brain
before coupling it to new electronics. The roadmap preserves what already
works—audio, text, memory, personality, vision, and the server/robot boundary—
while adding identity, policy, typed orchestration, reliable family knowledge,
and explicit uncertainty.

The ordering optimizes for false-positive avoidance and privacy, not feature
count. A capable model without identity and authorization is less useful in a
home than a smaller system that knows when it does not know.

Iroko uses two independent product axes per
[ADR 0014](../adr/0014-orthogonal-social-and-responsibility-profiles.md): the
social profile (`personal` or `family`) and the responsibility
(`companion`, `care`, or `education`). The current target is
`personal + companion`; `care` and `education` remain unimplemented future
responsibilities with no product claim.

## Phases at a glance

- **P0 — trustworthy cognitive foundation:** closed.
- **P1 — personal companion:** identity closed (PC-1…PC-4); integrated acceptance
  (PC-5 / P1.3) open.
- **P2 — situated cognition and memory quality:** conversational memory (P2.2,
  CM-1…CM-7) is next; perception (P2.1), adaptation (P2.3) and outcomes (P2.4)
  follow.
- **P3 — family:** after the personal companion is accepted.
- **P4 — cloud escalation (optional) and physical body:** after the 19 slices.

The order of the remaining work is the portfolio below; what is already closed
is summarized in [Closed foundations](#closed-foundations--history).

## Canonical pre-electronics delivery portfolio

This is the **only** delivery queue. The specialized maps (personal companion,
conversational memory, RAG) explain one track in depth and the plan router holds
the single `NOW` item; neither defines order. If another document shows a
different order, this table governs and the other document is stale.

Iroko has one product axis: the personal companion, `STT -> memory -> LLM ->
TTS`, where memory is the brain. Identity (PC-1…PC-4) answers *who is speaking*
and is closed. Conversational memory (CM-1…CM-7) is the next chapter of the same
companion, not a separate program: it makes "¿te acuerdas de…?" work for the
owner and keeps every private fact closed to anyone else. Documentary retrieval
(R2, R3) adds documents afterwards; its other stages are already CM or P2.1 work
(see [RAG §25](../architecture/rag-and-memory-retrieval.md#25-secuencia-de-evolución)).

Numbered rows are the 19 required product slices. Rows marked `—` are hardening
or data-loading work that belongs to the queue without being a slice, so the
count stays 19. A row is neither a reserved plan number nor authorization: only
the `NOW` item in [`docs/plans/README.md`](../plans/README.md) may be executed,
after Pipec authorizes its `Ready` plan, and each row is re-audited against the
merged code before its plan is written (queue rule 4). `Depends on` lists hard
gates only.

| Order | Slice | Verifiable outcome / exit evidence | Depends on | State | Detail |
|---:|---|---|---|---|---|
| 1 | CM-0 — longitudinal benchmark | A versioned synthetic suite runs reproducibly; the harness is GREEN and the measured product honestly RED. | — | **Complete 2026-09-08** — Extraction scored precision 0.25 and recall 0.25. The full longitudinal run recorded 75 steps: 3 failed and 72 unsupported. The report's `source_commit` is `38fa89c`; `ac43c58` is the commit that added the report. It is a historical measurement, and memory code changed afterwards (PR #131, Plan 0053). | [Plan 0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md); [baseline](../evals/0046-longitudinal-memory-baseline.md) |
| 2 | PC-3A — speaker calibration | FAR/FRR, replay, quality and CPU latency measured offline on a frozen backend. | CM-0 | **Complete 2026-09-25** — provisional: threshold 0.4834, 0/24 false accepts, 6/8 replay accepted, p95 231 ms | [Plan 0047](../plans/completed/0047-speaker-evidence-calibration-study.md) |
| 3 | PC-3B — consented speaker evidence | Local enrolment, revocation and typed `VOICE` evidence; weak or failed evidence is `unknown`. | PC-3A | **Complete 2026-09-29** | [Plan 0053](../plans/completed/0053-consented-speaker-runtime-evidence.md) |
| 4 | PC-4 — identity fusion | The owner's face identifies at `basic`, face plus verified voice at `strong`; another enrolled person or two faces veto; the PIN is optional. | PC-3B | **Complete 2026-09-30** — accepted on real hardware; replay not defended; no reserved capability yet | [Plan 0054](../plans/completed/0054-face-default-identity-fusion.md); [ADR-0016](../adr/0016-face-and-voice-identity-fusion.md) |
| — | PC-4 follow-ups | A store error during face recognition degrades to `unknown`; face and speaker models warm at startup; one `identity_source` and one clock; two coverage holes closed. | PC-4 | **Complete 2026-10-01** (PR #152, `1c0a914`) — automated gates green; one hardware sample: first protected turn 3.58 s (was 8 to 13 s); static independent review blocker fixed | [Plan 0055](../plans/completed/0055-pc4-identity-fusion-followups.md) |
| — | Audit repairs | The 12 repairs of the 0049 audit: import cycles, one seam to Ollama, fail-closed parsing of Ollama transport responses (not the classic `response`/`emotion` parser), image bounds, stored classification honoured, owner-scoped readiness, setup contract, dead settings, no names in logs, architecture guards, the owner → stranger matrix, docs truth. | — | Draft; re-audit against PC-3B/PC-4 before promotion | [Plan 0050](../plans/open/0050-server-audit-repairs.md) |
| — | Voice-pipeline reliability and truthful diagnostics | Whisper no longer returns its own initial prompt from a noise clip (seen four times) and the first utterance after a restart is transcribed correctly; the classic parser rejects a non-text `response` (for example `{"response": []}`) while the raw-text fallback stays a separate, explicit decision; `just test-pipeline` runs again (its `llm.generate_response` call lacks the client) and is described as an STT → LLM → TTS smoke test, not the cognitive path; `just eval-chat` measures the streaming `EMOTION:` protocol (0049 O-04), not only the classic generator; the longitudinal evaluator reports the three staged verdicts (personal, family, full suite) defined in the [evaluation spec](../architecture/longitudinal-conversational-memory-evaluation.md#cm-0-measured-baseline). | Audit repairs | Not written | [0049 O-04](../plans/open/0049-server-objective-conformance-audit.md) |
| 5 | CM-1 — scoped memory capabilities | First every grant is bound to one named operation ([ADR-0015](../adr/0015-owner-grant-scope-and-speaker-binding.md) decision 1, implemented by **Plan 0051**, the first plan of this slice; its scope must also cover the voice enrolment and revocation endpoints Plan 0053 added after the ADR, a household-looking stub answer that today spends a grant, and the optional PIN hardware case left unrun by Plan 0054); then policy distinguishes `read`, `propose`, `confirm`, `correct` and `forget` for personal memory, and `SECURITY` data declare their `strong` requirement, without turning identity into authorization. | PC-4 | Unplanned | [Memory map](conversational-memory-delivery-map.md#delivery-sequence) |
| 6 | CM-2 — authorized actor propagation | The actor and grants resolved by face, voice or PIN reach the generic conversation, with no name interpolated into the prompt and no widened grant. Today identity is resolved only on protected turns ([ADR-0016 §5](../adr/0016-face-and-voice-identity-fusion.md#5-turn-order)), so CM-2 needs a new ADR that supersedes that section: when a generic turn is identified (cost: one face check and one ~0.5 s voice embedding), how an authorized session is kept, and when its history is discarded. `just chat-test` is adapted, because it expects continuity between unauthenticated public requests. Its first visible result is short-term continuity: the identified actor's last turns (in-process working memory, never persisted) reach the next turn, and a change of speaker or an `unknown`/`ambiguous` turn clears them — with its own acceptance test. Connecting the actor is not enabling durable memory: legacy retrieval and consolidation stay blocked, and each read or write opens only in the slice that implements its guarantees (writes CM-3, episodes CM-4, retrieval CM-5). | CM-1 | Unplanned | [Memory map](conversational-memory-delivery-map.md#current-fracture) |
| 7 | CM-3 — candidates and the canonical V4 writer | Extraction only proposes; one deterministic writer assigns the classification (never the speaker) and promotes to V4 facts and relations with provenance, deduplication and contradictions. Every channel it claims is tested separately: today classic and streaming voice schedule consolidation but `/chat` does not. A spoken "lo recordaré" from the LLM is never evidence of a write; confirming, correcting and forgetting need their own controller branches. | CM-2; audit repairs | Unplanned | [Memory map](conversational-memory-delivery-map.md#lifecycle) |
| — | Seed load ("step 0") | Owner, household, photos and classifications load in person from a local file or form as a second input channel of the CM-3 writer; seeded sensitive facts change only with owner verification; the owner → stranger matrix passes once per channel. Until then `just setup-personal` and `just onboard` remain the setup. | CM-3 | Not written | Rules in [0050 *Non-goals*](../plans/open/0050-server-audit-repairs.md#non-goals) |
| 8 | CM-4 — protected episodes | Episodes declare owner, subjects, visibility, sensitivity, consent, validity and retention. | CM-3 | Unplanned | [Memory map](conversational-memory-delivery-map.md#delivery-sequence) |
| 9 | CM-5 — authorized relevant retrieval | Person, visibility, sensitivity and validity filter vector and structured candidates before the prompt; a relevance threshold permits zero results and keeps provenance (RAG stage R1). Structured household reads beyond the children list and count (today every other authorized family question answers "todavía no está conectada") go through the same authorized seam. The first reserved (`SECURITY`) category becomes real here: written with that classification by the CM-3 writer, read only at assurance `strong`, while `basic` (face alone) and strangers get the generic denial; which datum it is is decided when CM-3 is planned. | CM-4 | Unplanned | [Memory map](conversational-memory-delivery-map.md#retrieval) |
| 10 | CM-6 — correction and forgetting | Correction and deletion reach facts, relations, episodes, embeddings, summaries and caches. | CM-3 through CM-5 | Unplanned | [Memory map](conversational-memory-delivery-map.md#forgetting) |
| 11 | CM-7 — real longitudinal scenario | The real server/robot path proves `learn -> restart -> recall -> correct -> restart -> recall current truth -> forget -> do not disclose`, including turn-to-turn continuity, one `SECURITY` datum (`strong` reads it, `basic` and strangers do not) and the benchmark's **personal acceptance** verdict PASS without relaxed thresholds. Family acceptance stays `pending` for P3.2 (`recipient_only_message`, `two_adult_private_facts`) and the full suite keeps failing until then; no scenario is excluded. | CM-0 through CM-6 | Unplanned | [Evaluation](../architecture/longitudinal-conversational-memory-evaluation.md#pc-5-longitudinal-gate) |
| 12 | PC-5 / P1.3 — integrated personal acceptance | Pipec completes voice, biometric, protected-memory, visual, correction, forgetting, denial, degradation and audible-output scenarios with literal transcripts; it decides whether scene description must work in streaming mode (today the robot refuses to start with streaming and server vision together, so scenes are classic-only); the CPU/RAM/latency budget and the Uvicorn concurrency (`UVICORN_LIMIT_CONCURRENCY`) are measured on the homelab server. | CM-7 | Unplanned | [Plan 0015](../plans/open/0015-personal-companion-design.md#pc-5--integrated-personal-companion-acceptance--unstarted) |
| 13 | P2.1 — structured perception and `WorldState` | Typed observations for people, objects, sensor state and location carry source, time, confidence and expiry; simulated sensors can later be replaced by firmware. | P1 controller and policy | Unplanned | [Memory and world state](../architecture/memory-and-world-state.md#world-state-is-not-long-term-memory) |
| 14 | R2 — minimum documentary source | One local Markdown or text source is versioned, classified, chunked and retrieved with owner, visibility, provenance and deletion. | CM-5, CM-6 | Unplanned | [RAG §25](../architecture/rag-and-memory-retrieval.md#25-secuencia-de-evolución) |
| 15 | R3 — lexical and hybrid retrieval | Lexical and vector retrieval over authorized candidates; RRF, deduplication, zero results and measured quality. | R2 | Unplanned | [RAG §15](../architecture/rag-and-memory-retrieval.md#15-recuperación-híbrida) |
| 16 | P2.3 — bounded adaptation and initiative | Personality stays coherent and private; initiative is explainable, sparse, rate-limited and disableable. | P2.1, CM-7 | Unplanned | [P2.3](#p23--personality-adaptation-and-bounded-initiative) |
| 17 | P2.4 — outcomes and feedback | Decisions link to observed outcomes and authorized feedback without claiming unobserved learning. | P2.1, CM-7 | Unplanned | [P2.4](#p24--outcomes-and-feedback-contracts) |
| 18 | P3.1 / PC-6A — family onboarding and consent | One idempotent service, the seed-load writer extended to more members, creates members, roles, relationships, visibility and revocable consent. | PC-5 | Unplanned | [P3.1](#p31--family-onboarding-ui-and-consent) |
| 19 | P3.2 / PC-6B — family interaction acceptance | Adults, children, guests, pets, identity conflict, personal/shared/`recipient_only` isolation and biometric-failure recovery; the family-scope CM benchmark scenarios left pending by CM-7 turn GREEN. | P3.1, P2.1 | Unplanned | [P3.2](#p32--family-companion-interaction) |

After all 19 slices close with their own evidence, P4.2 may open its first
physical-architecture plan: the Raspberry Pi versus microcontroller boundary,
typed action proposals, capability checks, electrical and motion safety,
simulation, emergency stop and human acceptance before motion. P4.1 cloud
escalation is optional and does not block P4.2.

### Cross-cutting gates and conditional work

These items do not add slices. Required evidence belongs to the plan that creates
the load or the behavior; conditional work opens only after a measured need.

| Item | Classification | Required disposition | Owned by |
|---|---|---|---|
| CPU, RAM, token and latency budget | Cross-cutting required evidence | Measure bounded contention among STT, LLM, VLM, embeddings and consolidation, plus the Uvicorn concurrency limit, on the homelab server; no unbounded parallel workload or separate scheduler by default. | CM plans that add load; PC-5 acceptance |
| Liveness and replay defense | Conditional per [ADR-0016 §9](../adr/0016-face-and-voice-identity-fusion.md#9-replay-and-spoofing-measured-not-closed) | Replay is measured, not defended: a photograph plus a recording of the exact question can still reach `strong`. A liveness plan opens only if the measurement justifies it; making it a mandatory gate needs a new ADR that supersedes that section. | CM-5, which introduces the first reserved read, re-measures and decides |
| Remaining biometric measurements | Required before relying on voice beyond the laptop | Runtime impostors, genuine utterances of 1.5–3 s and a second acoustic condition were never measured (PC-3B). | The recalibration of electronics track 1, or PC-5 if the laptop stays the body |
| Privacy contract of the senses | Required before any new continuous capture | What is kept, what never leaves the device, and a physical switch and indicator once there is hardware. Needs an ADR. It gates new capture (an always-on microphone or camera, recording beyond one turn), not the purchase: porting today's per-turn capture to the Pi does not need it. | An ADR written with the seed load |
| Diarization / simultaneous speakers | Required decision, conditional implementation | Before P3.2 becomes `Ready`, choose an explicit turn-taking constraint or local diarization. Speaker verification is not diarization. | P3.2 readiness design |
| R4 PDF, OCR, advanced chunking and reranking | Conditional | Only when real documents or R3 metrics prove Markdown/text plus hybrid retrieval insufficient. | [RAG evolution](../architecture/rag-and-memory-retrieval.md) |
| Alternative TTS | Conditional, non-blocking | Piper and the WAV contract remain the baseline. | Future plan outside the critical path |
| Care and education | Future responsibilities, non-blocking | Separate ADRs, policies, outcomes/feedback and acceptance after the companion core. | Future responsibility profiles |

### Pre-purchase readiness gate — "plug it in and it works"

Revised 2026-09-30 on Pipec's decision; it replaces the 2026-09-25 rule "buy the
electronics when CM-7 closes" and its blocks A–D. The server is a generic audio
API and the robot a generic audio client
([ADR 0002](../adr/0002-server-robot-separation.md)), and `robot/` already owns
capture, playback and the camera. Buying electronics therefore splits into three
independent tracks, and only the last two wait on software:

| Track | What | Gate | Why |
|---|---|---|---|
| 1. The same senses on the Pi | Raspberry Pi 5 with a microphone, a speaker and a camera replacing the laptop's | None in the cognitive queue | It is a port of the robot client; the server does not change. Required work: repeat the face ([Plan 0030](../plans/completed/0030-real-camera-face-acceptance.md)) and speaker ([Plan 0047](../plans/completed/0047-speaker-evidence-calibration-study.md)) calibrations on the new devices, because the thresholds `0.5815` and `0.4834` were measured on the laptop and are device-specific. |
| 2. New kinds of sensors | Temperature, distance, presence and similar | The P2.1 contract is designed (row 13) | A sensor is an adapter behind a typed observation; choosing sensors before the contract can force rework. |
| 3. Anything that moves | Motors and actuators | P4.2, after the 19 slices | Typed action proposals, a safety layer, an emergency stop and human acceptance come first. |

**What "it works when plugged in" means for any new device.** A device is an
adapter behind an existing software contract, never a reason to change one:

1. It produces a typed observation or typed identity evidence with source, time,
   confidence and expiry (P0.1 vocabulary; P2.1 for sensors; PC-4 for identity).
2. Missing, weak or failed evidence is `unknown` and grants nothing by itself;
   authorization stays in the policy layer, so a new sensor cannot widen access.
3. It is proven first as a simulator or replay against the same contract tests;
   replacing the simulator by the real device must not change a test.
4. The server does not learn the device exists (server = generic API, robot =
   generic client); only the adapter in the robot side knows the hardware.
5. Physical *actuation* is a different, later gate: P4.2 (typed action
   proposals, safety layer, emergency stop, human acceptance). An LLM never
   commands a motor directly.

**Not required before buying, on purpose:** a fingerprint reader or any other
electronic biometric (future adapter for the identity seam, no ADR yet), cloud
escalation (P4.1, optional), R4 PDF/OCR, alternative TTS, and the care and
education responsibilities. Independent of the queue: the second GT-P3110 tablet
(a hobby task).

**Who decides.** Closing a row is evidence-based (each plan's own gates). The
decision to spend money is Pipec's and is not made by this document; it only
states what is ready.

### How Chat and Codex advance the portfolio

1. Read this table to identify the first row whose dependencies are closed.
2. Confirm the operational cursor in [`docs/plans/README.md`](../plans/README.md#operational-board).
3. Execute only the single explicitly authorized `Ready` plan in `NOW`.
4. Close it with observed RED/GREEN evidence, review, required gates and real
   acceptance where applicable.
5. Update this row, the specialized delivery map, current state and the plan
   router in the same closure documentation change. Closure narratives live in
   the completed plan, not in this table.
6. Re-audit the next row before assigning a plan number or writing its detailed
   plan. New evidence may split or combine implementation plans, but it must not
   silently remove the row's product outcome.

Rows 1–4 and the PC-4 follow-ups are closed and `NOW` is empty. What each row still needs before
it can become `NOW` (checked 2026-10-01):

| Work | What is really missing |
|---|---|
| Plan 0050 | Revalidation against `main` (known items (a)–(h) in the plan; Plan 0055 closed 2026-10-01) and Pipec's decisions 1–5 |
| Voice-pipeline reliability and diagnostics | A plan is written: Whisper prompt echo and first-turn STT, the classic parser, `test-pipeline`, `eval-chat` streaming and the staged benchmark verdicts |
| CM-1 / Plan 0051 | Plan 0051 is written; CM-1 must also cover the later memory permissions (`read`, `propose`, `confirm`, `correct`, `forget`) |
| CM-2 | An ADR on identity in generic turns (it supersedes ADR-0016 §5), then the plan |
| CM-3 → seed load → CM-7 | Separate plans; the first `SECURITY` datum and its gates are specified before it is enabled |
| PC-5 | The streaming-with-vision scope is decided when its plan is written; measurement on the homelab happens during acceptance |

## Closed foundations — history

Closed work is summarized here in one line per phase; its evidence (commands,
counts, commits, real-hardware runs) lives in each completed plan, not in this
file.

| Phase | Outcome | Closed by |
|---|---|---|
| C0 | Canonical tracked documentation; `project-history/` is reference-only | Documentation pass |
| P0.1–P0.2 | Typed domain models; active-person context with `identified`, `probable`, `unknown` and `ambiguous`; working history isolated by identity | [0001](../plans/completed/0001-cognitive-domain-models.md), [0002](../plans/completed/0002-active-person-context.md) |
| P0-S | Public biometric enrollment quarantined; least-exposed desktop defaults; cloud providers quarantined | [0002a](../plans/completed/0002a-local-first-provider-quarantine.md), [0002b](../plans/completed/0002b-biometric-enrollment-quarantine.md), [0002c](../plans/completed/0002c-desktop-security-and-drift.md) |
| P0.3 | Small typed controller; deterministic date and age; no ToolRegistry until several real tools share a need | [0003](../plans/completed/0003-typed-controller-and-deterministic-tools.md) |
| P0.4 | Relational memory V4: entity-ID relations, cardinality, lifecycle and a dry-run-first migration; v3 stays the runtime compatibility path | [0004](../plans/completed/0004-relational-memory-v4-design-and-migration.md), [0005](../plans/completed/0005-relational-memory-v4-implementation.md) |
| P0.5 | Deterministic fail-closed household authorization; policy-gated V4 reader and family tools | [0007](../plans/completed/0007-household-authorization-foundation.md)–[0010](../plans/completed/0010-policy-gated-v4-family-tools.md) |
| P0-C | Every public route obeys the controller/policy boundary; combined operator acceptance on 2026-08-25 | [0011](../plans/completed/0011-p0-closure-and-acceptance.md)–[0023](../plans/completed/0023-p0-grounded-visual-dialogue.md) |
| P1.1 / PC-1 | A freshly authenticated owner hears the children's names through the real server/robot path; without authentication nothing is revealed | [0024](../plans/completed/0024-owner-authenticated-memory-mvp-design.md)–[0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md) |
| X1 | Server production baseline: privacy, uploads, PIN hardening, SQLite transactions, CI, Uvicorn, lifecycle, OpenAPI and streaming | [0031](../plans/completed/0031-server-production-baseline-design.md)–[0045](../plans/completed/0045-async-test-client-resources-parity.md), [0048](../plans/completed/0048-fastapi-baseline-final-hardening.md) |
| CM-0 | Longitudinal benchmark and its RED baseline | [0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md) |
| P1.2 / PC-2…PC-4 | Consented face evidence (threshold 0.5815), consented speaker evidence (0.4834) and fusion: face `basic`, face plus voice `strong`, another person vetoes | [0029](../plans/completed/0029-consented-local-face-evidence.md), [0030](../plans/completed/0030-real-camera-face-acceptance.md), [0047](../plans/completed/0047-speaker-evidence-calibration-study.md), [0053](../plans/completed/0053-consented-speaker-runtime-evidence.md), [0054](../plans/completed/0054-face-default-identity-fusion.md) |

Real-hardware acceptances are historical: they cover only the recorded
scenarios, devices and configuration and are not a new run on the current tree.
Limits carried forward from these phases, each owned by a queue row or a
cross-cutting item above: no liveness (a photograph identifies at `basic`) and
replay measured but not defended; on hardware Plan 0054 proved the two-faces
veto, while the veto of a single other enrolled person was proven only against
test doubles until Plan 0055 (Task 4) pinned it against real role rows in automated tests; the calibrations are provisional (one owner,
few impostors, laptop devices); the grant is not bound to an operation (CM-1);
the generic conversation has no continuity or memory (CM-2…CM-5).

## P1.3 — Personal companion acceptance (PC-5)

Demonstrate the full companion flow with `just run-server` and
`just run-robot`: voice, face/voice evidence, authorized personal data,
longitudinal memory, on-demand scene description, deterministic claims, and
Piper output. A raw
frame never enters the text LLM; the controller receives only typed,
policy-approved evidence and scene results.

**Exit gate:** Pipec can complete approved personal scenarios, including
`aprendo -> reinicio -> recuerdo -> corrijo -> olvido`; an unknown speaker
cannot read protected data; a model outage degrades safely; and every
acceptance transcript records literal STT, route, response, audible output, and
audit outcome. P1.3 executes only after P2.2's longitudinal gate, even though
the roadmap groups it under P1.

## P2 — Situated cognition and memory quality

### P2.1 — Current world state and structured perception

Introduce typed, expiring observations and `WorldState` for people, objects,
sensor state, and location. Keep it separate from durable memory and raw
telemetry. Convert on-demand vision first; provider clients stay inside
adapters.

**Exit gate:** stale data expires; contradictions remain explicit; visual scene
description is distinct from face identity; every observation carries source,
timestamps, confidence, and expiry; frames are not retained by default.

### P2.2 — Memory lifecycle and retrieval

Bring the longitudinal runtime slice forward after PC-4 and before P1.3. CM-0
ran intentionally earlier: Plan 0046 measured the current RED baseline
(`ac43c58`, 2026-09-08) without changing runtime. Follow CM-1 through CM-7 after
PC-4 in the
[conversational-memory delivery map](conversational-memory-delivery-map.md):
start with a reproducible RED benchmark; add candidate confirmation,
deduplication, contradictions, supersession, scoped authorization, V4 canonical
writes, protected episodes, relevance thresholds, authorized semantic
retrieval and complete forgetting. Then add documentary and hybrid retrieval
in the staged order defined by [RAG, memory, and hybrid
retrieval](../architecture/rag-and-memory-retrieval.md). Derived indexes must be
rebuildable and deletions must propagate. This does not reopen the completed
P1.1 structured “Joaquín y Martina” proof.

**Exit gate:** the versioned evaluation defined in
[longitudinal-conversational-memory-evaluation.md](../architecture/longitudinal-conversational-memory-evaluation.md)
passes; low-relevance queries return no memory; protected memories never enter
model context; corrections expose only the current truth; forgetting reaches
facts, episodes, summaries, embeddings and caches; and the real server/robot
path proves persistence, correction, abstention and cross-person privacy.

### P2.3 — Personality adaptation and bounded initiative

Move stable identity, relationship style, dynamic state, and situational
expression into bounded structured composition. Add proactive behavior only
from fresh authorized events with cooldowns, quiet hours, cancellation, and
rate limits.

**Exit gate:** one coherent personality survives across roles; no private
cross-person prompt leakage occurs; transient interactions do not become
permanent traits; proactive prompts are explainable, sparse, and disableable.

### P2.4 — Outcomes and feedback contracts

After the longitudinal memory core is accepted, define typed outcomes for
observable results and typed feedback for authorized evaluation of those
results. Keep both distinct from events, telemetry and autobiographical memory;
link them through stable provenance instead of copying them into a generic
prompt. This phase does not authorize online model training or autonomous
policy changes.

**Exit gate:** a decision or action can be linked to an observed outcome and
authorized feedback; missing outcomes remain unknown; private feedback is
access-controlled; corrections and deletion propagate according to policy; and
no system claims to have learned from a result that was never observed.

## P3 — Family companion and UI

The family profile is intentionally later than the validated personal
companion. It reuses the same local entities, relationships, policy evaluator,
and identity evidence; it must not create a separate family brain or relax
sensitive-data policy.

### P3.1 — Family onboarding UI and consent

Build one reviewable local onboarding application service, exposed later through
the UI and controlled import paths. It creates the household profile, adults,
children, pets, relationships, visibility defaults, consent grants, and
biometric consent. The initial owner/admin configures the household but does
not automatically obtain another adult's personal data.

**Exit gate:** onboarding is idempotent; consent is explicit and revocable;
relationships and provenance remain structured; no UI or voice channel writes
truth by raw SQL or independent rules.

### P3.2 — Family companion interaction

Extend Iroko's social interaction to consented, identified household members.
It may greet members, use permitted household context, and adapt its style, but
must return unknown, ambiguous, or unauthorized rather than disclose another
person's private data.

**Exit gate:** multi-member acceptance covers adults, children, guests, pets,
identity conflicts, data isolation, and recovery after biometric failure.

## Future responsibility profiles — not scheduled

`care` and `education` are orthogonal to the `personal`/`family` social axis;
they are not later maturity labels for the same permissions. They reuse the
accepted companion core only after outcomes and feedback have explicit
contracts.

A future `care` capability must distinguish beneficiary, family member,
caregiver, health professional, technical administrator and emergency contact.
A future `education` capability must distinguish student, tutor and educator.
No role inherits another person's private data or unrestricted action authority.

Before either responsibility is scheduled it needs a separate accepted ADR,
bounded capability policy, risk classification, deterministic failure posture,
outcome/feedback contract and real acceptance criteria. Until then, Iroko is a
companion; the roadmap makes no nurse, clinical-monitoring or autonomous-teacher
claim.

## P4 — Cloud escalation and physical body

### P4.1 — Controlled cloud escalation

Cloud is an optional escalator, not the primary brain. Create a separate ADR
and plan for an explicit gateway only after local result validation exists.

Escalation requires all of:

```text
local result is uncertain or insufficient
+ the task is eligible
+ the active person is authorized
+ the data categories may leave the home
+ a minimized/redacted request has real expected benefit
+ timeout, cost, audit, and local fallback policies are available
```

Biometrics, children's raw images/audio, full household profiles, medical
records, complete conversations, location history, credentials, and home maps
do not leave by default. A cloud failure returns the best safe local outcome,
including `unknown`; it never blocks basic operation.

**Exit gate:** policy and redaction tests run without network; provider adapters
are replaceable; every attempt is auditable without logging protected payloads;
budgets and timeouts are enforced; cloud output is validated as untrusted.

### P4.2 — Physical body and ROS2 decision

Only after cognitive, identity, policy, and current-state contracts are stable
should the project choose physical action architecture. ROS2 is appropriate if
real requirements demand distributed nodes, navigation, device discovery, or
its ecosystem; it is not a prerequisite for the cognitive foundation.

Physical work starts with typed action proposals and a separate safety layer:

```text
cognitive intent
-> authorization
-> capability check
-> physical safety/interlocks
-> actuator adapter
-> outcome observation
```

**Exit gate before motion:** simulation and emergency-stop behavior, limits,
timeouts, collision/failure handling, cancellation, audit, and human acceptance
tests exist. An LLM never commands a motor directly.

## Global constraints for every plan

- Local-first and open-source-compatible operation is the default.
- Optimize for CPU operation; optional acceleration must have a safe fallback.
- Use the existing Python 3.12 workspace, SQLite, and `sqlite-vec` unless a
  measured requirement and ADR justify a change.
- Preserve the server/robot and public audio contracts in
  [`implementation-guardrails.md`](../architecture/implementation-guardrails.md).
- Use one small typed orchestrator; do not introduce a multi-agent runtime,
  giant framework, general autonomous loop, or plugin ecosystem.
- Unknown, ambiguous, contradictory, and unauthorized are successful domain
  outcomes when they accurately represent the evidence.
- Identity and authorization precede private retrieval and generation.
- New electronics are adapters after software contracts, not the starting point.
- Every plan states exact files, tests, rollback/migration concerns, and non-goals.
- No plan may require ignored `project-history/local-docs/` content or unstated chat history.
- No commit, push, PR, dependency install, or unrelated cleanup is implicit in
  an implementation request.

## How to hand work to Codex

Use one instruction of this form:

```text
Implement docs/plans/open/NNNN-name.md exactly as written.
Read docs/architecture/implementation-guardrails.md,
docs/architecture/README.md, and only the required files named by the plan.
Respect the permitted file list. If code or current behavior
contradicts the plan, stop and report the exact conflict; do not redesign or
expand scope. Run the listed verification. Do not commit unless asked.
```
