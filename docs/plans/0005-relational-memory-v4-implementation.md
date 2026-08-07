# Plan 0005 — Relational memory v4 implementation

## Status

**Draft — not executable.** This plan is subordinate to the approved
[P0.4 design and migration decision](0004-relational-memory-v4-design-and-migration.md).
It must remain Draft until Plan 0002 and the P0.3 controller plan are Complete,
the actual codebase is re-read, and its exact file scope/migration version is
reviewed. No agent may implement this document yet.

## Objective

Implement the approved relational-memory v4 model: separate literal facts from
entity-ID relations, enforce predicate cardinality and lifecycle rules, migrate
only unambiguous legacy records with an audit ledger, provide a non-destructive
compatibility path, and make age a derived value from ISO `birth_date`.

P0.5 authorization remains a prerequisite to retrieving protected v4 data in a
production conversation. This plan does not substitute a migration, entity ID,
or confidence score for permission.

## Required authority when becoming Ready

1. `AGENTS.md` and applicable `.codex/rules/`.
2. [`memory-and-world-state.md`](../architecture/memory-and-world-state.md).
3. [`identity-and-access.md`](../architecture/identity-and-access.md).
4. [`cognitive-architecture.md`](../architecture/cognitive-architecture.md)
   and [`cognitive-contracts.md`](../architecture/cognitive-contracts.md).
5. [ADR-0004](../adr/0004-local-first-cognitive-policy.md) and
   [ADR-0005](../adr/0005-small-typed-cognitive-controller.md).
6. [Plan 0004](0004-relational-memory-v4-design-and-migration.md), all its
   decisions, and the then-current Plan 0006 authorization status.
7. Current `schema.sql`, database migration registry, declarative/relations
   modules, normalizer/consolidator, controller seam, and directly related
   tests.

Historical `docs/local/` records are not operational authority.

## Locked outcomes

- Preserve current SQLite entity and fact references as integers; use UUID only
  for envelopes/evidence/correlation.
- Add v4 storage; do not reinterpret, delete, or reuse legacy `facts` rows in
  place.
- Store entity relations as source/target SQLite integer IDs, never only names.
- Keep literal facts and entity relationships separate.
- Use a small typed predicate registry for kind, cardinality, inverse-query,
  type, temporal, sensitivity, visibility, and normalization semantics.
- Treat `birth_date` as single-current ISO literal and derive age from it. No
  v4 `age` fact exists.
- Preserve siblings of multi-value preferences; use one canonical relation row
  and derive inverse queries; retain valid temporal history.
- Migrate only deterministic, unambiguous legacy rows; record every defer or
  reject in a local ledger.
- Keep migration local, idempotent, auditable, and logically reversible.
- Do not return protected v4 data without the P0.5 authorization boundary.

## Provisional implementation slices

These slices define intent, not present implementation authority. Their exact
file ownership, migration number, test names, and commands must be frozen only
in the Ready revision after re-reading current `main`.

### Slice 1 — Registry and immutable repository contracts

- [ ] Add tests first for the closed predicate registry: aliases, kinds,
  cardinality, inverse/symmetry, allowed entity types, default classifications,
  ISO literal validation, and explicit unsupported-predicate outcome.
- [ ] Run and record observed RED using the future focused repository test.
- [ ] Add the smallest typed registry/repository contracts. Do not introduce an
  ORM, plugin framework, LLM classifier, or database I/O in pure models.
- [ ] Run focused GREEN and review strict typing, immutability, docstrings, and
  no `Any`/unbounded string predicate path.

### Slice 2 — Additive schema and lifecycle repositories

- [ ] Write migration tests against a temporary real SQLite database before SQL:
  new v4 tables, foreign keys, active uniqueness, symmetric-pair uniqueness,
  lifecycle/validity fields, metadata classifications, and no legacy mutation.
- [ ] Run and record RED.
- [ ] Add exactly one numbered forward migration and database-registry entry;
  use additive tables and indexes only.
- [ ] Implement literal/relation repositories that enforce registry cardinality
  and lifecycle semantics transactionally.
- [ ] Run focused GREEN, migration idempotence, and `PRAGMA foreign_key_check`.

### Slice 3 — Conservative legacy migration ledger

- [ ] Build fixture databases covering: unique relation target; same-name
  ambiguity; missing target; ISO and prose birth dates; multi-value preferences;
  `edad`; negative `ninguno`; superseded fact; unsupported predicate; and
  temporal value.
- [ ] Write RED tests that require exactly one ledger outcome for every active
  legacy source row.
- [ ] Implement deterministic classification/migration with no entity creation,
  LLM use, cloud call, or first-match name heuristic.
- [ ] Verify `migrated`, `deferred`, and `rejected` reasons; run twice to prove
  idempotence; preserve the original database rows and IDs.

### Slice 4 — Read/write compatibility cutover

- [ ] Write tests for a v4-preferred reader, legacy fallback only when no v4
  outcome exists, and explicit legacy/unverified result labels.
- [ ] Test that post-cutover writes target v4 only and that disabling the v4
  feature restores legacy reads without deleting v4 tables or ledger rows.
- [ ] Implement the smallest compatibility adapter at the current repository
  seam. Do not dual-write divergent fact definitions.
- [ ] Run focused GREEN and verify existing callers retain their documented
  public contracts until their own migration plan changes them.

### Slice 5 — Deterministic relation/date tools and safety integration

- [ ] Add RED tests for `get_children`, relationship count, inverse lookup,
  `birth_date` age calculation, missing/ambiguous/contradictory values, and
  `unauthorized` before data is fetched.
- [ ] Connect only to the then-approved P0.3 controller and P0.5 policy seams.
  An LLM may phrase tool output but cannot calculate, count, decide a relation,
  or mutate it.
- [ ] Keep normalizer/consolidator changes bounded: LLM extraction proposes
  candidates, while registry, grounding, confirmation, and policy decide
  persistence.
- [ ] Run focused GREEN and confirm no protected values reach model context on
  denied/confirmation-required paths.

### Slice 6 — Final migration, rollback, and repository gates

- [ ] Run complete migration fixtures on a copy of the legacy schema and retain
  ledger/statistics evidence.
- [ ] Test logical rollback by disabling the v4 reader/writer path; prove legacy
  rows remain readable and no destructive DDL/data deletion occurs.
- [ ] Run `just lint`, `just typecheck`, and `just test` after focused checks.
- [ ] Audit `git diff --check` and file scope; review local-only behavior,
  entity IDs, lifecycle, cardinality, privacy boundary, and no audio/server-
  robot contract change.

## TDD execution protocol

When this plan becomes Ready, every slice uses
`superpowers:subagent-driven-development` (preferred) or
`superpowers:executing-plans` (sequential fallback). Every task must:

1. write the focused test first;
2. record an observed RED failure;
3. implement the smallest scoped behavior;
4. record focused GREEN;
5. perform a diff/type/privacy review; and
6. preserve unrelated work and never commit directly to `main`.

Subagents are a temporary development technique only; they do not imply a
production multi-agent architecture.

## Stop conditions

Stop and write a new decision/ADR rather than widening Plan 0005 if any task
needs a new global identifier strategy, a graph database, destructive migration,
automatic ambiguity resolution, automatic confirmation, a public data/role API,
cloud processing, biometric processing, action control, world-state storage, or
a changed audio/server-robot contract.

## Conditions to promote this plan to Ready

- [ ] Plan 0002 is Complete with all gates evidenced.
- [ ] The P0.3 controller plan is Complete and its actual seam is inspected.
- [ ] The P0.4 design is still accepted after current-tree review.
- [ ] P0.5 policy integration order is confirmed, including no protected read
  before decision.
- [ ] Exact new schema version, files, fixtures, focused commands, rollback
  switch, and compatibility behavior are reviewed and recorded.
- [ ] A new execution runbook with concrete per-task file ownership, RED/GREEN
  commands, and final checks is approved.
