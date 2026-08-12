# Plan 0005 — Relational memory v4 foundation: execution runbook

**Status:** Ready — companion to canonical
[Plan 0005](0005-relational-memory-v4-implementation.md), revalidated on
2026-08-12 at `d136f5f` on `main`.

> **For implementation workers:** execute tasks sequentially, use the
> checkbox steps as the source of truth, and record an observed RED before
> writing production code. This runbook authorizes only P0.4 storage and local
> migration work; it does not authorize P0.5 access policy or runtime cutover.

## Goal

Create a local, additive SQLite v4 relation/fact foundation with a closed
predicate registry and an explicit, dry-run-first legacy migration command,
while preserving the entire v3 runtime path unchanged.

## Architecture

The existing `facts` table remains the live compatibility store. Migration 4
only creates empty v4 tables. Pure registry code classifies known predicates;
v4 repositories own transactional writes; a local command migrates only
deterministic legacy facts into the additive tables and ledger. No router,
prompt, controller, consolidator, or legacy retrieval module reads v4 yet.

## Tech stack and invariants

- Python 3.12, `aiosqlite`, SQLite, and the existing root `uv` workspace only;
  no dependency or environment variable is added.
- IDs remain SQLite integers. UUIDs remain only for cognitive envelopes and
  evidence.
- Migration version is exactly 4. It adds tables/indexes only; it never updates
  or deletes legacy `facts` rows.
- The local migration command defaults to dry-run. `--apply` is required to
  write v4 rows or ledger entries, and it logs counts but never raw household
  values.
- P0.5 authorization owns runtime v4 retrieval/writes. This plan must not
  modify `context.py`, `relations.py`, `consolidation.py`, `text_turn.py`,
  `controller.py`, routers, audio, robot code, or public schemas.
- `unknown`, `ambiguous`, and unsupported values are migration outcomes, not
  opportunities for LLM normalization or entity creation.

---

### Task 1: Closed predicate registry

**Files:**

- Create: `server/src/server/memory/predicate_registry.py`
- Create: `tests/unit/test_predicate_registry.py`

**Produces:**

```python
class PredicateKind(StrEnum): ...


class PredicateCardinality(StrEnum): ...


class PredicateDefinition(BaseModel): ...


def resolve_predicate(alias: str) -> PredicateDefinition | None: ...
def normalize_literal(definition: PredicateDefinition, value: str) -> str | None: ...
```

The registry owns exactly the initial canonical IDs in Plan 0005. `edad` and
unsupported names return `None`; no fallback or dynamic registration exists.

- [ ] Write RED tests for the following executable expectations:

  ```python
  assert resolve_predicate("fecha_nacimiento").canonical_id == "birth_date"
  assert normalize_literal(birth_date, "2017-12-29") == "2017-12-29"
  assert normalize_literal(birth_date, "29 de diciembre de 2017") is None
  assert resolve_predicate("edad") is None
  assert resolve_predicate("le_gusta").cardinality is PredicateCardinality.MULTI_VALUE
  assert resolve_predicate("hijo_de").inverse_query_id == "parent_of"
  ```

- [ ] Run `uv run pytest tests/unit/test_predicate_registry.py -v` and record
  the missing-module RED.
- [ ] Implement immutable, pure definitions, alias normalization, and strict
  ISO validation; do not import `server.db`, `settings`, an LLM, or a router.
- [ ] Re-run the focused test GREEN, then run:

  ```powershell
  uv run ruff check server/src/server/memory/predicate_registry.py tests/unit/test_predicate_registry.py
  uv run mypy server/src/server/memory/predicate_registry.py
  ```

- [ ] Commit only Task 1 files with
  `feat(memory): add v4 predicate registry`.

### Task 2: Additive version-4 schema and repositories

**Files:**

- Modify: `server/src/server/db.py`
- Create: `server/src/server/memory/migration_004_relational_v4.sql`
- Create: `server/src/server/memory/relational_v4.py`
- Create: `tests/integration/test_memory_v4_schema.py`
- Create: `tests/integration/test_memory_v4_repository.py`

**Consumes:** `PredicateDefinition` from Task 1 and the existing opened SQLite
connection from `server.db.get_conn()`.

**Produces:** repository methods that accept only a resolved
`PredicateDefinition`, integer entity IDs, canonical literals, and explicit
metadata. They return typed v4 rows; they do not call the legacy outbox or any
runtime context builder.

- [ ] Write RED schema tests against a fresh temporary database. Assert:

  ```python
  assert user_version == 4
  assert {"literal_facts_v4", "entity_relations_v4", "legacy_fact_migration_v4"} <= tables
  assert await foreign_key_violations() == []
  assert await legacy_facts_count() == legacy_count_before
  ```

- [ ] Write RED repository tests proving a second `likes` value remains active,
  a second `birth_date` supersedes the first, an invalid self-relation is
  rejected, and mirrored `partner_of` pairs yield one canonical active record.
- [ ] Run the two new suites and record RED before adding SQL or repository code.
- [ ] Register `(4, "migration_004_relational_v4.sql")` in
  `server.db._MIGRATIONS`. The SQL may contain only `CREATE TABLE IF NOT EXISTS`
  and `CREATE INDEX IF NOT EXISTS` statements for v4 records; no legacy DML,
  trigger, or automatic backfill is permitted.
- [ ] Implement repository transactions with a rollback on error. Enforce
  cardinality from the registry, not from a free-form request predicate. Keep
  multi-value siblings active and canonicalize `partner_of` by ordered IDs.
- [ ] Run GREEN:

  ```powershell
  uv run pytest tests/integration/test_memory_v4_schema.py tests/integration/test_memory_v4_repository.py -v
  uv run pytest tests/integration/test_memory_integration.py tests/integration/test_memory_relational.py -v
  ```

- [ ] Commit Task 2 files with `feat(memory): add additive v4 storage`.

### Task 3: Conservative legacy migration and local command

**Files:**

- Create: `server/src/server/memory/legacy_v4_migration.py`
- Create: `scripts/migrate_memory_v4.py`
- Create: `tests/integration/test_memory_v4_migration.py`

**Consumes:** Task 1 registry and Task 2 repositories/schema.

**Produces:**

```python
class MigrationCounts(BaseModel): ...


async def migrate_active_legacy_facts(*, apply: bool) -> MigrationCounts: ...
```

`apply=False` performs classification without writes. `apply=True` atomically
creates only deterministic v4 rows and their ledger entries. The command opens
the configured local DB, runs existing schema migrations, invokes this function
with `--apply` only when explicitly requested, and logs aggregate counts.

- [ ] Build fixture data for all exact cases: unique person target, no target,
  two allowed matching targets, strict ISO birth date, prose date, two
  preferences, `edad`, `ninguno`, unsupported predicate, unique `vive_en` place,
  and a superseded legacy fact.
- [ ] Write RED assertions:

  ```python
  assert dry_run.ledger_rows_written == 0
  assert legacy_rows_after == legacy_rows_before
  assert outcome_for("prose birth date") == "deferred"
  assert outcome_for("edad") == "rejected"
  assert outcome_for("ambiguous target") == "deferred"
  assert no_ledger_row_exists_for(superseded_fact_id)
  assert await migrate_active_legacy_facts(apply=True) == await migrate_active_legacy_facts(
      apply=True
  )
  ```

- [ ] Run the migration test RED. Do not create an entity, call a model, parse
  a prose date, select a first target, or invoke a script against a real family
  database while RED.
- [ ] Implement exact canonical/alias folding. A relation is migrated only if
  one allowed target resolves; all other cases must receive a stable deferred or
  rejected ledger reason. Preserve the original `facts.id`, `object_value`, and
  lifecycle fields.
- [ ] Implement the CLI defaulting to dry-run and requiring `--apply`. Ensure
  its logger emits only aggregate `migrated/deferred/rejected` counts.
- [ ] Run GREEN:

  ```powershell
  uv run pytest tests/integration/test_memory_v4_migration.py -v
  uv run pytest tests/integration/test_memory_v4_schema.py tests/integration/test_memory_v4_repository.py -v
  ```

- [ ] Commit Task 3 files with `feat(memory): add audited v4 legacy migration`.

### Task 4: Scope review, final gates, and documentation

**Files:**

- Modify: `docs/architecture/current-state.md`
- Modify: `docs/roadmap/cognitive-roadmap.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/0005-relational-memory-v4-implementation.md`
- Modify: this runbook

- [ ] Review the diff and prove no runtime file from the exclusion list changed.
  Confirm no v4 data can enter `build_context`, a prompt, `/chat`, or
  `/transcribe`.
- [ ] Run the complete final sequence:

  ```powershell
  just lint
  just typecheck
  just test
  just audit
  just check
  git diff --check
  ```

- [ ] Record exact RED/GREEN evidence, migration version, fixture outcomes, and
  verification limitations. Do not mark P0.5 Ready or Complete.
- [ ] Commit documentation only with `docs(cognition): record P0.4 foundation`.

## Stop conditions

Stop and request a new ADR or plan if implementation needs a new global ID
strategy, schema rewrite/destructive migration, ORM, graph database, automatic
ambiguous resolution, runtime use of v4, public/admin API, cloud, biometric
processing, environment variable, or any audio/server-robot contract change.

## Completion boundary

Plan 0005 is complete only when additive v4 schema/repository/migration tests
and repository gates pass. It intentionally leaves the production reader and
writer on v3. P0.5 must provide authorization before a later plan enables
policy-gated v4 retrieval, family tools, or consolidation writes.
