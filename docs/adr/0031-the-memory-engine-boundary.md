# 0031 — The memory engine: one boundary, swappable policies

- **Status:** Accepted (2026-11-09, on Pipec's review; it has no implementing plan of its own:
  it is the contract later plans build against). Proposed and amended the same day with two
  external reviews, decisions 6 and 7 of *Pipec's decisions*; the final review gave its
  architectural approval. Direction
  confirmed by Pipec in the planning sessions of 2026-11-06 and 2026-11-09. Nothing in the code
  changes with this ADR: it fixes the boundary that later plans build against, and the engine is
  extracted only after CM-7 + PC-5 (decision 11).
- **Date:** 2026-11-09
- **Builds on:** [ADR 0002](0002-server-robot-separation.md),
  [ADR 0004](0004-local-first-cognitive-policy.md),
  [ADR 0011](0011-sqlite-transaction-ownership.md),
  [ADR 0014](0014-orthogonal-social-and-responsibility-profiles.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md),
  [ADR 0024](0024-seed-load-senses-secrets-and-channels.md),
  [ADR 0027](0027-conversation-record-and-the-diary.md),
  [ADR 0028](0028-recall-what-the-owner-told.md),
  [ADR 0029](0029-it-knows-who-is-listening.md)
- **Amends:** nothing yet. It constrains the ADRs that follow it on the
  [closing path](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory): block C
  (ADR 0032, correction and forgetting), the deployment (ADR 0033) and documents (ADR 0034, R2).
- **Delivers:** no roadmap slice. It is the contract of the memory half of the companion
  (CM-0…CM-7) and the first decision of the row *Memory engine contract* of the
  [cross-cutting table](../roadmap/cognitive-roadmap.md#cross-cutting-gates-and-conditional-work).

## Context

Pipec's goal, in his words: the robot is a companion, a pet or a personal assistant, and the core
is the same in the three: a memory that remembers, like a person does, so a conversation can go
back in time. That memory must also work for another project of his that has no face or voice
enrolment and does not need the household firewall. The firewall exists because a companion of
an older adult hears private data, and a nurse or a cleaner who finds the robot must not get the
bank account or a code by asking for it.

[ADR 0014](0014-orthogonal-social-and-responsibility-profiles.md) already decided one cognitive
architecture for every responsibility. What no ADR decides is **where the memory ends and the
firewall begins**. What holds today (verified on `main` at `cc8f1f1`, 2026-11-09):

1. **The engine exists and works.** Canonical V4 facts and relations with validity
   (`valid_from`, `valid_to`, migration 004) and provenance (`asserted_by_entity_id`, `channel`,
   migration 010); one deterministic writer (`canonical_writer`, `memory_writer.promote`);
   candidates (migration 009); the conversation record and the diary (migration 013); recall units
   with FTS5 and `vec0` fused by RRF behind an absolute gate, each unit stamped with its
   `embedding_model` and searchable by its words before its vector exists (migration 014,
   `recall_index.backfill_vectors`); retention jobs (`retention.py`). It is local and on SQLite.
2. **It has no boundary.** `server/src/server/memory/` holds 77 modules. It imports no voice,
   vision or HTTP route, but **20 of them import `server.cognition`**, in four kinds:

   | Kind of coupling | What is imported | Modules |
   |---|---|---|
   | Policy and identity | `evaluate_authorization`, `AuthorizationRequest`, `DataSensitivity`, `DataVisibility`, `AuthorizationAction`, `ActivePersonContext`, `HouseholdRole`, `IdentityAssurance`, `strong_actor`, `FusionReason`, `pin_credentials` | `candidate_classifier`, `candidate_dialogue`, `candidate_policy`, `candidate_proposal`, `canonical_writer`, `conversation_capture`, `household_authorization`, `memory_writer`, `owner_credentials`, `admin_pin`, `policy_gated_v4_reader`, `profile_card`, `profile_card_access`, `recall_access`, `sensitive_access` |
   | Language understanding | `intent_resolution`, `recall_cues`, `household_request.CHILD_WORDS`, `spoken_dates` | `recall_store`, `recall_search`, `recall_answer`, `sensitive_access` |
   | Reply wording | `response_plan` (`RecallReply`, `MemoryAnswerReply`, `ProfileSummaryReply`, `NO_MEMORY`) | `candidate_dialogue`, `profile_card_access`, `recall_access`, `recall_answer`, `sensitive_access` |
   | Time | `clock.utc_now` | `candidate_dialogue`, `candidate_proposal`, `conversation_capture`, `conversation_jobs`, `retention` |

   Some modules inside `memory/` are not memory at all: `household_authorization`,
   `owner_credentials`, `admin_pin`, `commissioning`, `care_contacts` and `sensitive_access` belong
   to the firewall or to the alta. Reusing the memory elsewhere today drags face, voice and PIN
   with it.
3. **The policy is already one pure function.** `evaluate_authorization(AuthorizationRequest) ->
   AuthorizationDecision` decides from the actor, the action, the target, visibility, sensitivity
   and consent, and returns a decision with `policy_id` and `reason` that is audited before the
   effect. It is the household's policy, called directly by the modules above rather than handed
   to them.
4. **Time is one date on the recall side.** A recall unit has `said_at` (when it was told);
   «el sábado fui a la playa», told on Monday, is found as Monday's. V4 facts already carry an
   interval of validity. Nothing records when a told event happened.
5. **What a record is, is only partly said.** V4 knows who asserted a fact and through which
   channel. The diary summary is written by the model from the owner's verified words: it is a
   transformation of what the owner said, but nothing marks it so. The robot observes nothing
   durable yet (P2.1).
6. **Memory does not survive years by design.** The eligible record lives 365 days, the rest 30,
   and the whole record is capped at 200 MB (`conversation_record_*` settings); episodes and recall
   units are deleted in cascade with their record.
7. **The field outside.** Hindsight (MIT; retain, recall, reflect; runs on local Ollama), Mem0,
   Letta, Zep/Graphiti, LangGraph/LangMem, Chroma and the SQLite-native `sqlite-memory` solve
   storage and retrieval in ways close to what Iroko already has. CoALA (Sumers et al., TMLR 2024)
   is the reference vocabulary: working, episodic, semantic and procedural memory, retrieval and
   learning actions, a decision procedure. The Open Memory Protocol Initiative is pre-1.0 with no
   reference implementation.
8. **Two gaps of the recall path against invariants this ADR states**, of different kinds (found
   by an external review of 2026-11-09 and read in `memory/recall_store.py` and
   `memory/recall_search.py`):
   - *Mixed vector spaces* — an invariant the code does not hold, latent until the model changes.
     `units_without_vector` selects only units whose `embedding_model IS
     NULL`, and `vector_hits` never compares the stored model with the query's. Changing
     `EMBEDDING_MODEL` to another 768-dimension model would compare vectors of two spaces and
     never re-embed the old units. Latent: the model has not changed.
   - *Filters not re-applied at delivery* — a risk found by static reading, pending
     reproduction. `recall_search` filters the ids, awaits the HTTP
     embedding call to Ollama, and then reads the text with `units_by_id`, which does not
     re-check owner, sensitivity or expiry. A record raised to `medical` by the diary job
     (`raise_record_sensitivity`) during those seconds could still reach the answer. A race, not
     an observed leak. **Fixed by [Plan 0080](../plans/completed/0080-mvp-recall-phrasings.md)
     (2026-11-09):** `units_by_id(ids, *, owner_entity_id, now)` joins the record and re-applies
     owner, `personal`, `normal` and the record's expiry in the statement that returns the text,
     and the tests reclassify or expire a unit between the search and the read and pass another owner's ids. Residual:
     text already read is not recalled while the model words the answer. The first bullet is **still
     latent** (block C, C1).

## Decision

### 1. What the engine is, and what it is not

The **memory engine** is the subsystem that keeps, classifies, relates, retrieves, updates and
deletes authorized knowledge and experiences, with provenance, time, privacy, resource limits and
reproducible tests. It owns:

| Owned by the engine | CoALA name |
|---|---|
| The facts and relations store (V4) | Semantic memory |
| The record, the diary and the recall units; later documents (decision 13) | Episodic memory (documents: an external source) |
| The in-process continuity slot | Working memory (the volatile part) |
| The verbs: propose, confirm, read, correct, forget; capture and index | Learning and retrieval actions |
| Retrieval: SQL, FTS5, vectors, RRF, time windows, the relevance gate, zero results | Retrieval |
| Lifecycle: retention, expiry, supersession, cascade, the jobs | — |
| Its own health measures (decision 9) and the longitudinal benchmark | — |

It does **not** own: who is speaking (face, voice, PIN, fusion), what a sentence asks (intent
grammars, recall cues, spoken dates), how an answer is worded (reply plans, persona, templates),
the alta and administration, the transport (FastAPI) or the body. Those are the **firewall** and
the **product** layers, which use the engine through decisions 2 and 11.

### 2. The policy is a port, checked at every boundary

Every operation that reads data or leaves a durable effect asks one policy first and audits the
answer before the effect: **capture** (is this turn kept, and as whose), **write** (propose,
confirm, promote), **index** (embed, backfill), **read and retrieve**, **correct**, **forget**,
**export**, and **backup and restore**. Retrieval filters by the policy's answer *before*
ranking; nothing protected is fetched to be filtered later. **The filters must still hold when
the content is handed over** (to the model, a template or an export): the read that returns the
text re-applies owner, classification and validity, so a unit revoked or reclassified during a
search is not delivered (*Context* item 8; proposed for Plan 0080, subject to Pipec approving
that plan's scope).

**Background jobs** (episodes, vectors, retention, backfill) have no person in front of the
camera. They act as a **system actor** with a closed list of operations (derive, index, expire,
purge), bound by the consent and the validity of the data they touch; they never read data out to
a person or a model's answer, and they never need face, voice or PIN.

The port has the shape of the evaluator that already exists:

```python
from typing import Protocol


class MemoryAccessRequest:
    """Operation, actor reference, data owner, purpose, classification, consent, audience."""


class MemoryDecision:
    """Allow or deny, with an auditable reason."""


class MemoryPolicy(Protocol):
    """Decides one memory operation before its effect; pure, no I/O."""

    policy_id: str

    def evaluate(self, request: MemoryAccessRequest) -> MemoryDecision: ...
```

`MemoryAccessRequest` carries the operation, the actor reference (an opaque subject id and an
assurance level, never a face or a voice), the owner of the data, the purpose, the classification
(visibility, sensitivity), the consent and, when the policy asks for it, the audience context.
`MemoryDecision` is allow or deny with an auditable reason, as `AuthorizationDecision` is today.
The names are illustrative; the plan that writes the port fixes them.

### 3. Two policies, chosen explicitly, never by accident

| Policy | Behaviour |
|---|---|
| `HouseholdMemoryPolicy` | Today's rules, unchanged: identity evidence and assurance by level, sensitivity classes, consent, the audience (two faces), the secret guard, scoped PIN grants. It wraps `evaluate_authorization`; it does not rewrite it |
| `PersonalAppMemoryPolicy` | One authenticated user, no biometrics, own data only. It accepts only the classifications it declares; anything it does not declare is refused |

The policy is chosen in the composition of the application, in code, not by a setting that a
typo could flip: Iroko composes the household policy and has no path to the open one. Tests pin
that neither policy reads the other's data and that Iroko cannot start with the open policy.

**One installation, one database.** Identity and policy do not stop two applications from reusing
the same entity ids. Each installation (a robot, the other project) has its own SQLite file; no
table gets a tenant column until a real need for several installations in one store appears.

### 4. Every record has an identity and a provenance

Every stored unit has a stable id, an owner, a source (the channel) and a pointer to its canonical
source; a derived unit (a summary, a recall unit, a vector, a document chunk) points to what it
was derived from, so deleting the source reaches it. This is how V4, the record and the recall
units already work; it becomes a rule for every new source.

### 5. Time has four meanings, and only the ones a use case needs are stored

| Meaning | Today |
|---|---|
| **Said** — when the person told it | `said_at` on recall units; the record's turns |
| **Recorded** — when the engine wrote it | `created_at` columns |
| **Occurred** — when the told event happened, possibly an interval or imprecise («en 2015», «el verano pasado») | Not stored |
| **Valid** — while a fact holds («trabajé en Santiago entre 2018 y 2021») | `valid_from`, `valid_to` on V4 |

The semantics are fixed here; columns are added only when a use case needs them, by the plan of
that use case. The engine never invents an occurred time it was not told, and an answer says which
time it reports («me lo contaste el lunes» is not «fuiste el lunes»). **The minimum for «¿cuándo
fui a la playa?» is decided (Plan 0080, 2026-11-09):** the answer says the day it was **told**
(`said_at`), never the date of the event; a `WhenKind` (`TOLD` or `HAPPENED`) on the recall cue
selects a fixed table with no model, and `HAPPENED` opens «No tengo registrado cuándo fue. Sí
recuerdo que {día} me contaste esto: …». No `occurred` column and no migration: the occurred time
itself stays future, added by the plan of the use case that needs it.

### 6. Every record says where it came from and what was done to it

Two independent dimensions, so that a faithful summary of what a person said is not confused with
a conclusion the model drew:

| Origin | Meaning | Today |
|---|---|---|
| `reported` | A person said it | The record, the owner's verified turns, spoken tastes, the alta |
| `observed` | The robot perceived it | Nothing durable (P2.1, WorldState) |
| `document` | It comes from a loaded document | Nothing yet (R2) |

| Transformation | Meaning | Today |
|---|---|---|
| `original` | The words or data as received | The record's turns, the turn recall units, V4 facts from the alta |
| `summary` | A shortened restatement of an original | The diary episode and its recall unit |
| `extracted` | A structured item taken from an original | A taste candidate before confirmation |
| `inferred` | A conclusion not stated in the original | Nothing stored today |

They are never treated as equivalent: an extracted or inferred item never becomes a confirmed fact
without the canonical writer and its confirmation, and an answer does not present a summary or an
inference as the person's own words. This is a contract, not a schema: the plan that first stores
a second origin, or retrieves a `summary` or an `inferred` item next to an `original`, adds the
explicit marker.

### 7. The lifecycle: states, operations and physical results are three different things

Not every source passes through the same states: a conversation record is kept, never
«proposed»; a taste is proposed and confirmed; a document is loaded. So the contract separates:

| Layer | Values |
|---|---|
| **Logical state** of a memory | `proposed`, `active`, `superseded`, `revoked`, `expired` |
| **Operation** that changes it | confirm, correct (supersede), revoke, forget, purge (expiry) |
| **Physical result** of a removal | the source row deleted; every projection invalidated (decision 4); only the audit evidence the policy allows kept, with no value |

Each source declares which states and operations apply to it. Who may correct and forget is the
policy's (decision 2); for the household it is ADR 0032.

**A restore must not resurrect what was forgotten**
([ADR 0024](0024-seed-load-senses-secrets-and-channels.md) already requires it). A cascade in the
live database does not achieve it: a backup taken before the deletion still holds the data. A
restore must reconcile the deletions confirmed after the backup, through a protected deletion
register that holds no value, or an equivalent such as crypto-shredding. This is a **goal, not an
implemented guarantee** until a test proves it; ADR 0032 (forgetting) and ADR 0033 (backups)
design it.

### 8. Consistency: one writer, idempotent jobs, indexes follow their source

Writes keep one transaction owner ([ADR 0011](0011-sqlite-transaction-ownership.md)). Background
jobs (episodes, vectors, retention) are idempotent: a retry after a crash never duplicates an
episode or a unit. An index is a projection: it may lag its source (a unit without a vector is
searchable by its words), never outlive it, and can be rebuilt from it.

**Embedding compatibility.** Each vector names its model, and a vector search only compares
vectors of the model that embedded the query. When the configured model changes, the engine
refuses the cross-model comparison (vector search off, lexical search on) and re-embeds every unit
in a verifiable re-index before it turns vector search back on. Today's code does not hold this
(*Context* item 8); it is proposed for Block C's first plan (C1).

### 9. The engine measures its own health

So that «it never stored it» can be told from «it stored it and cannot find it», the engine exposes
counts, never values:

| Measure | Question |
|---|---|
| Coverage | Of what was eligible to be kept, how much was kept? |
| Retrievability | Of what was kept, how much can a known question find? |
| Integrity | Does every index row match a live source row, and every source its indexes? |
| Forgetting | After a forget, does anything derived remain? |
| Staleness | How long does a unit stay without its vector or its episode? |
| Performance | p50 and p95 of capture, indexing and retrieval, and the resources they use |

Retrievability is measured against a set of questions with known expected answers (the
longitudinal benchmark and its dataset v4), not by operational counters alone. Block C's first
plan (C1) builds the integrity and staleness checks; CM-7 reports all six.

### 10. What «learning» means here

The engine learns by changing the persistent, authorized state of the agent, not the model's
weights. L0, continuity (CM-2), is **context, not learning**: it lives in the process and is gone
after a restart. The learning levels are L1 experiences (CM-4, CM-5b), L2 declarative knowledge
(CM-3), L3 correction (CM-6), L4 behaviour adaptation (P2.3, P2.4), L5 procedures (a taught,
authorized, reversible routine) and L6 training a model. The MVP covers L0 to L3. L5 is out of the MVP and is
**not forbidden**: a routine taught and stored is learning even when no weight changes. L6 is out
of scope and needs its own ADR.

### 11. The boundary is internal; the code moves after the final acceptance

The engine is a boundary inside this repository, not a published package: no stable public API,
no second repository, no version promise. Its contract is independent of FastAPI, biometrics and
hardware. What waits is the **extraction**: moving the firewall and product modules out of
`memory/` and putting the four kinds of coupling of *Context* item 2 behind ports happens **after
CM-7 + PC-5**, in its own plan. Memory code still changes before that when a plan needs it: the
fixes of *Context* item 8, C1's checks and tests, CM-6. Until then an
architecture guard test, written by C1, lists today's 20 modules that import `server.cognition`
and fails when a new one does; the list may shrink, never grow. CM-6 (ADR 0032) and R2 (ADR 0034)
are designed against this contract.

### 12. The storage stays; tuning is measured

SQLite stays the source of truth, with FTS5 and `sqlite-vec`. No external engine, vector store,
graph store or framework is adopted for the MVP:

| Candidate | Why not now |
|---|---|
| Hindsight | Overlaps the engine; its own server and stores; its LLM decides what is retained, where Iroko's writer decides |
| Mem0 | The LLM decides what becomes true; Iroko confirms through a deterministic writer |
| Letta | A separate agent server with its own database |
| Zep / Graphiti | A graph store (Neo4j); V4 already holds relations with validity |
| LangGraph / LangMem, LangChain | Orchestration; no identity, no cascade forgetting |
| Chroma, Qdrant, pgvector | The role `sqlite-vec` already plays, in another process |
| `sqlite-memory`, `sqlite-vector` | The same pattern as Iroko's; a second vector extension and a migration for no measured gain |
| Paid extensions (SEE, SQLCipher commercial) | Encryption is the deployment's decision (ADR 0033); disk encryption covers it today |

Tuning follows this order, each step only if the previous one's measure asks for it: (1) measure
real errors separately for speech-to-text, language understanding, retrieval and generation;
(2) the database hygiene of the roadmap (timestamps, indexes on foreign keys, dead tables);
(3) the current retrieval against an FTS5 `trigram` index (and, if it helps, Spanish stemming) on
a real Spanish corpus — `trigram` helps a word that reached the engine misspelt, not an intent the
grammar missed; (4) scale, latency, RAM and concurrency on the target host; (5) `int8` vectors,
cache and durability pragmas. Step 5 is not transparent: today's column is `float[768]` with
cosine distance, so `int8` means a migration, a re-index and a new calibration of the gate.

### 13. Documents are one more source of the engine

The documentary RAG (R2) is a source type inside the engine, under the same policy port, with its
own provenance (file, hash, version, position) and kept apart from what a person told: a manual
is not the owner's experience, and an instruction inside a document is data, never a command.
Its first source is Markdown, plain text and PDF with a text layer; scanned PDF and OCR stay in
R4. **This changes R2's earlier scope** (Markdown or text only, PDF in R4; roadmap of 2026-10-30)
by Pipec's decision of 2026-11-06; the roadmap and RAG §25 record the change in the same
documentation change as this ADR, and ADR 0034 decides it, after CM-7 + PC-5.

## Pipec's decisions and where they land

| # | Decision | Date | Where |
|---|---|---|---|
| 1 | The memory engine is one core for every variant of the robot, and reusable by another project of his without biometrics; ports minimal and internal, no published package | 2026-11-06, 2026-11-09 | Decisions 1, 3, 11 |
| 2 | Write the contract now; move the code after CM-7 + PC-5 | 2026-11-06 | Decision 11 |
| 3 | Keep SQLite, FTS5 and `sqlite-vec`; tune only by measurement | 2026-11-09 | Decision 12 |
| 4 | Documents (R2) after CM-7 + PC-5, with Markdown, text and PDF with text; OCR later | 2026-11-06 | Decision 13 |
| 5 | Numbering: 0030 stays reserved (ADR 0029 decision 15); engine 0031, block C 0032, deployment 0033, documents 0034 | 2026-11-06 | *Amends*, roadmap |
| 6 | Take in the second external review: origin and transformation as two dimensions, the lifecycle split into states, operations and physical results, embedding compatibility, the system actor of background jobs, filters re-applied at delivery, the restore reconciliation as a goal, one database per installation, L0 as context. The delivery race is fixed by Plan 0080, the embedding guard by C1 | 2026-11-09 | Decisions 2, 3, 6, 7, 8, 10, 11, 13; *Context* item 8 |
| 7 | Take in the final review: the Plan 0080 and C1 assignments are proposals tied to those plans' scopes; the two recall gaps classified apart (an invariant not held, a race pending reproduction); retrievability measured on questions with expected answers; complete forgetting not declared while a restore can bring a memory back | 2026-11-09 | *Context* item 8; decisions 2, 5, 8, 9, 13; *Test consequences* |
| 8 | Accept this ADR on review, before any plan implements it | 2026-11-09 | *Status* |

The author's calls, for Pipec's review: the four meanings of time and the names of origins and
transformations; the shape of the port and of the two policies (from two external reviews of
2026-11-09); the six health measures; the L0–L6 scale; that the guard test lands in C1; the order
of tuning.

## Not decided here

| Subject | Owner |
|---|---|
| Who may correct and forget, and the retention of memories for years | ADR 0032 (block C) |
| The deletion register (or crypto-shredding) that stops a restore from resurrecting what was forgotten | ADR 0032 with ADR 0033 |
| Where the engine runs (a container on the home server), encryption at rest and of backups | ADR 0033 (deployment) |
| The documentary source contract, chunking, the PDF library and its licence | ADR 0034 (R2) |
| ~~The minimum occurred-time for «¿cuándo fui…?»~~ | Decided by Plan 0080: the day it was told, no `occurred` column (decision 5); the occurred time itself stays future |
| The exact names and module layout of the port | The extraction plan, after CM-7 + PC-5 |
| An export format (Open Memory Protocol Initiative or another) | When the protocol publishes a specification; not before the MVP |
| Reflection (inferred opinions or summaries of summaries) | Not planned; it would need its own ADR |

## Alternatives considered

- **Extract the engine now, before block C.** Rejected: about twenty modules rewired right before
  correction, forgetting and the final acceptance; the regression risk lands where it costs most.
- **Leave the boundary until after CM-7.** Rejected: CM-6 and R2 would be built on the mixture,
  and the coupling grows with every plan.
- **A published, versioned package.** Rejected for now: one real installation and an unaccepted
  MVP; a stable public API is cost without a second user.
- **Adopt an external memory engine** (Hindsight, Mem0, Letta, Zep). Rejected: each overlaps what
  exists, adds a server or a store, and none carries Iroko's combination of physical identity
  evidence, household sensitivity, consent and a deterministic writer. Their ideas are taken
  instead: time ranges on facts and the split of reported, observed and inferred (Hindsight), and
  LongMemEval's dimensions for the benchmark.
- **The firewall only on CoALA's retrieval and learning arrows.** Rejected after review: capture,
  indexing, export and backups also expose data or leave effects.
- **A policy selected by a setting.** Rejected: a configuration error must not open the household
  to the open policy.

## Consequences

### Positive

- The core is the same for the companion, the pet and the assistant, and reusable without a face
  or a voice.
- CM-6, the deployment and documents are designed against one contract instead of extending the
  mixture.
- «Not stored» and «not found» become measurable, which is what the 35.5 % voice coverage needs.
- Nothing is installed and no code moves before the final acceptance.

### Negative

- Until the extraction, the contract and the code differ; the guard test only stops the gap from
  growing.
- Two policies are two things to test; the open one has no user until the second project exists.
- The four meanings of time, the origins and the transformations add fields to future plans, by
  need.

## Test consequences

- Plan 0080 (proposed, subject to its scope): a RED test that reproduces the delivery race first,
  where a unit is reclassified (`medical`) or its record deleted between
  the search and the read, and is not delivered.
- C1: the architecture guard over `memory/` imports (the list may only shrink); integrity and
  staleness checks with counts only; a RED test where the configured embedding model changes and
  no cross-model comparison happens until the re-index ends.
- The extraction plan: the two policies cannot read each other's data; Iroko cannot compose the
  open policy; every boundary of decision 2 asks the policy before its effect.
- CM-7: the six health measures reported with the benchmark; a restart and a backup restore are
  separate cases, and the restore case forgets something after the backup and checks that it does
  not come back. CM-7 may run it and record a failure, but it **may not declare complete
  forgetting met** until that case passes or an accepted ADR explicitly limits the guarantee;
  until then Iroko does not claim that a forgotten memory cannot return from a backup.

## Docs to update

The [roadmap](../roadmap/cognitive-roadmap.md) (the rows this ADR names), the
[ADR index](README.md), and, when the code moves, `current-state.md`, the
[conversational-memory map](../roadmap/conversational-memory-delivery-map.md) and the architecture
diagram.

## Review

Revisit when the second project starts to use the engine, when the extraction plan is written,
when the robot first stores an `observed` record (P2.1), or when the Open Memory Protocol
Initiative publishes a version 1 specification.
