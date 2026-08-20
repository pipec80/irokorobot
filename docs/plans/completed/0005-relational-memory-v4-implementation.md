# Plan 0005 — Relational memory v4 implementation

## Status

**Complete — merged to `main` as `3b01b58` through PR #40 on 2026-08-12.**
The feature branch implementation was validated at `5958ee6`
(`feat/p04-relational-memory-v4`) before final GitHub CI and merge. This plan is
subordinate to the completed [P0.4 design and migration
decision](0004-relational-memory-v4-design-and-migration.md). The actual tree,
legacy schema/migration registry, declarative and relational modules,
consolidation path, controller boundary, and 24 focused memory integration
tests were re-read. This authorization is limited to the storage/migration
foundation below; it does not authorize P0.5 retrieval or runtime cutover. The
companion [execution runbook](0005-relational-memory-v4-execution.md) contains
the task-by-task RED/GREEN sequence.

## Objective

Implement the approved relational-memory v4 **foundation**: separate literal
facts from entity-ID relations, enforce predicate cardinality and lifecycle
rules within v4 repositories, migrate only unambiguous legacy records with an
audit ledger, and make age a derived value from ISO `birth_date`.

P0.5 authorization remains a prerequisite to retrieving protected v4 data in a
production conversation. The existing legacy `build_context`, `relations`,
`consolidation`, and `/chat` paths remain the runtime reader/writer throughout
this plan; no v4 value reaches a prompt. This plan does not substitute a
migration, entity ID, or confidence score for permission.

## Required authority when becoming Ready

1. `AGENTS.md` and applicable `.codex/rules/`.
2. [`memory-and-world-state.md`](../../architecture/memory-and-world-state.md).
3. [`identity-and-access.md`](../../architecture/identity-and-access.md).
4. [`cognitive-architecture.md`](../../architecture/cognitive-architecture.md)
   and [`cognitive-contracts.md`](../../architecture/cognitive-contracts.md).
5. [ADR-0004](../../adr/0004-local-first-cognitive-policy.md) and
   [ADR-0005](../../adr/0005-small-typed-cognitive-controller.md).
6. [Plan 0004](0004-relational-memory-v4-design-and-migration.md), all its
   decisions, and the current Draft status of Plan 0006 authorization.
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
- Add migration version **4** only for additive v4 tables and indexes. Legacy
  data backfill is an explicit local administrative command with dry-run as its
  default, never a startup side effect or HTTP endpoint.
- Leave legacy runtime reads and writes unchanged. A later P0.5-gated plan owns
  the v4 reader/writer cutover and deterministic family tools.

## Exact permitted file scope

| Path | Change |
|---|---|
| `server/src/server/db.py` | Register migration version 4; do not alter prior migration semantics. |
| `server/src/server/memory/migration_004_relational_v4.sql` | Add only v4 tables and indexes. No legacy-row `UPDATE`, `DELETE`, or automatic data backfill. |
| `server/src/server/memory/predicate_registry.py` | Define the closed, pure predicate registry and literal normalization. |
| `server/src/server/memory/relational_v4.py` | Implement typed v4 literal/relation repositories and transactional lifecycle/cardinality writes. |
| `server/src/server/memory/legacy_v4_migration.py` | Classify and migrate active legacy rows with an idempotent ledger. |
| `scripts/migrate_memory_v4.py` | Provide a local-only migration command: dry-run default, explicit `--apply`, no HTTP or cloud use. |
| `tests/unit/test_predicate_registry.py` | Cover pure registry semantics and strict ISO validation. |
| `tests/integration/test_memory_v4_schema.py` | Cover version 4 schema, constraints, and unchanged legacy tables. |
| `tests/integration/test_memory_v4_repository.py` | Cover literal/relation cardinality, lifecycle, inverse/symmetry, and foreign keys. |
| `tests/integration/test_memory_v4_migration.py` | Cover fixture migration, ledger reasons, idempotence, dry-run, and legacy preservation. |
| `docs/architecture/current-state.md`, `docs/roadmap/cognitive-roadmap.md`, `docs/plans/README.md`, this plan, and its execution runbook | Record completion evidence only after all gates pass. |

Do not modify `schema.sql`, `declarative.py`, `relations.py`, `context.py`,
`consolidation.py`, `normalize.py`, any router, `text_turn.py`, the controller,
the robot client, or existing public schemas in this plan. No dependency,
environment variable, HTTP endpoint, public admin API, automatic startup
backfill, cloud call, or hardware capability is authorized.

## Frozen v4 contracts and schema

The registry is a closed Python mapping, not a database table or plugin API. It
must expose `PredicateDefinition`, `PredicateKind`, `PredicateCardinality`,
`resolve_predicate(alias: str) -> PredicateDefinition | None`, and
`normalize_literal(definition: PredicateDefinition, value: str) -> str | None`.
The initial canonical IDs are exactly `birth_date`, `likes`, `dislikes`,
`prefers`, `allergic_to`, `child_of`, `partner_of`, `pet_of`, `lives_in`, and
`works_at`. `age`/`edad` are unsupported and have no v4 target.

Migration 4 creates these additive records:

- `literal_facts_v4`: integer primary key; `subject_entity_id`; canonical
  predicate; `value_text`; confidence; optional `source_memory_id` and
  `confirmed_by_entity_id`; assertion/confirmation/validity timestamps;
  lifecycle, visibility, and sensitivity classifications.
- `entity_relations_v4`: the same metadata plus integer
  `source_entity_id`/`target_entity_id`; canonical relation predicate; and a
  check preventing self-relation. `partner_of` stores the lower entity ID first.
- `legacy_fact_migration_v4`: unique `legacy_fact_id`; outcome
  `migrated|deferred|rejected`; exactly one nullable target foreign key for a
  migrated literal or relation; stable reason; and timestamp.

Partial unique indexes prevent duplicate active literal values and duplicate
active relation triples. Repository transactions, using the registry rather
than a universal SQL constraint, enforce single-current and temporal
supersession. Multi-value literals coexist. No v4 write emits an outbox record
in this slice because the legacy outbox has no v4 aggregate/lifecycle contract.

## Executable TDD slices

### Slice 1 — Registry contracts

- [x] Write `tests/unit/test_predicate_registry.py` RED for exact aliases,
  allowed entity types, `birth_date` strict `YYYY-MM-DD`, multi-value preference
  coexistence, inverse `child_of -> parent_of`, symmetric `partner_of`, and
  unsupported `edad`.
- [x] Run `uv run pytest tests/unit/test_predicate_registry.py -v`; record the
  missing-module RED.
- [x] Implement `predicate_registry.py` with immutable definitions and no I/O.
- [x] Re-run the focused suite GREEN; run Ruff and type checks for the new module.

### Slice 2 — Additive schema and repositories

- [x] Write schema/repository RED tests using a temporary real SQLite database:
  user version 4, new tables/indexes, `PRAGMA foreign_key_check`, untouched
  legacy facts, single-current supersession, multi-value coexistence, temporal
  validity, and symmetric-pair deduplication.
- [x] Add migration 4 and register it in `server.db._MIGRATIONS`; it must create
  tables/indexes only and leave migration 1–3 unchanged.
- [x] Implement the v4 repositories with explicit transactions and rollback on
  failure; no model, provider, router, outbox, or legacy-runtime import.
- [x] Run schema/repository tests GREEN, then re-run the legacy memory tests to
  prove migrations 1–3 and their callers remain readable.

### Slice 3 — Conservative legacy migration

- [x] Create fixture databases for unique target, missing target, duplicate
  allowed target, strict and prose birth dates, preferences, `edad`, `ninguno`,
  unsupported predicate, temporal relation, and a superseded fact.
- [x] Write RED migration tests: each active candidate has exactly one ledger
  row; superseded rows stay untouched and receive no candidate ledger row;
  source rows/IDs never change; running `--dry-run` writes nothing; a second
  apply is idempotent.
- [x] Implement folded canonical-name/alias matching that migrates a relation
  only when exactly one allowed target entity resolves. Do not create entities,
  choose first matches, call an LLM, or upload data.
- [x] Add the local command with dry-run default and explicit `--apply`; it must
  log aggregate counts only and never print facts, prompts, biometrics, or raw
  household data.
- [x] Run migration tests GREEN and retain ledger reason assertions for every
  deferred/rejected fixture.

### Slice 4 — Compatibility, rollback, and handoff

- [x] Verify existing legacy retrieval remains the only runtime path: no change
  to `build_context`, `entities_for_relations`, consolidation, controller, or
  `/chat`; no v4 data reaches a prompt.
- [x] Prove logical rollback by not invoking the local migration command and by
  retaining all legacy rows after an applied fixture migration. Dropping v4
  tables, forced reverse migration, dual write, or runtime feature flags are
  out of scope.
- [x] Run focused v4 and legacy memory suites, then `just lint`, `just
  typecheck`, `just test`, `just audit`, `just check`, and `git diff --check`.
- [x] Record exact RED/GREEN, schema version, migration test output, and limits.
  Promote no P0.5 plan; prepare a separate policy-gated runtime-cutover plan
  only after household authorization is complete.

## TDD execution protocol

Every slice uses the approved execution runbook and records an observed RED
before its smallest GREEN implementation. The implementation may run inline or
with bounded development delegation, but this does not change Iroko's
production architecture. Every task must:

1. write the focused test first;
2. record an observed RED failure;
3. implement the smallest scoped behavior;
4. record focused GREEN;
5. perform a diff/type/privacy review; and
6. preserve unrelated work and never commit directly to `main`.

Development coordination is not a production multi-agent architecture.

## Stop conditions

Stop and write a new decision/ADR rather than widening Plan 0005 if any task
needs a new global identifier strategy, a graph database, destructive migration,
automatic ambiguity resolution, automatic confirmation, a public data/role API,
cloud processing, biometric processing, action control, world-state storage, or
a changed audio/server-robot contract.

## Readiness evidence

- [x] Plan 0002 is Complete with recorded gates.
- [x] Plan 0003 is Complete; its actual `/chat` seam was re-read.
- [x] Plan 0004 remains accepted after current-tree review.
- [x] P0.5 order is confirmed: no protected v4 read/write is connected before
  deterministic authorization; therefore runtime cutover is excluded here.
- [x] Migration version 4, files, fixture categories, explicit local rollback
  behavior, and focused commands are frozen above.
- [x] The companion execution runbook provides per-task ownership, RED/GREEN
  commands, and final gates.

## Implementation evidence

- RED was observed for each missing module: predicate registry, v4 repository,
  and legacy migration service.
- Migration 4 creates only the additive v4 tables and indexes. Focused tests
  prove schema version 4, foreign-key integrity, cardinality, temporal history,
  symmetric partner deduplication, rollback on duplicate literals, dry-run,
  deterministic migration outcomes, ledger idempotence, and unchanged legacy
  rows.
- Focused v4 plus legacy suites passed 37 tests. Final `just gate` passed with
  527 tests, Ruff, formatting, mypy, Pyright, security checks, and `pip-audit`.
- No v4 reader/writer was connected to `build_context`, a prompt, `/chat`, or
  `/transcribe`. The real local household database migration was not run; the
  CLI default remains dry-run and requires explicit `--apply`.
