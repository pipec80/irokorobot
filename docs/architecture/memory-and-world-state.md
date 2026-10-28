# Memory, relationships, onboarding, and world state

> **Status:** Canonical target design
>
> **Principle:** Storing data is not the same as remembering it, and observing
> something is not sufficient reason to retain it permanently.

The specialized [RAG, memory, and hybrid retrieval
architecture](rag-and-memory-retrieval.md) defines document ingestion,
chunking, embeddings, lexical/vector fusion, grounding, evaluation, and the
incremental delivery path. This document remains the authority for memory
semantics, truth lifecycle, relationships, onboarding, and WorldState.

## Current baseline

Iroko already has useful foundations: working conversation history, entities,
literal facts, episodic memories, embeddings, semantic search, events, sensor
tables, inverse relationship queries, and legacy owner-onboarding code that is
not a public trusted flow. SQLite and `sqlite-vec` are sufficient for the next
stages; a new database or vector service is not justified.

The current runtime still has limits that later plans must handle explicitly:

- the legacy writer (`consolidate_turn`) stored relation targets as text and
  replaced facts as if every predicate had one active value, and it never ran in
  production; Plan 0062 retired it. The canonical conversational writer is now
  `memory/memory_writer.py`, the only place a memory candidate becomes a V4
  literal fact, with entity-ID subjects, cardinality and lifecycle. Since Plan
  0063 (closed 2026-10-16) it is reached by a spoken offer and an explicit spoken
  answer, so the one conversational write path exists end to end, but only
  behind the default-off kill-switch `MEMORY_CANDIDATES_ENABLED`; with it off no
  conversation writes durable memory. Reading a stored taste back is CM-5, and
  correcting or forgetting one is CM-6
  ([ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md)).
  Since Plan 0065 (CM-3b tranche A, [ADR 0022](../adr/0022-household-rules-and-third-party-memory.md))
  the store itself is one channel-neutral writer, `memory/canonical_writer.py`
  (`write_literal`, `write_relation`), and `promote` is its first caller; see
  *The canonical writer* below;
- semantic retrieval returns the nearest items without a relevance threshold;
- retrieval is not yet filtered by the active person's authorization;
- provenance, validity periods, verification state, and sensitivity are not
  uniformly represented;
- onboarding is owner-centric rather than a complete household workflow;
- raw sensor readings, observations, facts, episodes, and current state can be
  confused if they are treated as one generic memory.

This document defines the target semantics. It does not prescribe an immediate
database migration.

## The memory layers

| Layer | Purpose | Lifetime | Examples |
|---|---|---|---|
| Working context | Keep one conversation coherent. | 180 seconds of silence, at most 3000 characters, in process only ([ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md)). | Recent turns, pending clarification. |
| World state | Represent what is probably true now. | Seconds to hours, with TTL. | Person visible, door open, room occupied. |
| Declarative facts | Store confirmed literal knowledge. | Until superseded or revoked. | Birth date, preferred name, allergy. |
| Relationships | Connect known entities by identity. | Validity interval. | Ana is parent of Leo. |
| Episodic memory | Record meaningful occurrences. | Retained by policy. | Leo asked about Saturn yesterday. |
| Semantic memory | Retrieve relevant meaning across episodes. | Derived and rebuildable. | Embeddings and summaries. |
| Reflections/hypotheses | Hold inferred patterns pending validation. | Reviewable and revocable. | May prefer shorter answers at night. |
| Procedural knowledge | Describe learned routines. | Deferred until actions are safe. | Bedtime routine steps. |
| Audit events | Explain what the system did and why. | Retention policy. | Access denied, cloud escalation attempted. |
| Telemetry | Diagnose system and hardware health. | Short operational retention. | CPU temperature, latency, battery voltage. |

These layers may reference one another but must not collapse into one table or
one undifferentiated prompt.

## Literal facts and relationships are different

A literal fact points from an entity to a value:

```text
(person: 12, birth_date, "2018-04-09")
```

A relationship points from one known entity to another known entity:

```text
(person: 7, parent_of, person: 12)
```

The target relationship representation needs, conceptually:

- `source_entity_id`: current SQLite integer entity ID;
- stable predicate;
- `target_entity_id`: current SQLite integer entity ID;
- confidence and evidence basis;
- source/provenance;
- assertion and confirmation timestamps;
- `valid_from` and optional `valid_to`;
- active, superseded, disputed, or revoked status;
- visibility and sensitivity classification.

Inverse predicates such as `parent_of` / `child_of` are query semantics. They
must not create two contradictory truths that drift independently.

## Predicate cardinality and temporal policy

Every supported predicate requires a registry entry before it is used for
automatic replacement or counting.

| Kind | Examples | Expected behavior |
|---|---|---|
| Single current value | `preferred_name`, `birth_date` | A new confirmed value supersedes the old active value. |
| Multiple values | `likes`, `dislikes`, `allergic_to` | Values coexist; one insertion must not erase siblings. |
| Entity relationship | `parent_of`, `sibling_of`, `partner_of` | Target is an entity ID and inverse queries are defined. |
| Temporal relationship | `lives_in`, `works_at` | Preserve validity intervals and history. |
| Stated value | `stated_age` | A single current whole number (0 to 130) with its as-of date (the row's `asserted_at`); it is what the owner said, **not** today's age. A `birth_date`, when known, always supersedes it. |
| Derived value | today's `age`, household counts | Calculate at query time; do not persist as a fact. |

Dates are stored in ISO format when known. Age is calculated deterministically
from `birth_date` and the current date, including whether the birthday has
occurred this year. A language model must not guess or perform this arithmetic.
When only a **stated** age exists («mi hija tiene 7 años», Plan 0065), the age shown later is
the stated value plus the whole years elapsed since its as-of date, and is approximate by up to
a year because the birthday is unknown. Today's age is never persisted, and the helper that
derives it has no consumer before CM-5, so it is not written yet.

## The canonical writer (Plan 0065, ADR 0022)

There is **one** place that stores a household fact, whatever the channel: the spoken
confirmation of CM-3a (`voice_classic`, `voice_stream`) and the initial import of Step 0
(`import_file`, `import_assisted`) call the same `write_literal` and `write_relation`; after the alta
closes the local admin CRUD (`admin_local`, Plan 0073, ADR 0025 decision 4) is a further caller for the
amendment path, and a `revoke` sets the row inactive (V4 `lifecycle='revoked'`, a contact's `revoked_at`)
with one audit row that holds no value — a hard delete is CM-6. The speaker never assigns
the classification; the writer looks it up from the predicate and the subject in one table:

| Subject | Stored as |
|---|---|
| The owner | `personal`, with the registry's sensitivity; the owner's `birth_date` is `personal`/`private` |
| A child or a pet of the owner | `household`, with the registry's sensitivity (so the household reader still serves it) |
| The partner, or anyone else | Refused with the closed reason `not_household_member`; for the partner only the name and the relationship (`partner_of`) are stored |
| Anyone but the owner, for a predicate whose registry default is `personal` (`private_topic`) | Refused with `owner_only_predicate` |

Membership relations (`child_of`, `partner_of`, `pet_of`) are `household` data; `lives_in` and
`works_at` follow their source like a literal. «Child» means a child the owner is guardian of;
the entity's `guardianship` attribute says whether they are a minor or an adult (ADR 0024
decision 9): an **adult child** gets the partner's rule, name and relationship only, on every
channel, and may still be a contact; a child with no marker is treated as a minor. The owner's
**relatives** (`has_parent`, `has_grandparent`, `has_grandchild`, symmetric `has_sibling`, owner at
the source end) get the same rule, and so do the people to keep out (`withhold_from`, which may
point at anyone). A relative or a contact can never be relabeled a child, a pet or the partner
(`role_conflict`), nor a member a relative; an exact repeat of an active relation is always
accepted. The asserter is the owner and so is the confirmer, unless the owner did not confirm
(`confirmed_by_owner=False`, an assisted interview in `representative` mode: `confirmed_by`
stays `NULL`, `confirmed_at` is kept, ADR 0024 decision 6), and
each row records them and the channel (`asserted_by_entity_id`, `channel`, migration 010; older
rows and the local setup read `NULL`). A load made while commissioning can ask the writer to
refuse a different single value instead of superseding it (`on_conflict=REFUSE`: `value_conflict`). A repeat of an active value with the same classification is
idempotent; a stored row labelled otherwise is refused as `classification_conflict`. Since Plan 0071
a `text` value is compared by its key (`server/text_keys.py`: folded, without a leading article;
ADR 0024 decision 12), so a spoken «El Café» and an imported «café» are one row; a date, a number,
a reference, and a text whose key is empty compare exactly. Nobody who is
already the partner, or holds an adult role, can be declared a child to unlock their facts. A temporal
relation closes the previous one at the new `valid_from`, an explicit `valid_to` stores history
(lifecycle `expired`, never closing the current row), and dates are `YYYY-MM-DD` or `YYYY-MM`.
A third party is created apart, once: `create_third_party` refuses a second entity with the same
folded name and type (`AmbiguousEntityError`), and the import key makes a re-run return the same
entity. Several writes can join a transaction the caller owns, so an importer gets
all-or-nothing with no new API. **The importer (Plan 0071)** is that caller: `memory/seed_import.py`
writes a plan of operations (`memory/seed_plan.py`, built from a validated seed file) through these
writers with the channel `import_assisted` and the refuse policy, in one transaction with the
commissioning record (`memory/seed_run.py`); while no commissioning is closed and nothing was learned by voice,
`memory/seed_replace.py` retracts what earlier imports wrote (rows and contacts of the import
channels, the statuses, the seed entities nothing refers to) before writing again. See
[current-state](current-state.md).

The registry also knows `species` (pets), `stated_age`, `private_topic` («no menciones X delante
de visitas»: only the predicate exists, its behaviour needs CM-5 and Step 0) and `access_code`
(the first `security` datum, with no Spanish alias). **A secret is never stored (ADR 0024
decision 4, Plan 0070):** `access_code` is registered but not `storable`, so the repository refuses
it whatever label a caller asks for (`UnstorableValueError`, before any write or log); what is
stored is *who knows* it (`secret_holder`) and *where a document is* (`document_location`), free
text of 2 to 120 characters that refuses four digits in any script, `personal`/`security`, read at
`strong` (reading is CM-5). The repository also refuses a stated sensitivity that disagrees with the
predicate's, in both directions.

**The data pool and the contacts.** The commissioning's pool (`seed-data-pool.md`) adds the
predicates for the owner's health, function and home (all `personal`, about people only; choices
are Spanish codes) and two tables outside the V4 facts: `care_contacts` (a person with a phone
the owner wants called or told; written only by `memory/care_contacts.py`, which assigns
`personal`/`private`, or `location` for a key holder; being a contact opens no fact about the
person) and the `commissioning_records` / `commissioning_sections` of the acta (who interviewed,
how the owner confirmed, the hash and counts of each import, one status per section; no household
value; written only by `memory/commissioning.py`). Nothing reads them by voice before CM-5.

## Provenance, confidence, and truth status

Each durable item must be able to answer:

- who or what supplied it;
- when it was asserted and last confirmed;
- whether it is directly asserted, measured, estimated, or inferred;
- what evidence supports it;
- who confirmed it, if confirmation was needed;
- what period it was valid for;
- whether it is active, superseded, disputed, revoked, or expired;
- who may retrieve it and how sensitive it is.

Confidence does not turn an inference into a confirmed fact. Multiple weak
signals can produce a useful hypothesis, but promotion to durable knowledge is
governed by explicit predicate policy and, for sensitive data, confirmation.

## Memory lifecycle

```text
observation or conversation
        |
        v
candidate extraction -- normalize --> duplicate/conflict check
        |                                  |
        |                                  +--> clarification or dispute
        v
episode or hypothesis
        |
        +-- policy says no retention --> discard/expire
        |
        +-- confirmation required ----> ask the authorized person
        |
        v
confirmed fact or relationship
        |
        +--> supersede with history
        +--> revoke/delete by policy
        +--> consolidate into a reviewable summary
```

The LLM may propose a candidate; it does not directly establish household
truth. Normalization, deduplication, contradiction handling, cardinality, and
authorization are deterministic services around the model.

## Longitudinal conversational memory contract

A durable autobiographical item must carry enough semantics to answer:

- whose memory or data it is;
- who asserted it and through which source;
- when the underlying event occurred and when the assertion was made;
- whether it is a fact, relationship, episode, preference, observation or
  inference;
- whether it is proposed, confirmed, disputed, superseded, revoked or expired;
- its visibility, sensitivity, consent basis and retention policy;
- which earlier item it corrects or supersedes;
- which embeddings, summaries, caches or other projections derive from it.

This is a conceptual contract, not an instruction to add all fields to one
table. Facts, relationships, episodes and audit records keep their distinct
representations while sharing stable references and policy semantics.

Automatic extraction creates a **candidate**, never household truth. Promotion
may be automatic only when an explicit predicate policy permits it; otherwise
the authorized subject or delegate confirms or rejects it. Inference remains
labelled as inference even when its confidence is high.

### Candidate lifecycle (CM-3a, ADR 0021)

A candidate lives in its own table (`memory_candidates`), never inside the
canonical V4 tables, and has one of five statuses:

```text
proposed --offered aloud--> offered --explicit "yes" answer--> confirmed (one V4 fact)
    ^                          |
    |                          +--explicit "no" answer--------> rejected
    +-- no answer in time -----+
                               (a candidate past its lifetime or out of offers: expired)
```

- **proposed:** the person said a first-person taste on a voice turn whose face
  and voice were both verified; nothing has been said back yet.
- **offered:** the robot spoke the offer on a later voice turn. The offer and
  the answer are spoken, never typed. The status records that the offer was
  built for that reply, not that the person heard it.
- **confirmed:** the person gave an explicit spoken «yes» (a closed verb; the
  value is optional and, when present, must match); the single writer inserted one canonical `personal` fact that records who
  confirmed it and when.
- **rejected:** the explicit negative answer, or a contradiction found at
  promotion. The stored value is erased.
- **expired:** the lifetime lapsed or the offers ran out; the value is erased.

Rules of the contract:

- **One open offer per person.** While an offer waits for its answer, nothing
  else of that person is offered, so an answer always names the offer it resolves.
- **A response window.** An offer unanswered within
  `MEMORY_CANDIDATE_ANSWER_SECONDS` (60) returns to `proposed`; a candidate is
  offered at most `MEMORY_CANDIDATE_MAX_OFFERS` (2) times and then expires.
- **The answer is an explicit closed verb; the value is optional** (Plans 0066
  and 0067, ADR 0021 decision 9). A bare «sí» never promotes. A long verb alone
  («autorizo», «acepto») answers the person's one open offer; the short verbs
  («guarda», «guárdalo», «guárdala») answer alone only after a leading «sí», and
  with a value they need an article before it. A value that is present must
  match the open offer. A valueless answer resolves the offer only when exactly
  one is open inside the window. The trade-off (a recording of the verb could
  answer without knowing the value) is written in ADR 0021.
- **Face and voice of the same person, on that turn's own clip,** for every
  proposal, offer, answer and promotion, never a token. Anything else is the
  ordinary turn, byte for byte, so the existence of a candidate is never revealed.
- **Erased on resolution.** A resolved candidate holds no value; this is a
  schema rule, not a convention.
- **Not defended:** replay (a photograph plus an earlier recording of the owner)
  is measured and unprotected (ADR 0016 section 9); since Plan 0066 a replay of
  the verb can answer an open offer without knowing its value, bounded by the
  answer window, the single open offer, face and voice of that turn's clip, and
  the audit row.

Conversational memory requires capabilities narrower than a generic personal
read grant:

- `read_personal_conversation_memory`;
- `propose_personal_memory`;
- `confirm_personal_memory`;
- `correct_personal_memory`;
- `forget_personal_memory`.

Identity evidence can help resolve the actor, but only policy grants one of
these actions and its data scope. An owner or administrator does not acquire
another adult's private memory by role alone.

The executable quality contract is defined in
[longitudinal-conversational-memory-evaluation.md](longitudinal-conversational-memory-evaluation.md).

## Retrieval order

Retrieval happens only after active-person resolution and access evaluation.
The preferred order is:

1. restrict the search to data categories visible to the active person;
2. resolve exact entities and structured relationships;
3. execute deterministic tools for dates, counts, and current state;
4. retrieve relevant literal facts;
5. retrieve episodes/semantic candidates above an explicit relevance policy;
6. rank authorized candidates by relevance, importance, recency, and trust;
7. keep provenance and uncertainty attached to the result;
8. return `unknown`, `ambiguous`, `contradictory`, or `unauthorized` when
   appropriate instead of filling a fixed top-k context.

Filtering protected content after retrieval is too late: the model must never
receive facts the active person was not permitted to access.

For the first personal-companion proof, “¿quiénes son mis hijos?” is not a
vector-search problem. After fresh owner authentication and authorization,
Iroko resolves Pipec's entity ID and reads active structured child
relationships through the existing deterministic tool. Semantic/vector
retrieval remains appropriate for fuzzy recollection; lexical retrieval for
exact identifiers; documentary RAG for future imported sources. None of those
mechanisms may bypass the same pre-retrieval authorization boundary.

## Directed household messages are not generic memory

A recado is sensitive temporal data addressed to a recipient, not a fuzzy fact
for household-wide RAG. Its minimum semantics include sender, recipient,
content, creation/expiry times, `recipient_only` visibility, delivery state and
audit references. Retrieval requires the confirmed authorized recipient; an
unknown speaker, guest, administrator or other family member receives neither
the content nor a hint that the recado exists unless an explicit policy says
otherwise.

Episodes may reference that a delivery occurred, subject to retention policy,
but copying the message into an unrestricted conversation summary or embedding
would violate its visibility.

## World state is not long-term memory

`WorldState` is an assembled, expiring view of the environment. A future typed
contract should include at least:

- creation time and `valid_until`;
- location or logical zone, when known;
- people present and separately identified active person;
- visible objects and relevant scene attributes;
- latest authorized sensor states;
- source observation IDs;
- confidence and contradictions;
- explicit unknown fields rather than invented values.

A camera frame or sensor sample updates current state. It becomes an episode
only when an event policy judges it meaningful, for example a requested photo,
an explicitly saved family moment, or a safety incident. Continuous frames,
biometric embeddings, and room activity must not become permanent memories by
default.

## Telemetry is not autobiographical memory

Telemetry exists to operate the system: latency, temperatures, error counts,
battery, and raw sensor samples. It has separate retention and access rules.
Only a meaningful interpreted event may cross into memory, and that promotion
must keep a pointer to its evidence rather than copy an unlimited raw stream.

Examples:

- `CPU reached 82 C` is telemetry;
- `the server throttled and the conversation failed` can be an audit event;
- `the kitchen was 30 C for two hours` may become a household event if a policy
  explicitly needs it;
- none of these facts should automatically become part of a person's profile.

## Memory, events, outcomes, and feedback are separate

An event records what happened; memory preserves authorized knowledge about the
past; an outcome records the observed result of a decision or action; feedback
records an authorized evaluation of that result. These domains may link by
stable identifiers but do not collapse into one prompt or table.

Outcomes and feedback are not implemented as a general subsystem. They become
necessary before Iroko can claim it learns from real-world results, especially
for future `care` or `education` responsibilities. More conversation storage is
not a substitute for that evidence loop.

## One onboarding service, several channels

The personal companion is built first with a bounded local administrative flow.
The general service described below belongs to the later `family` profile; it
must reuse the same entities, relationships, role policy, and provenance rather
than create a second data model. A technical owner/admin initializes the family
profile but does not automatically gain another adult's personal/private data.

Voice, web forms, and controlled imports must call the same application
service. They must not implement independent truth rules or write SQL directly.

Recommended stages:

1. household identity and owner/admin confirmation;
2. owner profile and preferred communication;
3. other adults;
4. children and age-appropriate access;
5. pets and relevant household entities;
6. relationships among entity IDs;
7. preferences and routines;
8. data visibility, consent, and retention choices;
9. optional face and voice enrollment with explicit consent;
10. review, contradiction resolution, and confirmation.

Every channel records provenance. Imported data is not automatically more
trusted than spoken data. Re-running onboarding updates confirmed knowledge
without duplicating the household or erasing unrelated multi-value facts.

## Privacy and deletion

- Biometric templates are a separate sensitive data category, not ordinary
  semantic memory.
- Medical, child, location, and private-conversation data require explicit
  policies.
- A person must be able to correct, revoke, export, and delete data they are
  authorized to control.
- Derived embeddings and summaries must be invalidated when their source is
  deleted or access is revoked.
- Backups preserve encryption and deletion/retention policy; they are not an
  escape hatch around consent.

## Acceptance scenarios for later plans

1. **Count children:** resolve the active authorized adult, query active
   `parent_of` relationships, count deterministically, and explain unknown or
   contradictory data without guessing.
2. **Calculate age:** read the person's confirmed birth date and calculate age
   from the current date; never read a stored `age` string. When only a stated age
   exists, derive the approximate age from it and its as-of date.
3. **Multiple preferences:** adding a second preference does not supersede the
   first because the predicate is multi-value.
4. **Moved home:** the old residence keeps a closed validity interval and the
   new one becomes active.
5. **Unknown guest:** the system can discuss public topics but does not retrieve
   private household episodes.
6. **Stale observation:** a person seen five minutes ago is not reported as
   currently present after the world-state TTL expires.
7. **Weak semantic match:** no memory is returned when candidates do not meet
   the relevance policy.
8. **Correction:** a confirmed correction supersedes the old fact while keeping
   auditable history and removing it from normal retrieval.

## Migration constraints

Schema evolution must be incremental, reversible where practical, and covered
by migration and repository tests. Existing entity integer IDs remain the
compatibility baseline; changing the global identifier strategy is a separate
decision, not hidden inside the cognitive-model plan. Existing memories must
not be silently reclassified as confirmed facts, and no migration may upload
local data to a cloud service.
