# Cognitive roadmap

> **Status:** Canonical implementation order
>
> **Starting point:** [Current cognitive implementation](../architecture/current-state.md)
>
> **Personal-companion traceability:** [Delivery map](personal-companion-delivery-map.md)
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

## Priority summary

| Priority | Capability | Contribution | Depends on |
|---|---|---|---|
| C0 | Canonical documentation | Lets later Codex tasks execute bounded plans without chat/local-only context. | Repository inspection |
| P0.1 | Typed cognitive domain models | One stable vocabulary for evidence, context, confidence, authorization, and outcomes. | C0 |
| P0.2 | Active-person context | Stops assuming the owner and isolates conversations by identity state. | P0.1 |
| P0-S1 | Biometric enrollment quarantine | Prevents public biometric poisoning until household policy exists. | P0.2 |
| P0-S2 | Desktop security and drift | Makes desktop defaults least-exposed and aligns operating guidance. | P0-S1 |
| P0.3 | Deterministic tools and small controller | Separates evidence gathering, retrieval, policy, generation, and validation. | P0.1–P0.2 |
| P0.4 | Relational memory v4 | Correct entity links, cardinality, time, provenance, dates, and counts. | P0.1–P0.3 |
| P0.5 | Household authorization | Filters protected data before retrieval and generation. | P0.2, P0.4 |
| P0-C | Runtime policy hardening | Makes every enabled public route obey the P0 controller/policy boundary and proves it through the robot. | P0.3–P0.5 |
| P1.1 | Owner-authenticated memory MVP | Uses a one-use local unlock to prove the authorized “Máximo y Dominga” path and paired denial. | P0-C6 audible streaming |
| P1.2 | Progressive biometric identity | Adds consented face, then speaker evidence through the same authentication contract. | P1.1, P0.2 |
| P1.3 | Personal companion acceptance | Demonstrates authentication, authorized memory, visual scene, recovery, and denial through the real PC path. | P1.1–P1.2 |
| P2.1 | Situated perception and WorldState | Represents fresh observations independently of durable memory. | P1 controller/policy |
| P2.2 | Memory lifecycle and retrieval quality | Adds confirmation, contradiction, relevance thresholds, consolidation, and forgetting. | P0.4–P0.5 |
| P2.3 | Bounded adaptation and initiative | Makes Iroko more personal and proactive without prompt growth or surveillance. | P1 identity, P2.1–P2.2 |
| P3.1 | Family onboarding UI and consent | Builds the family profile, selective privacy, and reviewable household truth. | P1 acceptance, P2.2 |
| P3.2 | Family companion interaction | Extends social interaction to multiple members without blanket data access. | P3.1, P1.2, P2.1 |
| P4 | Cloud escalation and physical body | Evaluates optional cloud and safe embodiment only after cognitive policy is stable. | P0–P3 acceptance gates |

## C0 — Documentation foundation

This phase is the current documentation-only work. It creates accepted ADRs,
an implementation snapshot, canonical architecture documents, this roadmap,
and narrow executable plans. It makes no production-code change.

**Exit gate**

- all future requirements needed for the cognitive foundation exist in tracked
  documents;
- `project-history/local-docs/` is explicitly historical/reference-only;
- contradictions between current behavior and target behavior are named;
- a future Codex can start from one named plan without reconstructing the chat;
- no code or commit is included in the documentation pass.

## P0 — Trustworthy cognitive foundation

P0 answers five questions for every turn: What happened? Who is interacting?
What are they allowed to do or know? What evidence is needed? What result can
the system support?

### P0.1 — Typed cognitive domain models

Implement [Plan 0001](../plans/completed/0001-cognitive-domain-models.md) exactly within
its file scope. The models are pure values; they do not integrate with current
routes or invoke providers.

**Outcome:** later services share typed observations, events, confidence,
authorization, context, and explicit knowledge states.

**Exit gate:** serialization, datetime, immutability, enum, authorization, and
no-I/O tests pass offline with no new framework.

### P0.2 — Active-person context and conversation isolation

Implement [Plan 0002](../plans/completed/0002-active-person-context.md) after P0.1.
It introduces typed identity evidence and `ActivePersonContext`, preserves the
current integer entity IDs, and removes owner identity as an implicit fact of
every voice turn.

**Minimum outcomes**

- `identified`, `probable`, `unknown`, and `ambiguous` are represented;
- evidence can include authenticated session, manual selection, face, speaker,
  and conversational continuity without treating any one signal as permission;
- an unknown or ambiguous speaker is a valid state;
- working history is isolated so a new/unknown person cannot inherit owner
  context from `voice-primary`;
- no biometric implementation is required in this first slice.

**Exit gate:** tests prove conflicting identity evidence does not silently pick
the owner and private history is not reused across identity boundaries.

### P0-S — Hardening and consistency

P0-S is two small prerequisite slices, not a shortcut to P0.5.

- **P0-S1:** [Plan 0002b](../plans/completed/0002b-biometric-enrollment-quarantine.md)
  quarantines both HTTP and conversational public face enrollment. It preserves
  existing biometric data and does not introduce authentication or roles.
- **P0-S2:** [Plan 0002c](../plans/completed/0002c-desktop-security-and-drift.md) changes
  desktop exposure defaults and aligns configuration, scripts, and evidence
  after P0-S1 revalidation.

**Exit gate: COMPLETE.** No public request can persist a biometric profile;
active documentation/configuration no longer claims removed identity scopes or
a cloud-default runtime. Plan 0003 is complete; later plans remain Draft.

### P0.3 — Small controller and deterministic tools

**Exit gate: COMPLETE.** [Plan 0003](../plans/completed/0003-typed-controller-and-deterministic-tools.md)
pilots one typed controller behind `/chat` without changing `text_turn` or the
audio API. It creates a fresh `CognitiveEvent`, returns an immutable
`ResponsePlan`, calculates current date and age from a strict ISO birth date,
and returns `unknown` or `unauthorized` for out-of-scope requests before legacy
delegation. Generic safe text preserves the existing local text-turn behavior.

The complete P0.3 slice intentionally does **not** add a ToolRegistry: two
closed static functions do not justify registration, dispatch, metadata, or a
framework. Reconsider it only when an approved later plan has multiple real
tools with a shared requirement.

The long-term intended turn sequence is:

```text
receive event
-> resolve active person
-> classify intent/information need
-> evaluate preliminary policy
-> execute deterministic tools
-> retrieve authorized memory
-> assemble bounded context
-> generate locally
-> validate result
-> propose memory candidate
-> optionally consider cloud escalation
```

Future typed tools, once P0.4/P0.5 make them trustworthy, may include:

- `identify_current_person`;
- `get_person_details`;
- `get_children` and `count_relationships`;
- `calculate_age` from ISO birth date and current date;
- current date/time;
- known authorized preferences;
- current perception/world state;
- `remember_confirmed_fact` only after memory policy approves it.

P0.3 verification recorded 514 passing repository tests, clean lint/type/audit
gates, and no dependency, schema, memory, authorization-policy, provider/cloud,
vision, robot, or audio-contract change. It did not implement deterministic
family queries; those require P0.4 relational memory and P0.5 authorization.

### P0.4 — Relational memory v4

**Plan 0004 and [Plan 0005](../plans/completed/0005-relational-memory-v4-implementation.md)
are complete; P0.4 merged as `3b01b58` through PR #40.** The bounded
slice adds only an additive SQLite v4 foundation:
integer entity relationships, predicate cardinality, lifecycle metadata, and an
explicit dry-run-first local migration with an audit ledger. It keeps literal
facts distinct from entity relationships and leaves the v3 runtime reader/writer
unchanged until P0.5 policy exists.

**Exit gate:** migration fixtures preserve current data; multi-value preferences
do not erase each other; inverse relations and historical intervals are
consistent; age remains derived; and v3 remains the unchanged runtime
compatibility path. A later P0.5-gated cutover plan owns production retrieval,
tools, and writes.

### P0.5 — Household authorization

**P0.5-A is complete — merged to `main` as `960f160` through PR #42.**
[Plan 0007](../plans/completed/0007-household-authorization-foundation.md) implements
role and data-category policy as a deterministic service, safe local role/audit
records, an explicit local owner bootstrap, and controller enforcement before
protected delegation. It uses the minimum roles `owner`, `adult`, `child`,
`guest`, and `unknown`, while allowing per-person overrides later. It does not
connect v4 data to runtime prompts or family tools; that P0.5-B cutover is
written only after a fresh revalidation.

**P0.5-A exit gate:** decisions are deterministic and fail closed; local role
bootstrap is explicit and auditable; protected controller branches evaluate
policy before delegation; missing policy defaults to denial or confirmation;
child, biometric, medical, private, location, and action categories have
explicit rules; denials are auditable and do not leak protected facts.

**P0.5 overall exit gate:** policy-gated v4 retrieval/model-context and family
tools are added under a separately revalidated P0.5-B plan; protected values
are filtered before retrieval and never enter a prompt when denied. The current
[Plan 0008 design](../plans/completed/0008-policy-gated-v4-household-tools-design.md)
keeps child relationships and birth dates consent-gated and public chat
unknown-by-default; it does not authorize a public identity or consent path.
[Plan 0009](../plans/completed/0009-policy-gated-v4-reader.md) is complete: PR #45
merged as `a7550d0` on 2026-08-13 after its local 555-test gate and green
GitHub CI. It adds the reader-only cut.

**P0.5-B2 is Complete in [Plan 0010](../plans/completed/0010-policy-gated-v4-family-tools.md).**
PR #48 merged as `0d16969` on 2026-08-14 after local `just lint`, `just
typecheck`, `just test` (571 passed), `just audit`, `just check`, and green
GitHub CI. It adds only a policy-gated internal family-tool seam and two
self-referential child-query patterns. Public chat remains unknown-by-default,
and cannot provide identity or consent or invoke the v4 reader.

**P0 foundation is complete; runtime acceptance is pending.**
[Plan 0011](../plans/completed/0011-p0-closure-and-acceptance.md) records the merged-main
foundation evidence. [Plan 0012](../plans/completed/0012-p0-runtime-acceptance-design.md)
must still connect P0 to `just run-server` plus `just run-robot` and pass its
operator runbook. P1.1 product design and Plans 0025–0028 are prepared, but no
P1 implementation or runtime acceptance has started.

## P1 — Personal companion

The next product target is Iroko with Pipec, using the `personal` profile from
[ADR 0006](../adr/0006-personal-and-family-companion-profiles.md). This phase
does not create a general UI or family onboarding. It proves that identity,
authorization, local face/voice evidence, visual scene understanding, memory,
and recovery work together through the actual PC robot path.

### P1.1 — Owner-authenticated memory MVP

Connect only the path needed for the first product proof: explicit first boot,
Pipec as the confirmed owner, confirmed child relationships, a local
short-lived one-use unlock, active-person resolution, policy-gated structured
retrieval, and audible output. It must not be a public admin API.

**Exit gate:** after one explicit local unlock, Pipec asks “¿quiénes son mis
hijos?” and hears “Máximo y Dominga” through `just run-server` plus
`just run-robot`; without fresh authentication the same request reveals no
names, count, hint, or fact existence. Both scenarios are repeatable and
audited. [Plan 0024](../plans/open/0024-owner-authenticated-memory-mvp-design.md)
defines the design. Its executable portfolio is [0025 owner setup and
PIN](../plans/open/0025-personal-owner-bootstrap-and-pin-setup.md) → [0026 classic
authenticated turn](../plans/open/0026-one-use-owner-authenticated-classic-turn.md)
→ [0027 streaming parity](../plans/open/0027-one-use-owner-streaming-parity.md) →
[0028 real runtime acceptance](../plans/open/0028-owner-authenticated-memory-runtime-acceptance.md).
The plans are prepared but not implemented.

The [personal-companion delivery map](personal-companion-delivery-map.md)
is the canonical cross-plan traceability view. It identifies which foundations
already exist in code/tests, which gaps are verified absent, and which one
bounded plan owns each remaining outcome. It does not authorize execution.

**Order revision (2026-08-20):** P1.1 runs immediately after P0-C6 instead of
waiting for full P0-C acceptance. P0.5 built the owner role, policy, and audit,
but no local path produces an identified owner, so every public route stays
permanently unknown and no operator run can exercise an authorized path.
Running P1.1 earlier supplies that missing key, so the remaining P0-C slices
and the combined acceptance run can be exercised as the owner as well as as a
stranger. P1.2 and P1.3 keep their original P0-C acceptance prerequisite.
[ADR 0007](../adr/0007-first-boot-and-default-posture.md) keeps explicit first
boot and owner-before-household ordering. [ADR
0008](../adr/0008-progressive-owner-authentication.md) supersedes automatic
owner-by-local-channel presumption: every protected request needs fresh,
expiring authentication evidence. The first method is a one-use local unlock;
face and voice follow without blocking this proof.

### P1.2 — Progressive biometric identity

First integrate consented local face evidence, then add a real speaker
enrollment/verification adapter, then conservative fusion with temporary
manual/session evidence. Specialized models emit typed evidence; they do not
grant access directly. STT/VAD are not voice identity. The VLM may describe a
scene, but is not the authority that names Pipec.

**Exit gate:** calibrated local evaluation covers agreement, conflict, expiry,
backend failure, false accept, and false reject. Conflicting evidence returns
`ambiguous`; the administrative recovery path remains available.

### P1.3 — Personal companion acceptance

Demonstrate the full companion flow with `just run-server` and
`just run-robot`: voice, face/voice evidence, authorized personal data,
on-demand scene description, deterministic claims, and Piper output. A raw
frame never enters the text LLM; the controller receives only typed,
policy-approved evidence and scene results.

**Exit gate:** Pipec can complete approved personal scenarios; an unknown
speaker cannot read protected data; a model outage degrades safely; and every
acceptance transcript records literal STT, route, response, audible output, and
audit outcome.

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

Add candidate confirmation, deduplication, contradictions, supersession,
retention/forgetting, authorized semantic retrieval, relevance thresholds, and
reviewable consolidation. Then add documentary and hybrid retrieval in the
staged order defined by [RAG, memory, and hybrid
retrieval](../architecture/rag-and-memory-retrieval.md). Derived indexes must be
rebuildable and deletions must propagate. This work does not block the P1.1
structured “Máximo y Dominga” acceptance scenario.

**Exit gate:** low-relevance queries return no memory; protected memories never
enter model context; corrections and deletions affect summaries/embeddings;
evaluation cases cover precision, privacy, temporal validity, and provenance.

### P2.3 — Personality adaptation and bounded initiative

Move stable identity, relationship style, dynamic state, and situational
expression into bounded structured composition. Add proactive behavior only
from fresh authorized events with cooldowns, quiet hours, cancellation, and
rate limits.

**Exit gate:** one coherent personality survives across roles; no private
cross-person prompt leakage occurs; transient interactions do not become
permanent traits; proactive prompts are explainable, sparse, and disableable.

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

[Plan 0001](../plans/completed/0001-cognitive-domain-models.md),
[Plan 0002](../plans/completed/0002-active-person-context.md), and
[Plan 0002a](../plans/completed/0002a-local-first-provider-quarantine.md) are complete.
Plans 0002b, 0002c, 0003, the Plan 0004 design, and Plan 0005 are complete;
Plan 0005 merged as `3b01b58` through PR #40. Plan 0007 P0.5-A merged as
`960f160` through PR #42. Plan 0008 is approved and Plan 0009 P0.5-B1 is
complete, merged as `a7550d0` through PR #45. Plan 0010 P0.5-B2 then merged
as `0d16969` through PR #48, and Plan 0011 records the completed P0 closure.
P1 implementation plans are written just in time after a fresh revalidation;
the accepted personal-companion design is not permission to implement it before
P0-C operator acceptance.
