# 0065 — CM-3b, tranche A: the channel-neutral writer core

> **Status:** `Draft` — written 2026-10-16 from the CM-3b audit of the same day and from
> [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md) (`Proposed`). **Blocked** until
> Pipec accepts ADR 0022 and marks this plan `Ready` and `NOW`; to be executed in a **new
> session**. **Not rehearsed** in a scratch copy: the tasks below are specifications (files, rules,
> tests to write first), not rehearsed diffs. It does not require Plan 0064.

> **For agentic workers:** if the status above does not say `Ready`, or ADR 0022 is not
> `Accepted`, stop. REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. **Pipec's rules win over the skills:** one plain
> branch from `main`, never a git worktree, subagents only if Pipec asks, this plan lives under
> `docs/plans/`. One commit per task, every test observed RED for the stated reason first. If
> evidence contradicts the plan, stop and report instead of redesigning. The Bash tool of this
> environment loses backslashes and non-ASCII characters in heredocs: use the Write and Edit tools.
> Run the suite with `MEMORY_ENABLED=false` (CI does). A test that builds data at a fixed date
> must pin the clock too (Plan 0063 shipped a test that broke the next day).

**Goal:** Before Step 0 exists, the memory layer has **one writer that any channel can call**: the
spoken confirmation of Plan 0063 and the initial import of Step 0 produce the same stored fact with
the same classification, assigned by the writer and never by the speaker; a relation can carry a
visibility, a sensitivity, a confirmer and a validity range; a third party with a repeated name is
never merged; the household has its own pair of capabilities; and the registry knows `species`, the
disclosure predicate and the first SECURITY predicate, with the writer refusing to store a
SECURITY value until Step 0 decides storage at rest. Nothing new is spoken, no route changes, the
robot is untouched.

**Architecture:** (1) Registry entries. (2) `relational_v4.assert_entity_relation` gains the
arguments `assert_literal_fact` already has, plus validity. (3) A small
`memory/third_parties.py` that creates a third-party entity without merging by name. (4) Two new
`AuthorizationAction` members and their rules in `cognition/authorization.py`, with matrix tests
and the architecture guard that nothing but the writer consumes them. (5)
`memory/canonical_writer.py`: `write_literal(...)` and `write_relation(...)` over
`(subject, predicate, object, asserter, channel, confirmer)` with the classification table, the
`security` refusal, the "only the subject writes into their `personal` memory" invariant and the
validity rule; `memory_writer.promote` becomes its first caller **without changing behaviour**.
(6) Benchmark dataset v3 and an honest driver.

**Tech Stack:** Python 3.12, aiosqlite, pydantic, pytest. No new dependency. **One migration only if
Task 2 proves it is needed** (it should not be: the columns exist).

**Spec:** [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md) (all of it),
[ADR 0019](../../adr/0019-personal-memory-capabilities.md) §2 and §3,
[ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decisions 5 to 8 and 13,
`docs/evals/longitudinal-conversational-memory-evaluation.md` (the frozen gates).

## Global Constraints

- No real household data anywhere: invented canaries (`scripts/check_reserved_terms.py`).
- The firewall (face and voice of the same person on the turn's clip, never a token), the no-oracle
  rule, audit-before-effect and "a value never reaches a log, `llm_response` or the history" are
  unchanged and keep their tests.
- `memory_writer.promote` keeps its behaviour byte for byte: the Plan 0062 and 0063 tests stay green
  **unmodified** after Task 5.
- The writer assigns the classification; a caller cannot pass one for a `personal` fact.
- No `security` value is stored until the Step 0 ADR decides storage at rest (a test pins the
  refusal; the refusal's reason is a closed string, never the value).
- `db.transaction()` is not reentrant; `manage_transaction` is the join mechanism.
- Type hints, Google docstrings, `ruff` clean over explicit paths (including `scripts/`),
  `mypy server/src robot/src` clean, no `print()`, commit titles at most 72 characters.

## Decisions

1. **D-1 — Predicate names.** `species` (literal, single current, subject a pet);
   `stated_age` (literal, single current, subject a person or a pet; the value is a whole number
   from 0 to 130 and the row's `asserted_at` is its as-of date; ADR 0022 decision 6);
   `private_topic` (literal, multi-value, subject a person, `personal`/`normal`) for the disclosure
   rule; `access_code` (literal, single current, subject a person, `personal`/`security`) for the
   first SECURITY datum.
2. **D-2 — Classification table of the writer.** For a `personal` subject (the owner) the writer
   stores `personal`; for a child, a partner or a pet it stores `household`, with the registry's
   sensitivity (`child_data` for a child's `birth_date`). A caller never overrides it.
3. **D-3 — The household pair** is `PROPOSE_HOUSEHOLD_MEMORY` and `CONFIRM_HOUSEHOLD_MEMORY`
   (owner only, `household` visibility, `strong`, no PIN route, consent not applied for normal data).
4. **D-4 — Collision handling.** `create_third_party` raises `AmbiguousEntityError` when an entity
   of that name and type already exists and no explicit `key` is given; it never returns the
   existing one silently.
5. **D-5 — Validity.** `valid_from` is the given date, else the assertion date; the previous row
   of a `single_current` predicate is closed **at the new `valid_from`**; a row with an explicit
   past `valid_to` may be inserted already closed (history).
6. **D-6 — Dataset v3** keeps both versions readable; the report states the cut.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/`.
- [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md), ADR 0019, ADR 0021.
- `server/src/server/memory/{relational_v4,predicate_registry,memory_writer,candidates,
  declarative,schema.sql,policy_gated_v4_reader}.py`,
  `server/src/server/cognition/{authorization,models}.py`, `server/src/server/personal_setup.py`,
  `tests/unit/test_architecture_guards.py`, `tests/evals/golden_longitudinal_memory.yaml`,
  `scripts/{longitudinal_eval_driver,eval_longitudinal_memory}.py`.

## Permitted files

- Production: `server/src/server/memory/{predicate_registry,relational_v4,memory_writer}.py`,
  new `server/src/server/memory/{third_parties,canonical_writer}.py`,
  `server/src/server/cognition/{authorization,models}.py`.
- Scripts and data: `tests/evals/golden_longitudinal_memory.yaml`,
  `scripts/{longitudinal_eval_driver,eval_longitudinal_memory,longitudinal_eval_models,longitudinal_eval_metadata}.py`.
- Tests: the files named in each task and their new files.
- Docs (Task 7): the list there.

No new URL, route, status code, response field or setting. `robot/src`, `/chat`, `/vision/respond`,
the household reader's contract and the spoken dialogue are not edited.

---

## Task 0: Revalidate the baseline

- [ ] **Step 0:** this plan says `Ready` and ADR 0022 says `Accepted`; otherwise stop.
- [ ] **Step 1:** `git checkout main && git pull`, clean tree, `git checkout -b feat/0065-cm3b-a-writer-core`.
- [ ] **Step 2:** `just gate`; record the outcome and count.
- [ ] **Step 3: Re-audit** (each must find what the plan names): `rg -n "def assert_entity_relation"
  server/src`, `rg -n "def promote" server/src`, `rg -n "PredicateDefinition\(" server/src/server/memory/predicate_registry.py`,
  `rg -n "class AuthorizationAction" server/src`, `rg -n "_VERSION|version" scripts/eval_longitudinal_memory.py tests/evals/golden_longitudinal_memory.yaml`.

## Task 1: The registry knows `species`, `stated_age`, `private_topic` and `access_code`

**Files:** `server/src/server/memory/predicate_registry.py`; test
`tests/unit/test_predicate_registry.py`.

- [ ] **Step 1: Failing tests.** `resolve_predicate("species")` returns a literal, single-current
  definition whose subject types are the pet type only and whose format is text;
  `resolve_predicate("stated_age")` is a single-current literal on a person or a pet that accepts
  `"8"` and rejects `"ocho"`, `"-1"`, `"131"` and `"8 años"`;
  `resolve_predicate("private_topic")` is a multi-value literal on a person with default visibility
  `personal`; `resolve_predicate("access_code")` is a single-current literal on a person with
  default visibility `personal` and default sensitivity `security`; the Spanish aliases
  (`especie`, `edad_dicha`, `tema_privado`, `codigo_acceso`) resolve to them; a pet is rejected as the subject
  of `private_topic` and `access_code`. Expected RED: `resolve_predicate(...)` returns `None`.
- [ ] **Step 2: Implement** the four `PredicateDefinition`s. `LiteralFormat` has only `TEXT` and
  `ISO_DATE` today: add `LiteralFormat.INTEGER` with its normalizer (a whole number from 0 to 130,
  digits only) next to the ISO-date one, and use it for `stated_age`. **Step 3:** run
  `tests/unit/test_predicate_registry.py tests/unit/test_architecture_guards.py` (a guard may list
  the registry's predicates); lint and types. **Step 4: Commit**
  `feat(server): register species, private topic and access code (plan 0065)`.

## Task 2: A relation can carry a classification, a confirmer and a validity

**Files:** `server/src/server/memory/relational_v4.py`; test
`tests/integration/test_relational_v4_relation_classification.py` (new) and the existing
relational tests.

- [ ] **Step 1: Failing tests** (temporary SQLite, the project's usual fixture): `assert_entity_relation`
  accepts `visibility`, `sensitivity`, `confirmed_by_entity_id`, `confirmed_at`, `valid_from` and
  `valid_to`, stores them and returns them in `EntityRelationV4` (which gains `confirmed_by_entity_id`
  and `confirmed_at`); with no argument the stored values are the registry's defaults (today's
  behaviour, pinned by the existing tests); for a `single_current` predicate the previous row is
  closed with `valid_to` equal to the **new row's `valid_from`**, not `now`; a row inserted with an
  explicit past `valid_to` is stored as history and does not become current. Expected RED:
  `TypeError: assert_entity_relation() got an unexpected keyword argument`.
- [ ] **Step 2: Implement** by mirroring `assert_literal_fact` (same argument names and defaults);
  the supersede statement uses the new row's `valid_from` when given. No migration is expected;
  if a column is missing, stop and report.
- [ ] **Step 3:** run `tests/integration/test_relational_v4*.py tests/integration/test_policy_gated_v4_reader*.py`
  and everything that imports `EntityRelationV4`; lint and types. **Step 4: Commit**
  `feat(server): classify, confirm and date a v4 relation (plan 0065)`.

## Task 3: A third party is created without merging by name

**Files:** new `server/src/server/memory/third_parties.py`; test new
`tests/integration/test_third_parties.py`.

- [ ] **Step 1: Failing tests:** `create_third_party(name="Canary Child", type="person", key="c1")`
  returns a new entity id; a second call with the same name and type and a different key creates a
  **different** entity (the name is not unique across keys); the same name and type with **no** key
  when one exists raises `AmbiguousEntityError`; the same key returns the same entity (idempotent
  for the import); a pet is typed `other`. Expected RED: `ModuleNotFoundError`.
  Check first whether `entities` can hold two rows with one `(name, type)`: if the table's
  `UNIQUE(name, type)` forbids it, the key is stored in the entity's name qualifier column or the
  plan stops and reports the conflict (a migration needs its own decision).
- [ ] **Step 2: Implement** (SQL only through the repository module that owns `entities`; no
  second module issues SQL on it). **Step 3:** guards, lint, types. **Step 4: Commit**
  `feat(server): create third parties without merging by name (plan 0065)`.

## Task 4: The household pair of capabilities

**Files:** `server/src/server/cognition/{models,authorization}.py`; tests
`tests/unit/test_authorization_household_memory.py` (new) and the existing matrix tests.

- [ ] **Step 1: Failing matrix tests:** `PROPOSE_HOUSEHOLD_MEMORY` and `CONFIRM_HOUSEHOLD_MEMORY`
  are allowed for the owner at `strong` (face and voice) on a `household` fact whose subject is a
  child, partner or pet of the owner; denied for: the owner at `basic`, an actor holding only a
  token, a visitor, another adult, a minor, a `personal` visibility, and a subject outside the
  owner's household; the five personal capabilities give the same decisions as before (the
  existing matrix, unchanged); no PIN route; consent not applied for `normal`/`child_data`.
  Expected RED: `AttributeError: AuthorizationAction has no member PROPOSE_HOUSEHOLD_MEMORY`.
- [ ] **Step 2: Implement** the two members and their rules next to the personal ones; update the
  closed lists the existing tests enumerate (the eleven older actions are unchanged).
- [ ] **Step 3: Guard.** In `tests/unit/test_architecture_guards.py` add that only
  `memory/canonical_writer.py` may name the two new actions (nothing consumes them until Task 5).
- [ ] **Step 4:** run the authorization tests and the guards; lint and types. **Step 5: Commit**
  `feat(server): add the household memory capabilities (plan 0065)`.

## Task 5: The canonical writer, and `promote` as its first caller

**Files:** new `server/src/server/memory/canonical_writer.py`; modify
`server/src/server/memory/memory_writer.py`; tests new
`tests/integration/test_canonical_writer.py` and the unchanged Plan 0062/0063 tests.

**Interface (specification).** `async write_literal(*, subject_entity_id, predicate, value,
asserter_entity_id, channel, confirmer_entity_id, confirmed_at, valid_from=None, valid_to=None,
manage_transaction=True) -> LiteralFactV4` and `async write_relation(*, source_entity_id,
predicate, target_entity_id, ...) -> EntityRelationV4`. `channel` is a closed `StrEnum`
(`voice_dialogue`, `import_file`; `perception` reserved and refused for now). The classification is
looked up in the writer's own table (D-2) from the predicate and the subject; there is no
`visibility` or `sensitivity` parameter.

- [ ] **Step 1: Failing tests:** the same fact written through `voice_dialogue` and `import_file`
  has identical visibility and sensitivity; a child's `birth_date` is `household`/`child_data`; the
  owner's `likes` is `personal`/`normal`; `species` of a pet is `household`/`normal`; `stated_age` of a child is `household`/`child_data` and
  the derived current age of a stated 8 written one year earlier reads 9 (a pure helper
  `current_age(stated, as_of, today)` with its own tests, and a later `birth_date` wins); **the invariant:**
  a `personal` fact whose asserter is not its subject is refused with a closed reason; a `security`
  value is refused with the closed reason `security_storage_undecided` and **nothing is written and
  the value is in no log** (caplog and `extra` scanned); `perception` is refused; `lives_in` with a
  spoken `valid_from` closes the previous row at that date; a `lives_in` given as past (explicit
  `valid_to`) is stored as history; an exact repeat is idempotent. Expected RED: `ModuleNotFoundError`.
- [ ] **Step 2: Implement.** Keep the classification table in one place; the writer calls
  `assert_literal_fact` / `assert_entity_relation` with the explicit arguments and `manage_transaction`.
- [ ] **Step 3: Refactor `promote`** to call `write_literal` for its `personal` literal, without
  changing its transaction shape, its audit order or its outcomes. Run, **unmodified**,
  `tests/integration/test_memory_writer*.py tests/integration/test_candidate_dialogue.py
  tests/integration/test_memory_dialogue_routes.py`; they must stay green with no edit.
- [ ] **Step 4:** the architecture guard for who may write V4 facts (extend it so
  `canonical_writer.py` joins the writers and nothing else gains the right); lint and types.
- [ ] **Step 5: Commit** `feat(server): add the channel-neutral canonical writer (plan 0065)`.

## Task 6: Benchmark dataset v3 and an honest driver

**Files:** `tests/evals/golden_longitudinal_memory.yaml`,
`scripts/{longitudinal_eval_driver,eval_longitudinal_memory,longitudinal_eval_models,longitudinal_eval_metadata}.py`;
tests that pin the dataset version and the driver's unsupported operations.

- [ ] **Step 1: Read** the spec (`longitudinal-conversational-memory-evaluation.md`, the gates are
  **frozen**: do not relax one) and the current report of Plan 0046. List in the execution record
  what each change below does to comparability with the v2 baseline.
- [ ] **Step 2: Failing tests** for each of: (a) the dataset `version` is `3` everywhere it is
  pinned (three code files) and v2 is still readable; (b) `expected_items` use V4 vocabulary
  (`birth_date` as a full ISO date, `stated_age` where the scenario only says an age, `other` for
  a pet, `species` as a predicate); (c) the
  operation `confirm` exists in the schema and the driver reports it as supported by the
  canonical writer; (d) the SECURITY scenario exists with an **invented** code and a closed
  expected outcome (stored refused until Step 0, so the scenario is marked pending, not failing);
  (e) `provenance_attribution` is scoped `family` (ADR 0022 decision 5) and the report states that
  the personal acceptance has one scenario fewer and the full suite stays red until P3.2; (f) the
  driver's `PROPOSE` reason no longer says the writes go through legacy `assert_fact()`.
  Expected RED: each fails on the old value.
- [ ] **Step 3: Implement.** **Step 4:** run the benchmark's unit tests and, with Pipec's Ollama,
  one full offline run to confirm the report still generates (record counts only).
- [ ] **Step 5: Commit** `feat(evals): longitudinal dataset v3 and an honest driver (plan 0065)`.

## Task 7: Documentation truth

- [ ] ADR 0022 `Accepted` (with the date and what Pipec confirmed); ADR 0019 §2 and ADR 0021
  decisions 4 and 5 cross-references; `docs/architecture/identity-and-access.md` (the household
  pair), `memory-and-world-state.md` (writer, validity, `private_topic`, `access_code`),
  `current-state.md` and its Archify diagram if it mentions the writer (validate, then deliver);
  `docs/roadmap/cognitive-roadmap.md` and `conversational-memory-delivery-map.md` (CM-3b tranche A
  closed, tranche B next after Step 0), the plan indexes, the local table (never committed); move
  this plan to `completed/` with its execution record.
- [ ] `uv run ruff format --check .`, `uv run python scripts/check_reserved_terms.py`, every relative
  link resolves; commit `docs: close plan 0065`; PR; merge only with Pipec's go-ahead.

## Completion criteria

1. Tasks 0 to 7 done, one commit per task, every test RED before GREEN.
2. `just gate` green; Plan 0062 and 0063 tests unchanged and green.
3. The same fact written from two channels has one classification; a repeated third-party name is
   never merged; a `security` value is refused without a trace of the value.
4. The household pair passes its matrix and only the writer consumes it.
5. Dataset v3 loads, v2 stays readable, no gate relaxed, the report states the comparability cut.

## Rollback boundary

Each task is one commit and independent except Task 5 (needs 1 to 4). Reverting Task 5 restores
`promote` as it was. No migration is expected; if Task 2 or 3 needed one, it is its own commit and
its rollback is documented there. Facts already written stay.

## Not here, and why

- **Spoken capture of third parties**, **reported facts**, **the behaviour of the disclosure rule**
  and **perceptual candidates**: tranche B, after Step 0 (ADR 0022 decisions 5, 8 and 10).
- **Storing a SECURITY value** and **reading it back**: the Step 0 ADR decides storage at rest;
  reading is CM-5.
- **The initial import itself, the per-channel assurance levels, enrolment as the first setup step
  and the "are you with someone?" escalation**: Step 0.
- **`correct` and `forget`**: CM-6.

## Execution record

*(Filled in when the plan is executed.)*
