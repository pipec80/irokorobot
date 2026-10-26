# 0071 — Step 0, second plan: the file importer of the commissioning

> **Status:** `Ready` / `NOW` (written 2026-10-23, revised the same day after the second review; promoted by
> Pipec on 2026-10-26 after confirming D-1 to D-8 below). [Plan 0070](../completed/0070-seed-load-data-pool-storage.md)
> **closed on 2026-10-23**, so nothing blocks it; Task 0 re-audits it against the code Plan 0070 merged before
> any other work. It implements [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md)
> (`Proposed`) decisions 6 to 8, 11, 12 and 13; the ADR becomes `Accepted` when [Plan 0072](0072-commissioning-session.md)
> closes. Written for an executor who has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main`, never a git worktree,
> subagents only if Pipec asks, this plan lives under `docs/plans/`. One commit per task; every code
> test observed RED for the stated reason first (Tasks 7 and 8 are not automated or are text). If
> evidence contradicts the plan, stop and report. The Bash tool of this environment loses backslashes
> and non-ASCII characters in heredocs: use the Write and Edit tools. Run the suite with
> `MEMORY_ENABLED=false`. Pin the clock in any test with a date. Never run `uv sync --all-packages
> --all-groups` (use `--extra cuda`); commit `uv.lock` before `just gate` if it changed.

**Goal:** the interviewer can load the data pool of a household from a local TOML file: a dry run that
writes nothing and shows what would happen, then, when the owner has reviewed it and the interviewer
types `SI`, one transaction that writes it through the canonical writer (channel `import_assisted`) and
opens the commissioning record, or nothing at all. While the robot is being commissioned a new run with
`--replace` retracts what the previous one wrote and writes the file again; it never touches what was said
by voice and refuses to run once the robot has learned anything by voice. Loading the same file twice
changes nothing. No secret value is ever stored.

**Architecture:** (1) One neutral module of text keys replaces three copies of the folding function.
(2) A pure reader of the file, then a pure planner, over the models of Plan 0070. (3) An applier that owns
the single transaction and joins every writer to it. (4) A retraction that deletes by channel. (5) A
command, an example file that is also the questionnaire, a guard, and a reset script that respects
`BRAIN_DB_PATH`.

**Tech Stack:** Python 3.12, `tomllib` (standard library), pydantic, aiosqlite, httpx (already a dependency,
used synchronously in the command), pytest. **No new dependency, no migration, no new setting.**

**Spec:** ADR 0024 decisions 6 to 8 and 11 to 13, [`seed-data-pool.md`](../../architecture/seed-data-pool.md),
[Plan 0070](../completed/0070-seed-load-data-pool-storage.md) (the interfaces it produced).

## Decisions

Pipec confirmed D-1 to D-8 on 2026-10-26, which promoted this plan: D-1 to D-3 he had already chosen, and
D-4 to D-8 he accepted as the author proposed them.

1. **D-1 — A file, a dry run by default, the owner's review.** (ADR 0024 decisions 6 and 11.)
2. **D-2 — Replacement while commissioning, none after.** `--replace` is allowed only while
   `commissioning.importer_window_open()` is true; it retracts the earlier import and then writes with the
   refuse policy; it is refused when a V4 row or a memory candidate with a voice channel exists. Once a
   record is closed the importer refuses to run at all. (Decision 8.)
3. **D-3 — The authority** is access to the machine with the server stopped. (Decision 11.)
4. **D-4 — The file's keys** are English (the file is edited by a technician) and every comment is Spanish
   (the questionnaire). They map to the predicates of Plan 0070 as follows; a key not listed has the
   predicate's own name. *The author's call.* `conditions` → `health_condition`; `allergies` → `allergic_to`;
   `medications` → `medication`; `devices` → `implanted_device`; `documents` → `document_location`;
   `emergency_facility` → `preferred_emergency_facility`; `address` → `home_address`; `access_note` →
   `home_access_note`; `secrets` → `secret_holder`; `private_topics` → `private_topic`; `[[parents]]` →
   `has_parent`; `[[grandparents]]` → `has_grandparent`; `[[siblings]]` → `has_sibling`; `[[grandchildren]]` →
   `has_grandchild`; `[[withhold]]` → `withhold_from`; `[partner]` → `partner_of`; `[[children]]` → `child_of`;
   `[[pets]]` → `pet_of`; `[[contacts]]` → `care_contacts`.
5. **D-5 — Statuses.** The eleven sections of Plan 0070 D-10 carry a status. A section with items is
   `provided` (an explicit status other than `provided` is an error); a section without items takes the
   explicit `[status]` entry, or `not_asked` when there is none, and the report says «no preguntada». Which keys
   make a section `provided` (the catalogue's *Section* column): `conditions` ← `conditions`; `allergies` ←
   `allergies`; `medications` ← `medications`, `takes_anticoagulant`, `rescue_medication`; `devices` ← `devices`;
   `contacts` ← `[[contacts]]`; `withhold` ← `[[withhold]]`; `secrets` ← `secrets`; `documents` ← `documents`;
   `household` ← the partner, a child or a pet; `home` ← `address`, `dwelling_type`, `floor`, `has_lift`,
   `access_note`, `lives_alone`, `emergency_facility`; `function` ← `mobility`, `hearing`, `vision`. A key outside
   those lists (the name, `preferred_name`, `address_form`, `birth_date`, `health_coverage`, `blood_type`, the tastes,
   the relatives) has no status. *The author's call.*
6. **D-6 — Names.** One entity per distinct folded person name in the file. The owner, the partner, the
   children and the four relative lists must not repeat a name among themselves; a **contact or a `[[withhold]]`
   entry may repeat any name of a person** and then is that person (no second entity), otherwise it is a new third
   party; a contact or a `[[withhold]]` entry named like the owner or like a pet is a reading error. *The author's call.*
7. **D-7 — Where the code lives.** `server/text_keys.py` (top level, so `cognition` and `memory` both may import
   it), `memory/seed_file.py`, `memory/seed_plan.py`, `memory/seed_import.py`, `memory/seed_replace.py` and
   `seed_cli.py` next to `personal_setup.py`. Errors are `SeedFileError` and `SeedOwnerError` (subclasses of
   `ValueError`, so `main()` prints their closed message) in `exceptions.py`.
8. **D-8 — The command's arguments.** `seed-import PATH... [--apply] [--replace] [--interviewer LABEL...]
   [--role builder|family|technician|other] [--mode owner_in_person|representative|builder_is_owner]
   [--disk-encryption yes|no|unknown]` and `seed-import --print-schema` (prints the file's JSON Schema, touches no database and no server). The
   last four options are required to open the record (the first apply) and ignored afterwards. The review question's wording follows the mode (ADR 0024 decision 6). *The author's call.*

### The file (schema version 1)

```toml
schema_version = 1
pool_version = 1

[owner]                          # the owner already set up with `just setup-personal`
name = "Canary Owner"
preferred_name = "Canary"        # ¿Cómo quiere que le llamen?
address_form = "tu"              # "tu" o "usted"
birth_date = "1950-05-17"        # fecha completa
health_coverage = "Canary Plan"
conditions = ["Canary condition"]        # enfermedades crónicas
allergies = ["Canary allergy"]           # alergias y su reacción
medications = ["Canary pill, 10 mg, 8:00 y 20:00, con comida"]
takes_anticoagulant = "no"               # "si", "no" o "no_se"
rescue_medication = ["Canary inhaler, en el velador"]
devices = ["Canary implant"]
blood_type = "O+"
mobility = "solo"                # solo, baston, andador o silla_de_ruedas
hearing = "normal"               # normal, audifonos o dificultad
vision = "lentes"                # normal, lentes o dificultad
documents = ["el testamento está en el cajón del escritorio"]   # dónde están, nunca su número
emergency_facility = "Canary Clinic"
address = "Canary Street 100, Canary Town"   # aquí sí van los números
dwelling_type = "departamento"   # "casa" o "departamento"
floor = 20
has_lift = "si"
access_note = "conserje en recepción"    # cómo entrar; nunca un código ni un número
lives_alone = "si"
likes = ["té verde"]
dislikes = []
prefers = []
private_topics = []
secrets = ["la alarma la tiene Canary Friend"]   # quién lo sabe; NUNCA el código (cuatro dígitos se rechazan)

[status]                         # para una sección sin ítems: "none", "unknown" o "declined" (si falta: "not_asked")
devices = "none"

[partner]
name = "Canary Partner"

[[children]]
name = "Canary Child"
guardianship = "minor"           # "minor" o "adult"; un hijo adulto es solo nombre y relación
birth_date = "2015-03-02"        # o stated_age = 7, no ambos
likes = ["dibujar"]

[[pets]]
name = "Canary Pet"
species = "gato"
stated_age = 3

[[parents]]                      # también [[grandparents]], [[siblings]], [[grandchildren]] y [[withhold]]
name = "Canary Parent"           # solo el nombre; en [[withhold]] puede ser alguien ya nombrado arriba

[[contacts]]
name = "Canary Child"            # el mismo nombre de un miembro es esa persona
role = "caregiver"               # emergency caregiver doctor key_holder neighbor trusted other
relationship = "hija"
may_view_activity = false        # ¿podrá ver más adelante los eventos de actividad? (no habilita nada todavía)
phone = "+56900000001"           # formato internacional
phone_alt = "+56200000002"       # opcional: un segundo teléfono de la misma persona
call_order = 1                   # sin orden, una alerta nunca llama a esta persona
has_key = true
may_receive_health_info = true
```

Limits: the file at most 262144 bytes; names 1 to 80 characters; at most 20 members per list and 50 values per
list. A value that is in `likes` and in `dislikes` is an error.

## Review Focus

The inputs the tasks' main tests would miss; each line has its test in the task named.

1. The same file twice changes no count; the second dry run is all `unchanged`, **including a caregiver child who
   is also a contact** (Task 4a).
2. A differing single-value fact, a different partner or a changed `guardianship` stops the load without
   `--replace` and writes nothing (Task 4a); with `--replace` the earlier import's rows are retracted and the file is
   written again with the refuse policy, never overwriting a voice fact; with a voice row present `--replace` is
   refused (Task 5).
3. A failure half-way, or a refusal in any operation, leaves nothing, the commissioning record included (Task 4b).
4. Nothing is written without the interviewer's answer to the owner's review; the wording follows the mode;
   `representative` leaves `confirmed_by` empty (Tasks 4b, 6a).
5. A secret, a phone or a name leaves no trace in a log, an error, a pydantic message or a `repr` (Tasks 2, 4a).
6. The importer runs only with the server stopped, an existing database at the current version and a ready owner
   whose name matches; it creates none of them and prints the database it uses (Tasks 4a, 6a).
7. A name that already exists as an entity (a homonym, a child made by `personal-setup`) is a conflict (Task 4a).
8. The entity cleanup of the replacement never deletes an entity that something else refers to; a new table that
   refers to `entities` fails a test until the cleanup knows it (Task 5).
9. The example file is a template and cannot be applied; a path inside the repository outside `data/` warns (Task 6a).
10. `just reset-db` with `BRAIN_DB_PATH` set deletes that file and never `data/omnibot.db`, and the backup holds the
    `-wal` too (Task 7).
11. A commissioning error is never swallowed as an «invalid value» of one operation (Task 4b).

## Global Constraints

- **The plan of operations is the one contract** for entering and changing data (ADR 0025 decision 11): the file, the
  command-line CRUD of Plan 0073, a future form and a future inbox of changes all produce `SeedOperation`s and the same applier
  writes them; no front end writes SQL or calls a writer by itself.
- The constraints of [Plan 0070](../completed/0070-seed-load-data-pool-storage.md) apply unchanged (rules, canaries, the writer
  assigns the classification, commit titles, ruff and types). Invented phones such as `+56900000001`.
- Pydantic errors keep the failing input in `__cause__`: re-raise `SeedFileError` **`from None`** with only the field
  path and the error type. Sensitive fields use `Field(repr=False)`. No traceback is printed.
- A value appears only on the terminal report of the person who runs the command, never in a logger.
- `tomllib` returns `Any`: the one place it is used carries the reason for the `Any`.
- The command must not construct an `httpx.AsyncClient` (the architecture guard allows it only in the lifespan) and
  must not block the event loop: the health probe is one synchronous call in `main()` before `asyncio.run`.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/` (including `scripts-powershell.md`).
- ADR 0024, ADR 0022 (*Implementation notes*), Plan 0070 (the interfaces), the data-pool document.
- `server/src/server/memory/{canonical_writer,write_types,care_contacts,commissioning,declarative,relational_v4,predicate_registry,candidate_classifier,candidates,lexicon,preference_gate,legacy_v4_migration,owner_credentials,entity_labels}.py`,
  `server/src/server/cognition/intent_resolution.py` (where `normalize_spanish` lives today),
  `server/src/server/{personal_setup,db,exceptions,settings}.py`, `scripts/{onboard,eval_consolidation}.py`,
  `scripts/reset_db.ps1`, `justfile`, `server/pyproject.toml`, `tests/unit/test_architecture_guards.py`,
  `tests/integration/test_personal_setup.py`.

## Permitted files

- Production: new `server/src/server/text_keys.py`; `server/src/server/cognition/intent_resolution.py` (only the move
  of `normalize_spanish`); `server/src/server/memory/{canonical_writer,declarative,relational_v4,care_contacts,commissioning,candidates,candidate_classifier,preference_gate,lexicon,legacy_v4_migration}.py`;
  new `server/src/server/memory/{seed_file,seed_plan,seed_import,seed_replace}.py`; new `server/src/server/seed_cli.py`;
  `server/src/server/{personal_setup,db,exceptions}.py`; `server/pyproject.toml` (one script); `justfile` (one recipe);
  `scripts/eval_consolidation.py`; `scripts/reset_db.ps1`.
- Examples and docs: `docs/examples/seed-household.example.toml` (new) and the list of Task 8.
- Tests: the files named in each task and their new files.

No new route, status code, response field or setting. `robot/src`, the policy and the spoken dialogue are not edited.

---

## Task 0: Revalidate the baseline

- [ ] **Step 0:** this plan says `Ready`, Pipec confirmed D-1 to D-8, and Plan 0070 is closed and merged
  (`git merge-base --is-ancestor <0070 squash commit> origin/main`). Otherwise stop.
- [ ] **Step 1:** `git checkout main && git pull`, a clean tree, `git checkout -b feat/0071-seed-file-importer`.
- [ ] **Step 2:** `just gate`; record the count.
- [ ] **Step 3: Re-audit:** the interfaces of Plan 0070 exist as written (`rg -n "def write_contact|def open_commissioning|def importer_window_open|class ConflictPolicy|IMPORT_ASSISTED|IMPORT_CHANNELS" server/src`);
  `rg -n "_fold_name|def comparison_key|def normalize_spanish" server scripts`; the architecture guards that say which
  package may import which (`tests/unit/test_architecture_guards.py`): confirm that a top-level `server/text_keys.py`
  with no imports from `cognition` or `memory` is importable from both; `rg -n "def get_active_owner_pin_credential|def read_personal_setup_status" server/src`;
  how `db.py` can expose the latest schema version; the channel guard. Read `scripts/reset_db.ps1` again. A difference is
  reported before code.

## Task 1: One module of text keys

**Files:** new `server/src/server/text_keys.py`; `server/src/server/cognition/intent_resolution.py`,
`server/src/server/memory/{candidate_classifier,preference_gate,declarative,canonical_writer,legacy_v4_migration}.py`,
`server/src/server/personal_setup.py`, `scripts/eval_consolidation.py`; tests new `tests/unit/test_text_keys.py`,
`tests/integration/test_canonical_writer_folding.py`.

**Interfaces — Produces:** `fold_name(name: str) -> str` (accent- and case-insensitive); `normalize_spanish(text: str)
-> str` (moved unchanged from `cognition/intent_resolution.py`, which imports it back); `comparison_key(phrase: str) ->
str` (folded, without a leading article; empty when nothing remains); `ARTICLES` if the key needs it. The module imports
nothing from `cognition` or `memory`.

- [ ] **Step 1: Failing tests.** `fold_name("José")` equals `fold_name("jose")`; the key of «El Café» equals the key of
  «café»; an article-only or punctuation-only phrase gives `""`. *Pinned limit:* «C++» and «C#» both give `c`. Writer: a taste
  promoted by voice as «El Café» and then written by `write_literal(likes, "café", IMPORT_ASSISTED)` leaves **one** row, in
  both orders; two different tastes stay two; an ISO date and an integer compare exactly; when either key is empty the
  comparison is exact. `promote` behaves as before. **Expected RED:** the module does not exist; two rows exist.
- [ ] **Step 2: Implement.** Move the functions; replace the copies in `declarative`, `personal_setup`, `legacy_v4_migration` and
  `scripts/eval_consolidation.py` (it imports a private name today); the writer compares `LiteralFormat.TEXT` values by key.
- [ ] **Step 3:** run the new files, `tests/integration/test_canonical_writer_*.py`, `test_memory_writer.py`, the Plan 0063 dialogue
  tests, `test_personal_setup.py`, the legacy migration tests, the intent tests, the architecture guards; ruff over `server scripts tests`.
- [ ] **Step 4: Commit** `refactor(server): one folding module for names and values (plan 0071)`.

## Task 2: The seed file and its reader (pure)

**Files:** new `server/src/server/memory/seed_file.py`; `server/src/server/exceptions.py`; tests new
`tests/unit/test_seed_file.py` (text in, no disk) and `tests/integration/test_seed_file_loading.py` (files on disk).

**Interfaces — Produces:** frozen pydantic models for the owner, partner, children, pets, relatives, contacts and the file
(`extra="forbid"`, tuples for lists, `repr=False` on every sensitive field); `MAX_SEED_BYTES = 262144`;
`parse_seed_text(text: str) -> SeedFile`; `load_seed_file(path: Path) -> LoadedSeed` where `LoadedSeed(seed, sha256)` is a frozen
wrapper; `exceptions.SeedFileError(ValueError)` whose message is a list of `field.path: reason` pairs.

- [ ] **Step 1: Failing tests** (canaries only). A complete valid file parses with every field of the schema above, and a file with
  only the owner's name parses. Each raises `SeedFileError`: no `schema_version`, or 2; a `pool_version` greater than the supported
  one; an unknown key at any level (`photo`, `audio`, `access_code`, `rut`, `language`); a child without `guardianship` or with
  `"teen"`; an adult child with `likes` or `birth_date`; `birth_date` with `stated_age`; a bad date (`"1950-13-01"`, a year alone);
  `stated_age` 131; an option outside a choice (`"quizas"`); a relative or the partner with any key but `name`; a contact with a
  phone or `phone_alt` in local format, an unknown role, a call order below 1 or repeated, or a `relationship` of 41 characters; a
  contact or `[[withhold]]` entry named like the owner or like a pet; a name repeated among the owner, partner, children and
  relative lists (a contact or `[[withhold]]` name may repeat a person's name); a name of 81 characters or with
  a control character; 21 children; 51 values; a value of 201 characters; `secrets` with four digits; a value both in `likes` and in
  `dislikes`; a status for a section that has items (other than `provided`); a status outside the five; invalid TOML. From disk: a
  file over `MAX_SEED_BYTES` (checked from the size before reading), invalid UTF-8, a path that does not exist, and a path that is a
  directory. **No error message, `repr` or `__cause__` contains the offending value**: a canary in each failing field is absent from
  `str(error)`, `repr(error)` and the formatted traceback. **Expected RED:** the module does not exist.
  *The schema as a contract:* `SeedFile.model_json_schema()` equals the committed `docs/examples/seed-household.schema.json` (a test fails
  when the model changes and the file does not), and the schema carries the `schema_version` and the `pool_version`; this file is what the
  Excel converter, a future form and a future SaaS validate against, so no front end re-implements the rules (ADR 0025 decision 11).
- [ ] **Step 2: Implement.** Decode, `tomllib.loads`, validate with the models and the registry's normalizers inside validators;
  rebuild the message from the pydantic `loc` and `type` and raise `from None`; for TOML errors keep only the line number. No database access.
  Write the JSON Schema file from the model (the command of Task 6a prints it).
- [ ] **Step 3:** run both files; ruff, mypy and pyright; the module stays near 200 lines (split the member models into a second module if not).
- [ ] **Step 4: Commit** `feat(server): read and validate the seed file (plan 0071)`.

## Task 3: The plan of operations (pure)

**Files:** new `server/src/server/memory/seed_plan.py`; tests new `tests/unit/test_seed_plan.py`.

**Interfaces — Consumes:** `SeedFile`, `text_keys.fold_name`, `declarative.Guardianship`, the section enum of Plan 0070.
**Produces:** `OperationKind(StrEnum)` (`create_entity`, `write_relation`, `write_literal`, `write_contact`; the statuses are not
operations: they travel in `SeedPlan.section_statuses` and are stored by Task 4b);
`SeedRole(StrEnum)`; frozen `SeedRef(role, key)`; frozen `SeedOperation(kind, subject, predicate, target, value, entity_name,
entity_type, import_key, attributes, label)` (`repr` omits `value` and `entity_name`; `label` is safe, such as `child.likes`);
`SeedPlan(operations, section_statuses)` with `counts()`; `build_plan(seed: SeedFile) -> SeedPlan`.

- [ ] **Step 1: Failing tests.** For a full file the plan lists, in order, one `create_entity` per distinct person name other than
  the owner (the partner, children, relatives, and any contact or `[[withhold]]` name not already listed) and per pet (people typed
  `person`, pets `other`); then the membership relations (`child_of`, `partner_of`, `pet_of`); then the relative relations and
  `withhold_from`; then the literals (owner, children, pets); then the contacts; then the statuses. Import keys are
  `seed-v1:<role>:<folded name>`, identical on two builds and independent of the order of other members. An adult child's entity
  carries `guardianship=adult`, a minor's `minor`; an adult child yields no literal; a relative yields no literal; the owner yields
  no `create_entity`; a contact named like a child points at that child (no second entity); a name used by a contact and by
  `[[withhold]]` is one entity. Every file key maps to the right predicate (the mapping in D-4 is the test's oracle). The statuses
  follow D-5. `repr` of an operation holds no value or name. **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement** `build_plan` as straight-line code; no database, no clock.
- [ ] **Step 3:** run the file; ruff, mypy and pyright.
- [ ] **Step 4: Commit** `feat(server): plan the operations of a seed load (plan 0071)`.

## Task 4a: The applier: owner, dry run, writes and conflicts

**Files:** new `server/src/server/memory/seed_import.py`; `server/src/server/memory/{relational_v4,declarative,care_contacts}.py`
(one counting function each); `server/src/server/exceptions.py`; `tests/unit/test_architecture_guards.py`; tests new
`tests/integration/test_seed_import.py`.

**Interfaces — Consumes:** Tasks 2 and 3; from Plan 0070 the three writers with `on_conflict`, `confirmed_by_owner` and
`manage_transaction=False`, `create_third_party(attributes=...)`, `WriteChannel.IMPORT_ASSISTED`; `read_personal_setup_status`,
`get_active_owner_pin_credential`, `get_person_label`, `fold_name`. **Produces:** `count_v4_rows() -> V4Counts`,
`count_entities() -> int`, `count_active_contacts() -> int`; `OperationStatus(StrEnum)` (`written`, `unchanged`, `refused`,
`skipped`); frozen `OperationOutcome(operation, status, reason)`; frozen `SeedReport(outcomes, statuses, rows_before, rows_after, applied,
record_id)` with `problems` (`statuses` are the section statuses the run records or, in a dry run, would record); `SeedOwnerError(ValueError)` (reasons `owner_not_ready`, `owner_name_mismatch`);
`async resolve_ready_owner(expected_name: str) -> int`; `async run_operations(plan: SeedPlan, *, owner_entity_id: int, now: str,
confirmed_by_owner: bool) -> tuple[OperationOutcome, ...]` (runs inside the caller's transaction; the policy is `REFUSE`). The
architecture guard fails when any module but `write_types.py` and `seed_import.py` names `IMPORT_FILE`, `IMPORT_ASSISTED` or the
strings `"import_file"` and `"import_assisted"` in code (docstrings excepted; found with `ast`); the retraction uses `IMPORT_CHANNELS`.

- [ ] **Step 1: Failing tests** (temporary SQLite; an owner set up as `personal-setup` does, with no children; invented data).
  *Owner:* with no owner, no credential, two owners, or a stored owner whose folded name differs, `resolve_ready_owner` raises
  `SeedOwnerError` with the stated reason and **nothing is created**. *Writes:* the full plan writes the entities, relations,
  literals and contacts with the channel `import_assisted`, the owner as asserter, the classification the writer assigns (the owner's
  facts `personal`, a child's and a pet's `household`, a relative `personal`); `asserted_at` is the `now` it is given. *Statuses of
  operations:* `written` or `unchanged` comes from the row counts before and after each operation. *Idempotent:* applying the same
  plan twice leaves identical counts and the second run is all `unchanged`, **a caregiver child who is also a contact included**.
  *Conflict:* a stored `birth_date` that differs, a different active partner, a changed `guardianship`, or an existing entity with a
  child's folded name (a homonym, or a child made by `personal-setup`) yields `refused` (`value_conflict`, `value_conflict`,
  `guardianship_conflict`, `entity_exists`), the dependents of a failed entity are `skipped` (`dependency_failed`), and the whole
  list of problems is reported. A contact whose call order is taken is `refused` (`order_taken`); a different phone, second phone,
  order or flag for a known contact and role is `refused` (`value_conflict`). *Secrets:* `secrets` are stored `personal`/`security`; the outcomes' `repr`, every log record and its
  `extra` hold no name, value or phone (`caplog` at DEBUG). **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement.** Catch, **per operation**, exactly `WriteRefusedError` (its reason), `AmbiguousEntityError`
  (`entity_exists`), `UnstorableValueError` (`unstorable_value`) and the registry's validation `ValueError` raised for one value
  (`invalid_value`); catch nothing else. Map `SeedRef` to ids as entities are created.
- [ ] **Step 3:** run the file, `tests/integration/test_canonical_writer_*.py`, `test_care_contacts.py`, the architecture guards;
  ruff, mypy and pyright.
- [ ] **Step 4: Commit** `feat(server): apply a seed plan, operation by operation (plan 0071)`.

## Task 4b: The transaction, the record and the owner's review

**Files:** `server/src/server/memory/seed_import.py`; tests `tests/integration/test_seed_import_transaction.py`.

**Interfaces — Produces:** `async run_seed(loaded: LoadedSeed, plan: SeedPlan, *, owner_entity_id: int, commit: bool, approved:
bool, commissioning: CommissioningInput | None, replace: bool, now: str) -> SeedReport`. `approved` is the interviewer's answer to the
review question; `commissioning` is required only when no record is open (the first apply) and is ignored afterwards: a second
apply reads the confirmation mode from `get_open_commissioning()` and derives `confirmed_by_owner` from it. The
commissioning calls (`open_commissioning`, `record_import`, `set_section_status`) run **outside** the per-operation `try` of
Task 4a, so a `CommissioningError` is never swallowed.

- [ ] **Step 1: Failing tests.** *Dry run:* `commit=False` returns `applied=False`, every outcome `written` or `unchanged`,
  `rows_after` counted **inside the transaction before the rollback**, and no entity, row, contact or record persisted; it opens
  nothing and stores no status (the report lists the statuses it would record). *Apply:* with `commit=True` and `approved=True`
  it writes, opens the record with the given label, role, mode and declaration (or reuses the open one), stores the file's hash and
  the counts, and records each section's status; in `representative` mode the rows' `confirmed_by_entity_id` is `NULL`, **also on a second apply that passes
  `commissioning=None`** (the mode is read from the open record).
  `commit=True` with `approved=False`, or with no record open and `commissioning=None`, raises and writes nothing. Any problem
  rolls everything back, **the record included**. A half-way failure injected in an operation (an unexpected error) leaves no
  row and no record and propagates. A closed record makes `run_seed` raise `CommissioningClosedError` before anything else. The
  run does not read `memory_enabled` (`MEMORY_ENABLED=false` still imports). The final log line holds the record id, the first
  12 hex digits of the hash, counts and the database path only. **Expected RED:** `run_seed` does not exist.
- [ ] **Step 2: Implement** one `db.transaction()` around the operations and the commissioning calls; roll back by a private exception
  raised inside it when there is any problem or `commit` is false, caught outside.
- [ ] **Step 3:** run the new file and `test_seed_import.py`, `test_commissioning.py`, the architecture guards; ruff, mypy and pyright.
- [ ] **Step 4: Commit** `feat(server): run a seed load in one transaction (plan 0071)`.

## Task 5a: The deleting and counting functions of the replacement

**Files:** `server/src/server/memory/{relational_v4,care_contacts,commissioning,candidates,declarative}.py` (one or two functions
each); tests new `tests/integration/test_seed_retraction_repositories.py`, `tests/integration/test_entity_references.py`.

**Interfaces — Produces** (all joinable with `manage_transaction=False`):
`relational_v4.delete_rows_by_channel(channels: Collection[str]) -> int`, `relational_v4.count_rows_by_channel(channels:
Collection[str]) -> int` and `relational_v4.entity_has_rows(entity_id: int) -> bool`; `care_contacts.delete_contacts_by_channel(channels:
Collection[str]) -> int`; `candidates.count_live_candidates() -> int` (the candidates that still hold a value, ADR 0021: a resolved one
has been erased); `commissioning.clear_section_statuses(record_id: int) -> None`;
`declarative.delete_orphan_import_entities(has_rows: Callable[[int], Awaitable[bool]], has_contacts: Callable[[int], Awaitable[bool]])
-> int` (deletes an entity whose `import_key` starts with `seed-v1:` when neither callback finds anything).

- [ ] **Step 1: Failing tests.** Each function does what its name says on a temporary database: deleting by channel leaves rows of
  other channels untouched; the counts agree; `entity_has_rows` sees a V4 row on either end of a relation; the orphan deletion removes
  an import-created entity that nothing refers to and keeps one that a callback reports. *Reference list:* a test reads
  `PRAGMA foreign_key_list` of **every table** and fails unless each table that refers to `entities` is in an explicit allowlist with its
  reason: (a) **checked by the cleanup**: `literal_facts_v4`, `entity_relations_v4`, `care_contacts`; (b) **`ON DELETE CASCADE`, covered by
  the refusal to replace once the robot learned by voice**: `memory_candidates` and the legacy `facts`; (c) **`RESTRICT`, `NO ACTION` or
  `SET NULL`, which fail loudly or are harmless**: every other table (face, voice and consent tables, role assignments, credentials,
  authorization events, commissioning). A new table that refers to `entities` fails the test until someone classifies it.
  **Expected RED:** the functions do not exist.
- [ ] **Step 2: Implement.** The SQL stays in the owning repositories; the cleanup never relies on `ON DELETE CASCADE` to decide what is safe.
- [ ] **Step 3:** run the new files and the architecture guards; ruff, mypy and pyright.
- [ ] **Step 4: Commit** `feat(server): add the repository functions for a replacement (plan 0071)`.

## Task 5b: Retract what an earlier import wrote

**Files:** new `server/src/server/memory/seed_replace.py`; `server/src/server/memory/seed_import.py`; tests new
`tests/integration/test_seed_replace.py`.

**Interfaces — Consumes:** Task 5a; `write_types.IMPORT_CHANNELS` and `VOICE_CHANNELS` (Plan 0070). **Produces:**
`seed_replace.assert_no_voice_memory() -> None` (raises a closed `ReplaceRefusedError(ValueError)` when `count_rows_by_channel(VOICE_CHANNELS)`
or `count_live_candidates()` is above zero); `seed_replace.retract_earlier_import() -> int` (in this order: V4 rows, contacts, section
statuses, then entities); `run_seed(..., replace=True)` runs `assert_no_voice_memory`, then the retraction, then the operations with the
refuse policy, inside the transaction.

- [ ] **Step 1: Failing tests.** In an open window a first apply, then a changed file with `replace=True`: the earlier rows (V4
  literals and relations, contacts, statuses) are gone and the new ones written, **with the refuse policy** (a birth date changed in the
  file simply takes the place of the retracted one); an entity created by the import that nothing refers to is deleted; **with a voice row
  stored first (or a live candidate) `replace=True` raises `ReplaceRefusedError` and nothing is retracted**; `replace=True` with a closed
  record raises `CommissioningClosedError`; `replace=True` with no earlier import is harmless; a retraction followed by a refusal rolls back
  the retraction too. A `guardianship` that differs from the stored one on an entity that still exists after the retraction is
  `guardianship_conflict`. **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** run the new file and the earlier seed tests, the architecture guards; ruff, mypy and pyright.
- [ ] **Step 4: Commit** `feat(server): replace what an earlier import wrote (plan 0071)`.

## Task 6a: The command

**Files:** new `server/src/server/seed_cli.py`; `server/src/server/db.py` (a public `latest_schema_version()`);
`server/pyproject.toml` (`seed-import = "server.seed_cli:main"`); `justfile` (recipe `seed-import *ARGS`, ASCII-only echo,
Spanish comment); tests new `tests/integration/test_seed_cli.py`.

**Interfaces — Produces:** `async run_seed_command(path: Path, *, apply: bool, replace: bool, commissioning: CommissioningInput | None,
read_text, write_text, now) -> int` (the exit code; the adapters injected like `run_personal_setup_wizard`); `main() -> None`, which
does the **synchronous** health probe (`httpx.get` on `/health`, the port from the settings, a 2 s timeout) **before** `asyncio.run`
and refuses when the server answers.

- [ ] **Step 1: Failing tests.** *Without `--apply`:* the report is printed (values included, in Spanish), nothing is written, the exit
  is 0 with no problems and 1 with problems, and the first line prints the database about to be used. *With `--apply`:* it prints the
  report and asks the review question, worded by the mode («¿La persona titular revisó este resumen y lo aprueba?» or, for
  `representative`, «¿La persona que representa a la titular revisó este resumen y lo aprueba?»), then «Escribe SI para aplicar:»; it
  writes only on exactly `SI`, anything else prints «Carga cancelada.» and writes nothing; a problem in the dry run never reaches the
  question; the first apply without `--interviewer`, `--role` or `--mode` is refused with a closed message, as is `--mode
  builder_is_owner` with a role other than `builder`. *Refusals* (each prints its closed message and exits 1, and nothing is created
  or migrated): the database file does not exist; the schema version is not the latest (the message names `just setup-personal
  status`); no ready owner; the owner's name differs; the file has an error; the file name ends in `.example.toml` and `--apply`
  is given («copia la plantilla a data/seed/»); a closed commissioning; `--replace` with voice memory. A path inside the repository
  outside `data/` prints a warning. A locked database prints the same message as `personal-setup`. The summary reminds the
  interviewer that the file holds real data and was not deleted, that it must be created on this machine only, and that the report
  stays in the terminal's scrollback («limpia la pantalla»). The probe's refusal is tested through `main()` with the probe stubbed.
  **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement.** `argparse` with `path` as `nargs="+"` joined with spaces (the rule for `just` on Windows); the command opens
  the database without creating it and never runs migrations; `now` is UTC ISO 8601 with microseconds like the other writers.
- [ ] **Step 3:** run the new tests and ruff over `server/src scripts tests`.
- [ ] **Step 4: Commit** `feat(server): add the seed-import command (plan 0071)`.

## Task 6b: The example that is also the questionnaire

**Files:** new `docs/examples/seed-household.example.toml`; tests `tests/integration/test_seed_example.py`.

- [ ] **Step 1: Failing test.** The example parses, builds a plan and passes a dry run on a prepared temporary database; every key carries
  its question as a Spanish comment (tuteo neutro, no voseo: a test greps the comments for voseo forms), including «nunca escribas el
  código, solo quién lo sabe» and «aquí sí van los números» next to `address`; it holds only invented names and phones; the file name
  ends in `.example.toml`. **Expected RED:** the example does not exist.
- [ ] **Step 2:** write it from the schema above (all eleven sections, one status entry, one caregiver child who is also a contact).
- [ ] **Step 3:** run the test; `just seed-import docs/examples/seed-household.example.toml` against a prepared scratch database with `BRAIN_DB_PATH`
  and the server stopped prints a dry run.
- [ ] **Step 4: Commit** `docs: add the seed-household example and questionnaire (plan 0071)`.

## Task 7: `reset-db` respects `BRAIN_DB_PATH` (not automated)

**Files:** `scripts/reset_db.ps1`. No automated test exists for the script (it is PowerShell); the checks are manual and recorded.

- [ ] **Step 1:** `Resolve-DbPath` with the order `BRAIN_DB_PATH` in the environment, then in `.env` (the pattern of `Resolve-ServerPort`), then
  `data/omnibot.db`; print the resolved database and the backup folder before doing anything; copy the `-wal` and `-shm` sidecars into the backup when
  they exist (they are deleted afterwards); after the backup print «Esta copia contiene datos biometricos y de salud. El sistema no la borra: anota su
  ruta y la fecha en que la destruiras.» (ASCII only, per `scripts-powershell.md`).
- [ ] **Step 2:** verify by hand on a scratch database: with `BRAIN_DB_PATH=data/scratch-reset.db` set, `just reset-db` backs up (with the `-wal`) and
  deletes **that** file and leaves `data/omnibot.db` untouched; with it unset it targets `data/omnibot.db` as before (use a copy, never the real file).
  Record both outcomes.
- [ ] **Step 3: Commit** `fix(scripts): make reset-db honour BRAIN_DB_PATH (plan 0071)`.

## Task 8: Documentation truth and acceptance (text only, no RED)

- [ ] ADR 0021 and ADR 0022 pointers; [`seed-data-pool.md`](../../architecture/seed-data-pool.md) *Plan* column true; `identity-and-access.md` (the level of
  each channel, the importer bypasses the policy and why); `memory-and-world-state.md`; `current-state.md` and its Archify diagram (validate, then deliver);
  the roadmap's Step 0 row; `docs/plans/README.md`; `docs/plans/open/README.md`; `server/README.md` (one paragraph on `seed-import` and the commissioning
  order); the local tracking table (never committed). Move this plan to `completed/` with its execution record. ADR 0024 stays `Proposed` until Plan 0072 closes.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, `uv run python scripts/check_reserved_terms.py`, every relative link resolves, `just gate`.
- [ ] **Acceptance by Pipec on a database kept apart** (outcomes only, never values, in `docs/evals/0071-seed-import-acceptance.md`): set `BRAIN_DB_PATH` to a
  scratch file; `just setup-personal` with the owner and no children; copy the example to `data/seed/`; `just seed-import <path>` (dry run); `... --apply
  --interviewer <label> --role builder --mode builder_is_owner` and `SI`; the same again (all `unchanged`); change one birth date and run without `--replace`
  (a conflict, nothing written); with `--replace` (replaced); start the server and ask for the number of children (the one answer the household reader gives
  today); stop it; `just reset-db` on the scratch path deletes only the scratch file. Everything else the file holds cannot be asked by voice until CM-5: say so.
- [ ] Commit `docs: close plan 0071`; PR; merge only with Pipec's go-ahead.

## ADR 0024 coverage

| ADR 0024 | Where |
|---|---|
| 6 the assisted channel, the record, the owner's review | Tasks 4b, 6a |
| 7 the level of each channel; the bypass stated | Tasks 4a, 8 |
| 8 replacement while commissioning, none after | Tasks 4b, 5 |
| 11 who may import | Tasks 4a, 6a |
| 12 one comparison for duplicates | Task 1 |
| 13 the reset and the backup note | Task 7 |
| 14, 15 and the rest of 13 | Plan 0072 |

## Completion criteria

1. Tasks 0 to 8 done, one commit per task, every code test RED before GREEN (Tasks 7 and 8 declared).
2. `just gate` green; the Plan 0062, 0063, 0065 and 0070 tests unchanged.
3. The dry run is the default; nothing is applied without the owner's review answer; the same file twice changes nothing; a conflict or a failure writes
   nothing; a replacement keeps the voice rows and refuses when there are any; no value, phone or name reaches a log.
4. The acceptance record exists with outcomes only.

## Rollback boundary

Each task is one commit and there is no migration. Rows already written by an applied load stay until the commissioning is closed (`--replace` removes them);
after that, correcting and forgetting are CM-6. Task 1 touches several files: revert it as one commit.

## Not here, and why

- **Closing the commissioning from a command, enrolling face and voice in one flow, the voice session, the readiness report, the acta file, the baseline
  backup:** [Plan 0072](0072-commissioning-session.md). Until then the window stays open and `--replace` stays available.
- **Reading the loaded data by voice or by an alert:** CM-5 and the care ADR.
- **The amendment path for contacts and medications after the closing:** a plan before the care capabilities (ADR 0024 decision 8).
- **The interview's interface and the 107-question catalogue:** a later Step 0 plan.
- **Adopting an existing entity as a child, or two entities with one name:** a conflict; the interviewer loads the children with the file.
- **Places and `lives_in`, a structured medication schedule, a `beliefs` classification:** later.
- **A representative importing for the owner:** the `family` profile and legal advice.

## Execution record (2026-10-26)

Executed by Claude Code on branch `feat/0071-seed-file-importer` from `main` at `8992039`, one commit
per task: Task 1 `2f4df39`, Task 2 `cad2eab`, Task 3 `0ae85df`, Task 4a `dc1d0b1`, Task 4b `fb29f71`,
Task 5a `57769a0`, Task 5b `5b78f51`, Task 6a `b2b8562`, Task 6b `f43113d`, Task 7 `d953dfa`, a late Task 1 fix `ed1606f`
(the import-graph guard of Plan 0050 now lets the cognitive core import the stdlib-only
`server.text_keys`, as ADR 0024 decision 12 decides; the first full gate caught it) and the
documentation of Task 8. Every code test was observed RED first (a missing module or name; Task 1's
writer test also on «two rows»); the architecture guards of Tasks 4a and 5a pass on first run by
nature and their detection tests prove they bite. Baseline `just gate` 4511 passed; branch
`just gate` 4709 passed (lint, mypy, pyright, tests, audit), run with `MEMORY_ENABLED=false`. `uv.lock` did not change.

**Status is unchanged on purpose:** this plan stays `Ready`/`NOW` in `open/` until Pipec's acceptance
on a database kept apart ([record](../../evals/0071-seed-import-acceptance.md), pending) and his
go-ahead to merge; ADR 0024 stays `Proposed` until Plan 0072 closes.

**Decisions taken while executing** (each with what it costs if wrong, in the PR description):

- Task 1: the Plan 0065 test that pinned «idempotence is exact text» was inverted to the folding
  ADR 0024 decision 12 asks for (completion criterion 2 yields to the ADR here).
- Task 2: the member models live in `memory/seed_members.py`; `pool_version` is required; an explicit
  `provided` for a section with no items is refused; children carry `birth_date` or `stated_age` and
  tastes, pets `species`, `stated_age` and tastes (no allergies for either); a pet's name may not
  repeat a person's; validators raise closed `ValueError` words (no `pydantic_core` import, which
  would be a new direct dependency).
- Task 4a/4b: the acta's counts are the rows of each kind the file holds plus `written`; a first apply
  without the declaration raises `CommissioningMissingError`; import rows keep the writer's default
  confidence 0.9.
- Task 6a: the first apply needs all four declaration options; «Carga cancelada.» exits 1; the probe
  targets `127.0.0.1:<SERVER_PORT>`.
- Task 6b: the caregiver contact of the example is an adult child.

**Open:**

- Task 7's `-wal`/`-shm` copy in `just reset-db` could not be exercised: `scripts/scrub_candidates.py`
  runs first and removes the sidecars. The rest of Task 7 was verified by hand (the scratch database
  deleted, `data/omnibot.db` unchanged by hash, the default and the `.env` resolution).
- Deferred minors of the self-review: `memory/seed_import.py` imports `personal_setup` (a command
  module); `seed_file.py` and `seed_import.py` exceed the 200-line guideline; a lapsed candidate not yet
  housekept refuses a replacement (fails closed); the report shows the first phone only; an orphan
  seed entity a face or voice profile refers to stops the cleanup with an `IntegrityError` traceback.
