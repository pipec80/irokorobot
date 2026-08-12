# Cognitive roadmap

> **Status:** Canonical implementation order
>
> **Starting point:** [Current cognitive implementation](../architecture/current-state.md)
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
| P1.1 | Unified onboarding | Builds a confirmed household graph through voice, web, or import. | All P0 |
| P1.2 | World state | Represents fresh people, objects, sensors, and location with TTL. | P0 controller/policy |
| P1.3 | Structured perception | Converts vision/audio/sensors into typed observations independent of hardware. | P1.2 |
| P1.4 | Multimodal identity | Combines session, face, speaker, and context evidence conservatively. | P0.2, P1.3 |
| P2.1 | Memory lifecycle and retrieval quality | Adds confirmation, contradiction, relevance thresholds, consolidation, and forgetting. | P0.4–P0.5 |
| P2.2 | Cloud escalation gateway | Uses a stronger model only for permitted, sanitized, uncertain cases. | P0 controller/policy, P2.1 |
| P2.3 | Bounded adaptation and initiative | Makes Iroko more personal and proactive without prompt growth or surveillance. | P1 world/identity, P2.1 |
| P3 | Physical actions and ROS2 evaluation | Connects safe action proposals to hardware after the brain contract is stable. | P0–P2 acceptance gates |

## C0 — Documentation foundation

This phase is the current documentation-only work. It creates accepted ADRs,
an implementation snapshot, canonical architecture documents, this roadmap,
and narrow executable plans. It makes no production-code change.

**Exit gate**

- all future requirements needed for the cognitive foundation exist in tracked
  documents;
- `docs/local/` is explicitly historical/reference-only;
- contradictions between current behavior and target behavior are named;
- a future Codex can start from one named plan without reconstructing the chat;
- no code or commit is included in the documentation pass.

## P0 — Trustworthy cognitive foundation

P0 answers five questions for every turn: What happened? Who is interacting?
What are they allowed to do or know? What evidence is needed? What result can
the system support?

### P0.1 — Typed cognitive domain models

Implement [Plan 0001](../plans/0001-cognitive-domain-models.md) exactly within
its file scope. The models are pure values; they do not integrate with current
routes or invoke providers.

**Outcome:** later services share typed observations, events, confidence,
authorization, context, and explicit knowledge states.

**Exit gate:** serialization, datetime, immutability, enum, authorization, and
no-I/O tests pass offline with no new framework.

### P0.2 — Active-person context and conversation isolation

Implement [Plan 0002](../plans/0002-active-person-context.md) after P0.1.
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

- **P0-S1:** [Plan 0002b](../plans/0002b-biometric-enrollment-quarantine.md)
  quarantines both HTTP and conversational public face enrollment. It preserves
  existing biometric data and does not introduce authentication or roles.
- **P0-S2:** [Plan 0002c](../plans/0002c-desktop-security-and-drift.md) changes
  desktop exposure defaults and aligns configuration, scripts, and evidence
  after P0-S1 revalidation.

**Exit gate: COMPLETE.** No public request can persist a biometric profile;
active documentation/configuration no longer claims removed identity scopes or
a cloud-default runtime. Plan 0003 is complete; later plans remain Draft.

### P0.3 — Small controller and deterministic tools

**Exit gate: COMPLETE.** [Plan 0003](../plans/0003-typed-controller-and-deterministic-tools.md)
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

**Plan 0004 and [Plan 0005](../plans/0005-relational-memory-v4-implementation.md)
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

**P0.5-A is complete on the feature branch, pending PR merge evidence.**
[Plan 0007](../plans/0007-household-authorization-foundation.md) implements
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
are filtered before retrieval and never enter a prompt when denied.

## P1 — Situated household awareness

### P1.1 — Unified onboarding

Build one application service shared by voice, web, and controlled imports.
Capture the household, people, relationships, birth dates, preferences,
permissions, and optional biometric consent in reviewable stages.

**Exit gate:** re-running onboarding is idempotent, contradictions require
resolution, source/provenance is retained, and no channel writes truth by raw
SQL or independent rules.

### P1.2 — Current world state

Introduce a typed, expiring `WorldState` assembled from observations. Keep it
separate from durable memory and raw telemetry.

**Exit gate:** stale data expires; contradictory sensors remain explicit;
absence of an observation is not interpreted as a false value; current state
can be queried through a deterministic tool.

### P1.3 — Structured perception adapters

Convert on-demand vision first, then audio/sensors as needed, into typed
observations. Preserve the existing generic media boundaries. Hardware brands
and provider clients remain inside adapters.

**Exit gate:** simulated and real adapters can produce the same contract;
visual scene description is distinct from face identity; every observation has
source, timestamps, confidence, and expiry; frames are not permanently retained
by default.

### P1.4 — Multimodal identity

Add local speaker identification/verification and conservative evidence fusion
with face, session, manual, and continuity signals. Diarization and recognition
remain separate concepts.

**Exit gate:** enrollment requires consent; biometric templates stay local by
default; conflicts become `ambiguous`; spoof/quality limits are documented;
identification still does not grant authorization.

## P2 — Quality, escalation, and adaptation

### P2.1 — Memory lifecycle and retrieval

Add candidate confirmation, deduplication, contradictions, supersession,
retention/forgetting, authorized semantic retrieval, relevance thresholds, and
reviewable consolidation. Derived indexes must be rebuildable and deletions
must propagate.

**Exit gate:** low-relevance queries return no memory; protected memories never
enter model context; corrections and deletions affect summaries/embeddings;
evaluation cases cover precision, privacy, temporal validity, and provenance.

### P2.2 — Cloud escalation gateway

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

### P2.3 — Personality adaptation and bounded initiative

Move stable identity, relationship style, dynamic state, and situational
expression into bounded structured composition. Add proactive behavior only
from fresh authorized events with cooldowns, quiet hours, cancellation, and
rate limits.

**Exit gate:** one coherent personality survives across roles; no private
cross-person prompt leakage occurs; transient interactions do not become
permanent traits; proactive prompts are explainable, sparse, and disableable.

## P3 — Physical body and ROS2 decision

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
- No plan may require ignored `docs/local/` content or unstated chat history.
- No commit, push, PR, dependency install, or unrelated cleanup is implicit in
  an implementation request.

## How to hand work to Codex

Use one instruction of this form:

```text
Implement docs/plans/NNNN-name.md exactly as written.
Read docs/architecture/implementation-guardrails.md,
docs/architecture/README.md, and only the required files named by the plan.
Respect the permitted file list. If code or current behavior
contradicts the plan, stop and report the exact conflict; do not redesign or
expand scope. Run the listed verification. Do not commit unless asked.
```

[Plan 0001](../plans/0001-cognitive-domain-models.md),
[Plan 0002](../plans/0002-active-person-context.md), and
[Plan 0002a](../plans/0002a-local-first-provider-quarantine.md) are complete.
Plans 0002b, 0002c, 0003, the Plan 0004 design, and Plan 0005 are complete;
Plan 0005 merged as `3b01b58` through PR #40. Plan 0007 has passed P0.5-A
local gates on its feature branch and awaits PR merge evidence. P0.5-B and
later plans remain `Draft` until their prerequisites and current tree are
revalidated. Later plans are written just in time after the previous exit gate;
otherwise they encode guesses about code that has already moved.
