# 0065 — CM-3b, tranche A: the channel-neutral writer core

> **Status:** `Ready` and `NOW` — promoted by Pipec on 2026-10-22, **not rehearsed** in a scratch copy
> (Pipec's choice). Written 2026-10-16 from the CM-3b audit of the same day and from
> [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md) (`Proposed`; it becomes
> `Accepted` when this plan closes, Task 8); **rewritten the same day after an independent review** that
> found six blockers (see *Review record*). Pipec confirmed on 2026-10-16 (by taking the
> recommendations) the three decisions ADR 0022 marked *Pipec to confirm* (migration 010 for the
> asserter and channel, the personal provenance scenario, the homonym rule). **Revalidated against
> `main` on 2026-10-21** and **amended on 2026-10-22** after a review of the Phase 0 draft Pipec
> brought (see *Revalidation record*): two additions, the meaning of «child» and one atomicity test.
> The tasks below are specifications (files, rules, tests to write first), not rehearsed diffs; to be
> executed in a **new session**. It does not require Plan 0064.

> **For agentic workers:** if the status above does not say `Ready`, stop (ADR 0022 records that
> its three open decisions were confirmed on 2026-10-16). REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. **Pipec's rules win over the skills:** one plain
> branch from `main`, never a git worktree, subagents only if Pipec asks, this plan lives under
> `docs/plans/`. One commit per task, every code test observed RED for the stated reason first (the
> text-only Task 8 has none). If evidence contradicts the plan, stop and report instead of
> redesigning. The Bash tool of this environment loses backslashes and non-ASCII characters in
> heredocs: use the Write and Edit tools. Run the suite with `MEMORY_ENABLED=false` (CI does). A test
> that builds data at a fixed date must pin the clock too (Plan 0063 shipped a test that broke the
> next day); tests of validity use fixed ISO dates and never compare against the real clock.

**Goal:** Before Step 0 exists, the memory layer has **one writer that any channel can call**: the
spoken confirmation of Plan 0063 and the initial import of Step 0 produce the same stored fact with
the same classification, assigned by the writer and never by the speaker, and recorded with who
asserted it and through which channel; a relation can carry a visibility, a sensitivity, a confirmer
and a validity range; a third party whose name already exists is never created twice; the household
has its own pair of capabilities (policy only, as Plan 0060 did for the personal ones); and the
registry knows `species`, `stated_age`, the disclosure predicate and the first SECURITY predicate,
with the repository refusing to store a SECURITY value until Step 0 decides storage at rest.
Nothing new is spoken, no route changes, the robot is untouched.

**Architecture:** (1) Registry entries, a new integer literal format and the repository's refusal of
`security` values. (2) One additive migration (010): `asserted_by_entity_id` and `channel` on both V4
tables. (3) `assert_entity_relation` gains the arguments `assert_literal_fact` already has, plus
validity and the two new columns. (4) A strict third-party creation in `memory/declarative.py`
(the module that owns `entities`). (5) Two new `AuthorizationAction` members and a closed
`subject_relation` on the request, with matrix tests and no consumer (policy only). (6)
`memory/canonical_writer.py`: `write_literal` and `write_relation` over `(subject, predicate,
object, owner, channel)` with the classification table, the invariants and the validity rule;
`memory_writer.promote` becomes its first caller. (7) Benchmark dataset v3 and an honest driver.

**Tech Stack:** Python 3.12, aiosqlite, pydantic, pytest. No new dependency. **One migration (010).**

**Spec:** [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md) (all of it),
[ADR 0019](../../adr/0019-personal-memory-capabilities.md) §2, §3 and §6,
[ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decisions 5 to 8 and 13,
`docs/architecture/longitudinal-conversational-memory-evaluation.md` (the frozen gates).

## Task overview

| # | Task | Closes (ADR 0022) |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | The registry: `species`, `stated_age`, `private_topic`, `access_code`; the repository refuses `security` | 6, 8, 9 |
| 2 | Migration 010: who asserted a fact and through which channel | 2 |
| 3 | A relation carries a classification, a confirmer and a validity | 2, 6 |
| 4 | A third party is never created twice | 7 |
| 5 | The household pair of capabilities (policy only) | 3, 4 |
| 6a | The canonical writer: literals, classification, invariants | 2, 4, 5, 9 |
| 6b | The canonical writer: relations and validity | 2, 6 |
| 6c | `promote` becomes the first caller | 2 |
| 7a | Dataset v3: schema, version, frozen v2 | 5 |
| 7b | Dataset v3: scenarios and an honest driver | 5, 9 |
| 8 | Documentation truth | the docs this plan makes stale |

## Review Focus

Inputs the plan's tests could miss and a reviewer should check by hand: (1) a conversation fact and
an import fact of the same subject end with identical visibility and sensitivity; (2) the household
reader still returns the facts the new writer stores (they must equal the registry defaults); (3)
`promote` writes the same rows as before, including `confidence 1.0`, the `asserted_at` of the
turn and the audit order; (4) a homonym never creates a second entity and never merges silently;
(5) a `security` value leaves no trace (row, log, exception message); (6) the personal stage of the
benchmark still has a provenance denominator; (7) `Joaquín` and `Joaquin` collide; (8) several writes made inside one caller-owned transaction, one
of them refused, leaves nothing once the caller rolls back; (9) a child of the owner who is an adult
is **not** treated specially here (see D-2): the writer cannot tell, and Step 0 decides.

## Global Constraints

- No real household data anywhere: invented canaries (`scripts/check_reserved_terms.py`); the
  example ages in tests are invented numbers.
- The firewall (face and voice of the same person on the turn's clip, never a token), the no-oracle
  rule, audit-before-effect and "a value never reaches a log, `llm_response` or the history" are
  unchanged and keep their tests.
- `memory_writer.promote` keeps its behaviour byte for byte. The Plan 0062 and 0063 tests stay green
  after Task 6c **with exactly two edits, declared here**: the two tests of
  `tests/integration/test_memory_writer.py` that monkeypatch `memory_writer.assert_literal_fact` and
  `memory_writer.get_active_literal_facts` (about lines 563 to 617) patch the same names on
  `canonical_writer` instead. Nothing else in those test files changes.
- The writer assigns the classification; a caller cannot pass one.
- `db.transaction()` is not reentrant; `manage_transaction` is the join mechanism.
- Type hints, Google docstrings, `ruff` clean over explicit paths (including `scripts/`),
  `mypy server/src robot/src` clean, no `print()`, commit titles at most 72 characters.

## Decisions

1. **D-1 — Predicate names.** `species` (literal, single current, subject a pet, text);
   `stated_age` (literal, single current, subject a person or a pet, new `LiteralFormat.INTEGER`: a
   whole number from 0 to 130, digits only, no leading zero except `"0"`; default sensitivity
   `child_data` for any subject so that the household reader, which requires the stored sensitivity to
   equal the default, can see it; its row's `asserted_at` is its as-of date); `private_topic`
   (literal, multi-value, subject a person, `personal`/`normal`); `access_code` (literal, single
   current, subject a person, `personal`/`security`). Spanish aliases: `especie`, `edad_dicha`,
   `tema_privado`. **`access_code` has no alias.**
2. **D-2 — Classification table of the writer.** Relations of membership (`child_of`, `partner_of`,
   `pet_of`) are `household` with the registry sensitivity. A literal whose subject is the **owner** is
   `personal` with the registry sensitivity, except the owner's `birth_date`, which is
   `personal`/`private`. A literal whose subject is a **child** or a **pet** of the owner is
   `household` with the registry sensitivity. A literal whose subject is the **partner**, or anyone
   outside the closed set, is refused with the closed reason `not_household_member`. **«Child» means a
child the owner is guardian of** (ADR 0022 decision 3). The writer cannot tell a minor from an adult
child (no age is required to write `child_of`), so it classifies both the same way; how an **adult**
child is treated (for example an owner who lives alone and whose children are grown: ADR 0022 decision
4 says other adults are name and relationship only) is the open gap the ADR already names, and the
Step 0 ADR decides it. Nothing here pretends to solve it. How the writer
   knows the role: the owner is the `owner_entity_id` argument; membership is read through
   `get_active_role` and the owner's active `child_of`/`partner_of`/`pet_of` relations, so
   `canonical_writer.py` joins `_MAY_IMPORT_RAW_V4_READERS` in the architecture guard.
3. **D-3 — The household pair** is `PROPOSE_HOUSEHOLD_MEMORY` and `CONFIRM_HOUSEHOLD_MEMORY`
   (owner only, `household` visibility, `strong`, no PIN route, consent not applied for
   `normal`/`child_data`). `AuthorizationRequest` gains `subject_relation: HouseholdSubject | None =
   None` (closed: `owner`, `child`, `partner`, `pet`), **classified by the caller before any read**;
   the pair allows `child` and `pet` for literals and `child`, `partner` and `pet` for relations. No
   code consumes the pair in this plan (as Plan 0060): its guard homes are `cognition/models.py` and
   `cognition/authorization.py`.
4. **D-4 — Homonyms.** `create_third_party` raises `AmbiguousEntityError` when an entity of that
   folded name and type already exists, with or without a key; the import key is stored in
   `attributes["import_key"]`, so the same key returns the same entity (idempotent re-run). Two
   homonymous third parties are impossible until the Step 0 ADR decides a migration.
5. **D-5 — Validity** as ADR 0022 decision 6: only `temporal` predicates close the previous row, at
   the new `valid_from`; an explicit `valid_to` inserts a row with lifecycle `expired` that never
   runs the supersede and may have no `valid_from`; dates are `YYYY-MM-DD` (or `YYYY-MM`).
6. **D-6 — Channels** are a closed `StrEnum` `WriteChannel`: `voice_classic`, `voice_stream` (the two
   values a candidate already carries) and `import_file`. A perceptual channel is not added (it
   would be code for a later phase).
7. **D-7 — Dataset v3** keeps the extraction scenarios' legacy vocabulary (the extractor under test
   still emits it); it changes the version, the frozen v2 copy, the personal provenance scenario, the
   `confirm` operation as an honestly unsupported one, and a pending SECURITY scenario. Gates do not
   move.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/`.
- [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md), ADR 0019, ADR 0021.
- `server/src/server/memory/relational_v4.py`, `predicate_registry.py`, `memory_writer.py`,
  `candidates.py`, `declarative.py`, `schema.sql`, `migration_004_relational_v4.sql`,
  `migration_009_memory_candidates.sql`, `policy_gated_v4_reader.py`, `household_authorization.py`;
  `server/src/server/db.py` (the `_MIGRATIONS` list); `server/src/server/cognition/{authorization,models}.py`;
  `server/src/server/personal_setup.py`, `server/src/server/memory/legacy_v4_migration.py`;
  `tests/unit/test_architecture_guards.py`; `tests/evals/golden_longitudinal_memory.yaml`;
  `scripts/{longitudinal_eval_driver,eval_longitudinal_memory,longitudinal_eval_models,longitudinal_eval_metadata,longitudinal_eval_aggregation,eval_consolidation}.py`;
  `tests/unit/test_longitudinal_staged_verdicts.py`.

## Permitted files

- Production: `server/src/server/memory/{predicate_registry,relational_v4,memory_writer,declarative}.py`,
  new `server/src/server/memory/canonical_writer.py`, new `server/src/server/memory/migration_010_*.sql`,
  `server/src/server/{db,exceptions}.py`, `server/src/server/cognition/{authorization,models}.py`.
- Scripts and data: `tests/evals/golden_longitudinal_memory.yaml` (and a frozen
  `tests/evals/golden_longitudinal_memory_v2.yaml`),
  `scripts/{longitudinal_eval_driver,eval_longitudinal_memory,longitudinal_eval_models,longitudinal_eval_metadata}.py`.
- Tests: the files named in each task and their new files.
- Docs (Task 8): the list there.

No new URL, route, status code, response field or setting. `robot/src`, `/chat`, `/vision/respond`,
the household reader's contract, `personal_setup`, the legacy migration and the spoken dialogue are
not edited.

---

## Task 0: Revalidate the baseline

- [ ] **Step 0:** this plan says `Ready` and ADR 0022's status line records that its three open
  decisions were confirmed by Pipec on 2026-10-16. Otherwise stop.
- [ ] **Step 0b:** the Plan 0063 code and the documents of this plan are in `main`
  (`git fetch && git merge-base --is-ancestor <0063 squash commit> origin/main`). Otherwise stop.
- [ ] **Step 1:** `git checkout main && git pull`, clean tree, `git checkout -b feat/0065-cm3b-a-writer-core`.
- [ ] **Step 2:** `just gate`; record the outcome and count (3807 after Plan 0069, if nothing else
  merged first; otherwise the count of `main` at that moment).
- [ ] **Step 3: Re-audit** (each must find what the plan names): `rg -n "def assert_entity_relation"
  server/src`, `rg -n "def promote" server/src`, `rg -n "PredicateDefinition\(" server/src/server/memory/predicate_registry.py`,
  `rg -n "class AuthorizationAction" server/src`, `rg -n "_MIGRATIONS" server/src/server/db.py`,
  `rg -n "version" scripts/eval_longitudinal_memory.py scripts/longitudinal_eval_models.py scripts/longitudinal_eval_metadata.py`.
  Expected: every command prints at least one line. A difference is reported before code.

## Task 1: The registry and the repository's refusal of `security`

**Files:** `server/src/server/memory/{predicate_registry,relational_v4}.py`; tests
`tests/unit/test_predicate_registry.py`, `tests/integration/test_memory_v4_repository.py`.

- [ ] **Step 1: Failing tests.** `resolve_predicate("species")` is a single-current text literal whose
  subject type is the pet type only; `resolve_predicate("stated_age")` is a single-current
  `INTEGER` literal on a person or a pet that accepts `"7"` and `"0"` and rejects `"ocho"`, `"-1"`,
  `"131"`, `"07"`, `"7 años"` and `"²"`; `resolve_predicate("private_topic")` is a multi-value literal on
  a person, default visibility `personal`; `resolve_predicate("access_code")` is a single-current
  literal on a person with default visibility `personal` and sensitivity `security`; the aliases
  `especie`, `edad_dicha` and `tema_privado` resolve and `codigo_acceso` does **not**; a pet is
  rejected as the subject of `private_topic` and `access_code`. In the repository tests:
  `assert_literal_fact` with the `access_code` definition raises a closed error
  (`SecurityStorageUndecided`) and writes **nothing**, and the error message, the log records and
  their `extra` contain no part of the value. Expected RED: `resolve_predicate(...)` returns `None`;
  the repository stores the value.
- [ ] **Step 2: Implement** the four definitions; add `LiteralFormat.INTEGER` with its normalizer
  (`re.fullmatch(r"(0|[1-9][0-9]{0,2})", value)`, then `0 <= n <= 130`; never `str.isdigit`, which
  accepts Unicode digits); add the refusal to `assert_literal_fact` and `assert_entity_relation`
  when `definition.default_sensitivity == "security"`, before any write and before any log, with a
  closed exception defined in `server/exceptions.py`.
- [ ] **Step 3:** run `tests/unit/test_predicate_registry.py tests/integration/test_memory_v4_repository.py
  tests/unit/test_architecture_guards.py` (a guard may list the registry's predicates); lint and types.
- [ ] **Step 4: Commit** `feat(server): register species, stated age, topics and access code (plan 0065)`.

## Task 2: Who asserted a fact and through which channel (migration 010)

**Files:** new `server/src/server/memory/migration_010_asserter_and_channel.sql`,
`server/src/server/db.py`, `server/src/server/memory/relational_v4.py`; tests
`tests/integration/test_memory_v4_schema.py`, `tests/integration/test_memory_v4_migration.py`.

- [ ] **Step 1: Failing tests.** After `run_migrations`, `literal_facts_v4` and `entity_relations_v4`
  have the columns `asserted_by_entity_id` (nullable, references `entities`, `ON DELETE SET NULL`)
  and `channel` (nullable text); an existing row is untouched and reads `None` in both; the
  migration list ends at version 10 and a database at version 9 upgrades in place without losing
  rows; `LiteralFactV4` and `EntityRelationV4` expose both fields with default `None`. Update every
  test that pins "version 9" (`rg -n "migration_009|_MIGRATIONS|Schema up-to-date" tests server/src`).
  Expected RED: `no such column` / the list ends at 9.
- [ ] **Step 2: Implement** the migration (`ALTER TABLE … ADD COLUMN …`, two per table; no table
  rebuild) and register it in `db._MIGRATIONS`; add the two optional fields with defaults to both
  models. **If Pipec chose the alternative of ADR 0022 decision 2 (store neither), this task is
  replaced by a test that the writer logs the channel as a closed value and checks the asserter at
  write time; stop and ask.**
- [ ] **Step 3:** run the schema, migration, repository and reader tests; lint and types.
  **Step 4: Commit** `feat(server): record who asserted a v4 fact and through which channel (plan 0065)`.

## Task 3: A relation carries a classification, a confirmer and a validity

**Files:** `server/src/server/memory/relational_v4.py`; tests new
`tests/integration/test_memory_v4_relation_classification.py` and the existing
`test_memory_v4_repository.py`, `tests/unit/test_policy_gated_v4_reader.py`,
`tests/unit/test_household_knowledge_tools.py` (they construct `EntityRelationV4` directly: the new
fields must have defaults).

- [ ] **Step 1: Failing tests** (temporary SQLite): `assert_entity_relation` accepts `visibility`,
  `sensitivity`, `confirmed_by_entity_id`, `confirmed_at`, `valid_from`, `valid_to`,
  `asserted_by_entity_id` and `channel`, stores them and returns them; with no argument the stored
  values are the registry's defaults (today's behaviour); for a `temporal` predicate (`lives_in`,
  `works_at`; no relation predicate is `single_current`) the previous active row is closed with
  `valid_to` equal to the **new row's `valid_from`**, not `now`; a row given an explicit `valid_to`
  is inserted with lifecycle `expired`, never runs the supersede, may have `valid_from` NULL and does
  not collide with the active-triple unique index; an exact repeat returns the existing active row
  **without** updating its confirmer or classification (documented: a `child_of` created by
  `setup-personal` keeps no confirmer). Fixed ISO dates only; no comparison against the real clock.
  Expected RED: `TypeError: assert_entity_relation() got an unexpected keyword argument`.
- [ ] **Step 2: Implement** by mirroring `assert_literal_fact` (same argument names and defaults);
  the supersede statement uses the new row's `valid_from` when given.
- [ ] **Step 3:** run `tests/integration/test_memory_v4_*.py tests/integration/test_p05b2_household_acceptance.py
  tests/unit/test_policy_gated_v4_reader.py tests/unit/test_household_knowledge_tools.py` and everything
  that imports `EntityRelationV4`; lint and types. **Step 4: Commit**
  `feat(server): classify, confirm and date a v4 relation (plan 0065)`.

## Task 4: A third party is never created twice

**Files:** `server/src/server/memory/declarative.py` (the module that owns `entities`),
`server/src/server/exceptions.py`; test new `tests/integration/test_third_parties.py`.

- [ ] **Step 1: Failing tests:** `create_third_party(name="Canary Child", type="person",
  import_key="c1")` returns a new entity id and stores the key in `attributes["import_key"]`; the same
  key again returns the **same** id; the same folded name and type with another key, or with none,
  raises `AmbiguousEntityError`; `Joaquín` after `Joaquin` (and the reverse) raises it too; a pet is
  typed `other`; `upsert_entity` is unchanged (`personal_setup` keeps using it). Expected RED:
  `ImportError: cannot import name 'create_third_party'`.
- [ ] **Step 2: Implement** with a folded-name `SELECT` before the `INSERT` (the table's own
  `UNIQUE(name, type)` stays the last line of defence); no second module issues SQL on `entities`.
- [ ] **Step 3:** guards, lint, types. **Step 4: Commit**
  `feat(server): create third parties without merging by name (plan 0065)`.

## Task 5: The household pair of capabilities (policy only)

**Files:** `server/src/server/cognition/{models,authorization}.py`; tests new
`tests/unit/test_authorization_household_memory.py` and the closed-list tests named in Step 2.

- [ ] **Step 1: Failing matrix tests:** `PROPOSE_HOUSEHOLD_MEMORY` and `CONFIRM_HOUSEHOLD_MEMORY` are
  allowed for the owner at `strong` (face and voice) on a `household` fact whose `subject_relation`
  is `child` or `pet` (literals) or `child`, `partner` or `pet` (relations); denied for: the owner at
  `basic`, an actor holding only a token, a visitor, another adult, a minor, a `partner` literal, an
  `owner` subject, a `personal` visibility and `subject_relation=None`; the five personal
  capabilities give the **same decisions** as before; no PIN route; consent not applied for
  `normal`/`child_data`. Expected RED: `AttributeError: … has no attribute PROPOSE_HOUSEHOLD_MEMORY`.
- [ ] **Step 2: Implement** the two members, `HouseholdSubject` and the request field next to the
  personal ones. The closed lists that enumerate the actions change (they are lists, not
  decisions): update `tests/unit/test_personal_memory_policy.py`, `tests/unit/test_cognitive_models.py`,
  `tests/unit/test_authorization_characterization.py` and `tests/unit/test_architecture_guards.py`.
- [ ] **Step 3: Guard.** In `tests/unit/test_architecture_guards.py` add that only
  `cognition/models.py` and `cognition/authorization.py` name the two new actions (nothing consumes
  them yet; the first consumer is the import of Step 0 or tranche B, which extends the guard).
- [ ] **Step 4:** run the authorization tests and the guards; lint and types. **Step 5: Commit**
  `feat(server): add the household memory capabilities (plan 0065)`.

## Task 6a: The canonical writer, literals

**Files:** new `server/src/server/memory/canonical_writer.py`; tests new
`tests/integration/test_canonical_writer_literals.py`; `tests/unit/test_architecture_guards.py`.

**Interface (specification).** `WriteChannel` (`StrEnum`: `voice_classic`, `voice_stream`,
`import_file`); `async write_literal(*, owner_entity_id, subject_entity_id, predicate, value,
channel, confirmed_at, confidence=0.9, asserted_at=None, valid_from=None, valid_to=None,
manage_transaction=True) -> LiteralFactV4`. The asserter and the confirmer are the owner (ADR 0022
decision 0). There is no `visibility`, `sensitivity` or `asserter` parameter: the writer looks the
classification up in D-2.

- [ ] **Step 1: Failing tests:** the same fact written through `voice_stream` and `import_file` has
  identical visibility and sensitivity; the owner's `likes` is `personal`/`normal`; the owner's
  `birth_date` is `personal`/`private`; a child's `birth_date` and `stated_age` are
  `household`/`child_data`; a pet's `species` is `household`/`normal`; a literal on the **partner**
  or on a subject outside the household is refused with `not_household_member` and nothing is
  written; a `personal` fact whose subject is not the owner cannot be requested (the invariant of
  ADR 0022 decision 5 has a test that tries); a `security` predicate is refused by the repository
  (Task 1) and the writer lets the closed error through without logging the value; the stored row
  has `asserted_by_entity_id` = the owner and the channel; an exact repeat is idempotent; **the
  household reader still returns the child's and the pet's facts** (the stored classification equals
  the registry defaults). Expected RED: `ModuleNotFoundError`.
- [ ] **Step 2: Implement.** Keep the classification table in one place. Add `memory/canonical_writer.py`
  to `_MAY_IMPORT_RAW_V4_READERS` and to the writer homes of the V4 guards; add a guard that only
  `canonical_writer.py`, `personal_setup.py` and `legacy_v4_migration.py` call the repository's
  `assert_*` functions (the two older callers are the documented exceptions of ADR 0022 decision 2).
- [ ] **Step 3:** lint and types. **Step 4: Commit**
  `feat(server): add the canonical writer for literals (plan 0065)`.

## Task 6b: The canonical writer, relations and validity

**Files:** `server/src/server/memory/canonical_writer.py`; tests new
`tests/integration/test_canonical_writer_relations.py`.

**Interface.** `async write_relation(*, owner_entity_id, source_entity_id, predicate,
target_entity_id, channel, confirmed_at, confidence=0.9, asserted_at=None, valid_from=None,
valid_to=None, manage_transaction=True) -> EntityRelationV4`.

- [ ] **Step 1: Failing tests:** `child_of`, `partner_of` and `pet_of` are `household` with the
  registry sensitivity, from both channels; `lives_in` with a spoken `valid_from` closes the previous
  row at that date; `lives_in` given as past (explicit `valid_to`) is stored as history; a relation
  whose target is a third party created by `create_third_party` is accepted; `partner_of` is
  symmetric, so the owner/partner order of ids does not change the stored classification; asserter
  and channel are stored; **a batch is atomic:** inside one transaction the **caller** owns
  (`manage_transaction=False`), a `write_literal` and a `write_relation` succeed and a third write is
  refused (`not_household_member`); the caller rolls back and no literal row, no relation row and no
  entity row remain, and the refusal logged nothing that contains the value (this is what an importer
  needs for all-or-nothing and for a preview, with no new API). Expected RED: `AttributeError: module … has no attribute write_relation`.
- [ ] **Step 2: Implement.** **Step 3:** lint and types. **Step 4: Commit**
  `feat(server): add relations and validity to the canonical writer (plan 0065)`.

## Task 6c: `promote` becomes the first caller

**Files:** `server/src/server/memory/memory_writer.py`; the two declared test edits in
`tests/integration/test_memory_writer.py`.

- [ ] **Step 1: Failing test first:** a test that `promote` stores the fact through
  `canonical_writer.write_literal` (patch it and see it called with the candidate's channel value),
  while every outcome, audit order, `confidence 1.0` and `asserted_at == iso_utc(now)` stay as
  before (the existing tests pin them). Expected RED: the patch is never called.
- [ ] **Step 2: Implement.** `write_literal` accepts `confidence` and `asserted_at` for exactly this
  reason. `promote` keeps its transaction shape (it joins with `manage_transaction=False`), its audit
  order and its outcomes; it passes the candidate's channel.
- [ ] **Step 3: The two declared edits** (the monkeypatch targets move to `canonical_writer`), then
  run, otherwise **unmodified**, `tests/integration/test_memory_writer*.py
  tests/integration/test_candidate_dialogue.py tests/integration/test_memory_dialogue_routes.py
  tests/integration/test_candidate_proposal.py`; they must be green.
- [ ] **Step 4:** guards, lint and types. **Step 5: Commit**
  `refactor(server): promote through the canonical writer (plan 0065)`.

## Task 7a: Benchmark dataset v3, schema and version

**Files:** `tests/evals/golden_longitudinal_memory.yaml`, new `tests/evals/golden_longitudinal_memory_v2.yaml`,
`scripts/{eval_longitudinal_memory,longitudinal_eval_models,longitudinal_eval_metadata}.py`; tests
`tests/unit/test_longitudinal_staged_verdicts.py` and the dataset tests (`rg -n "golden_longitudinal"
tests`).

- [ ] **Step 1: Read** the spec (the gates are **frozen**: do not relax one) and the Plan 0046 report;
  list in the execution record what each change below does to comparability with the v2 baseline.
- [ ] **Step 2: Failing tests:** the dataset `version` is `3` in the five places it is pinned
  (`eval_longitudinal_memory.py` lines 52 and 108 to 110, `longitudinal_eval_models.py` lines 142 and
  269, `longitudinal_eval_metadata.py` line 66, plus `test_longitudinal_staged_verdicts.py:142`); a
  frozen copy of v2 stays loadable (`Literal[2, 3]`); the metadata reads the suite's version.
  Expected RED: each fails on the old value. **Step 3: Implement. Step 4: Commit**
  `feat(evals): version 3 of the longitudinal dataset, v2 kept (plan 0065)`.

## Task 7b: Benchmark dataset v3, scenarios and an honest driver

**Depends on Tasks 1 and 6a.**

- [ ] **Step 1: Failing tests:** (a) the dataset has a **personal-scope provenance scenario** (the
  owner states a fact; a later recall must name `subject=owner, assertor=owner,
  source=conversation`) and `provenance_attribution` stays `family`;
  `test_every_gate_of_a_stage_is_fed_by_a_scenario_of_that_stage[personal]` and
  `test_the_frozen_dataset_declares_a_scope_for_every_scenario` pass with the new set (update the
  latter's expected version and set); (b) the operation `confirm` exists in the schema and the driver
  reports it **unsupported** with the reason "no public seam drives the canonical writer" (nothing
  runs it, so it is not reported as supported); (c) a SECURITY scenario exists with an **invented**
  access code and is marked pending (the write is refused until Step 0), not failing; (d) the
  driver's `PROPOSE` reason no longer says writes go through the legacy `assert_fact()`. Expected
  RED: each fails on the old value.
- [ ] **Step 2: Implement.** **Step 3:** run the benchmark's unit tests and, with Pipec's Ollama, one
  full offline run to confirm the report still generates (record counts only).
- [ ] **Step 4: Commit** `feat(evals): personal provenance, honest confirm and a pending SECURITY scenario (plan 0065)`.

## Task 8: Documentation truth (text only, no RED)

- [ ] ADR 0022 `Accepted` (the date and what Pipec confirmed); ADR 0019 §2 and ADR 0021 decisions 4,
  5 and 13 (cross-references and the derived-age exception); `docs/architecture/identity-and-access.md`
  (the household pair and `subject_relation`), `memory-and-world-state.md` (writer, validity,
  `stated_age`, `private_topic`, `access_code`, the derived-age row), `current-state.md` and its
  Archify diagram if it mentions the writer (validate, then deliver); `docs/roadmap/cognitive-roadmap.md`
  and `conversational-memory-delivery-map.md` (CM-3b tranche A closed, tranche B after Step 0), the
  plan indexes, the local table (never committed); move this plan to `completed/` with its execution
  record.
- [ ] `uv run ruff format --check .`, `uv run python scripts/check_reserved_terms.py`, every relative
  link resolves; commit `docs: close plan 0065`; PR; merge only with Pipec's go-ahead.

## ADR 0022 coverage

| ADR 0022 | Where |
|---|---|
| 0 the frame (spoken capture is tranche B) | not here; the writer enforces the asserter |
| 2 one writer; asserter and channel recorded | Tasks 2, 6a, 6b, 6c |
| 3 the household pair and `subject_relation` | Task 5 |
| 4 other adults: name and relation only | Task 6a (`not_household_member`) |
| 5 reported facts; personal provenance scenario | Tasks 6a, 7b |
| 6 validity; stated age | Tasks 1, 3, 6b |
| 7 homonyms | Task 4 |
| 8 disclosure predicate (registry only) | Task 1 |
| 9 SECURITY: predicate and refusal | Tasks 1, 7b |

## Completion criteria

1. Tasks 0 to 8 done, one commit per task, every code test RED before GREEN.
2. `just gate` green; the Plan 0062 and 0063 tests unchanged except the two declared edits.
3. The same fact written from two channels has one classification and records its asserter and
   channel; a homonym is never created twice; a `security` value is refused without a trace.
4. The household pair passes its matrix and nothing consumes it.
5. Dataset v3 loads, v2 stays readable, no gate relaxed, the report states the comparability cut.

## Rollback boundary

Each task is one commit. Task 6c needs 6a and 6b; Task 7b needs 1 and 6a; Task 2 adds a migration:
reverting it means a down-step is **not** provided (the added columns are nullable and unused by
older code), so the rollback is to leave them. Facts already written stay.

## Not here, and why

- **Spoken capture of third parties**, **reference resolution («mi hija»)**, **reported facts**,
  **the behaviour of the disclosure rule** and **perceptual candidates**: tranche B, after Step 0.
- **Storing a SECURITY value** and **reading it back**: the Step 0 ADR decides storage at rest;
  reading is CM-5.
- **The initial import itself, the per-channel assurance levels, enrolment as the first setup step,
  the "are you with someone?" escalation and homonymous third parties**: Step 0.
- **A `current_age` helper**: no consumer before CM-5.
- **Adult children, a representative who confirms for the owner, and an interviewer who is not the
  asserter**: the writer fixes the asserter and the confirmer to the owner (ADR 0022 decision 0), the
  safe default; whether a representative or a second adult can assert or confirm, and how an adult
  child is classified, are Step 0 decisions. The nullable asserter column of migration 010 does not
  block either.
- **A SQL `CHECK` on the channel**: the closed list lives in `WriteChannel` and its test, so adding a
  channel later (the perceptual one of P2.1) is not a migration.
- **A public preview or classification API**: the classification table stays in one place so a later
  importer can wrap it; exposing it now would be code with no caller.
- **`correct` and `forget`**: CM-6.

## Revalidation record (2026-10-21)

Made against `main` at `68a348c` (Plan 0069 merged), five days after the plan was written, by reading
the code and the history; nothing was executed or rehearsed in a scratch copy.

- **Files.** Every file the plan names exists, except one path in the *Spec* line, which pointed to
  `docs/evals/longitudinal-conversational-memory-evaluation.md`; the document is
  `docs/architecture/longitudinal-conversational-memory-evaluation.md` (corrected above).
- **What changed since 2026-10-16.** `git log` shows no commit on `relational_v4.py`,
  `predicate_registry.py`, `memory_writer.py`, `declarative.py`, `db.py`, `cognition/authorization.py`,
  `cognition/models.py`, `tests/integration/test_memory_writer.py`,
  `tests/unit/test_architecture_guards.py`, `tests/evals/golden_longitudinal_memory.yaml` or
  `scripts/longitudinal_eval_driver.py`. Only two files it touches moved: `memory/candidates.py`
  (Plans 0066 and 0067: the offer's compare-and-set also refuses a second open offer of the same
  person, and the open offer can be looked up without a value) and `exceptions.py` (Plan 0069 added
  `UnclearSpeechError`). Neither collides with a task: Task 6c leaves `promote` and its callers as they
  are, and `exceptions.py` only gains `AmbiguousEntityError` in Task 4.
- **Anchors that still hold.** `assert_literal_fact` (`relational_v4.py:297`),
  `assert_entity_relation` (`:459`), `get_active_literal_facts` (`:238`), `get_active_role`
  (`household_authorization.py:76`), `AuthorizationAction` (`cognition/models.py:59`, fourteen
  members), `LiteralFormat` with only `TEXT` and `ISO_DATE` (`predicate_registry.py:39`),
  `_MAY_IMPORT_RAW_V4_READERS` (`test_architecture_guards.py:24`), `_MIGRATIONS` ending at version 9 so
  **010 is the next free migration** (`db.py:36`), the channel values `voice_classic` and
  `voice_stream` as `CandidateChannel` (`memory/candidate_types.py:59-60`, also the CHECK of migration
  009), `AuthorizationRequest` (`cognition/authorization.py:77`), and the two tests that
  monkeypatch `memory_writer.assert_literal_fact` and `get_active_literal_facts`
  (`tests/integration/test_memory_writer.py`, lines 582 and 607, inside the "about lines 563 to 617" the
  plan declares).
- **Corrected in this revalidation.** The wrong spec path; the stale line that said the plan waits for
  Plan 0064; the gate baseline of Task 0.
- **Checked afterwards.** The dataset `golden_longitudinal_memory.yaml` is at version 2, which Task 7a
  bumps to 3; no test counts the members of `AuthorizationAction` (a search for `len(` over it finds
  none), so Task 5 adding two does not break a pin.
- **Not checked, left to Task 0.** The matrix tests of the architecture guard that enumerate modules;
  the cost of the third face-and-voice resolution per turn, which the roadmap keeps for the homelab.
  The plan stays `Draft`: it is promoted to `Ready` only by Pipec.

## Amendment record (2026-10-22)

Made before the promotion, from a read of an external Phase 0 draft Pipec brought (untracked; no plan
may require it). Two additions, both text or test-only, none touching the code design: (1) D-2 and the
*Not here* list now say what «child» means and name the adult-child gap, because that draft's model
case is an older adult who lives alone, whose children are adults; (2) Task 6b gained the
atomic-batch test and Review Focus (8) and (9). Looked at and left unchanged: the channel stays
closed in Python only; no preview API; the asserter stays the owner. Everything else in that draft
(the interview record, the answer states, the activation gates, decisions D1 to D12) belongs to Step 0
and is not used here.

## Review record

**Independent review, 2026-10-16** (read-only, against the code): the plan could not start (it
required an ADR `Accepted` that only this plan could make so); the homonym task needed a column that
does not exist; the asserter and the channel had nowhere to be stored; `promote` could not be
refactored with its tests untouched; moving `provenance_attribution` alone made the personal stage
unpassable; the household policy lacked the data to know a subject is the owner's child. Also folded
in: the supersede only applies to `temporal` predicates; `access_code` without an alias and the
repository's refusal (a Spanish alias could have routed a legacy fact into it); the classification
table now covers the reader's equality rule; the closed-list tests that change; the version is
pinned in five places; Tasks 5 and 6 were split; the channel vocabulary matches the candidates'.

## Execution record

*(Filled in when the plan is executed.)*
