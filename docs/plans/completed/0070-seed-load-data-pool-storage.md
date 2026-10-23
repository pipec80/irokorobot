# 0070 — Step 0, first plan: the storage of the data pool and the provenance of an assisted interview

> **Status:** `Closed` on 2026-10-23 (executed on the branch `feat/0070-seed-data-pool-storage`; see the *Execution
> record* at the end). Written 2026-10-22 and rewritten 2026-10-23 after three rounds of independent
> review; **promoted by Pipec on 2026-10-23 with D-1 to D-11 confirmed** (D-1 to D-6 chosen by him, D-7 to D-11
> confirmed as written the same day). Task 0 re-audited it against `main` before any code. It implements the storage half of
> [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) (`Proposed`; it becomes `Accepted`
> when Plans 0071 and 0072 close). The importer is [Plan 0071](../open/0071-seed-load-file-importer.md), which
> cannot start before this plan closes; the session itself is [Plan 0072](../open/0072-commissioning-session.md).
> Written for an executor who has not seen this repository: what it needs is here, in the ADR or in
> [`seed-data-pool.md`](../../architecture/seed-data-pool.md), not in the chat that produced them.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main`, never a git worktree,
> subagents only if Pipec asks, this plan lives under `docs/plans/`. One commit per task; every code
> test observed RED for the stated reason first (Tasks 1 and 8 have none, and say why). If evidence
> contradicts the plan, stop and report instead of redesigning. The Bash tool of this environment
> loses backslashes and non-ASCII characters in heredocs: use the Write and Edit tools. Run the
> suite with `MEMORY_ENABLED=false` (CI does). A test that builds data at a fixed date pins the clock
> too. Never run `uv sync --all-packages --all-groups` (it removes the optional `cuda` extra: use
> `--extra cuda`); commit `uv.lock` before `just gate` if it changed.

**Goal:** the database can hold the whole data pool of the commissioning and say how it got there:
the new predicates of the pool; a table of contacts with phones; a commissioning record with the
status of each section and the places for the acta; a channel for an assisted interview; secrets as
references; an adult child, a relative and a contact that can never be relabeled into a household
member to unlock facts; and a writer that can refuse to overwrite and can record that the owner did
not confirm. Nothing reads any of it by voice, no route changes and the robot is untouched.

**Architecture:** (1) A mechanical rename of the security refusal. (2) Registry: `storable`, reference
and choice formats, `secret_holder`, the pool predicates and the relative relations. (3) A small module
of write types shared by the writer and the contacts. (4) Writer guards for the adult child, the
relatives and the contacts, and a refusal policy. (5) One migration (011): `care_contacts`,
`commissioning_records`, `commissioning_sections`. (6) Two repositories, each the only home of its
tables' SQL.

**Tech Stack:** Python 3.12, aiosqlite, pydantic, pytest. No new dependency. **One migration (011).**
No new setting or environment variable.

**Spec:** [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) decisions 2 and 4 to 10 and 15,
[`seed-data-pool.md`](../../architecture/seed-data-pool.md), [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md)
(*Decision* and *Implementation notes*).

## Decisions

Pipec confirms D-1 to D-11 before promoting; D-1 to D-6 he already chose.

1. **D-1 — Scope.** Storage and provenance only. No file, no command, no enrolment, no read by voice.
2. **D-2 — A secret is stored by reference.** `access_code` is never stored (`storable = False`);
   `secret_holder`, `document_location` and `home_access_note` are references. (Decision 4.)
3. **D-3 — Contacts are a table**, `care_contacts`, written by one function; they are not V4 facts. (Decision 5.)
4. **D-4 — The assisted channel and the commissioning record** carry the provenance. The asserter is the
   owner's entity; the confirmer is the owner's entity unless the mode is `representative`. (Decision 6.)
5. **D-5 — The adult child** is a marker in the entity's attributes that the writer reads. (Decision 9.)
6. **D-6 — The relatives** are `has_parent`, `has_grandparent`, `has_sibling` (symmetric) and
   `has_grandchild`, with `withhold_from`, name and relationship only. (Decision 10.)
7. **D-7 — The names and Spanish aliases** are those of the Task 3 table. *The author's call; Pipec may rename.*
8. **D-8 — Choices are Spanish codes** (the sets are in the Task 3 table); the normalizer folds case and
   accents (`Sí` is stored `si`). *The author's call.*
9. **D-9 — Roles of a contact** are `emergency`, `caregiver`, `doctor`, `key_holder`, `neighbor`, `trusted`,
   `other`. A contact has a phone and an optional second one (`phone_alt`); each is `+` followed by 8 to 15
   digits, the first not `0`; the writer strips spaces, hyphens, dots and parentheses and refuses anything
   else. The call order belongs to the person, one active row per owner, contact and role. *The author's call.*
10. **D-10 — Statuses and sections.** Five statuses (`provided`, `none`, `unknown`, `declined`, `not_asked`)
    and eleven sections: `conditions`, `allergies`, `medications`, `devices`, `contacts`, `withhold`,
    `secrets`, `documents`, `household`, `home`, `function`. *The author's call.*
11. **D-11 — Modalities** (a closed list for the acta): `pin`, `face`, `voice`, and the reserved `fingerprint`,
    `iris`, `token`. Only the first three can be enrolled today. (Decision 15.) *The author's call.*

## Review Focus

The failure modes the tasks' main tests would miss; each line has its test in the task named.

1. A caller states a sensitivity other than `security` for `secret_holder`, or `security` for `likes`:
   refused both ways (Task 2).
2. A relative, a contact or an adult child relabeled a child, a pet or the partner to unlock facts: refused;
   **and the exact repeat of an existing membership relation of a caregiver child is accepted** (Tasks 4a, 6).
3. A symmetric relative relation written from the wrong end; a relative that is already a member (Task 4a).
4. A phone in a local format, with letters, or too short; two active contacts with one call order; one person with
   two roles (caregiver and key holder) and one phone; a contact with a second phone (Task 6).
5. A contact who is the owner, a pet, or not a person (Task 6).
6. A reference with four digits in any script (Task 2); a secret or a phone leaves no trace in a row, a
   log, an error or a `repr` (Tasks 2, 6).
7. A second commissioning record opened while one is open, or after one closed; a status outside the closed
   list; `builder_is_owner` with a role that is not `builder`; a record that carries a household value; an installation id that is
   random, 36 characters and the same across the imports of one record (Task 7).
8. The migration applied twice and on a database at version 10 with data; the older tests that pin
   «version 10» updated; the two partial unique indexes really enforce (Task 5).
9. `confirmed_by` is `NULL` when the owner did not confirm, and the rows are still readable (Task 4b).
10. A raw query on the new tables outside their repository (architecture guard, Tasks 6 and 7).

## Global Constraints

- No real household data anywhere: invented canaries (`scripts/check_reserved_terms.py`), invented
  phones such as `+56900000001`.
- `.claude/rules/` apply: English identifiers, docstrings and comments; Google docstrings on every
  public function; type hints everywhere; no `print()`; logging with `%` and never a value; specific
  exceptions, always chained (`from exc`); `pathlib`; functions of about 30 lines, files of about 200
  (a module that gains a second responsibility is split: `canonical_writer.py` is already over, so new
  code goes to new modules); `Any` only with its reason.
- The writer assigns the classification; no caller passes one. The firewall, the no-oracle rule and the
  audit-before-effect rule of the voice channels are untouched. `db.transaction()` is not reentrant: a
  writer joined to a caller's transaction passes `manage_transaction=False`.
- `memory_writer.promote` keeps its behaviour; the tests of Plans 0062, 0063 and 0065 stay green with
  only the edits declared in the tasks.
- Titles of commits at most 72 characters; one commit per task; `ruff` over explicit paths including
  `scripts/`; `mypy server/src robot/src` and `pyright` clean.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/`.
- ADR 0024, ADR 0022 (including *Implementation notes*), ADR 0019 §2 and §3, the data-pool document.
- `server/src/server/memory/{canonical_writer,relational_v4,predicate_registry,declarative,memory_writer,household_authorization,legacy_v4_migration,policy_gated_v4_reader}.py`,
  `migration_004_relational_v4.sql`, `migration_010_asserter_and_channel.sql`,
  `server/src/server/{db,exceptions}.py`; `tests/unit/test_architecture_guards.py`,
  `tests/integration/test_canonical_writer_{literals,relations,hardening}.py`,
  `tests/integration/test_third_parties.py`, `tests/integration/test_memory_v4_{repository,schema,migration,relation_classification}.py`.

## Permitted files

- Production: `server/src/server/memory/{predicate_registry,relational_v4,declarative,canonical_writer,legacy_v4_migration}.py`,
  new `server/src/server/memory/{write_types,care_contacts,commissioning}.py`,
  new `server/src/server/memory/migration_011_contacts_and_commissioning.sql`,
  `server/src/server/{db,exceptions}.py`.
- Tests: the files named in each task and their new files.
- Docs (Task 8): the list there.

No new route, status code, response field or setting. `robot/src`, `/chat`, `/transcribe`, the policy
(`cognition/authorization.py`), `personal_setup.py`, `scripts/` and the spoken dialogue are not edited.

---

## Task 0: Revalidate the baseline

- [ ] **Step 0:** this plan says `Ready` and Pipec confirmed D-1 to D-11 in writing. Otherwise stop.
- [ ] **Step 1:** `git checkout main && git pull`, a clean tree, `git checkout -b feat/0070-seed-data-pool-storage`.
- [ ] **Step 2:** `just gate`; record the count (4179 at `5f90e6e`, otherwise the count of `main` now).
- [ ] **Step 3: Re-audit** (each must find what the plan names): `rg -n "def refuse_security_value" server/src`,
  `rg -n "SecurityStorageUndecidedError|refuse_security_value" server tests scripts docs -l`,
  `rg -n "def create_third_party" server/src`, `rg -n "_is_member_of_owner|_may_become_a_member" server/src`,
  `rg -n "class WriteChannel|class WriteRefusal" server/src`, `rg -n "_MIGRATIONS" server/src/server/db.py`,
  `rg -n "inverse_query_id" server/src`. Check that every id and alias of the Task 3 table is unused
  (`rg`), that `parent_of` is only an inverse query id, and how the test directories assign markers (by
  directory or `pytestmark`). A difference is reported before code.

## Task 1: Rename the security refusal (mechanical, no RED)

**Files:** `server/src/server/memory/{relational_v4,canonical_writer}.py`, `server/src/server/exceptions.py`
and every test that names them (`rg -l` from Task 0).

This commit changes names only, so it has no RED: the evidence is that the same tests pass before and
after. A name that says «undecided» would be false once Task 2 lands.

- [ ] **Step 1:** rename `refuse_security_value` to `refuse_unstorable_value` and
  `SecurityStorageUndecidedError` to `UnstorableValueError` (message: «this value cannot be stored»),
  everywhere; no alias. The legacy migration keeps deferring a refused fact with its ledger reason
  `security_storage_undecided` (a stored value that does not change).
- [ ] **Step 2:** `just test` on the touched files, lint and types; `rg` finds no old name in `server`,
  `tests` or `scripts`.
- [ ] **Step 3: Commit** `refactor(server): rename the security refusal to unstorable (plan 0070)`.

## Task 2: A secret is stored by reference, never by value

**Files:** `server/src/server/memory/{predicate_registry,relational_v4}.py`; tests
`tests/unit/test_predicate_registry.py`, `tests/integration/test_memory_v4_repository.py`,
`tests/integration/test_canonical_writer_literals.py`, `tests/integration/test_canonical_writer_hardening.py`.

**Interfaces — Produces:** `PredicateDefinition.storable: bool = True`; `LiteralFormat.REFERENCE`;
`resolve_predicate("secret_holder")`; `refuse_unstorable_value(definition, sensitivity=None)` with the new rule.

- [ ] **Step 1: Failing tests.** `resolve_predicate("access_code").storable is False` and every other
  predicate is storable. `secret_holder` (alias `quien_conoce_el_secreto`) is a multi-value literal on a
  person, format `REFERENCE`, visibility `personal`, sensitivity `security`. The `REFERENCE` normalizer
  strips, collapses whitespace, accepts 2 to 120 characters and returns `None` for `""`, one character,
  121 characters and any value with four or more characters for which `str.isdigit()` is true, in any
  script (`"clave 1234"`, `"1 2 3 4"`, Arabic-Indic digits). Repository: `assert_literal_fact` with
  `access_code` raises `UnstorableValueError` and writes nothing; with `secret_holder` and no stated
  sensitivity it stores the row (`security`); with `sensitivity="security"` it stores it; with
  `sensitivity="normal"` it raises (the downgrade); `likes` with `sensitivity="security"` raises (the
  upgrade); the message, every log record and its `extra` hold no part of the value, in every case.
  Writer: the owner's `secret_holder` is stored `personal`/`security`; a child's is refused as
  `owner_only_predicate`; `access_code` is refused first, before anything is classified or logged.
  **Expected RED:** `secret_holder` resolves to `None`; `storable` does not exist.
- [ ] **Step 2: Implement.** Add the field, the format with its `match` case in `normalize_literal`, the
  definition, and the rule: refuse when `not definition.storable`; refuse when
  `definition.default_sensitivity == "security"` and a stated sensitivity differs from it; refuse when a
  stated sensitivity is `security` and the default is not. Still first, before any query, write or log.
- [ ] **Step 3:** run the four files and `tests/unit/test_architecture_guards.py`; lint and types.
- [ ] **Step 4: Commit** `feat(server): store who knows a secret, never the secret (plan 0070)`.

## Task 3: The pool predicates

**Files:** `server/src/server/memory/predicate_registry.py`; tests `tests/unit/test_predicate_registry.py`.

**Interfaces — Produces:** `LiteralFormat.CHOICE` with `PredicateDefinition.choices: frozenset[str] | None`;
the predicates below, each added to the registry's tuple, none with an `inverse_query_id`. The existing
`LiteralFormat.INTEGER` (0 to 130) serves `floor`; basements are not supported.

| Id | Spanish alias | Kind, cardinality | Subject → target | Format | Visibility / sensitivity |
|---|---|---|---|---|---|
| `preferred_name` | `nombre_preferido` | literal, single | person | text | personal / normal |
| `address_form` | `trato` | literal, single | person | choice `tu usted` | personal / normal |
| `health_coverage` | `prevision` | literal, single | person | text | personal / private |
| `health_condition` | `condicion_de_salud` | literal, multi | person | text | personal / medical |
| `medication` | `medicamento` | literal, multi | person | text | personal / medical |
| `takes_anticoagulant` | `toma_anticoagulante` | literal, single | person | choice `si no no_se` | personal / medical |
| `rescue_medication` | `medicamento_de_rescate` | literal, multi | person | text | personal / medical |
| `implanted_device` | `dispositivo_implantado` | literal, multi | person | text | personal / medical |
| `blood_type` | `grupo_sanguineo` | literal, single | person | choice `A+ A- B+ B- AB+ AB- O+ O-` | personal / medical |
| `mobility` | `movilidad` | literal, single | person | choice `solo baston andador silla_de_ruedas` | personal / medical |
| `hearing` | `audicion` | literal, single | person | choice `normal audifonos dificultad` | personal / medical |
| `vision` | `vision` | literal, single | person | choice `normal lentes dificultad` | personal / medical |
| `document_location` | `ubicacion_de_documento` | literal, multi | person | reference | personal / security |
| `preferred_emergency_facility` | `urgencia_preferida` | literal, single | person | text | personal / location |
| `home_address` | `direccion` | literal, single | person | text | personal / location |
| `dwelling_type` | `tipo_de_vivienda` | literal, single | person | choice `casa departamento` | personal / location |
| `floor` | `piso` | literal, single | person | integer | personal / location |
| `has_lift` | `tiene_ascensor` | literal, single | person | choice `si no` | personal / location |
| `home_access_note` | `acceso_a_la_casa` | literal, single | person | reference | personal / location |
| `lives_alone` | `vive_solo` | literal, single | person | choice `si no` | personal / location |
| `has_parent` | `tiene_padre_o_madre` | relation | person → person | — | personal / normal |
| `has_grandparent` | `tiene_abuelo_o_abuela` | relation | person → person | — | personal / normal |
| `has_grandchild` | `tiene_nieto_o_nieta` | relation | person → person | — | personal / normal |
| `has_sibling` | `tiene_hermano_o_hermana` | relation, symmetric | person → person | — | personal / normal |
| `withhold_from` | `no_informar_a` | relation | person → person | — | personal / private |

- [ ] **Step 1: Failing tests.** Each id and its alias resolves to the row above; no alias collides with another
  predicate; `parent_of` still resolves to nothing (it stays an inverse query id). The `CHOICE` normalizer folds
  case and accents, stores the canonical code and returns `None` for a value outside the set (`"Sí"` becomes
  `si`, `"quizas"` is refused, `"o+"` becomes `O+`, `"silla de ruedas"` becomes `silla_de_ruedas`, `"No sé"` for
  `takes_anticoagulant` becomes `no_se`). `home_address` accepts digits; `home_access_note` refuses four digits;
  `floor` accepts `"20"` and refuses `"-1"` and `"131"`. A pet is refused as the subject of every new literal.
  *Legacy:* the new Spanish aliases (`direccion`, `piso`, `movilidad`, `audicion`, `vision`, `vive_solo`, …) now
  resolve in the registry, and `legacy_v4_migration` resolves legacy predicates through it: a legacy fact whose
  predicate is one of the new ids or aliases is **deferred, never written** (its ledger reason is a new closed
  string, `pool_predicate_not_migrated`), with a test that runs the migration over such a fact.
  **Expected RED:** the ids resolve to `None`; the legacy fact would be written.
- [ ] **Step 2: Implement** the format, the field and the definitions; a table-driven builder for the literals
  keeps the registry small; `legacy_v4_migration` skips the pool predicates through one frozenset of ids exported
  by the registry.
- [ ] **Step 3:** run the registry tests, the repository tests and the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): register the household data pool predicates (plan 0070)`.

## Task 4a: Write types, the adult-child marker and the fence

**Files:** new `server/src/server/memory/write_types.py`; `server/src/server/memory/{canonical_writer,declarative}.py`;
tests new `tests/integration/test_canonical_writer_fence.py`, and `tests/integration/test_third_parties.py`.

**Interfaces — Produces:** in `write_types.py`: `WriteChannel` (the three existing members plus
`IMPORT_ASSISTED = "import_assisted"`), `IMPORT_CHANNELS` and `VOICE_CHANNELS` (frozensets), `WriteRefusal` (the three
existing reasons plus `VALUE_CONFLICT`, `ORDER_TAKEN`, `NOT_A_PERSON`, `CONTACT_IS_OWNER` and `ROLE_CONFLICT`),
`ConflictPolicy(StrEnum)` (`SUPERSEDE`, `REFUSE`) and `refusal_error(reason: WriteRefusal, *, what: str, channel:
WriteChannel) -> WriteRefusedError` (logs the reason, `what` and the channel only; `canonical_writer`'s `_refusal`
delegates to it, and `canonical_writer` re-exports the first two names so no caller changes).
`declarative.Guardianship(StrEnum)` (`MINOR`, `ADULT`); `create_third_party(..., attributes: Mapping[str, str] | None =
None, ...)`; `declarative.is_adult_dependent(entity_id: int) -> bool`.

- [ ] **Step 1: Failing tests** (temporary SQLite, invented data).
  *Marker:* `create_third_party(..., attributes={"guardianship": "adult"})` stores both the key and the marker;
  the same key returns the same id and leaves the attributes untouched; an `attributes` key named `import_key`
  raises `ValueError`. `is_adult_dependent` is true only for the marker `adult` (false for `minor`, none, attributes
  that are not an object or not JSON, and a missing id).
  *Adult child:* for each channel, a literal about an adult child (`likes`, `birth_date`, `stated_age`) raises
  `not_household_member`, the `child_of` row itself is accepted, and a minor or an unmarked child behaves as before.
  An adult child **cannot be declared the partner** (the guard still blocks it).
  *Relatives:* with an owner and relatives made by `create_third_party`: `write_relation(source=owner,
  predicate="has_parent", target=relative, channel=IMPORT_ASSISTED)` stores a row `personal`/`normal` with the owner
  as asserter and confirmer, and repeating it returns the same row; the same for `has_grandparent`, `has_grandchild`
  and `withhold_from` (`personal`/`private`, **its target may be a child, the partner or any person**);
  `has_sibling` written with the relative as its source is refused as `not_household_member`, with the owner as
  source it is stored once. A literal about a relative raises `not_household_member`; `write_relation(child_of,
  source=relative, target=owner)` is refused as `role_conflict`, as are `partner_of` with a relative and `pet_of`
  with a relative as source; a child, a pet or the partner as the target of `has_parent`, `has_grandparent`,
  `has_grandchild` or `has_sibling` is refused as `role_conflict`. **An exact repeat of an already active membership
  relation is accepted even if its source now holds another role** (the order of a load is membership first, but a
  second run must change nothing). **Expected RED:** `attributes` is an unexpected argument; `IMPORT_ASSISTED`
  does not exist; the relabelings are accepted.
- [ ] **Step 2: Implement.** Create `write_types.py` and import from it. Split the writer's membership check: a raw
  «has an active `child_of` or `pet_of` row» used by `_may_become_a_member`, and `_is_member_of_owner` = raw and
  not `is_adult_dependent`. `_may_become_a_member` first returns `True` for an identical active row, then refuses
  with `role_conflict` when the entity holds a relative role (`_holds_relative_role`: any active `has_parent`,
  `has_grandparent`, `has_grandchild` row between the owner and the entity, and `has_sibling` either way; **not**
  `withhold_from`), then applies the existing checks. The relative relations refuse a target that is already a
  member or the partner. Symmetric `has_sibling` is classified with the owner required at the source.
- [ ] **Step 3:** run the new files, `tests/integration/test_canonical_writer_*.py`, `test_third_parties.py`,
  `tests/integration/test_memory_writer.py` and the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): mark adult children and fence relatives (plan 0070)`.

## Task 4b: Refuse on conflict, and an honest confirmer

**Files:** `server/src/server/memory/canonical_writer.py`; tests new `tests/integration/test_canonical_writer_conflicts.py`.

**Interfaces — Produces:** `write_literal(..., on_conflict: ConflictPolicy = ConflictPolicy.SUPERSEDE,
confirmed_by_owner: bool = True)` and the same two parameters on `write_relation`. With `confirmed_by_owner=False`
the row's `confirmed_by_entity_id` is `NULL` and `confirmed_at` is kept.

- [ ] **Step 1: Failing tests.** With `on_conflict=REFUSE`, a second `birth_date` that differs from the active one
  raises `WriteRefusedError("value_conflict")` and the first stays active; the same value is idempotent; a second
  `partner_of` with another person (either end) raises `value_conflict`; a `lives_in` toward another place raises
  it; multi-value predicates never conflict; the default `SUPERSEDE` changes nothing (the existing supersede tests
  stay green). The refusal logs only the reason, the predicate id and the channel. With `confirmed_by_owner=False`
  a literal and a relation are stored with `confirmed_by_entity_id IS NULL` and a `confirmed_at`, and the
  policy-gated reader still serves them. **Expected RED:** `on_conflict` and `confirmed_by_owner` are unexpected arguments.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** run the new file, `tests/integration/test_canonical_writer_*.py`, `tests/integration/test_memory_writer.py`,
  the reader tests; lint and types.
- [ ] **Step 4: Commit** `feat(server): refuse-on-conflict policy for the writer (plan 0070)`.

## Task 5: Migration 011

**Files:** new `server/src/server/memory/migration_011_contacts_and_commissioning.sql`, `server/src/server/db.py`;
tests `tests/integration/test_memory_v4_schema.py`, `tests/integration/test_memory_v4_migration.py` and every test
that pins version 10 (`rg -n "migration_010|user_version|Schema up-to-date" tests server/src`).

The script is atomic like 010 (`BEGIN`, the statements, the version, `COMMIT`); timestamps follow migration 004's
convention. The tables, in prose and key constraints (the executor writes the full DDL):

- `care_contacts`: `id`; `owner_entity_id` and `contact_entity_id`, both `NOT NULL REFERENCES entities(id) ON DELETE
  RESTRICT`; `role` `CHECK` in the seven D-9 values; `relationship` nullable, 1 to 40 characters; `phone` `NOT NULL` and
  `phone_alt` nullable, each `GLOB '+[1-9]*'` and 9 to 16 characters (SQL checks the first digit and the length;
  `normalize_phone` validates the rest); `call_order` null or at least 1; `has_key`, `may_receive_health_info` and `may_view_activity` 0 or
  1, default 0; `visibility` `CHECK = 'personal'`; `sensitivity` `CHECK` in `private location`;
  `asserted_by_entity_id` nullable `ON DELETE SET NULL`; `channel` `NOT NULL`; `confirmed_by_entity_id` nullable
  `ON DELETE SET NULL`; `confirmed_at` `NOT NULL`; `created_at`; `revoked_at`. Two partial unique indexes:
  `(owner_entity_id, contact_entity_id, role) WHERE revoked_at IS NULL` (one active row per person and role; a
  person with two roles has two rows) and `(owner_entity_id, call_order) WHERE revoked_at IS NULL AND call_order
  IS NOT NULL` (the order belongs to the person, so a second phone is a column and not a second order).
- `commissioning_records`: `id`; `installation_id` `NOT NULL`, 36 characters (a random UUID); `started_at`; `interviewer_label` 1 to 80 characters; `interviewer_role` in
  `builder family technician other`; `confirmation_mode` in `owner_in_person representative builder_is_owner`;
  `disk_encryption` in `declared_yes declared_no unknown`; `pool_version`; nullable `seed_file_sha256`, `counts_json`,
  `biometric_notice_version`, `consents_json`, `modalities_json`, `backup_reference`, `backup_destroy_by`,
  `baseline_backup_reference`, `baseline_destroy_by`, `readiness_json`, `closed_at`; a table `CHECK` that
  `builder_is_owner` needs the role `builder`; **one open record**: `CREATE UNIQUE INDEX ... ON
  commissioning_records((1)) WHERE closed_at IS NULL` (a unique index on the nullable column itself would enforce nothing).
- `commissioning_sections`: `commissioning_id` `NOT NULL REFERENCES commissioning_records(id) ON DELETE CASCADE`;
  `section` `CHECK` in the eleven D-10 values; `status` `CHECK` in the five; `recorded_at`; primary key
  `(commissioning_id, section)`.

- [ ] **Step 1: Failing tests.** After `run_migrations` the database is at version 11 and has the three tables. A
  database at version 10 with rows upgrades in place without losing any; running the migrations twice changes
  nothing. Each `CHECK` rejects a value outside its list (a phone `0900000001`, a role `boss`, `builder_is_owner` with
  the role `family`, a status `maybe`). The partial indexes **enforce**: a second active row for one (owner, contact,
  role) fails while a second role for the same person succeeds, a revoked row does not block a new one, two active
  contacts with one call order fail while two with a null order do not, and a second record without `closed_at` fails
  while one after a closed record is not blocked at this layer. Deleting an entity that a contact row refers to fails
  (`RESTRICT`). **Expected RED:** `no such table`; the migration list ends at 10.
- [ ] **Step 2: Implement** the script and register it in `db._MIGRATIONS`; update the tests that pin 10.
- [ ] **Step 3:** run the schema, migration, repository and reader tests; lint and types.
- [ ] **Step 4: Commit** `feat(server): add migration 011, contacts and the acta (plan 0070)`.

## Task 6: Write a care contact

**Files:** new `server/src/server/memory/care_contacts.py`; `server/src/server/memory/canonical_writer.py` (the fence
of Task 4a learns about contacts); `tests/unit/test_architecture_guards.py`; tests new `tests/unit/test_phone_format.py`,
`tests/integration/test_care_contacts.py`.

**Interfaces — Consumes:** `write_types`, the tables. **Produces:** `ContactRole(StrEnum)` (D-9); frozen `CareContact` (the
row's fields; its `repr` omits the phone and the relationship); `normalize_phone(raw: str) -> str | None` (pure);
`async write_contact(*, owner_entity_id: int, contact_entity_id: int, role: ContactRole, phone: str, channel:
WriteChannel, confirmed_at: str, phone_alt: str | None = None, relationship: str | None = None, call_order: int | None =
None, has_key: bool = False, may_receive_health_info: bool = False, may_view_activity: bool = False, on_conflict: ConflictPolicy =
ConflictPolicy.SUPERSEDE, confirmed_by_owner: bool = True, manage_transaction: bool = True) -> CareContact`;
`async list_active_contacts(owner_entity_id: int) -> tuple[CareContact, ...]` (by call order, nulls last, then id; used by
the tests and by Plan 0072's readiness report);
`async has_active_contact(entity_id: int) -> bool`; `async entity_has_contact_rows(entity_id: int) -> bool` (any row,
revoked included). This module is the **only** place with SQL on `care_contacts` (the architecture guard says so).

- [ ] **Step 1: Failing tests.** `normalize_phone` accepts `+56 9 0000 0001`, `+56-900000001`, `(+56) 900.000.001` and returns
  `+56900000001`; it returns `None` for `0900000001`, `56900000001`, `+0900000001`, `+56abc`, `+5690`, 16 digits, empty.
  `write_contact` stores a row for an existing adult child, for the partner, for a relative and for a new third party; the
  classification is `personal`/`private` (`personal`/`location` when `has_key`); it records the owner as asserter, the channel,
  and the confirmer unless `confirmed_by_owner=False`. It raises `ValueError` for a bad phone (the message holds no
  digits), `WriteRefusedError` for the owner as contact (`contact_is_owner`), a pet or a non-person (`not_a_person`), and a
  second active contact with the same call order (`order_taken`). A contact has a phone and an optional `phone_alt` (also
  validated); one person with two roles (caregiver and key holder) has two rows and the same phone is accepted; repeating an
  identical contact (same owner, contact, role and values) returns the same row; the same (owner, contact, role) with another
  phone, second phone, order or flag supersedes the old row (it is revoked, the new one inserted) under `SUPERSEDE` and raises
  `value_conflict` under `REFUSE`. `list_active_contacts` hides revoked rows. **A person who holds an active
  contact is refused as the source of a new membership relation** (`role_conflict`: a neighbour cannot be relabeled the owner's
  child to unlock facts), **while the exact repeat of an existing `child_of` row of a caregiver child is accepted**, and being a
  contact opens no V4 fact. No log record, error or `repr` holds a phone. The guard test fails when any other module puts SQL
  on `care_contacts`. **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement.** One transaction, joined when `manage_transaction=False`; refusals through `write_types.refusal_error`
  with `what="care_contact"`; `canonical_writer._holds_relative_role` also calls `has_active_contact` (no import cycle:
  `care_contacts` imports `write_types` only).
- [ ] **Step 3:** run the new files, `tests/integration/test_canonical_writer_*.py`, the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): write care contacts, phone included (plan 0070)`.

## Task 7: The commissioning record

**Files:** new `server/src/server/memory/commissioning.py`; `server/src/server/exceptions.py`;
`tests/unit/test_architecture_guards.py`; tests new `tests/integration/test_commissioning.py`.

**Interfaces — Consumes:** the tables (Task 5). **Produces:** `InterviewerRole`, `ConfirmationMode`, `DiskEncryption`,
`SectionStatus`, `Section`, `Modality` (all `StrEnum`: the lists of Task 5, D-10 and D-11; `ENROLLABLE_MODALITIES` is the
frozenset of `pin`, `face`, `voice`); frozen `CommissioningInput(interviewer_label, interviewer_role, confirmation_mode,
disk_encryption)`; frozen `CommissioningRecord(id, installation_id, started_at, interviewer_label, interviewer_role, confirmation_mode,
disk_encryption, pool_version, seed_file_sha256, counts, closed_at)`; `POOL_VERSION = 1`; the opening generates the
installation id with `uuid.uuid4()` (random, never derived from a name, an address or the hardware); `CommissioningError(ValueError)`
with `CommissioningOpenError` and `CommissioningClosedError` (closed messages); `async importer_window_open() -> bool`
(true when **no** record is closed); `async open_commissioning(details: CommissioningInput, *, started_at: str,
manage_transaction: bool = True) -> CommissioningRecord` (raises `CommissioningOpenError` when one is open and
`CommissioningClosedError` when any record is closed); `async get_open_commissioning() -> CommissioningRecord | None`;
`async record_import(record_id: int, *, seed_file_sha256: str, counts: Mapping[str, int], manage_transaction: bool =
True) -> None`; `async set_section_status(record_id: int, section: Section, status: SectionStatus, recorded_at: str, *,
manage_transaction: bool = True) -> None`; `async list_section_statuses(record_id: int) -> Mapping[Section,
SectionStatus]`; `async close_commissioning(record_id: int, closed_at: str, *, manage_transaction: bool = True) -> None`.
Only this module has SQL on the two tables. (The columns for the consents, the modalities, the backups and the readiness
report are written by a function of Plan 0072.)

- [ ] **Step 1: Failing tests.** Open, read, record an import, set and overwrite a status, close; `importer_window_open` before
  any record (true), with an open one (true) and after a close (false); a second open record is refused while one is open and
  **a new one is refused after a close**; a label of 0 or 81 characters or with a control character is refused;
  `builder_is_owner` with the role `family` is refused; `counts` must be integers; the record holds no household value (a test
  stores a canary label and asserts that nothing else of a household can reach the row); a closed record rejects
  `record_import` and `set_section_status` (`CommissioningClosedError`); a status outside the five never reaches the database;
  the `Modality` list contains exactly the six names and `ENROLLABLE_MODALITIES` exactly three. The guard test fails when another
  module puts SQL on the two tables. **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement** with small functions; every write in its own `db.transaction()` unless joined.
- [ ] **Step 3:** run the new file and the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): record a commissioning and its sections (plan 0070)`.

## Task 8: Documentation truth (text only, no RED)

- [ ] [`seed-data-pool.md`](../../architecture/seed-data-pool.md): the *Plan* column says what shipped;
  `memory-and-world-state.md` (the new predicates, the adult child, the relatives, `secret_holder`, the contacts table,
  `access_code` is never stored); `identity-and-access.md` (the assisted channel, the fence, the modalities);
  `current-state.md` and its Archify diagram (validate, then deliver); `longitudinal-conversational-memory-evaluation.md` and
  `docs/evals/longitudinal-memory-v3.md` (the pending SECURITY scenario names `access_code`, now never stored: a dataset
  bump is CM-7 preparation); ADR 0021 decision 13 and ADR 0022 (pointers to ADR 0024); the roadmap's Step 0 row, the plan
  index, the open-plan index, the ADR index; the local tracking table (never committed). Move this plan to `completed/` with
  its execution record.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, `uv run python scripts/check_reserved_terms.py`, every relative
  link resolves, `just gate`.
- [ ] **Acceptance by Pipec on a database kept apart** (`BRAIN_DB_PATH` set to a scratch file; outcomes only): `just
  setup-personal status` shows `schema_version=11`; `sqlite3` lists the three tables. No behaviour reaches the voice, so there
  is no hardware case; say so in the record.
- [ ] Commit `docs: close plan 0070`; PR; merge only with Pipec's go-ahead.

## ADR 0024 coverage

| ADR 0024 | Where |
|---|---|
| 2 the data pool (the predicates, the statuses, the version) | Tasks 3, 5, 7 |
| 4 secrets by reference; the sensitivity guard | Tasks 1, 2 |
| 5 contacts | Tasks 5, 6 |
| 6 the assisted channel, the record, the honest confirmer | Tasks 4a, 4b, 5, 7 |
| 9 the adult child | Task 4a |
| 10 relatives and the people to keep out | Tasks 3, 4a |
| 15 the modalities inventory | Tasks 5, 7 |
| 7, 8, 11, 12, 13, 14 | Plans 0071 and 0072 |

## Completion criteria

1. Tasks 0 to 8 done, one commit per task, every code test RED before GREEN (Tasks 1 and 8 declared).
2. `just gate` green; the Plan 0062, 0063 and 0065 tests unchanged except the renamed refusal.
3. A secret is refused without a trace in either direction of the label; a relative, a contact and an adult child cannot be
   relabeled a member while an exact repeat is accepted; a contact needs a valid phone and an unambiguous order; the
   record carries no household value; no module but its repository puts SQL on the new tables.
4. The migration upgrades a version-10 database in place and its indexes enforce.

## Rollback boundary

Each task is one commit. Task 5 adds a migration: there is no down-step, the tables are new and unused by older code, so the
rollback is to leave them. Task 1 touches many files: revert it as one commit. Tasks 6 and 7 need Task 5; Tasks 4a and 4b need
Task 3.

## Not here, and why

- **The file, the command, the dry run, the replacement window, `reset_db.ps1`, the folding module:** Plan 0071.
- **Enrolling face and voice in one flow, the voice session, the readiness report, closing the commissioning from a command,
  the acta file, the baseline backup:** Plan 0072.
- **Reading any of it by voice, or by an alert service:** CM-5 and the care ADR (ADR 0024, *Not decided here*).
- **Removing a contact at the contact's request, forgetting by CM-6, the amendment path after the closing:** CM-6 and a later plan.
- **A structured medication schedule, places, a `beliefs` classification, sleep and meals routine:** later.
- **Two third parties with one name:** unchanged (a conflict).

## Execution record (2026-10-23)

Executed in one session on the branch `feat/0070-seed-data-pool-storage`, from `main` at `749752e`, with the
`executing-plans` skill (inline, a ledger, one commit per task) and no worktree. Every code test was observed RED
for its stated reason before the code existed (Tasks 1 and 8 declared none). Baseline `just gate` on `main`:
**4179 passed**.

**Commits (one per task):** Task 1 `0379570`, Task 2 `c3f16c4`, Task 3 `50d3c6b`, Task 4a `8c18e3f`, Task 4b
`497ed51`, Task 5 `001c2fa`, Task 6 `1f89189`, Task 7 `5d6cea4`. Task 8 is the documentation commit. The review fix pass, one commit per concern: `d5ce8f0` (the conflict policy and the contact role are coerced) and `782b31a` (a guardianship marker outside the list is refused).

**Verification.** `just gate`: **4511 passed**; lint, `mypy`, `pyright` and the security audit clean.
`scripts/check_reserved_terms.py` clean, `ruff format --check .` clean and every relative link of the changed
documents resolves. The Archify diagram of the current state was validated at the showcase level (9 of 9 checks)
and delivered. The three untracked drafts of `docs/history/` and the untracked `docs/evals/longitudinal-memory-v3.md`
are byte-identical to what they were at the start.

**Rulings made while executing** (the spec, ADR 0024, was the authority; each costs one small edit if wrong):

1. Task 2: the synthetic security-default **relation** in the Plan 0065 repository test gets `storable=False`; under
   the new rule a security-default predicate with no stated label is storable, and the test pins that the repository
   refuses the shape.
2. Task 3: `secret_holder` (Task 2) is part of `POOL_PREDICATE_IDS`, so a legacy fact so named is deferred as
   `pool_predicate_not_migrated`; the legacy `security_storage_undecided` deferral now keys on `not definition.storable`
   (same ledger string, same `access_code` case).
3. Task 4a: the Plan 0065 test that pins the channel list gains `import_assisted`; the fence helpers stay in
   `canonical_writer.py` (the permitted-files list names no new module for them) although the file is over the size
   guideline; `withhold_from` keeps person-only targets, so a pet cannot be its target.
4. Task 4b: the "reader still serves it" test uses a child (household-labelled rows), because the household reader
   never serves the owner's `personal` rows.
5. Task 6: the call-order and relationship `ValueError`s carry no digits, so the no-digit property holds for every bad
   input.
6. Task 7: the keys of `counts` must be plain lowercase words and the file hash 64 lowercase hex digits (the plan says
   only that counts are integers; "no household value can reach the row" needs the keys closed too);
   `list_section_statuses` returns all eleven sections with `not_asked` for an unrecorded one; a later `record_import`
   replaces the hash and counts (the acta keeps the last import). Plan 0071 must name its counts with plain words.
7. Task 8: `docs/evals/longitudinal-memory-v3.md` is **untracked** on `main` (it is Pipec's generated report of the
   2026-10-22 benchmark run, a measurement). It was **not edited**: the plan's instruction to update it cannot apply
   to an untracked, generated measurement. The evaluation document says the pending SECURITY scenario now names a
   datum that cannot exist and that replacing it is a dataset bump (CM-7 preparation).
8. Two inline `pragma: allowlist secret` comments on the enum members `SECRETS` and `TOKEN` of `commissioning.py`
   (the Detect Secrets hook flagged a section name and a modality name).

**Acceptance on a database kept apart.** With `BRAIN_DB_PATH` pointing at a scratch file, `just setup-personal status` printed `schema_version=11` and `sqlite3` listed `care_contacts`, `commissioning_records` and `commissioning_sections` (run by the executor; the scratch file was deleted). **Pipec's own run is still pending.** No behaviour reaches the voice, so there is no hardware case.

**Independent review.** One read-only reviewer (sonnet, whole branch, asked by Pipec through the review skills), no Critical finding. Two Important findings, both fixed with a failing test first: (1) a conflict policy given as the plain string `"refuse"` (or an invalid one) silently disabled `REFUSE` because it was compared with `is` and never coerced, in `write_literal`, `write_relation` and `write_contact` (the contact role is coerced too); (2) a `guardianship` marker with a typo (`"Adult"`) was stored and failed open, treating an adult child as a minor. **Deferred minors** (no fix pass): a person with two contact roles can put the call order on only one of them (matches the plan and ADR 0024; note for Plan 0071); an `interviewer_label` of only spaces or with Unicode separators and bidi controls passes the check (cosmetic); a revoked contact can still be relabeled a member (the plan and tests say revoked rows do not block; `entity_has_contact_rows` exists if Pipec wants the stricter rule); the architecture guards are regex-on-literal like the others; `canonical_writer.py` is about 690 lines and the fence (about 150 lines) is a clean extraction for a later split; the ledger reason `security_storage_undecided` is stale wording kept as a stored value. **For Plan 0071:** no getter separates the marker `minor` from no marker, which its "changed guardianship" conflict rule needs, and a later `record_import` replaces the hash and counts.
