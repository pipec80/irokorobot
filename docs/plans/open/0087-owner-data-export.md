# 0087 — The export of the owner's data: everything, or everything about one person

> **Status:** **Ready (promoted by Pipec on 2026-11-18)**; `NOW` on the board. Pipec chose the three
> open choices of *Pipec's decisions* at the end, each as recommended. Source:
> [ADR 0032](../../adr/0032-block-c-hygiene-correct-forget-and-years.md) decision 8 (Pipec,
> 2026-11-13), the last piece of block C; when this plan closes, ADR 0032 becomes `Accepted`. Every
> choice fits decision 8: no new ADR (ADR 0040 stays free). **Exporting the pool to the importer's
> TOML is not here** (Pipec, 2026-11-18): it is delivery 8b, with the spreadsheet. One plain branch
> from `main` (`feat/0087-owner-data-export`), one PR.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md`,
> `AGENTS.md` and every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans` (inline), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Task 6, and
> `superpowers:finishing-a-development-branch` at the end. Review agents run on `sonnet` and read
> `.claude/` in full before reading code. **Pipec's rules win over the skills:** one plain branch
> from `main`, never a git worktree; this plan lives under `docs/plans/`. One commit per task; every
> test seen RED for the stated reason first. If evidence contradicts the plan, stop and report; **a
> discovery this plan's goal does not need is recorded, not built.** The Bash tool loses
> backslashes and non-ASCII characters in heredocs: use the Write and Edit tools. Commit titles:
> Conventional Commits, at most 72 characters, check `git log` after each commit; never pipe
> `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI does.
> Never `uv sync` without `--extra cuda`. No `just gate` or full suite in the background while
> Pipec rehearses. Pipec starts the server and the robot. **The real database is touched only in
> Task 7**, after its backup. Before pushing: `pyright`, `ruff` and `mypy` over the whole project,
> `scripts/` linted with explicit paths, `uv run ruff format --check .`.

## What the code does today (verified 2026-11-18 on `main` at `68d3c89`, schema 21)

1. **No whole export.** `iroko-admin` has `list`, `status`, `health`, `audit`, `add`, `change`,
   `revoke`, `change-contact`, `label-parent`, `label-child`, `conversations`, `forget` and
   `archive` (`server/admin_cli.py`). The only export is `conversations export --out DIR [--id N]`
   (`conversation_admin.export_records`): one Markdown file per record, the PIN, one audit row
   `export` / `conversation_record`.
2. **«Everything about one person» already exists for a deletion.**
   `memory/forget_scope.person_scope(owner, *, now, entity_id, words, for_deletion=True)` returns the
   ids an `iroko-admin forget person` deletes: the person's active facts and relations
   (`relational_v4.rows_about_entity`), care contacts, the turns, episodes, recall units and pending
   topics whose words name the person (archived and expired included), and the owner's own facts
   whose value names them (`owner_facts`). It holds no SQL; each table is read through its owner.
3. **`rows_about_entity` reads `lifecycle = 'active'` only**; the history (`superseded`, `revoked`,
   `disputed`, `expired`) has no reader by entity.
4. **`admin_audit` has closed `CHECK`s** (operations `add`, `change`, `revoke`, `grant`, `export`,
   `delete`; kinds `pool_literal`, `pool_relation`, `care_contact`, `conversation_consent`,
   `conversation_record`; migration 013 rebuilt it once). No kind fits «all the data» or «one
   person».
5. **No secret value is stored.** `access_code` is `storable=False` (ADR 0024 decision 4); the
   owner's PIN lives only as a verifier with its salt (`owner_pin_credentials`); a face is a
   `vec_faces` vector, a voiceprint a `voice_profiles.embedding` blob.
6. **The turn verdict is kept per turn** (`verified`, `not_verified`, `not_owner`, `not_checked`):
   a `not_owner` or `not_checked` turn may be another person speaking.
7. **The deletion register** `deletions.jsonl` sits beside the database
   (`deletion_register.register_path()`), one line `{"seq", "kind", "id", "at"}` per deleted row,
   never a value.
8. **The folder guard of the importer** (`seed_cli._warn_about_the_place`) resolves a path and
   compares it with the repository root (`Path(__file__).resolve().parents[3]`); it only warns.
9. **The retired `memories` table** is locked by a trigger and read by nothing (ADR 0027 decision 9).

Task 0 re-verifies each item and **stops and reports** if one is false.

## Decisions

- **D-1 Scope.** ADR 0032 decision 8 as written: `iroko-admin export`, the PIN, the server stopped,
  everything or everything about one person, a readable document in Spanish and the same content as
  JSON, secrets by reference only, one audit row. No TOML (8b), no web administration (after the
  finish line), no wire, route, robot, setting or dependency change.
- **D-2 The command.** `iroko-admin export all [--out <carpeta>]`, `iroko-admin export person <id>
  [--out <carpeta>]` (an entity id of `list`; the owner's own id exports the owner) and
  `iroko-admin export person --name <palabras> [--out <carpeta>]` (a person only talked about), each
  with `--dry-run` and `--actor` (`--out` optional since Pipec's amendment of D-3, 2026-11-19). The order of `forget`: the PIN first (nothing about what is stored
  is shown without it), then the folder check, then one count line per section, then `SI` typed,
  then the two files, then the audit row and «Exportado a {carpeta}: exportacion.md y
  exportacion.json. {reminder}». `--dry-run` stops after the counts. The existing refusal of a
  server that answers `/health` covers «server stopped».
- **D-3 The folder** (Pipec, 2026-11-18; **amended by Pipec on 2026-11-19**: a fixed, protected
  folder that is kept). Without `--out` the export goes to its own new folder
  `data/exports/<instante>-<alcance>/` beside the database (`settings.brain_db_path.parent`,
  git-ignored, the future Docker volume): `20261119T120000Z-todo`, `…-persona-<id>` or `…-persona`
  (never a name in a path). `--out` is optional and resolved (`Path.resolve()`, so `..`, a relative
  path and a junction are seen as what they are). Refused, with a closed phrase and nothing
  written: a path inside the repository or the database's directory that is not under
  `data/exports/` (the code, the database, the register, the backups); an existing file; an
  existing folder that is not empty. A missing folder is created (parents too), readable and
  writable by the server's user only (`0700`, the files `0600`; on Windows it inherits the data
  directory's permissions). The folders are kept until the operator deletes them; encrypting them
  is ADR 0033's. Inside it exactly two
  files, UTF-8 with `\n`: `exportacion.md` and `exportacion.json`; the scope, the instant and the
  schema version go in the header of both. A failure while writing removes what this run wrote
  (both files, and the folder if this run created it), prints «No se pudo escribir la exportación:
  no quedó nada a medias.» and audits `refused` with reason `write`.
- **D-4 One content, two renderings.** `memory/export_model.py` holds the frozen model: a document
  is its scope, `generated_at`, `schema_version` and an ordered tuple of sections; a section is a
  `key`, a Spanish `title`, its columns (`key` in English, Spanish `label`) and its rows, each cell
  `str | int | None`. Both files are rendered from the one model (`memory/export_files.py`): the
  JSON is `{"format": "iroko-export", "version": 1, "scope": {...}, "generated_at": ...,
  "schema_version": ..., "sections": [{"key", "title", "columns", "rows": [{column key: cell}]}]}`
  (`ensure_ascii=False`, `indent=2`); the Markdown is a header, then per section `## {title}`, the
  row count and one table (header from the labels; a cell's `\`, `|` and line breaks escaped as
  `\\`, `\|` and `<br>`; `None` as `—`; an empty section says «Sin filas.»). A stored code (a
  lifecycle, a sensitivity, a verdict) is the same string in both; the document ends with a closed
  glossary «Qué significa cada valor» that translates every code. So «the same content» is testable:
  parsing the Markdown tables back gives exactly the JSON rows.
- **D-5 The sections of «todo»**, in this order, each read through its owner module (the rows, the
  history and what is archived; `archived_at` is a column of its rows, Pipec 2026-11-18):
  `personas` (entities: id, name, type, aliases, role, created), `datos` (every literal fact, all
  lifecycles: subject's name, predicate, value, lifecycle, sensitivity, visibility, validity, asserted,
  confirmed, superseded by and at, archived, channel), `relaciones` (the same, with both ends'
  names), `contactos` (every care contact, revoked included, phones included: a phone is the
  owner's data, not a secret), `roles`, `consentimientos` (conversation, face and voice grants),
  `credenciales` (the PIN as a reference: person, algorithm, created, updated, revoked; **never** the
  salt, the parameters or the verifier), `perfiles` (face and voice profiles as references: person,
  label, model, created; **never** a vector or an embedding), `conversaciones` (record metadata),
  `turnos` (id, record, instant, verdict, heard, said), `diario` (episodes: record, summary,
  sensitivity, created), `recuerdos` (recall units: kind, body, sensitivity, occurred interval,
  archived; no vector), `temas_pendientes`, `por_confirmar` (live memory candidates), `acta` (the
  commissioning records and their section statuses), `auditoria_admin`, `decisiones` (the policy's
  `authorization_audit_events`), `borrados` (the deletion register's lines as stored: seq, kind,
  id, instant; Pipec 2026-11-18) and `no_sale` (what is not exported and why, with its row count:
  the FTS5 and vector projections, `vec_faces`, the voice embeddings, the PIN verifier, `meta`, the
  retired `memories`). The audit row of the export itself is written after the files, so it is not
  in them (the header says so).
- **D-6 «Everything about one person»** (Pipec, 2026-11-18: «igual que forget»). The scope is
  `person_scope(..., for_deletion=True)`, so an export shows what `forget person` would delete,
  plus the person's identity rows (entity, role, consents, credential and profile references,
  the `admin_audit` rows whose `target_entity_id` is the person and the `decisiones` rows where
  the person is actor or target), with the facts and relations read **with their history**. Never in
  a person's export: a fact or relation whose **subject is another person**, so `owner_facts` is
  left out (a relation names its other end by name only); a turn whose verdict is `not_owner` or
  `not_checked` (it may be another adult's words); `borrados` (a deleted id can no longer be tied to
  anyone). For **the owner**: the owner's entity, facts, relations, contacts, roles, consents,
  references, every record with its turns of verdict `verified` or `not_verified`, the whole diary,
  the units, topics and live candidates, the acta, the `admin_audit` rows (all were run under the
  owner's PIN) and the owner's `decisiones`. An episode goes whole (a summary cannot be partly
  unsaid, ADR 0032 decision 2). Each excluded class appears in `no_sale` as a count. Nothing found:
  «No hay nada guardado de esa persona.», nothing written, audited `refused` with reason `empty`.
- **D-7 The audit row** (migration 022). `admin_audit` is rebuilt as migration 013 did, adding the
  target kind `household_data`; every row and index is kept. One row per export attempt: operation
  `export`, kind `household_data`, `field_id` `all`, `person:<id>` or `person` (a name only),
  `target_entity_id` the person or `NULL`, outcome `applied` or `refused`, reason `pin`, `place`,
  `empty` or `write`. No value, no name, no path. The data dictionary entry follows.
- **D-8 The existing `conversations export` stays as it is.** Merging it into `export` is deferred
  (trigger: Pipec asks, or a second export path diverges).
- **D-9 The operator manual** gets the command, the folder rules (`data/exports/` by default and
  kept there, `--out` for another new or empty folder), what each section holds, what is never
  exported, and that the files hold personal data: keep them on an encrypted disk, never in a
  synced folder, delete them after use (ADR 0032 decision 8, last sentence).

## Deferred, with their triggers

| Deferred | Its trigger | Owner |
|---|---|---|
| Exporting the pool to the importer's TOML | Delivery 8b | 8b |
| Exporting from a browser | The remote dashboard, after the finish line | ADR 0025, remote half |
| Encrypting the export files | ADR 0033 encrypts the backups, or Pipec asks | ADR 0033 |
| One export command instead of two (`conversations export`) | Pipec asks, or the two diverge | — |
| Exporting the retired `memories` rows | Task 0 counts rows in it on the real database | Pipec decides there |
| A person's export that leaves out the owner's stories that name them | A real request by someone other than the owner | — |

**Goal.** With the PIN and the server stopped, `iroko-admin export` writes everything the robot
keeps, or everything about one person, to a new folder outside the repository, as `exportacion.md`
(Spanish, sections and tables) and `exportacion.json` with exactly the same rows; no secret value,
no vector, no other adult's private data in a person's export; one audit row each time.

**Tech stack.** Python 3.12, aiosqlite, `json` and `pathlib` of the standard library, pytest. No new
dependency or setting.

**Spec.** ADR 0032 decision 8; ADR 0024 decision 4 (a secret is never stored); ADR 0025 (the local
path); ADR 0006 (an owner does not receive another adult's private data);
[guardrails](../../architecture/implementation-guardrails.md);
[data dictionary](../../architecture/data-dictionary.md).

**Required reading.** The above, then the code: `admin_cli.py`, `conversation_admin.py`,
`memory/forget_scope.py`, `memory/admin_forget.py`, `memory/admin_audit.py`,
`memory/migration_013_conversation_record.sql` (the audit rebuild), `memory/deletion_register.py`,
`relational_v4.py`, `declarative.py`, `care_contacts.py`, `conversation_record.py`,
`conversation_episodes.py`, `recall_store.py`, `pending_store.py`, `candidates.py`,
`commissioning.py`, `household_authorization.py`, `owner_credentials.py`, the three consent modules,
`vision/faces.py`, `voice/voiceprints.py`, `seed_cli.py` (the repository root), `db.py`; the tests
of each.

## Global constraints

- English code and docstrings; no `Any`, no `print` (the CLI's existing `# noqa: T201` pattern
  excepted), no `os.path`, no bare `except`; logging with `%`.
- SQL only in each table's owner module (the architecture guard); the export modules hold none.
- Counts and ids only in logs and the audit; a value, a name or a path never reaches a log line.
- Every other `iroko-admin` command, every route, prompt and reply is byte-identical to `main`.
- No real household data: invented canaries only (Canaria, Gaviota, el té, `+56900000000`);
  `scripts/check_reserved_terms.py` passes.

## Review focus

1. **Another adult's private fact in a person's export**: exporting a child related to a second
   adult never shows that adult's `private` or `medical` fact, nor an owner's fact that names the
   child (Task 3).
2. **Another person's words in a person's export**: a `not_owner` turn that names the person is in
   «todo» and absent from the person's and the owner's export (Task 3).
3. **A cell that breaks the table**: a turn with `|`, a line break, a backslash or Markdown in it
   keeps the table whole, and the parity test still passes (Task 4).
4. **A folder that is not what it looks like**: `..` back into the repository, a relative path, the
   data directory, an existing file, a non-empty folder: refused, nothing written (Task 4).
5. **A failure halfway**: the JSON written and the Markdown refused by the disk: nothing left, one
   `refused` audit row (Task 5).

---

## Permitted files

Paths under `server/src/server/` unless they start with `tests/`, `docs/` or the root; a need
outside the list stops the plan for Pipec.

| Task | Files |
|---|---|
| 1 | `memory/migration_022_export_audit.sql` (new), `db.py` (the migration list), `memory/admin_audit.py`, `docs/architecture/data-dictionary.md`; `tests/integration/test_migration_022.py` (new), the audit tests |
| 2 | `relational_v4.py`, `declarative.py`, `care_contacts.py`, `conversation_record.py`, `conversation_episodes.py`, `recall_store.py`, `pending_store.py`, `candidates.py`, `commissioning.py`, `household_authorization.py`, `owner_credentials.py`, `biometric_consent.py`, `voice_consent.py`, `conversation_consent.py`, `vision/faces.py`, `voice/voiceprints.py`, `memory/admin_audit.py`, `memory/deletion_register.py`; `tests/integration/test_export_readers.py` (new) |
| 3 | `memory/export_model.py` (new), `memory/data_export.py` (new), `memory/forget_scope.py`; `tests/integration/test_data_export.py` (new) |
| 4 | `memory/export_files.py` (new); `tests/unit/test_export_files.py` (new) |
| 5 | `admin_cli.py`; `tests/integration/test_admin_export.py` (new) |
| 7 | `docs/architecture/current-state.md`, `docs/architecture/data-dictionary.md`, the Archify memory diagram, `docs/runbooks/operator-manual.md`, `docs/evals/0087-export-acceptance.md` (new), ADR 0032 and the ADR index, the plan board, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, the roadmap (row 8), both delivery maps, Pipec's local `docs/roadmap/tabla-tareas.md` |

**Rollback boundary.** Before the merge, the branch. After it, a revert: migration 022 only widens a
`CHECK` the old code never writes past; the export files are outside the repository and the data
directory. The real data: the `pre-0087` backup of Task 7.

---

## Task 0: Re-audit and baseline

- [ ] **Step 1:** `git checkout main && git pull`, create `feat/0087-owner-data-export`; confirm 022
  is the next migration.
- [ ] **Step 2:** verify items 1 to 9 of *What the code does today* and **stop and report** if one
  is false.
- [ ] **Step 3:** with the server stopped, on a copy of the real database opened `immutable=1`
  (deleted the same day), counts only, one per table of D-5, the retired `memories` among them.
  **If `memories` holds a row, stop and ask Pipec** whether it is exported or deleted.
- [ ] **Step 4:** baseline: `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and
  not eval" -q -n auto`.

## Task 1: The audit kind of an export

**Interfaces:** `TargetKind.HOUSEHOLD_DATA = "household_data"`;
`async def record_admin_operation(...)` unchanged.

- [ ] **Step 1: Write the failing tests:** migration 022 accepts an `export` / `household_data` row
  and still refuses an unknown kind; every row and both indexes of a database at 21 survive it
  (`test_migration_022_keeps_every_audit_row`); the data dictionary guard passes.
- [ ] **Step 2:** FAIL. **Step 3:** implement (the rebuild of migration 013, through the atomic
  runner with its foreign-key guard). **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: an audit kind for the export of the data (plan 0087)`.

## Task 2: A reader per table, history and archive included

**Interfaces:** in each owner module, one `async def ..._for_export(...) -> tuple[Row, ...]` that
returns frozen dataclasses of exactly D-5's columns, ordered by id: `relational_v4.facts_for_export(
subject_ids: Collection[int] | None)` and `relations_for_export(entity_ids: Collection[int] | None)`
(every lifecycle, archived included; `None` means all), and the same shape for entities, contacts,
roles, the three consents, credentials, face and voice profiles, records, turns
(`turns_for_export(turn_ids | None, *, verdicts: Collection[TurnVerdict] | None)`), episodes, units,
topics, live candidates, commissioning records and sections, `admin_audit`, `decisiones` and
`deletion_register.lines_for_export()`; plus `count_rows(table)` for `no_sale`.

- [ ] **Step 1: Write the failing tests** (`test_export_readers.py`, one per reader): each returns
  the superseded, revoked and archived rows beside the active ones; `credentials_for_export` holds
  no salt, parameters or verifier field and `voice_profiles_for_export` no embedding (the canary
  bytes seeded are in neither); `turns_for_export(verdicts=...)` filters by verdict;
  `lines_for_export` returns the register's lines as stored.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS; every existing store test unchanged.
- [ ] **Step 5:** commit `feat: read every stored row for an export (plan 0087)`.

## Task 3: The content of «todo» and of one person

**Interfaces:** in `memory/export_model.py`: `type Cell = str | int | None`;
`@dataclass(frozen=True) class ExportColumn: key: str; label: str`;
`@dataclass(frozen=True) class ExportSection: key: str; title: str; columns: tuple[ExportColumn,
...]; rows: tuple[tuple[Cell, ...], ...]`; `class ExportScopeKind(StrEnum): ALL = "all"; PERSON =
"person"`; `@dataclass(frozen=True) class ExportScope: kind: ExportScopeKind; entity_id: int | None
= None; words: str | None = field(default=None, repr=False)`; `@dataclass(frozen=True) class
ExportDocument: scope: ExportScope; generated_at: str; schema_version: int; sections:
tuple[ExportSection, ...]`. In `memory/data_export.py`: `async def gather_export(scope: ExportScope,
*, owner_entity_id: int, now: str) -> ExportDocument` and `def export_counts(document:
ExportDocument) -> tuple[str, ...]` (one Spanish line per section, «{title}: {n} filas»).
`rows_about_entity` gains `include_history: bool = False` (the forget path keeps its default).

- [ ] **Step 1: Write the failing tests** (`test_data_export.py`, a seeded store with the owner, a
  child Gaviota, a second adult with a `medical` fact, a care contact, a canary Canaria only talked
  about, a `not_owner` turn naming Gaviota, an archived unit and two register lines):
  `test_all_holds_every_section_in_order` (D-5); `test_the_owner_export_leaves_out_other_voices`;
  `test_a_child_export_holds_no_other_adults_private_fact` and
  `test_a_person_export_leaves_out_owner_facts_naming_them` (Review focus 1);
  `test_a_not_owner_turn_is_only_in_all` (Review focus 2);
  `test_a_person_export_holds_what_forget_would_delete` (the ids of `person_scope(...,
  for_deletion=True)` minus D-6's exclusions); `test_a_name_only_export_holds_the_turns_that_name_it`;
  `test_an_archived_row_is_exported_with_its_instant`; `test_the_register_is_only_in_all`;
  `test_no_sale_counts_each_excluded_class`; `test_nothing_found_is_empty`.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: gather everything, or one person, for an export (plan 0087)`.

## Task 4: The two files and the folder

**Interfaces:** in `memory/export_files.py`: `def render_json(document: ExportDocument) -> str`;
`def render_markdown(document: ExportDocument) -> str`; `def check_export_folder(out: Path, *,
repository: Path, data_dir: Path) -> Path` (the resolved folder; raises `ExportPlaceError`, a new
`BrainMemoryError` subclass in `exceptions.py` whose message is D-3's closed phrase);
`def write_export(document: ExportDocument, folder: Path) -> tuple[Path, Path]` (removes what it
wrote and re-raises on `OSError`).

> **Amended 2026-11-19 (Pipec's folder):** `check_export_folder(out, *, repository, data_dir)`
> became `export_folder(out: Path | None, *, repository, data_dir, name) -> Path` plus
> `folder_name(scope, now) -> str`; Task 7 step 7 refuses `data\` itself (not `data\exports\`).

- [ ] **Step 1: Write the failing tests:**
  `test_the_markdown_tables_parse_back_to_the_json_rows` (the parity of D-4, over Task 3's
  document); `test_a_pipe_a_line_break_and_a_backslash_keep_the_table` (Review focus 3);
  `test_none_is_a_dash_and_an_empty_section_says_so`; `test_every_code_is_in_the_glossary`;
  `test_the_json_is_utf8_and_keeps_accents`; one refusal test per place of D-3, `..` back into the
  repository among them (Review focus 4); `test_a_missing_folder_is_created`;
  `test_a_failed_second_file_leaves_nothing` (Review focus 5); no file holds the canary salt,
  verifier or embedding.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: write an export as Markdown and JSON (plan 0087)`.

## Task 5: `iroko-admin export`

**Interfaces:** `AdminRequest` gains no field (`kind`, `row_id`, `name`, `out`, `dry_run` exist);
`async def _export(request, owner, read_text, read_secret, write_text, now) -> int` in
`admin_cli.py`, dispatched like `forget`.

- [ ] **Step 1: Write the failing tests** (`test_admin_export.py`, through `run_admin_command`): the
  three forms of D-2 write both files and one `applied` audit row (`field_id` `all`, `person:<id>`,
  `person`); a wrong PIN shows no count, writes nothing and audits `refused` / `pin`; a refused
  place audits `place`; nothing found audits `empty`; `--dry-run` prints the counts and writes no
  file and no `applied` row; a missing `--out` is refused before the PIN; a failing disk audits
  `write` and leaves nothing (Review focus 5); no audit row and no log line holds a name, a value
  or the path; the other sub-commands' tests unchanged.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: iroko-admin export, all or one person (plan 0087)`.

## Task 6: Verification and review

- [ ] **Step 1:** the CI selection, `uv run pyright`, `uv run mypy server/src robot/src`,
  `uv run ruff check .`, `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`, `just gate`.
- [ ] **Step 2:** the `simplify` skill, then `database-architect`, `security-auditor` and
  `pr-review-toolkit:code-reviewer` on `git diff main...HEAD` (`sonnet`, `.claude/` first,
  read-only); each accepted finding fixed with its RED test; Step 1 again. Push, PR, CI green.

## Task 7: Hardware acceptance, the real migration and close

**Setup.** With the server stopped, the agent backs up to `data/backups/pre-0087-<fecha>/` and
proves it opens; merge; Pipec starts the server once (migration 022 runs) and the robot, streaming
route, memory, record and recall on. The export folders are under `%USERPROFILE%\iroko-export-0087\`
(outside the repository); the agent runs every `iroko-admin` step and reads `logs/server.log`;
Pipec speaks, types the PIN and reads the document.

| # | Who | Step | Expected |
|---|---|---|---|
| 1 | Tú | «Ayer almorcé con mi amiga Canaria en el centro y conversamos harto rato.» (one long sentence) | An ordinary reply |
| 2 | Yo | Stop the server; `iroko-admin export all --out %USERPROFILE%\iroko-export-0087\todo` (PIN, `SI`) | The counts per section, then both files |
| 3 | Yo | The JSON parses; its row counts equal the counts printed; no key `salt`, `verifier`, `embedding` or `vector`; `borrados` holds the register's lines | Pass |
| 4 | Tú | Open `exportacion.md` and read it | Readable in Spanish: your data, your conversations, the diary, the acta, the glossary |
| 5 | Yo | `export person <tu id>` and `export person <id de un familiar del alta>` to two new folders | Both written; the relative's has no fact whose subject is another person |
| 6 | Yo | `export person --name Canaria`, then `forget person --name Canaria --dry-run` | The export holds step 1's turn; its counts match the forget counts |
| 7 | Yo | `export all --out` the repository's `data\`, and again to step 2's folder | Both refused, nothing written |
| 8 | Tú | One export with a wrong PIN | Refused, no count shown |
| 9 | Yo | `iroko-admin audit` | One `export` / `household_data` row per attempt (applied and refused), no value |
| 10 | Yo | `forget person --name Canaria` (PIN, `SI`); delete `%USERPROFILE%\iroko-export-0087\`; `iroko-admin health`; the `post-0087` backup made and proven | Health 0 |

A step that fails is fixed with its RED test and repeated.

- [ ] **Step 1:** the script above; the record `docs/evals/0087-export-acceptance.md` (outcomes and
  counts only).
- [ ] **Step 2:** when Pipec accepts, the `pre-0087` backup deleted and recorded; the documents of
  the permitted list updated (ADR 0032 `Accepted`: decision 8 implemented, the block closed); the
  plan moved to `completed/`; commit `docs: close plan 0087, the export of the owner's data`, push,
  PR, squash-merge, delete the branch.

---

## Completion criteria

1. The script of Task 7 passes on hardware, with the record written.
2. Migration 022 on the real database, `iroko-admin health` exits 0, a proven `post-0087` backup.
3. The Markdown and the JSON hold the same rows; no secret value or vector in either; a person's
   export holds no other person's fact and no other voice's turn; one audit row per attempt.
4. The CI selection, `just gate`, the type checkers, `ruff` and the reserved-terms guard pass.
5. The documents of Task 7 updated, ADR 0032 `Accepted`; the plan in `completed/`; `pre-0087`
   deleted after acceptance; the export folders deleted.

## Non-goals

Everything in *Deferred, with their triggers*; importing an export back; changing
`conversations export`; any wire, route, robot, prompt, setting or dependency change.

## Self-review (2026-11-18)

- **Spec coverage.** Every clause of ADR 0032 decision 8 has a task: the command, PIN and stopped
  server (D-2, Task 5); all or one person (D-5, D-6, Task 3); the folder outside the repository
  (D-3, Task 4); the two forms with the same content (D-4, Task 4); the list of what it holds (D-5,
  Task 2); secrets by reference (D-5, Tasks 2 and 4); no other adult's private data (D-6, Task 3);
  one audit row (D-7, Tasks 1 and 5); the operator's duty (D-9, Task 7). The ADR's test
  consequences are Task 4's parity test, Task 3's privacy tests, Tasks 2 and 4's secret tests and
  Task 5's audit tests.
- **Cheapest form.** One migration (the audit kind); one reader per table in its owner module; the
  person scope reused from `forget`; no new setting.
- **Type consistency.** `ExportColumn`, `ExportSection`, `ExportScope`, `ExportScopeKind`,
  `ExportDocument`, `gather_export`, `export_counts`, `render_json`, `render_markdown`,
  `check_export_folder`, `ExportPlaceError`, `write_export` and `TargetKind.HOUSEHOLD_DATA` are each
  defined once and named the same in later tasks.

## Pipec's decisions (2026-11-18, each as recommended)

1. **The folder (D-3):** a new or empty folder the operator names, refused inside the repository or
   the data directory; two files, `exportacion.md` and `exportacion.json`.
2. **One person (D-6):** the same reach as `forget person` (an entity of `list` or a name only
   talked about), plus the person's identity rows; for the owner, everything of the owner's; never a
   fact whose subject is another person, never a turn said by another person.
3. **The archive and the register (D-5):** an archived row is exported in its section with its
   `archived_at`, beside the history; the deletion register's lines only in «todo».
