# 0085 — Block C1: the storage foundation, minimum version

> **Status:** **Draft** (trimmed 2026-11-16). Rewritten on Pipec's scope rule of 2026-11-16
> («Yes, trim it»): **every piece must show which behaviour it enables, which defect it fixes or
> which concrete risk it reduces**; the schema carries only what Plan 0086 (C2: correct, archive
> and delete), Plan 0087 (the export) and today's recall need. Everything else of the earlier
> version is deferred with its trigger in [ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md)
> (*Amendment of 2026-11-16*) and listed in *Deferred, with their triggers* below; nothing was
> dropped silently. Source: ADR 0038 as amended and
> [ADR 0032](../../adr/0032-block-c-hygiene-correct-forget-and-years.md) decision 1. It becomes
> executable only when Pipec promotes it to `Ready`.
>
> **Two parts, two PRs, both merged after Plan 0084's acceptance closes.** **Part A**
> (`feat/0085a-storage-safety`) changes no table: it fixes the defects found in the code (the
> transaction window, a failed start, two time formats) and proves physical deletion. **Part B**
> (`feat/0085b-storage-schema`) makes four small, ordinary migrations (017 to 020): the dead
> tables out, the turns as rows, the turn linked to what is derived from it, and the two
> biometric profile tables fixed; then the dictionary, the guards and a minimal health check.
> Tasks A0 and B0 re-verify every claim against the merged code and **stop and report** if one is
> false.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md` and
> every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS: `superpowers:executing-plans`
> (inline), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Tasks A4 and
> B7, and `superpowers:finishing-a-development-branch` at the end of each part. Review agents run
> on the `sonnet` model and read `.claude/` in full before reading code. **Pipec's rules win over
> the skills:** one plain branch per part from `main`, never a git worktree, this plan lives under
> `docs/plans/`. One commit per task; every test seen RED for the stated reason first. If evidence
> contradicts the plan, stop and report instead of redesigning; **a discovery that is not needed
> by this plan's goal is recorded, not built** (Pipec's scope rule). The Bash tool loses
> backslashes and non-ASCII characters in heredocs: use the Write and Edit tools. Commit titles:
> Conventional Commits, at most 72 characters, check `git log` after each commit; never pipe
> `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI
> does. Never run `uv sync` without `--extra cuda`. Do not run `just gate` or the full suite in
> the background while Pipec rehearses. The server and the robot are started by Pipec. **The real
> database is touched only in Task B8**, after its backup, and only by the server Pipec starts. A
> copy of the real database goes under `data/rehearsal-0085/` and is deleted the same day. Before
> pushing, run `pyright`, `ruff` and `mypy` over the whole project, lint `scripts/` with explicit
> paths and `uv run ruff format --check .`.

## The audit (2026-11-13, structure and counts only)

A copy of `data/omnibot.db` (5.98 MB, `user_version` 16, server stopped) was opened with
`immutable=1` and compared with a clean database built by `db.run_migrations`; both copies were
deleted and no value was read.

1. The real database and a clean install have the same schema: 21 live tables, 3 virtual tables,
   9 dead tables, 4 triggers; `integrity_check` ok, no foreign key violation; every table has a
   primary key.
2. **Two time formats.** 26 values in the old `YYYY-MM-DD HH:MM:SS` in 13 columns of 9 tables;
   every other instant is ISO 8601 UTC with microseconds (32 characters). The old format comes
   from `DEFAULT (datetime('now'))` columns and from code writing `datetime('now')`; in
   `literal_facts_v4` both formats sit side by side, so ordering across them is wrong today.
   `relational_v4` also writes instants into the validity bounds (`valid_from`, `valid_to`).
3. 32 foreign keys have no index a cascade can use (26 on live tables).
4. **Dead tables, all with 0 rows:** `outbox`, `sensor_current`, `sensor_readings`,
   `sensor_aggregates_hourly`, `facts`, `legacy_fact_migration_v4`, `embeddings_cache`, `events`,
   and `memories` (retired by migration 013, still the parent of `source_memory_id` in both V4
   tables).
5. All 65 recall units name `granite-embedding:278m`; `units_without_vector` selects only
   `embedding_model IS NULL` and `vector_hits` never compares models.
6. The record's turns are one JSON array, read and written only by `conversation_record.py`;
   recall units, candidates and pending topics point at a turn by a text correlation id with no
   foreign key.
7. `face_profiles` reuses a deleted top id and `vec_faces.rowid` follows it (tested); its and
   `voice_profiles`' foreign keys have no explicit rule.
8. `db.transaction()` awaits `BEGIN IMMEDIATE` before its `try` (a cancellation there leaves a
   transaction open); `open_db()` keeps a half-set connection when a step after `connect` fails
   (the next call returns early); Python's `executescript()` commits an open transaction before
   it runs.
9. Runtime: uv-managed CPython 3.12.11 with SQLite 3.49.1 and `sqlite-vec` 0.1.9
   (`sqlite-vec>=0.1.6` in `server/pyproject.toml`).

## Decisions

### Part A — safety, no table changes

- **D-1 The runtime is checked, not upgraded.** `sqlite-vec` is pinned to `==0.1.9`. `open_db`
  asserts SQLite ≥ **3.42** (what the FTS5 `secure-delete` index this database already uses
  needs), FTS5 compiled in, extensions loadable and `vec_version() == "v0.1.9"`, and logs the
  versions once; below any of them it refuses to start. The Python patch upgrade (SQLite 3.53.1,
  above the WAL-reset fix of 3.51.3) is deferred to the move to the Pi or to a second process that
  writes while the server runs (ADR 0038 amendment).
- **D-2 The transaction and a clean start.** `transaction()` opens `BEGIN IMMEDIATE` inside its
  `try`, so a cancellation rolls back. Any failure in `open_db` after `connect` closes the
  connection and resets the module state, so the next `open_db` starts clean. `open_db` also runs
  `PRAGMA optimize=0x10002` (SQLite's advice for a long-lived connection); the other pragmas stay
  as they are.
- **D-3 One time format in the writers.** `server/timestamps.py` formats an instant
  (`instant_text`: 32 characters, UTC, microseconds, `+00:00`; a naive datetime raises), parses one
  and formats a day; a temporal V4 fact or relation opens and closes on a household **day**. Every
  writer passes its times explicitly through it; no `.py` under `server/src` writes
  `datetime('now')` (a guard matching `datetime\(\s*'now'`). The old values are converted in Task
  B5. The SQL defaults of untouched tables stay, unused: a test per store proves its inserts write
  the 32-character format, and the health check counts rows outside it.
- **D-4 Physical deletion proven at the byte level**, on today's schema: a canary written to a
  plain row and to a recall unit (so FTS5 and `vec0` hold it), deleted through its store, then a
  `checkpoint_wal()` that returns `True`; neither the database file nor its WAL holds the canary
  text or vector bytes. It proves the SQLite files, not the storage medium (that is encryption,
  ADR 0033). It runs in CI and again after Part B.

### Part B — the schema C2 and the export need

- **D-5 Four ordinary migrations, each atomic.** The runner wraps each new file in one script
  (`BEGIN IMMEDIATE`, the file, `PRAGMA user_version`, a foreign-key guard that aborts on any
  violation, `COMMIT`) run by a single `executescript()`, and rolls back on any error; a new file
  holds no transaction statements. A migration that rebuilds a table runs with
  `PRAGMA foreign_keys=OFF` set before that script and back on whatever happens. Migrations 001 to
  016 keep their own transactions. No squash, no baseline: a fresh install runs every migration.
- **D-6 Migration 017 — the dead tables out.** Drops the eight dead tables other than `memories`,
  aborting if any holds a row, and removes the code that names them (`retention`'s dead deletes,
  `embeddings.embed` and its cache helpers, `declarative.assert_fact` and `get_active_facts`,
  `memory/legacy_v4_migration.py`, `scripts/migrate_memory_v4.py`, the `events` write in
  `perception` (its log line stays), the dead-table part of `scripts/memory_test.py --show-db`)
  with their tests. `memories` and `source_memory_id` stay (dropping them needs a V4 rebuild that
  nothing else asks for now; `memories` is already locked by a trigger and documented as retired).
- **D-7 Migration 018 — the turns as rows** (ADR 0038 decision 6; C2 deletes and redacts one turn).
  A new `STRICT` table `conversation_turns`: `id INTEGER PRIMARY KEY AUTOINCREMENT`, `record_id`
  (→ `conversation_records`, `CASCADE`), `correlation_id` (`UNIQUE`), `said_at` (the exact instant
  check of ADR 0038 decision 5), `verdict` (the `TurnVerdict` values), `heard`, `said` (today's
  limits). The migration copies each JSON turn (`at`, `cid`, `heard`, `said`, `voice`) with
  `json_each`, in order, then drops the record's `turns`, `turn_count` and `byte_count` with
  `ALTER TABLE DROP COLUMN` (if SQLite refuses one, the record table is rebuilt by its documented
  procedure). `conversation_record.py` keeps its public functions and returns the same
  `RecordedTurn` tuple, ordered by `said_at` then `id`; the segment rule counts rows and the 200 MB
  cap counts **bytes** (`SUM(octet_length(heard) + octet_length(said))`).
- **D-8 Migration 019 — the turn linked to what is derived from it** (ADR 0038 decision 6;
  «everything derived from this turn» is one query). With `ALTER TABLE ADD COLUMN` (no rebuild):
  `recall_units.turn_id` (→ turns, `CASCADE`; set for turn units), `memory_candidates.source_turn_id`
  (→ turns, `CASCADE`; `NULL` when the record is off) and `pending_topics.source_turn_id`
  (→ turns, `CASCADE`), each filled from the old correlation id; unique indexes make one unit per
  turn and one unit per episode (a retried job cannot duplicate them); a trigger refuses an
  `UPDATE` of `recall_units.body` (FTS5 would drift). The existing record keys stay, so today's
  cascades are unchanged. The same migration creates the full indexes on every foreign key a
  cascade, a `SET NULL` or a `RESTRICT` check follows (21 on today's columns plus the new ones) and
  drops `entities_name_idx` (redundant with the unique `(name, type)` index).
- **D-9 Migration 020 — the old times and the two biometric tables.** One `UPDATE` per affected
  column converts a 19-character instant to `replace(x, ' ', 'T') || '.000000+00:00'` and a
  25-character one to `substr(x, 1, 19) || '.000000+00:00'`; any other format aborts the
  migration. The two instant validity bounds become their UTC day. `face_profiles` and
  `voice_profiles` are rebuilt (`STRICT`, `AUTOINCREMENT`, `ON DELETE RESTRICT` written: the
  consent revocation deletes biometrics and `vec_faces`); `sqlite_sequence` is set back to each
  table's old counter (captured before the `DROP`).
- **D-10 The embedding-model guard, simple** (ADR 0031 decision 8). `units_without_vector` selects
  units with no vector **or** a vector of another model; `vector_hits` runs only when no unit of
  the owner holds another model, else recall is lexical only and logs
  `recall.vector off reason=model_changed remaining=%d`; `store_vector` already replaces a vector
  and its model in one transaction. No new table.
- **D-11 The dictionary, the guards and a minimal health check** (ADR 0032 decision 1).
  `docs/architecture/data-dictionary.md`: per table its purpose, its owner module and its domain
  (memory, identity, administration), its columns, keys and rules, its indexes with the query each
  serves, its classification and retention; then the time format, the deliberate
  denormalizations and *Not tuned yet*. Guards: every table has a primary key, every foreign key a
  full index and an explicit rule on the tables this plan touches, every table and column is in the
  dictionary. `memory/db_health.py` and `iroko-admin health` (no PIN, server stopped, counts only):
  `integrity_check`, `foreign_key_check`, FTS5 `integrity-check`, orphans (vectors without a unit,
  units without an FTS row, face vectors without a profile), units without a vector and units of
  another model, rows outside the time format, and the SQLite and `sqlite-vec` versions; exit 1 on
  any fault.
- **D-12 Rehearsal, backup and timing.** Merge after Plan 0084 closes. With the server stopped:
  back up to `data/backups/pre-0085-<YYYYMMDD-HHMMSS>/`; prove the rollback (the backup restored
  into `data/rehearsal-0085/` opens at version 16 with integrity and counts intact); rehearse the
  migrations on a copy (per-table counts and health before and after, turn rows equal to the JSON
  turns, 0 rows outside the format); Pipec starts the server. The `pre-0085` backup is kept until a
  `post-0085` backup has been restored and opened with health exiting 0, and is deleted only then
  and after Pipec accepts.

## Deferred, with their triggers

Recorded in ADR 0038's *Amendment of 2026-11-16*; nothing below is built by this plan.

| Deferred | Its trigger | Owner |
|---|---|---|
| `uid` on durable rows (deterministic UUIDv8 for carried rows) | The deletion register needs a stable key | Plan 0086, by `ADD COLUMN` |
| `archived_at` on facts, relations, episodes, units | Archiving by voice | Plan 0086, by `ADD COLUMN` |
| A fact's link to its turn (`source_turn_id`) and «forgetting a story keeps a confirmed fact» | The deletion has to name it | Plan 0086, by `ADD COLUMN` |
| `episode_sources` and the episode's key to its record | The diary outlives the record (ADR 0032 decision 5) | Plan 0086 |
| The deletion durability protocol | Physical deletion with the PIN | Plan 0086 |
| The Python patch with SQLite 3.53.1, `.python-version` pinned to it | The move to the Pi, or a second writing process | The Pi move |
| `STRICT` and exact time checks on every table | A table is rebuilt for another reason | That plan |
| Record time renamed (`recorded_at`, `retracted_at`) | A query that needs it (`asserted_at`, `superseded_at` already mean it) | — |
| `embedding_spaces`, the model digest, a `vec0` with the space and the told day as metadata | A second embedding model is actually trialled | Its plan |
| The recall window filtered inside the KNN (today after the top 20) | A real recall miss caused by it | Its plan |
| Origin and transformation columns | A second origin is stored (ADR 0031 decision 6 says so already) | That plan |
| `memories` and `source_memory_id` dropped | A V4 rebuild for another reason | That plan |
| One-owner-per-table guard; biometric statements moved behind the consent stores | The engine's extraction (ADR 0031 decision 11) | The extraction plan |
| Pragmas read back; `cell_size_check`, `temp_store`, `journal_size_limit`, `wal_autocheckpoint` | A measured problem | — |
| The storage benchmark (10k to 100k units) and the storage fingerprint | The first tuning question, or the Pi move | Its plan |
| A v2 baseline with a squashed upgrade | Never needed while ordinary migrations stay small | — |

**Goal.** The store stops mixing time formats, cannot leave a transaction open or a half-started
connection, links each turn to what is derived from it so C2 can delete and prove it, never
compares vectors of two models, carries no dead table, and is documented table by table with a
health check that counts what is wrong.

**Tech stack.** Python 3.12 (uv-managed, SQLite 3.49.1), aiosqlite, FTS5, `sqlite-vec` 0.1.9,
pytest. No new dependency, no setting, no wire, route, prompt or robot change.

**Spec.** [ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md) as amended on
2026-11-16; [ADR 0032](../../adr/0032-block-c-hygiene-correct-forget-and-years.md) decision 1;
[ADR 0031](../../adr/0031-the-memory-engine-boundary.md) decisions 8 and 9;
[ADR 0011](../../adr/0011-sqlite-transaction-ownership.md);
[current state](../../architecture/current-state.md);
[guardrails](../../architecture/implementation-guardrails.md).

**Required reading.** The above, then the code: `db.py`; `memory/migration_013_*.sql` to
`migration_016_*.sql`; `relational_v4.py`, `declarative.py`, `candidates.py`, `pending_store.py`,
`conversation_record.py`, `conversation_types.py`, `conversation_capture.py`, `recall_store.py`,
`recall_search.py`, `recall_index.py`, `retention.py`, `biometric_consent.py`, `voice_consent.py`,
`vision/faces.py`, `voice/voiceprints.py`, `vision/perception.py`, `admin_cli.py`; the schema
tests under `tests/integration/` and `tests/unit/test_architecture_guards.py`.

## Global constraints

- English code and docstrings; no `Any`, no `print`, no `os.path`, no bare `except`; logging with
  `%`.
- Counts only: no database value in a log line, a health report, a test output or this plan's
  evidence.
- No behaviour change a person can hear: every route, prompt and reply is byte-identical to `main`
  with the same data, except the removed `events` row.
- No real household data: invented canaries only; `scripts/check_reserved_terms.py` passes.

## Review focus

1. **A value in a third time format** in the real database: migration 020 aborts and leaves version
   19 (Task B5).
2. **The record read back differently** after its turns become rows: same turns, same order, same
   verdicts; 0 turns; two equal instants (Task B3).
3. **A migration failing halfway** leaves no table, index, row or version behind (Task B1).
4. **A turn deleted** takes its unit, its FTS row, its vector, its candidate and its pending topic,
   and nothing else (Task B4).
5. **A model change** leaves recall lexical and compares no two models (Task B6).

---

## Permitted files

Paths under `server/src/server/` unless they start with `tests/`, `scripts/`, `docs/` or the root;
a need outside the list stops the plan for Pipec.

| Part | Files |
|---|---|
| A | `db.py`, `timestamps.py` (new), the writers of D-3 (`memory/candidates.py`, `conversation_consent.py`, `conversation_record.py`, `conversation_episodes.py`, `recall_store.py`, `household_authorization.py`, `biometric_consent.py`, `voice_consent.py`, `owner_credentials.py`, `declarative.py`, `meta.py`, `relational_v4.py`, `cognition/spoken_dates.py`, `admin_cli.py`), `server/pyproject.toml`, `uv.lock`; their tests, `tests/unit/test_timestamps.py`, `tests/integration/test_db_runtime.py`, `tests/integration/test_physical_deletion.py`, `tests/unit/test_architecture_guards.py` |
| B | `db.py`, `memory/migration_017_retire_dead_tables.sql` to `memory/migration_020_times_and_profiles.sql` (new), `conversation_record.py`, `recall_store.py`, `recall_search.py`, `recall_index.py`, `candidates.py`, `pending_store.py`, `pending_capture.py`, `conversation_capture.py`, `retention.py`, `embeddings.py`, `declarative.py`, `biometric_consent.py`, `voice_consent.py`, `vision/faces.py`, `voice/voiceprints.py`, `vision/perception.py`, `admin_cli.py`, `justfile`, `scripts/memory_test.py`, `memory/db_health.py` (new); deleted: `memory/legacy_v4_migration.py`, `scripts/migrate_memory_v4.py`; the schema and store tests they touch, `tests/integration/test_migrations_017_020.py`, `tests/integration/test_db_health.py`, `tests/unit/test_schema_guards.py`; `docs/architecture/data-dictionary.md` (new) and the documents of Task B8 |

**Rollback boundary.** Before a merge, the branch. After Part A's merge, a revert (no table
changed). After Part B's real upgrade, the `pre-0085` backup with the previous `main`.

---

## Part A — safety, no table changes

### Task A0: Re-audit and baseline

- [ ] **Step 1:** after Plan 0084 closes, `git checkout main && git pull`, create
  `feat/0085a-storage-safety`.
- [ ] **Step 2:** verify *The audit* items 2, 8 and 9, and every `datetime('now')` writer, and
  **stop and report** if one is false.
- [ ] **Step 3:** baseline: `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and
  not eval" -q -n auto` (not in the background while Pipec rehearses).

### Task A1: The runtime checked; the transaction and a clean start

**Files:** `db.py`, `server/pyproject.toml`, `uv.lock`, `tests/integration/test_db_runtime.py`,
`tests/integration/test_db_transaction.py`.

**Interfaces:** `SQLITE_FLOOR: Final = (3, 42, 0)`, `SQLITE_VEC_VERSION: Final = "v0.1.9"`;
`async def check_runtime(conn: aiosqlite.Connection) -> RuntimeReport` (a frozen dataclass of the
versions; raises `BrainMemoryError` with a closed message); `open_db` calls it, logs the report
once, runs `PRAGMA optimize=0x10002`, and cleans up on any failure after `connect`.

- [ ] **Step 1: Write the failing tests:** each runtime assertion refuses a patched report (3.41,
  no FTS5, `v0.1.10`) and passes on the real one; `test_a_failed_start_leaves_nothing_behind` (a
  pragma made to fail: the connection is closed, the state is `None`, a second `open_db` works and
  a `transaction()` commits); `test_a_cancelled_transaction_after_begin_rolls_back`.
- [ ] **Step 2:** FAIL. **Step 3:** implement; pin `sqlite-vec==0.1.9` (`uv lock`, then
  `uv sync --all-packages --all-groups --extra cuda`). **Step 4:** PASS.
- [ ] **Step 5:** commit `fix: check the SQLite runtime and close two start-up gaps (plan 0085)`.

### Task A2: One time format in the writers

**Files:** `timestamps.py` (new), the writers of D-3, their tests, `tests/unit/test_timestamps.py`,
`tests/unit/test_architecture_guards.py`.

**Interfaces:** `INSTANT_LENGTH: Final = 32`; `def instant_text(moment: datetime) -> str`;
`def parse_instant(text: str) -> datetime`; `def day_text(day: date) -> str`;
`def validity_day(moment: datetime, zone: ZoneInfo) -> str`. `timestamps` imports no settings,
database or FastAPI.

- [ ] **Step 1: Write the failing tests:** a `+03:00` moment becomes its UTC instant in 32
  characters; a naive one raises; round trip; text order equals time order; `validity_day` at
  02:30 UTC is the previous day in `America/Santiago`; a temporal V4 fact and relation open and
  close on a household day; each store's insert writes the 32-character format;
  `test_no_server_module_writes_datetime_now` with a leak test.
- [ ] **Step 2:** FAIL. **Step 3:** implement and move every writer. **Step 4:** PASS; the writers'
  tests unchanged in what they assert.
- [ ] **Step 5:** commit `refactor: write every time in one format (plan 0085)`.

### Task A3: The byte-level deletion test

**Files:** `tests/integration/test_physical_deletion.py`.

- [ ] **Step 1:** write D-4's test on a temporary database through `open_db` (a candidate's value
  scrub; a recall unit deleted with its record). If a canary survives, **stop and report**.
- [ ] **Step 2:** PASS. **Step 3:** commit `test: prove physical deletion at the byte level
  (plan 0085)`.

### Task A4: Verification, review and merge of Part A

- [ ] **Step 1:** the CI selection, `uv run pyright`, `uv run mypy server/src robot/src`,
  `uv run ruff check .`, `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`, `just gate`.
- [ ] **Step 2:** the `simplify` skill, then `database-architect`,
  `pr-review-toolkit:code-reviewer` and `pr-review-toolkit:silent-failure-hunter` on
  `git diff main...HEAD` (`sonnet`, `.claude/` first, read-only); each finding verified and fixed
  with its RED test; Step 1 again.
- [ ] **Step 3:** Pipec starts the server and the robot and speaks a short script (a greeting,
  «¿qué sabes de mí?», a recall question); the agent reads `logs/server.log` (versions logged).
  Push, PR, squash-merge with green CI, delete the branch.

---

## Part B — the schema C2 and the export need

### Task B0: Re-audit and baseline

- [ ] **Step 1:** `git checkout main && git pull` (Part A merged), create `feat/0085b-storage-schema`.
- [ ] **Step 2:** verify *The audit* items 1 to 7, the readers of `RecordedTurn`, every query on
  the correlation ids and `embedding_model`, and that `ALTER TABLE ADD COLUMN … REFERENCES … ON
  DELETE CASCADE` works on the installed SQLite; **stop and report** if one is false.
- [ ] **Step 3:** baseline, as Task A0.

### Task B1: The atomic runner

**Files:** `db.py`, `tests/integration/test_db.py`.

**Interfaces:** `@dataclass(frozen=True) class Migration: version: int; filename: str; rebuild:
bool = False; owns_transaction: bool = True` (`False` for 001 to 016, which carry their own);
`run_migrations` per D-5.

- [ ] **Step 1: Write the failing tests:** a new file holding `BEGIN`, `COMMIT` or `user_version`
  is refused; `test_a_migration_failing_halfway_leaves_nothing` (a script that creates a table and
  an index, inserts rows, then fails: no table, index, row or version change survives, foreign keys
  on); a `rebuild=True` file runs with foreign keys off and a violation aborts it.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: an atomic migration runner (plan 0085)`.

### Task B2: Migration 017 — the dead tables out

D-6, with the tests the removed code had: deleted `test_memory_v4_migration`,
`test_legacy_migration_*` and the `embed` cases of `test_embeddings`; reseeded through
`relational_v4` the tests that used `assert_fact`, `get_active_facts` or a dead table to set up a
scenario (`test_household_authorization_schema`, `test_memory_v4_schema`, `test_memory_relational`,
`test_owner_stranger_matrix`, `test_memory_integration`, `test_retention`); updated
`test_architecture_guards`.

- [ ] **Step 1:** failing tests (each dead table gone; a canary row in any aborts; no SQL names
  them). **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: retire the dead tables (plan 0085)`.

### Task B3: Migration 018 — the turns as rows

**Files:** the migration, `conversation_record.py`, `retention.py`,
`tests/integration/test_migrations_017_020.py`, the record suites.

- [ ] **Step 1: Write the failing tests:** a record's JSON turns become rows in order with the same
  fields; reading a record returns the same `RecordedTurn` tuple (Review focus 2); the segment's
  limit counts rows; the 200 MB cap counts bytes (a canary with accents and an emoji counts more
  bytes than characters, and the cap trips at the byte total); appending is one `INSERT`.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS; every record, capture, episode,
  admin and recall suite unchanged.
- [ ] **Step 5:** commit `feat: keep a conversation's turns as rows (plan 0085)`.

### Task B4: Migration 019 — the turn linked to what is derived from it

**Files:** the migration, `recall_store.py`, `candidates.py`, `pending_store.py`,
`pending_capture.py`, `conversation_capture.py`, their tests.

- [ ] **Step 1: Write the failing tests:** deleting one turn removes its unit, its FTS row, its
  vector, its candidate and its pending topic, and nothing else (Review focus 4); a candidate with
  the record off keeps a `NULL` turn; every existing unit, candidate and topic is mapped to its turn
  (none left unmapped); indexing a turn twice leaves one unit; an `UPDATE` of a unit's body is
  refused; each child lookup of a `DELETE FROM entities` and of a turn deletion uses an index
  (`EXPLAIN QUERY PLAN`).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: link each turn to what is derived from it (plan 0085)`.

### Task B5: Migration 020 — the old times and the biometric tables

**Files:** the migration, `biometric_consent.py`, `voice_consent.py`, `vision/faces.py`,
`voice/voiceprints.py`, their tests.

- [ ] **Step 1: Write the failing tests:** each 19- and 25-character instant converted exactly; a
  third format aborts and leaves 19 (Review focus 1); the two instant bounds become days; ordering
  across converted and new instants is right; the two profile tables refuse their person's deletion
  and never reuse a deleted top id; the face and voice suites pass unchanged.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: one time format in the data and fixed profile keys (plan 0085)`.

### Task B6: The embedding guard, the dictionary and the health check

**Files:** `recall_store.py`, `recall_search.py`, `recall_index.py`, `memory/db_health.py` (new),
`admin_cli.py`, `justfile` (`db-health`), `scripts/memory_test.py`,
`docs/architecture/data-dictionary.md` (new), `tests/integration/test_db_health.py`,
`tests/unit/test_schema_guards.py`, the recall tests.

**Interfaces:** D-10; `@dataclass(frozen=True) class HealthReport` (ints and bools only);
`async def check_health(conn: aiosqlite.Connection) -> HealthReport` (changes no row);
`def health_failed(report: HealthReport) -> bool`.

- [ ] **Step 1: Write the failing tests:** ADR 0031's C1 test (units of model A, configured model
  B: no vector comparison, the lexical hit still comes, the re-index moves every unit to B, then
  vector search is back) (Review focus 5); each health measure sees its planted fault and a clean
  database passes; no canary reaches the printed report; the guards of D-11 with their leak tests;
  the dictionary covers every table and column both ways.
- [ ] **Step 2:** FAIL. **Step 3:** implement and write the dictionary. **Step 4:** PASS; the
  deletion test of Task A3 passes on the new schema.
- [ ] **Step 5:** commit `feat: model guard, data dictionary and health check (plan 0085)`.

### Task B7: Verification and review of Part B

As Task A4 Steps 1 and 2, plus `pr-review-toolkit:pr-test-analyzer`.

### Task B8: Rehearsal, the real upgrade and close

**Files:** `docs/architecture/current-state.md` and the Archify memory diagram,
`docs/runbooks/operator-manual.md` (`iroko-admin health`, the backup before an upgrade and its
deletion), `docs/evals/0085-storage-foundation-acceptance.md` (new, counts only), ADR 0038 (C1
implemented; it becomes `Accepted` once its amended scope is built), ADR 0032 (*C1 implemented*),
the ADR index, the plan board, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, the
roadmap (row 8, *Database hygiene*), both delivery maps, Pipec's local `docs/roadmap/tabla-tareas.md`.

- [ ] **Step 1:** confirm on `main` that 017 to 020 are still the next numbers (else renumber and
  re-run Task B7). With the server stopped, D-12's backup, rollback proof and rehearsal; the copy
  deleted. Any difference stops the plan.
- [ ] **Step 2:** merge; Pipec starts the server (the migrations run) and the robot, and speaks the
  script of Task A4 plus one sensitive read of the owner's own data; each answers as before; with
  the server stopped, `iroko-admin health` exits 0; the `post-0085` backup made and proven.
- [ ] **Step 3:** when Pipec accepts, delete the `pre-0085` backup and record it; update the
  documents above; move the plan to `completed/`; commit `docs: close plan 0085, the storage
  foundation`, push, PR, squash-merge, delete the branch.

---

## Completion criteria

1. Part A merged: the runtime checked at start, the transaction and start-up gaps closed, one time
   format in every writer, the byte-level deletion test green.
2. Part B merged and the real database at version 20, with the rehearsal's counts equal and the
   eight dead tables gone with 0 rows.
3. `iroko-admin health` exits 0 on the real database (0 integrity errors, 0 foreign key violations,
   0 orphans, 0 rows outside the format).
4. The guards, the dictionary coverage and the deletion test pass; the spoken scripts answered as
   before.
5. A proven `post-0085` backup exists and the `pre-0085` backup is deleted after Pipec's
   acceptance; the documents of Task B8 updated; the plan in `completed/`.

## Non-goals

Everything in *Deferred, with their triggers*; correcting, archiving or deleting a memory (Plan
0086); the export (Plan 0087); backups, restore and encryption (ADR 0033); any wire, route,
prompt, robot or dependency change beyond the `sqlite-vec` pin.

## Self-review (2026-11-16)

- **Pipec's scope rule applied to every piece.** Kept because it fixes a defect found in the code:
  the transaction window, the half-started connection, two time formats, the reused face id, a
  non-atomic runner, model-mixing vectors. Kept because C2 or the export needs it: turns as rows,
  the turn linked to its derivatives, the indexes those cascades follow, the dictionary that tells
  where each memory lives. Kept because ADR 0032 decision 1 (Pipec, 2026-11-13) asks for it: the
  dead tables out, the indexes, the dictionary, the health check, the guards. Everything else is in
  *Deferred, with their triggers*, each with the event that would bring it back.
- **Cheapest form chosen.** `ADD COLUMN` and `CREATE INDEX` instead of rebuilds wherever SQLite
  allows; only the two small profile tables are rebuilt (and the record table if `DROP COLUMN` is
  refused); no squash, no new vector table.
- **Earlier versions.** The first draft (three migrations), the ADR 0038 version (a v2 schema and a
  squashed upgrade) and its reviews remain in git history; their findings that still matter are
  either in this plan or in the deferred list.
- **Type consistency.** `instant_text`, `parse_instant`, `day_text`, `validity_day`,
  `check_runtime`, `Migration`, `HealthReport`, `check_health`, `health_failed` are each defined
  once and named the same in later tasks.
