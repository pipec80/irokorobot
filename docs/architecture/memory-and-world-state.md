# Memory, relationships, onboarding, and world state

> **Status:** Canonical target design
>
> **Principle:** Storing data is not the same as remembering it, and observing
> something is not sufficient reason to retain it permanently.

## Current baseline

Iroko already has useful foundations: working conversation history, entities,
literal facts, episodic memories, embeddings, semantic search, events, sensor
tables, inverse relationship queries, and a basic owner onboarding flow. SQLite
and `sqlite-vec` are sufficient for the next stages; a new database or vector
service is not justified.

The current model also has limits that later plans must handle explicitly:

- a relation target is stored as text rather than as an entity identifier;
- fact replacement effectively assumes one active value per predicate;
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
| Working context | Keep one conversation coherent. | Minutes or one session. | Recent turns, pending clarification. |
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
| Derived value | `age`, household counts | Calculate at query time; do not persist as a fact. |

Dates are stored in ISO format when known. Age is calculated deterministically
from `birth_date` and the current date, including whether the birthday has
occurred this year. A language model must not guess or perform this arithmetic.

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

## One onboarding service, several channels

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
   from the current date; never read a stored `age` string.
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
