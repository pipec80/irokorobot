# Plan 0008 — Policy-gated v4 household reads and tools design

## Status

**Draft design — reviewed against `main` at `e65834d` on 2026-08-12.**

This document defines the remaining P0.5-B work required to close the P0
trust foundation. It is not executable implementation authority. A separate,
small implementation plan becomes `Ready` only after this design is reviewed
and its exact current seams are revalidated.

P0.5-A is complete in [Plan 0007](0007-household-authorization-foundation.md):
it supplies a pure fail-closed policy, persisted household roles, a safe audit
writer, explicit local owner bootstrap, and controller enforcement before
protected legacy delegation. P0.4 is complete in
[Plan 0005](0005-relational-memory-v4-implementation.md): it supplies the
isolated v4 schema, predicates, lifecycle repositories, and additive migration
foundation. Neither plan retrieves v4 values at runtime.

## Purpose

Connect the existing policy boundary to a minimal v4 household-read path and
deterministic family tools without weakening identity, authorization, or the
legacy v3 compatibility boundary.

The outcome is a small controller path that can, when it is given a *trusted
internal* actor and any required consent, authorize a narrow family query,
read only its permitted v4 records, calculate counts and ages deterministically,
and return an immutable response plan. Unknown public `/chat` remains unknown
and cannot retrieve family data.

This is not P1 onboarding, public login, face/voice authentication,
confirmation issuance, semantic retrieval, or natural-language entity
resolution.

## Revalidated implementation facts

| Finding | Evidence | Consequence |
|---|---|---|
| v4 reader functions return raw active facts/relations without runtime policy. | `server/src/server/memory/relational_v4.py`: `get_active_literal_facts()` and `get_active_entity_relations()` | P0.5-B needs a policy-gated application reader; raw repository functions remain test/foundation primitives. |
| `child_of` and `birth_date` default to `household` + `child_data`. | `server/src/server/memory/predicate_registry.py`: `_PREDICATES` | A family count or age must not become allowed merely because the actor is an owner. Existing policy requires explicit consent for these sensitive categories. |
| `likes`, `dislikes`, and `prefers` default to `household` + `normal`; `allergic_to` defaults to `medical`. | `predicate_registry.py` | Preferences can be served only through the normal-household rule; medical data remains consent-gated and is not a P0 family-tool capability. |
| P0.5-A policy is pure and audits decisions before protected legacy delegation. | `server/src/server/cognition/authorization.py`, `controller.py`, and `memory/household_authorization.py` | P0.5-B must reuse the closed vocabulary and audit writer; it must not add a second policy or a bypass. |
| Public `/chat` always composes an unknown actor. | `server/src/server/routers/chat.py`: `_public_unknown_actor()` | Public chat must continue to deny household reads, even after the internal family path exists. |
| The current relation repository can filter a relation only by source entity. | `relational_v4.py`: `get_active_entity_relations()` | Inverse `child_of` lookup for a parent needs a bounded target-ID filter or equivalent repository method. |
| P0.3 has no generic `ToolRegistry`, intentionally. | `docs/roadmap/cognitive-roadmap.md` P0.3; `cognition/controller.py` | P0.5-B uses a small closed family-tool service, not a framework or arbitrary prompt-driven dispatch registry. |

## Proposed design

### 1. Preserve the authorization-before-retrieval boundary

Every v4 read has this order:

```text
trusted internal actor + closed operation + predicate classification
    -> deterministic policy decision
    -> safe audit event
    -> only if allowed: bounded v4 SQL read
    -> typed known / unknown result
```

`denied` and `requires_confirmation` both produce
`KnowledgeStatus.UNAUTHORIZED` without executing a v4 query and without
revealing whether a person, relation, or fact exists. The policy decision is
scoped to one correlation ID and operation; it is never stored as a reusable
session grant.

The controller authorizes `execute_household_tool` before invoking a family
tool. The policy-gated reader authorizes `read_household_data` before it calls
a raw v4 repository. Both decisions use the same active actor, correlation ID,
closed classifications, and local audit writer. This deliberate two-boundary
check prevents a future tool implementation from treating tool permission as a
blanket read grant.

### 2. Use predicate metadata, not values, to classify a query

The reader obtains `visibility` and `sensitivity` from the closed
`PredicateDefinition` before fetching values. P0.4 writes v4 rows using those
same immutable defaults; no P0 API may override them.

The initial consequences are intentional:

| Query | Predicate | Classification | P0.5-B result without granted consent |
|---|---|---|---|
| Count/list children | `child_of` inverse lookup | household + child_data | unauthorized |
| Calculate a person's age | `birth_date` | household + child_data | unauthorized |
| Read preferences | `likes`, `dislikes`, `prefers` | household + normal | allowed only for a resolved owner/adult under the existing matrix |
| Read allergies | `allergic_to` | household + medical | unauthorized |

An internal adapter/test may provide `ConsentStatus.GRANTED` only from a
future trusted consent source. P0.5-B does not create consent, accept consent
from HTTP text, turn a self-identification into consent, or persist a broad
confirmation. P1 onboarding will become the first trusted source for household
consent choices.

### 3. Add one bounded policy-gated read service

Add a small service in the memory/application boundary (proposed name
`PolicyGatedV4Reader`) with typed, immutable input and output values. It owns
only:

- resolving an already-closed predicate alias;
- constructing a `READ_HOUSEHOLD_DATA` request from the predicate metadata;
- evaluating and auditing that request before a database call;
- bounded active literal and relation lookup by integer IDs; and
- explicit `known`, `unknown`, or `unauthorized` results.

It does not infer an entity from a name, call an LLM, compose a prompt, write
v4 data, mutate roles, issue consent, query v3 memory, or decide how to phrase
a response. Existing raw `relational_v4` functions remain isolated foundations
for migration and repository tests; production controller code reaches them
only through this service.

For `child_of`, the repository gains a backward-compatible target-entity-ID
filter. It returns active canonical relation rows; inverse semantics remain a
query operation, not a duplicate stored `parent_of` row.

### 4. Add closed deterministic family tools, not a framework

The next slice composes the reader into an injected `HouseholdKnowledgeTools`
service. Its methods have typed IDs and never accept arbitrary SQL, predicates,
or free-text names:

- `get_children(parent_entity_id, actor, consent, correlation_id)`;
- `count_children(parent_entity_id, actor, consent, correlation_id)`;
- `get_preferences(person_entity_id, actor, consent, correlation_id)`;
- `get_person_birth_date(person_entity_id, actor, consent, correlation_id)`;
- `calculate_person_age(person_entity_id, actor, consent, correlation_id, today)`.

The service resolves child labels from the existing `entities` table only after
the relationship read was allowed. It calculates age by reusing P0.3's strict
`calculate_age`; no `age` value is persisted or generated by an LLM. A missing
row is `unknown`. P0.4's active-record constraints mean this slice has no
generic contradiction resolver; disputed/corrected knowledge lifecycle remains
P2 work and must not be simulated as a guessed answer.

The controller recognizes only narrow Spanish family patterns that do not need
name grounding, initially "cuántos hijos tengo" and "cómo se llaman mis hijos".
It uses the resolved actor's integer ID as the query subject. Direct person-ID
tool calls are test/internal application seams; free-text names such as
"qué edad tiene Máximo" stay `unknown` until P1 provides explicit onboarding
and reference-resolution rules. This avoids choosing an entity from an
ambiguous name match.

The controller returns deterministic Spanish wording and typed tool results;
these closed facts do not enter `text_turn.py`, legacy v3 context construction,
or an LLM prompt. Generic conversation remains the existing legacy path with
no household context.

### 5. Keep trusted identity and consent outside public HTTP for P0

The public chat router continues to create one fresh unknown actor. It may
compose the family-tool collaborator, but policy stops an unknown actor before
any tool or reader call. The positive integration path is tested by directly
injecting a trusted `ActivePersonContext` and, for child data, an explicit
in-memory `ConsentStatus.GRANTED` test collaborator.

This is a deliberate P0 completion boundary, not a hidden product claim:

```text
P0: safe core and tested internal trusted seam
P1: unified onboarding and trusted interaction adapters
```

No route, request field, query parameter, cookie, device identifier,
conversation ID, face match, voice match, or self-declared name can supply
that trusted context in this plan.

## Proposed PR sequence

### P0.5-B1 — Policy-gated v4 reader

Implement the typed read service and target-ID relation query. Prove that an
allowed request returns only active rows, a missing allowed row is `unknown`,
and denied/confirmation-required cases do not invoke the raw repository. Audit
each policy evaluation. Do not change the controller's request classifier yet.

### P0.5-B2 — Deterministic family tools and controller cutover

Implement the closed family-tool service and narrow controller patterns.
Authorize a tool before invoking it; keep reader authorization before SQL.
Prove owner/adult normal preferences, consent-gated child relations/birth
dates, exact age calculation, no legacy/LLM call for closed results, and public
unknown `/chat` denial with no v4 read.

### P0-final — P0 closure evidence

Revalidate every P0 exit gate, run the complete local quality gate and GitHub
CI, review all P0 documents for status drift, and record exact command output,
merge SHA, and remaining P1 boundaries. This PR adds no new P1 capability.

## Explicit non-goals

- Public authentication, login, web administration, a consent UI, consent
  persistence, confirmation-session storage, or a public trusted-identity API.
- P1 onboarding, arbitrary person-name grounding, aliases as authority,
  speaker recognition, face evidence integration, diarization, or identity
  fusion.
- v3 retrieval/writes, semantic/vector retrieval, prompt assembly, LLM tool
  calling, general NLU, ToolRegistry/frameworks, new dependencies, cloud,
  biometrics, visual state, robot behavior, or audio/API contract changes.
- Destructive migration, v4 backfill changes, global ID changes, graph
  databases, and automatic conflict resolution.

## P0.5-B acceptance criteria

1. A protected v4 record is never queried, returned, audited by value, or put
   in an LLM/legacy prompt before a matching local policy decision allows it.
2. Unknown, ambiguous, role-less, denied, and confirmation-required actors
   receive a safe non-disclosing result and cannot trigger raw v4 reads.
3. Family tools use entity IDs, active v4 relations/facts, closed predicates,
   and deterministic Python calculations; they never use vector memory or an
   LLM for count, relationship, or age truth.
4. `child_of` inverse lookup counts children without writing duplicate inverse
   relationships. `birth_date` is the only age source, and preference siblings
   remain intact.
5. Public `/chat` stays schema-compatible and unknown-by-default. The positive
   trusted/consented path is available only through an internal typed seam until
   P1 onboarding supplies an approved adapter.
6. No new dependency, migration, endpoint, provider, cloud path, biometric
   path, audio change, or server/robot boundary change is introduced.

## Stop conditions

Stop and write a new ADR or design decision before implementation if the work
requires a public trusted-identity/consent interface, persistent confirmation,
policy-matrix change, per-record classifications that diverge from the closed
predicate registry, natural-language name resolution, legacy v3 cutover,
semantic retrieval, a schema migration, a dependency, cloud processing, or an
audio/server-robot contract change.

## Review checklist

- [ ] The distinction between identity, role, consent, and permission remains
  explicit in every contract and test.
- [ ] Every positive family-data test injects trusted identity and any required
  consent; no test uses a name, conversation ID, face, or voice as authority.
- [ ] Every denied/confirmation-required test proves no raw reader call and no
  legacy/LLM delegate call.
- [ ] The implementation plan freezes an exact file list, RED/GREEN commands,
  rollback, documentation updates, and final quality gates before code changes.
