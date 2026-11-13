# 0085 — Block C1: the memory engine's storage foundation (ADR 0038), in two parts

> **Status:** **Draft** (2026-11-13), rewritten the same day on
> [ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md) (`Proposed`; its nine
> recommendations confirmed by Pipec on 2026-11-13) and
> [ADR 0032](../../adr/0032-block-c-hygiene-correct-forget-and-years.md) decision 1. The first
> draft of this plan (three incremental migrations) was reviewed twice and then replaced: Pipec
> named the storage the core of the product, and a deeper research round (ADR 0038 *Context*)
> led to a v2 schema designed from zero with the data carried by one tested upgrade. It becomes
> executable only when Pipec promotes it to `Ready` with the *For Pipec* notes answered. Then
> completed from Pipec's own studies of the memory engine (*Self-review*, last but one bullet).
>
> **Two parts, two branches, two PRs.** **Part A** (`feat/0085a-storage-runtime`) changes no
> table: the runtime and its checks, the pragmas, the transaction, one time format in the writers,
> one writer per table, and the byte-level deletion test. **Part B**
> (`feat/0085b-schema-v2`) builds the v2 schema: developed as successive migrations on its branch
> so every task stays green, then squashed into one baseline for fresh installs and **one**
> upgrade for the real database. Both parts merge only after Plan 0084's acceptance closes
> (2026-11-19), Part A first. ADR 0038 becomes `Accepted` when Part B closes; ADR 0032 stays
> `Proposed` until Plan 0087. Written for an executor who has not seen this repository; Tasks A0
> and B0 re-verify every claim against the merged code and **stop and report** if one is false.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md` and
> every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS: `superpowers:executing-plans`
> (inline), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Tasks A6 and
> B11, and `superpowers:finishing-a-development-branch` at the end of each part. Review agents
> and any other subagent run on the `sonnet` model and read `.claude/` (CLAUDE.md and
> `.claude/rules/`) in full before reading code. **Pipec's rules win over the skills:** one plain
> branch per part from `main`, never a git worktree, this plan lives under `docs/plans/`. One
> commit per task; every test seen RED for the stated reason first. If evidence contradicts the
> plan, stop and report instead of redesigning. The Bash tool loses backslashes and non-ASCII
> characters in heredocs and arguments: use the Write and Edit tools (or a Python script written
> with Write). Commit titles: Conventional Commits, at most 72 characters, check `git log` after
> each commit (the hook rejects silently; a reformatting hook unstages the commit); never pipe
> `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI
> does. Never run `uv sync` without `--extra cuda`. Do not run `just gate` or the full suite in
> the background while Pipec rehearses (about 3.5 GB of RAM). The server and the robot are
> started by Pipec, never by the agent. **The real database is touched only in Task B12**, after
> its backup, and only by the server Pipec starts. Throwaway scripts go to
> `.superpowers/sdd/0085-database-good-practices/`; a copy of the real database goes under
> `data/rehearsal-0085/` (ignored by the tracked `.gitignore`) and is deleted the same day.
> Before pushing, run `pyright`, `ruff` and `mypy` over the **whole** project, lint `scripts/`
> with explicit paths and `uv run ruff format --check .` (CI also checks python blocks in
> `docs/*.md`).

## The audit (2026-11-13, structure and counts only)

A copy of `data/omnibot.db` (5.98 MB, `user_version` 16, server stopped) was opened with
`immutable=1` and compared with a clean database built by `db.run_migrations`; both copies were
deleted and no value was read. The facts this plan builds on:

1. The real database and a clean install have the same schema: 21 live tables, 3 virtual tables
   (`vec_faces`, `recall_units_fts`, `recall_units_vec`), 9 dead tables, 4 triggers;
   `integrity_check` ok, no foreign key violation; every table has a primary key.
2. **Two time formats.** 26 values in the old `YYYY-MM-DD HH:MM:SS` in 13 columns of 9 tables
   (`entities`, `care_contacts`, `face_profiles`, `voice_profiles`, the face and voice consents,
   the role, the PIN, `literal_facts_v4.superseded_at`); every other instant is ISO 8601 UTC with
   microseconds (32 characters), including the 197 `at` instants inside the record's JSON. The old
   format comes from 19 `DEFAULT (datetime('now'))` columns and from code writing
   `datetime('now')`. The validity bounds mix days, months and instants (`relational_v4` opens a
   temporal fact with `COALESCE(asserted_at, datetime('now'))` and closes it with
   `datetime('now')`).
3. **32 foreign keys without a usable index** (26 on live tables); two foreign keys with an
   implicit rule (`face_profiles.entity_id`, `voice_profiles.entity_id`).
4. **Dead tables, all with 0 rows:** `outbox`, `sensor_current`, `sensor_readings`,
   `sensor_aggregates_hourly`, `facts`, `legacy_fact_migration_v4`, `memories`, `embeddings_cache`
   and `events` (`events` is written by `vision/perception._record_unknown_face` and read by
   nothing; `embeddings_cache` only by `memory/embeddings.embed`, which has no caller). `meta` has
   0 rows but `personal_setup` reads it: it stays.
5. **All 65 recall units name `granite-embedding:278m`**; `units_without_vector` selects only
   `embedding_model IS NULL` and `vector_hits` never compares models (ADR 0031 *Context* item 8).
6. **The record's turns are one JSON array**, read and written only by
   `memory/conversation_record.py` (`json_insert` at its append; `_turns` at its read), exposed as
   `RecordedTurn`; recall units, candidates and pending topics point at a turn by a text
   correlation id with no foreign key.
7. **26 of the 72 modules of `server/memory/`** import `server.cognition` (ADR 0031 counted 20).
8. **Runtime:** uv-managed CPython 3.12.11 with SQLite 3.49.1 (inside the WAL-reset bug range,
   fixed in 3.51.3), `sqlite-vec` 0.1.9 with `sqlite-vec>=0.1.6` in `server/pyproject.toml`,
   uv 0.10.11.

## Decisions

Pipec's decisions are ADR 0038's nine (2026-11-13) and ADR 0032 decision 1. The calls below fill
in what they leave to the plan; the *For Pipec* notes say what he is asked.

### Part A — the runtime and its safety (no table changes)

- **D-1 The runtime** (ADR 0038 decision 2). Upgrade uv to a release that offers the 3.12 patch
  built with SQLite 3.53.1 (any `python-build-standalone` build from 20260602; 3.12.16 is the
  latest today), then `uv python install` it, recreate the `.venv` and
  `uv sync --all-packages --all-groups --extra cuda`. Before switching, the Dependabot rule for
  runtimes applies: in a separate environment with the new Python, the voice and face embeddings
  of the fixed test clips and frames must be identical and the `slow` tests must pass. Pin
  `sqlite-vec==0.1.9` in `server/pyproject.toml`. `open_db` asserts `sqlite_version >= 3.51.3`,
  the compile option `ENABLE_FTS5`, that extensions load, and `vec_version() == "v0.1.9"`; below
  any of them the server does not start (a closed error, no path in it). It logs the versions
  once. *For Pipec:* the Python patch upgrade happens on his laptop at Task A1; he says when.
- **D-2 Pragmas set and read back** (ADR 0038 decision 3): `journal_mode=WAL`,
  `synchronous=NORMAL`, `foreign_keys=ON`, `secure_delete=ON`, `busy_timeout=5000`,
  `wal_autocheckpoint=1000`, `journal_size_limit=67108864`, `temp_store=MEMORY`,
  `cell_size_check=ON`, `recursive_triggers=OFF`, `trusted_schema=ON` (its reason in a comment:
  the `vec0` delete inside `recall_units_ad`); a mismatch on read-back refuses to start. Then
  `PRAGMA optimize=0x10002` and `PRAGMA quick_check` (a failure logs its count and refuses to
  start). The retention job runs `PRAGMA optimize` once per pass; `close_db` keeps its own. The
  values live in one constant in `db.py`, not in settings (YAGNI; ADR 0031 decision 12).
- **D-3 The transaction** (ADR 0038 decision 3): `transaction()` opens `BEGIN IMMEDIATE` inside
  its `try`, so a cancellation after the `BEGIN` reached the database rolls back.
  `run_migrations` turns `foreign_keys` back on after every script, passed or failed.
- **D-4 One time format in the writers** (ADR 0038 decision 5). A new module
  `server/timestamps.py` formats an instant (`instant_text`: 32 characters, UTC, microseconds,
  `+00:00`; a naive datetime raises), parses one (`parse_instant`), formats a day (`day_text`)
  and a validity day (`validity_day`, the household day). Every writer uses it; no `.py` under
  `server/src` contains `datetime(\s*'now'`; the private `_iso` helpers and inline
  `isoformat(timespec="microseconds")` calls go. A temporal V4 fact or relation opens and closes
  on a household **day** (validity bounds are ISO dates at day or month precision). Existing rows
  are converted in Part B.
- **D-5 One writer per table, SQL only in `server/memory/`** (ADR 0038 decision 8). The face and
  voice profile statements move from `vision/faces.py` and `voice/voiceprints.py` behind the
  consent stores (`memory/biometric_consent.py`, `memory/voice_consent.py`), which then own every
  statement on `face_profiles`, `vec_faces` and `voice_profiles`; `owner_pin_credentials` gets one
  writer (`memory/owner_credentials.py`), which `household_authorization` calls; `personal_setup`
  reads roles, relations and PINs through their stores. A guard lists the owner module of
  **every** table and fails on any other module's SQL on it, and on any SQL outside
  `server/memory/` (with a leak test).
- **D-6 The byte-level deletion test** (ADR 0038 decision 9), on today's schema: a unique canary
  is written to a plain table row and to `recall_units` (so FTS5 and `vec0` get it), deleted
  through the owning store, then `checkpoint_wal()`; neither `omnibot.db` nor its `-wal` holds the
  canary text or the canary vector's bytes. It runs in CI (`integration`) and again in Part B on
  the v2 schema.

### Part B — the v2 schema

- **D-7 Developed as migrations, delivered as one.** On the branch, each task adds one
  development migration (017 to 022) so the suite stays green task by task. Task B8 then squashes
  them: `memory/schema_v2.sql` (a fresh install goes from 0 straight to version **17**) and
  `memory/upgrade_v16.sql` (the real database goes from 16 to 17 in one script); migrations 001 to
  016 and the development ones leave the tree (git keeps them). A non-empty database below 16 is
  refused with a closed error. The golden schema proves the squash: a fresh install and a
  version-16 canary database upgraded are identical.
- **D-8 The migration runner** (ADR 0038 decision 9). The runner owns atomicity for every v2
  script: `PRAGMA foreign_keys=OFF` when the entry says `rebuild=True` (set before the
  transaction), `BEGIN IMMEDIATE`, the script (which holds no `BEGIN`, `COMMIT` or
  `user_version`), `PRAGMA user_version`, `pragma_foreign_key_check` (any row aborts), `COMMIT`,
  then `foreign_keys=ON` whatever happened, then `checkpoint_wal()` and `PRAGMA optimize`; after
  a `rebuild=True` migration it also runs `VACUUM` (outside the transaction), which compacts the
  rebuilt tables and leaves no free page behind (6 MB today: instant).
  `_MIGRATIONS` entries become a small frozen dataclass (`version`, `filename`, `rebuild`).
  A rebuilt table copies its ids, sets `sqlite_sequence` back to its old counter (captured before
  the `DROP`), and creates its triggers after the copy.
- **D-9 Ids** (ADR 0038 decision 5). Every table keeps an `INTEGER PRIMARY KEY`; a table whose id
  another row, a vector, an audit or the register names gets `AUTOINCREMENT`. A `uid TEXT NOT
  NULL UNIQUE CHECK (length(uid) = 36)` goes on `entities`, `literal_facts_v4`,
  `entity_relations_v4`, `conversation_records`, `conversation_turns`, `conversation_episodes`,
  `recall_units`, `memory_candidates`, `pending_topics`, `care_contacts`, `face_profiles` and
  `voice_profiles`. New rows get a UUIDv7 from `server/ids.py` (`new_uid()`, RFC 9562, written
  here: Python 3.12 has no `uuid7` and no dependency is added); the upgrade gives existing rows a
  random UUIDv4 built in SQL (a `uid` must be unique and stable, not ordered).
- **D-10 Turns as rows** (ADR 0038 decision 6). `conversation_turns`: `id`, `uid`, `record_id`
  (→ `conversation_records`, `CASCADE`), `correlation_id` (`UNIQUE`), `said_at`, `verdict` (the
  `TurnVerdict` values), `heard` and `said` (as today's limits), `sensitivity` (`NULL` until a job
  sets it), `redacted_at`. `conversation_records` loses `turns`, `turn_count` and `byte_count`
  (counts become queries over the turns: one source of truth); the segment rule and the 200 MB cap
  use `COUNT` and `SUM(length(heard) + length(said))`. `conversation_record.py` keeps its public
  functions and returns the same `RecordedTurn` tuple, ordered by `said_at` then `id`; it appends
  with one `INSERT`. The upgrade copies each JSON turn (`at`, `cid`, `heard`, `said`, `voice`) to
  a row with `json_each`, in order.
- **D-11 Typed derivation** (ADR 0038 decision 6, ADR 0031 decisions 4 and 6). `recall_units`:
  `turn_id` (→ turns, `CASCADE`) **xor** `episode_id` (→ episodes, `CASCADE`), replacing
  `source_record_id` and `correlation_id`; plus `recorded_at`, `embedded_at`, `origin`,
  `transformation`. `episode_sources` (`episode_id` and `turn_id`, both `CASCADE`, primary key the
  pair): the link goes with its turn, the episode stays; the episode's own `record_id` keeps
  `CASCADE` until Plan 0086 decides the diary's retention. `memory_candidates` gains
  `source_turn_id` (nullable: no turn exists when the record is off; `CASCADE`) and keeps
  `source_correlation_id`. `pending_topics` replaces `source_record_id` and `correlation_id` with
  `source_turn_id` (`UNIQUE`, `CASCADE`). `literal_facts_v4` gains `origin_candidate_id`
  (→ candidates, `SET NULL`); `source_memory_id` leaves both V4 tables. `origin` (`reported`,
  `observed`, `document`) and `transformation` (`original`, `summary`, `extracted`, `inferred`) go
  on facts, relations, episodes and units with their CHECKs; the upgrade sets alta facts and
  relations `reported`/`original`, promoted facts `reported`/`extracted` with their candidate,
  episodes and episode units `reported`/`summary`, turn units `reported`/`original`. A trigger
  refuses an `UPDATE` of `recall_units.body`. **Idempotency is a schema rule, not only a job
  rule** (ADR 0031 decision 8): `recall_units.turn_id` and `recall_units.episode_id` are each
  `UNIQUE` (one unit per turn, one per episode), `episode_sources` has the pair as its key and
  `conversation_episodes.record_id` stays `UNIQUE`, so a background job retried after a crash
  cannot duplicate a unit, an episode or a link even if its own check is wrong.
- **D-12 Two times on every edge** (ADR 0038 decision 6). In both V4 tables `asserted_at` becomes
  `recorded_at` and `superseded_at` becomes `retracted_at` (set whenever a row leaves `active`);
  `valid_from` and `valid_to` keep world time as ISO dates at day or month precision. The two
  existing instant bounds become their UTC day in the upgrade (SQL knows no household zone; a
  bound closed between local and UTC midnight moves one day, accepted for those two rows).
- **D-13 Archive** (ADR 0038 decision 6): `archived_at` on both V4 tables, episodes and recall
  units; every reader filters `archived_at IS NULL` (a test per reader with an archived canary);
  nothing sets it in this plan (Plan 0086 does).
- **D-14 Embedding spaces** (ADR 0038 decision 6). `embedding_spaces`: `id`, `model_tag`,
  `digest` (from Ollama `/api/tags`), `dimension`, `metric`, `normalized`, `state` (`building`,
  `active`, `retired`; at most one `active`), `created_at`, `activated_at`. `recall_units` replaces
  `embedding_model` with `embedding_space_id` (nullable: no vector yet) and `embedded_at`. A new
  `recall_vectors_768` (`vec0`: `owner_entity_id` and `space_id` partition keys, `sensitivity` and
  `said_day` metadata, `embedding float[768] distance_metric=cosine`) replaces
  `recall_units_vec`; its rowid is the unit id. At warm-up `recall_index` reads the configured
  tag's digest; a tag or digest unlike the active space's opens a `building` space; units are
  re-embedded one by one into it (their old vector replaced); vector search is off for the owner
  until every unit is in the new space, then the space becomes `active` and the old one
  `retired`; lexical search never stops. The KNN filters the owner, the space, the sensitivity
  and the recall window's days **inside** the query (today the window is applied after the top
  20, so a narrow window can miss a match). The upgrade carries no vector: it creates no space,
  every unit starts with no vector, and the first start re-embeds the units into a new `active`
  space through this same path (65 units, a few seconds), which proves the re-index on the real
  data.
- **D-15 The uniform table rules** (ADR 0038 decision 5): every ordinary table `STRICT`; every
  instant column the exact CHECK (`length(x) = 32`, six explicit fraction digits, and
  `strftime('%Y-%m-%dT%H:%M:%S', substr(x, 1, 19)) IS substr(x, 1, 19)`), every day column
  `date(x) IS x`, validity bounds day or month; defaults `strftime('%Y-%m-%dT%H:%M:%f000+00:00',
  'now')`; `NOT NULL` and CHECK on states, sensitivities, visibilities, kinds, origins and
  transformations; the write channel and the policy audit's action and policy stay closed lists
  in Python; `json_valid` on every JSON column; the naming convention (tables plural `snake_case`;
  `<role>_entity_id`; instants `_at`, days `_day` or a named bound; indexes
  `<table>_<purpose>_idx`; triggers `<table>_<ai|ad|au_…>`); only indexes and the two V4 time
  columns are renamed; FTS5 `secure-delete=1` on every FTS5 table; a fixed `application_id`,
  checked by `open_db` once the database is at 17.
- **D-16 Keys and delete rules:** every relation a declared foreign key with an explicit rule;
  today's rules stay except `face_profiles.entity_id` and `voice_profiles.entity_id`, which become
  `RESTRICT` (the consent revocation deletes biometrics and `vec_faces`); `face_profiles` gets
  `AUTOINCREMENT` (a deleted top id was reused, and `vec_faces.rowid` followed it).
- **D-17 Indexes:** a full index on every foreign key (21 on today's columns, plus the new
  derivation keys), the three partial V4 indexes that lead with a cascading key made full,
  `entities_name_idx` dropped, every frequent query's index confirmed by `EXPLAIN QUERY PLAN` and
  named in the dictionary with its query.
- **D-18 Dead tables and their code:** the nine tables of *The audit* item 4 are absent from v2;
  the upgrade aborts if any holds a row; `retention`'s dead deletes, `embeddings.embed` and its
  cache helpers (`EMBEDDING_DIM` stays), `declarative.assert_fact` and `get_active_facts`,
  `memory/legacy_v4_migration.py`, `scripts/migrate_memory_v4.py`, the `events` write in
  `perception` (its log line stays) and the dead-table part of `scripts/memory_test.py --show-db`
  (it prints the health counts instead) go, with their tests.
- **D-19 The dictionary, the guards and the health check** on v2:
  `docs/architecture/data-dictionary.md` (per table: purpose, owner module, columns, keys and
  rules, indexes with their queries, classification `personal`/`biometric`/`credential`/`audit`/
  `operational`, retention; then the conventions, the time format, the deliberate
  denormalizations, the SQLite floor and *Not tuned yet*); guards for primary keys, `STRICT`,
  explicit rules, a full index per foreign key, dictionary coverage of tables and columns both
  ways, naming, the golden schema, and the 26 `memory/` modules importing `server.cognition` frozen
  by name; `memory/db_health.py` and `iroko-admin health` (no PIN, server stopped, counts only:
  integrity, foreign keys, FTS5 integrity, orphans of every projection, staleness with named
  constants, rows outside the formats, unknown channels, `page_count`, `freelist_count`, versions;
  exit 1 on any fault; `just db-health` its alias). It also prints the **storage fingerprint**:
  `user_version`, a SHA-256 of the normalized schema (the golden schema's normalization),
  `application_id`, `page_size`, the SQLite and `sqlite-vec` versions and the active embedding
  space's tag and digest; every benchmark and the freeze record it, so a before-and-after
  comparison always names the storage it measured (ADR 0038 decision 10).
- **D-20 Rehearsal, backup and timing:** merge after Plan 0084 closes; with the server stopped,
  back up to `data/backups/pre-0085-<YYYYMMDD-HHMMSS>/`; **prove the rollback first** (restore
  the backup into `data/rehearsal-0085/` and open it with the current `main`: version 16,
  `integrity_check` ok, the same counts); rehearse on a copy (health and per-table counts at 16,
  the upgrade, the same at 17, turn rows equal to the JSON turns, units, episodes and facts
  equal, 0 rows outside the formats); a reset, a restart and a restore are three different
  tests, and this plan runs the last two; Pipec starts the server; the backup is deleted
  once Pipec accepts (it would hold what a later deletion removes). The rollback is that backup
  with the previous `main`.
- **D-21 Tuning only listed** (ADR 0038 decision 11): a read pool, `synchronous=FULL` everywhere,
  `cache_size`, `mmap_size`, `int8` or binary vectors, FTS5 `trigram` or stemming, a second
  embedding model, `vec1` or `sqlite-vector`, backups by `VACUUM INTO`, encryption: each waits for
  its measurement (D-22) or its ADR. `page_size` stays SQLite's 4096. Optional extensions listed
  for later, each needing its own measurement, pin and ARM64 check: Sqlean's `fuzzy` and
  `unicode` (matching a spoken name through transcription errors) and R-Tree (already compiled
  in; sensors and places, P2.1). Not adopted: `sqlite-zstd` (its author does not trust it with
  production data), ZIPVFS, CEROD and SEE (paid).
- **D-22 A storage benchmark, so tuning has a baseline** (ADR 0031 decision 12 step 4, ADR 0038
  decision 11). `scripts/bench_storage.py` (`just db-bench`) builds a throwaway v2 database in
  `data/bench-0085/` with **synthetic** data only (invented Spanish sentences, random unit
  vectors): one owner, 10 000, 50 000 and 100 000 recall units with their turns and their FTS5
  and `vec0` rows. Per size it measures the insert rate, p50 and p95 of the lexical, vector and
  hybrid search through `recall_search` (window filter on and off), the file and WAL sizes, and
  the projected file size per year at a given turns-per-day rate. It changes no setting and
  tunes nothing: its record (`docs/evals/0085-storage-benchmark.md`, with the storage
  fingerprint and the host) is the baseline every later tuning step must beat, on the laptop now
  and on the Pi when it arrives.

**Goal.** The memory engine's store becomes the v2 foundation of ADR 0038 on a pinned, checked
SQLite: one time format, keys and typed derivation that make «everything derived from this turn»
one query, turns as rows, two times on every edge, embedding spaces that never mix, `STRICT`
tables with exact constraints, one writer per table, a dictionary, a counts-only health check and
a proven byte-level deletion, reached by the real database in one tested upgrade.

**Architecture.** Part A: `server/timestamps.py`, the runtime assertions and pragmas in `db.py`,
the transaction fix, the biometric writers behind their consent stores, the ownership guards, the
deletion test. Part B: development migrations squashed into `schema_v2.sql` and
`upgrade_v16.sql`, an atomic runner, `server/ids.py`, the stores adapted (record, recall,
candidates, pending, V4), `embedding_spaces` with a new `vec0`, `memory/db_health.py`, the
dictionary and the schema guards.

**Tech stack.** Python 3.12 (uv-managed, SQLite 3.53.1), aiosqlite, FTS5, `sqlite-vec` 0.1.9,
pytest. No new dependency (UUIDv7 is written here), no setting, no wire, route, prompt or robot
change.

**Spec.** [ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md);
[ADR 0032](../../adr/0032-block-c-hygiene-correct-forget-and-years.md) decision 1 and its C1
*Test consequences*; [ADR 0031](../../adr/0031-the-memory-engine-boundary.md) decisions 4 to 9,
11 and 12; [ADR 0011](../../adr/0011-sqlite-transaction-ownership.md);
[current state](../../architecture/current-state.md);
[guardrails](../../architecture/implementation-guardrails.md).

**Required reading.** The above, then the code: `db.py`; every `memory/migration_*.sql` and
`memory/schema.sql`; the stores of every table (`relational_v4.py`, `declarative.py`,
`candidates.py`, `conversation_record.py`, `conversation_types.py`, `conversation_capture.py`,
`conversation_episodes.py`, `conversation_jobs.py`, `recall_store.py`, `recall_search.py`,
`recall_index.py`, `pending_store.py`, `retention.py`, `care_contacts.py`, `commissioning.py`,
`household_authorization.py`, `owner_credentials.py`, `biometric_consent.py`, `voice_consent.py`,
`admin_audit.py`, `meta.py`); `vision/faces.py`, `voice/voiceprints.py`, `vision/perception.py`,
`personal_setup.py`, `admin_cli.py`; `tests/unit/test_architecture_guards.py` and the schema tests
under `tests/integration/`.

## Global constraints

- English code, comments and docstrings (Google style); no `Any`, no `print`, no `os.path`, no
  bare `except`; logging with `%`.
- Counts only: no database value in a log line, a health report, a test output, an exception
  message or this plan's evidence.
- No behaviour change a person can hear: every route, prompt and reply is byte-identical to
  `main` with the same data, except that a recall window now filters inside the KNN (D-14) and the
  removed `events` row (D-18).
- No real household data: invented canaries only; `scripts/check_reserved_terms.py` passes.

## Review focus

1. **A value in a third format** in the real database: the upgrade must abort and leave version
   16, never guess (Task B8, a canary of 23 characters).
2. **The record read back differently**: the same turns, in the same order, with the same
   verdicts, after the JSON becomes rows; a record with 0 turns; two turns with the same instant
   (Task B3).
3. **A projection lost or doubled by a rebuild**: FTS5 indexes every unit once, every vector has
   its unit, triggers exist, an `AUTOINCREMENT` counter never goes back (Tasks B4, B6, B8).
4. **A model change half done**: some units in the new space, a query arrives; nothing compares
   two spaces and lexical recall still answers (Task B6).
5. **A candidate without a record** (the record switch off): it is kept with a `NULL` turn and
   behaves as today (Task B4).

---

## Permitted files

Only these change (paths under `server/src/server/` unless they start with `tests/`, `scripts/`,
`docs/` or the root); a need outside the list stops the plan for Pipec.

| Part | Files |
|---|---|
| A | `timestamps.py` (new), `db.py`, the writers of D-4 (`memory/candidates.py`, `conversation_consent.py`, `conversation_record.py`, `conversation_episodes.py`, `recall_store.py`, `household_authorization.py`, `biometric_consent.py`, `voice_consent.py`, `owner_credentials.py`, `declarative.py`, `meta.py`, `relational_v4.py`, `retention.py`, `cognition/spoken_dates.py`, `admin_cli.py`), `vision/faces.py`, `voice/voiceprints.py`, `personal_setup.py`, `server/pyproject.toml`, `uv.lock`, `.python-version`; their tests, `tests/unit/test_timestamps.py`, `tests/integration/test_physical_deletion.py`, `tests/integration/test_db_runtime.py`, `tests/unit/test_architecture_guards.py` |
| B | `ids.py` (new), `db.py`, `llm_transport.py` (the digest read), `memory/schema_v2.sql` and `memory/upgrade_v16.sql` (new; the development migrations 017 to 022 live only on the branch), every store named in *Required reading*, `memory/embeddings.py`, `memory/db_health.py` (new), `vision/perception.py`, `admin_cli.py`, `scripts/memory_test.py`, `scripts/bench_storage.py` (new), `justfile`; deleted: `memory/schema.sql`, `memory/migration_*.sql`, `memory/legacy_v4_migration.py`, `scripts/migrate_memory_v4.py`; tests: every schema and store test that builds or reads a table, `tests/fixtures/migration_canaries.py`, `tests/fixtures/schema_v2.json`, `tests/unit/test_schema_guards.py`, `tests/integration/test_upgrade_v16.py`, `tests/integration/test_db_health.py`,
`tests/unit/test_bench_storage.py`; docs: `docs/evals/0085-storage-benchmark.md` (new), `docs/architecture/data-dictionary.md` (new) and the documents of Task B12 |

**Rollback boundary.** Each part is its own branch and PR; before the merge, the rollback is the
branch. Part A changes no table: after the merge its rollback is a revert (and the previous Python
patch). Part B's rollback after the real upgrade is the backup of D-20 with the previous `main`.

---

## Part A — the runtime and its safety

### Task A0: Re-audit and baseline

- [ ] **Step 1:** after Plan 0084 closes, `git checkout main && git pull`, then create
  `feat/0085a-storage-runtime`.
- [ ] **Step 2:** verify and **stop and report** if any is false: *The audit* items 6 to 8; that
  `transaction()` awaits `BEGIN IMMEDIATE` before its `try`; the statements on `face_profiles`,
  `vec_faces`, `voice_profiles` and `owner_pin_credentials` and their modules; every
  `datetime('now')` writer and `_iso` helper of D-4; which tables have no ownership guard today.
- [ ] **Step 3:** baseline count: `MEMORY_ENABLED=false uv run pytest -m "not slow and not
  hardware and not eval" -q -n auto` (not in the background if Pipec is rehearsing).

### Task A1: The runtime pinned and checked

**Files:** `server/pyproject.toml`, `uv.lock`, `.python-version`, `db.py`,
`tests/integration/test_db_runtime.py`.

**Interfaces:** `SQLITE_FLOOR: Final = (3, 51, 3)`, `SQLITE_VEC_VERSION: Final = "v0.1.9"`;
`async def check_runtime(conn: aiosqlite.Connection) -> RuntimeReport` (a frozen dataclass of the
versions and the compile options it needs), raising `BrainMemoryError` with a closed message below
the floor, without FTS5 or extension loading, or with another `sqlite-vec`; `open_db` calls it and
logs the report once.

- [ ] **Step 1:** in a separate environment (the Dependabot rule for runtimes): install the latest
  3.12 patch through an upgraded uv, confirm `sqlite3.sqlite_version == "3.53.1"`, that
  `sqlite-vec` loads, that the voice and face embeddings of the fixed fixtures are identical and
  that the `slow` tests pass. Pipec says when to switch the laptop (D-1).
- [ ] **Step 2: Write the failing tests:** each assertion refuses with a patched report (3.51.2,
  no FTS5, `v0.1.10`) and passes on the real one; the log line holds versions only.
- [ ] **Step 3:** Run → FAIL. **Step 4:** implement, switch the `.venv`, pin `sqlite-vec==0.1.9`.
  **Step 5:** Run → PASS.
- [ ] **Step 6:** commit `build: pin the SQLite runtime and check it at start (plan 0085)`.

### Task A2: Pragmas read back; the transaction and the runner

**Files:** `db.py`, `memory/retention.py`, `tests/integration/test_db_runtime.py`,
`tests/integration/test_db_transaction.py`.

**Interfaces:** `PRAGMAS: Final[Mapping[str, str | int]]` (D-2); `open_db` sets, reads back,
refuses a mismatch, runs `optimize=0x10002` and `quick_check`; `transaction()` with `BEGIN` inside
the `try`; `run_migrations` restores `foreign_keys`.

- [ ] **Step 1: Write the failing tests:** each pragma reads back its value; a mismatch (a patched
  read-back) refuses to start; a failing `quick_check` refuses; the retention pass calls
  `optimize`; `test_a_cancelled_transaction_after_begin_rolls_back` (the task is cancelled right
  after the `BEGIN` runs; the next `transaction()` succeeds and nothing was committed);
  `test_a_failed_migration_leaves_foreign_keys_on`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `fix: read pragmas back and close the transaction window (plan 0085)`.

### Task A3: One time format in the writers

**Files:** `timestamps.py` (new), the writers of D-4, `tests/unit/test_timestamps.py`, their
tests, `tests/unit/test_architecture_guards.py`.

**Interfaces:** `INSTANT_LENGTH: Final = 32`; `def instant_text(moment: datetime) -> str`;
`def parse_instant(text: str) -> datetime`; `def day_text(day: date) -> str`;
`def validity_day(moment: datetime, zone: ZoneInfo) -> str`. `timestamps` imports no settings,
database or FastAPI.

- [ ] **Step 1: Write the failing tests:** a `+03:00` moment becomes its UTC instant in 32
  characters; a naive one raises; round trip; text order equals time order; `validity_day` at
  02:30 UTC is the previous day in `America/Santiago`; a temporal V4 fact and relation open and
  close on a household day; `test_no_server_module_writes_datetime_now` (`datetime\(\s*'now'` in
  no `.py` under `server/src`, with a leak test); `test_the_instant_format_is_defined_once`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement and move every writer. **Step 4:** Run → PASS;
  the writers' tests unchanged in what they assert.
- [ ] **Step 5:** commit `refactor: write every time in one format (plan 0085)`.

### Task A4: One writer per table

**Files:** `memory/biometric_consent.py`, `memory/voice_consent.py`, `memory/owner_credentials.py`,
`memory/household_authorization.py`, `vision/faces.py`, `voice/voiceprints.py`,
`personal_setup.py`, their tests, `tests/unit/test_architecture_guards.py`.

**Interfaces:** the face profile insert and the reads `vision/faces.match_face` needs move to
`biometric_consent` (`store_face_profile`, `face_profile_rows`); the voiceprint insert and reads
to `voice_consent` (`store_voiceprint`, `voiceprint_rows`); `owner_credentials.revoke_for(
person_entity_id, *, conn)` is called by `household_authorization`; each reader `personal_setup`
needs lives in its store. `TABLE_OWNERS: Final[Mapping[str, str]]` in the guard test, one module
per table.

- [ ] **Step 1: Write the failing guards:** every table of a fresh database is in `TABLE_OWNERS`;
  no other module's SQL names it; no SQL outside `server/memory/`; leak tests.
- [ ] **Step 2:** Run → FAIL. **Step 3:** move the statements; behaviour unchanged (the face,
  voice, enrolment, revocation and setup suites pass unchanged). **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `refactor: one writer per table, SQL only in memory (plan 0085)`.

### Task A5: The byte-level deletion test

**Files:** `tests/integration/test_physical_deletion.py`.

- [ ] **Step 1:** write the test of D-6 (a temporary database through `open_db`): the canary text
  and the canary vector's bytes are present in the file or the WAL after the write and absent
  after the store's delete and `checkpoint_wal()`, for a plain row (a candidate's value scrub), an
  FTS5 row and a `vec0` row (a recall unit deleted with its record). If a canary survives, **stop
  and report**: it is a finding for ADR 0038, not something to patch here.
- [ ] **Step 2:** Run → PASS (the expected outcome on SQLite 3.53.1 and `sqlite-vec` 0.1.9).
- [ ] **Step 3:** commit `test: prove physical deletion at the byte level (plan 0085)`.

### Task A6: Verification and review of Part A

- [ ] **Step 1:** `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval"
  -q -n auto`, `uv run pytest -m slow -q` (the new Python), `uv run pyright`,
  `uv run mypy server/src robot/src`, `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run ruff check scripts/*.py`, `uv run python scripts/check_reserved_terms.py`, `just gate`.
- [ ] **Step 2:** the `simplify` skill, then in parallel `database-architect`,
  `architect-reviewer`, `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:silent-failure-hunter`
  and `security-auditor` on `git diff main...HEAD` (each on `sonnet`, `.claude/` first,
  read-only); every finding verified and fixed with its RED test; Step 1 again.

### Task A7: Merge Part A

- [ ] **Step 1:** Pipec starts the server and the robot and speaks a short script the agent gives
  (a greeting, «¿qué sabes de mí?», a recall question, a face-identified turn); the agent reads
  `logs/server.log` (versions logged, no pragma refusal) and records the outcomes.
- [ ] **Step 2:** push, PR, squash-merge with green CI, delete the branch.

---

## Part B — the v2 schema

### Task B0: Re-audit and baseline

- [ ] **Step 1:** `git checkout main && git pull` (Part A merged), create `feat/0085b-schema-v2`.
- [ ] **Step 2:** verify and **stop and report** if any is false: SQLite 3.53.1 in the `.venv`;
  *The audit* items 1 to 6 still hold (the schema on a clean database; counts by a throwaway
  script on a copy); the readers of `RecordedTurn`; every query on `correlation_id`,
  `source_record_id`, `embedding_model`, `asserted_at` and `superseded_at`; the frequent queries of
  D-17 with their indexes.
- [ ] **Step 3:** baseline count, as Task A0.

### Task B1: The runner and the ids

**Files:** `db.py`, `ids.py` (new), `tests/integration/test_db.py`, `tests/unit/test_ids.py`.

**Interfaces:** `@dataclass(frozen=True) class Migration: version: int; filename: str; rebuild:
bool = False`; `_MIGRATIONS: tuple[Migration, ...]`; `run_migrations` per D-8;
`def new_uid() -> str` (UUIDv7, 36 characters, version nibble 7, variant bits `10`, ordered within
a millisecond by a monotonic counter).

- [ ] **Step 1: Write the failing tests:** a v2 script holding `COMMIT` is refused; a failing
  script leaves the version and every table as before and foreign keys on; a `rebuild=True`
  script runs with foreign keys off and a violation aborts it; `new_uid` format, uniqueness over
  100 000 calls and ordering.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement (scripts 001 to 016 keep their own
  transactions until Task B8 removes them; only new entries are runner-owned). **Step 4:** Run →
  PASS.
- [ ] **Step 5:** commit `feat: an atomic migration runner and UUIDv7 ids (plan 0085)`.

### Task B2: Development migration 017 — the dead tables out

D-18: the eight dead tables other than `memories` dropped (aborting if one holds a row), their code
and tests removed or reseeded through `relational_v4` (deleted: `test_memory_v4_migration`,
`test_legacy_migration_*`, the `embed` cases of `test_embeddings`; reseeded:
`test_household_authorization_schema`, `test_memory_v4_schema`, `test_memory_relational`,
`test_owner_stranger_matrix`, `test_memory_integration`, `test_conversation_schema`,
`test_retention`; updated: `test_architecture_guards`). `memories` goes in Task B5, with the V4
rebuild.

- [ ] **Step 1:** failing tests (each dead table gone; a canary row aborts; no SQL names them).
  **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: retire the dead tables (plan 0085)`.

### Task B3: Development migration 018 — turns as rows

**Files:** the migration, `memory/conversation_record.py`, `memory/retention.py` (the cap),
`tests/integration/test_conversation_turns.py` (new), the record suites.

**Interfaces:** D-10; `conversation_record`'s public functions unchanged; `RecordedTurn` unchanged.

- [ ] **Step 1: Write the failing tests:** a record's JSON turns become rows in order with the same
  fields; reading a record returns the same `RecordedTurn` tuple as before (Review focus 2,
  including 0 turns and equal instants); the segment's turn limit and the 200 MB cap compute from
  rows; appending is one `INSERT`; a turn's `correlation_id` is unique.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS; every record, capture, episode,
  admin and recall suite unchanged.
- [ ] **Step 5:** commit `feat: keep a conversation's turns as rows (plan 0085)`.

### Task B4: Development migration 019 — typed derivation

**Files:** the migration, `recall_store.py`, `candidates.py`, `pending_store.py`,
`pending_capture.py`, `conversation_capture.py`, `conversation_episodes.py`, `memory_writer.py`,
`relational_v4.py`, their tests.

**Interfaces:** D-11.

- [ ] **Step 1: Write the failing tests:** deleting one turn removes its unit, its FTS row and its
  vector, its candidate and its pending topic, and only the link of its episode (the episode
  stays); a candidate without a record keeps a `NULL` turn (Review focus 5); a promoted fact names
  its candidate, and the candidate's deletion leaves the fact; the migration maps every unit,
  candidate and topic to its turn by the old correlation id (none left unmapped); origins and
  transformations as D-11; an `UPDATE` of a unit's body is refused; the indexing and episode
  jobs run twice over the same turns (a simulated retry) leave one unit per turn, one episode per
  record and one link per pair.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: typed derivation from turns to memories (plan 0085)`.

### Task B5: Development migration 020 — two times on every edge, archive, V4 rebuilt

**Files:** the migration, `relational_v4.py` and every V4 reader, `canonical_writer.py`,
`policy_gated_v4_reader.py`, `conversation_episodes.py`, `recall_store.py`, their tests.

**Interfaces:** D-12 and D-13; `memories` and `source_memory_id` gone.

- [ ] **Step 1: Write the failing tests:** `recorded_at` and `retracted_at` set as D-12; a
  supersede closes world time on a household day; the two instant bounds become days; every reader
  skips an archived fact, relation, episode and unit (one canary each); ordering across converted
  and new instants is right.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: record time and archive on memory edges (plan 0085)`.

### Task B6: Development migration 021 — embedding spaces

**Files:** the migration, `recall_store.py`, `recall_search.py`, `recall_index.py`,
`llm_transport.py` (the digest from `/api/tags`), their tests,
`tests/integration/test_recall_embedding_spaces.py` (new).

**Interfaces:** D-14; `async def model_digest(client: httpx.AsyncClient, tag: str) -> str | None`;
`async def active_space() -> EmbeddingSpace | None`; `async def ensure_space(tag: str, digest:
str, dimension: int) -> EmbeddingSpace`; `async def units_to_reindex(space_id: int, limit: int) ->
list[tuple[int, str]]`.

- [ ] **Step 1: Write the failing tests** (ADR 0031's C1 RED test first): units in space A; the
  configured model becomes B; a search runs no vector comparison and the lexical hit still comes;
  the re-index moves every unit to B, then vector search is on and B is `active`; half re-indexed,
  nothing compares across spaces (Review focus 4); another dimension is refused, logged by class,
  and leaves vector search off; a one-day window finds a match outside the global top 20; units
  with no space at start are embedded into a new `active` space (D-14's first start); no text in
  the log.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS; the calibrated recall gate tests
  unchanged.
- [ ] **Step 5:** commit `feat: embedding spaces that never mix (plan 0085)`.

### Task B7: Development migration 022 — the uniform rules

**Files:** the migration, the stores whose tables it rebuilds, the callers of `ids.new_uid`,
`tests/integration/test_schema_rules.py` (new).

**Interfaces:** D-9, D-15, D-16 and D-17 on every table not yet rebuilt, and `uid` everywhere D-9
says.

- [ ] **Step 1: Write the failing tests** (behaviour, one parametrized case per table): an old
  format, an impossible instant (`2026-13-45T99:99:99.0abcde+00:00`, `2026-02-31T…`), a bad day,
  invalid JSON and a text in an `INTEGER` column are refused; every new row has a `uid`; the two
  profiles refuse their person's deletion; a deleted top id is never reused; each child lookup of a
  `DELETE FROM entities` uses an index (`EXPLAIN QUERY PLAN`).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: strict tables, exact constraints and indexes (plan 0085)`.

### Task B8: The squash — one baseline and one upgrade

**Files:** `memory/schema_v2.sql`, `memory/upgrade_v16.sql` (new), `db.py`; deleted:
`memory/schema.sql`, `memory/migration_*.sql` and the development migrations;
`tests/fixtures/migration_canaries.py`, `tests/fixtures/schema_v2.json`,
`tests/integration/test_upgrade_v16.py`; every test that built a database at an old version.

**Interfaces:** D-7 and D-8; `_MIGRATIONS` holds the baseline (0 → 17) and the upgrade (16 → 17,
`rebuild=True`); `application_id` set by both and checked by `open_db` (D-15).

- [ ] **Step 1: Write the failing tests:** a fresh install and a version-16 canary database
  upgraded equal `schema_v2.json` (the golden schema, regenerated only on purpose by a documented
  helper); every table's rows carried with the expected counts and values; a third time format
  aborts and leaves 16 (Review focus 1); a non-empty database below 16 is refused; FTS5 indexes
  every unit once and the counters never go back (Review focus 3); after the upgrade
  `freelist_count` is 0 (the `VACUUM` of D-8); the deletion test of Task A5 passes on v2.
- [ ] **Step 2:** FAIL. **Step 3:** write the two scripts from the development migrations and
  remove the old files. **Step 4:** PASS, with the whole suite.
- [ ] **Step 5:** commit `feat: the v2 schema as one baseline and one upgrade (plan 0085)`.

### Task B9: The health check, the dictionary and the guards

**Files:** `memory/db_health.py` (new), `admin_cli.py`, `justfile`, `scripts/memory_test.py`,
`docs/architecture/data-dictionary.md` (new), `tests/integration/test_db_health.py`,
`tests/unit/test_schema_guards.py`, `tests/unit/test_architecture_guards.py`.

**Interfaces:** D-19; `@dataclass(frozen=True) class HealthReport` (ints and bools only);
`STALE_VECTOR_AFTER`, `STALE_EPISODE_AFTER: Final[timedelta]`; `async def check_health(conn:
aiosqlite.Connection, *, now: datetime) -> HealthReport` (changes no row);
`def health_failed(report: HealthReport) -> bool`.

- [ ] **Step 1: Write the failing tests:** each health measure sees its planted fault and a clean
  database passes; `check_health` changes no table's content; no canary reaches the printed
  report; the report prints the storage fingerprint, whose schema hash changes when the schema
  changes and not otherwise; the schema guards with their leak tests; the dictionary covers every
  table and column both ways.
- [ ] **Step 2:** FAIL. **Step 3:** implement and write the dictionary from the v2 schema and the
  code. **Step 4:** PASS; `scripts/check_reserved_terms.py` passes.
- [ ] **Step 5:** commit `docs: the data dictionary, schema guards and health check (plan 0085)`.

### Task B10: The storage benchmark

**Files:** `scripts/bench_storage.py` (new), `justfile` (`db-bench`),
`docs/evals/0085-storage-benchmark.md` (new), `tests/unit/test_bench_storage.py` (new).

**Interfaces:** D-22; `def build_fixture(path: Path, *, units: int, seed: int) -> None`;
`async def measure(path: Path, *, queries: int) -> BenchResult` (a frozen dataclass of rates,
latencies in milliseconds, sizes in bytes and the storage fingerprint); the script prints the
table of D-22 and refuses any path outside `data/bench-0085/`, so it never touches a real
database.

- [ ] **Step 1: Write the failing tests:** the fixture holds exactly the requested counts and only
  invented text (the reserved-terms check passes on a generated sample); `measure` returns every
  field on a 200-unit fixture; a path outside the bench folder is refused.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS; run `just db-bench` on the laptop
  (not in the background if Pipec is rehearsing) and write the record, numbers only, with the
  fingerprint and the host (CPU, RAM, disk); delete the bench folder.
- [ ] **Step 5:** commit `test: a reproducible storage benchmark (plan 0085)`.

### Task B11: Verification and review of Part B

As Task A6, plus `pr-review-toolkit:pr-test-analyzer` and `pr-review-toolkit:type-design-analyzer`.

### Task B12: Rehearsal, the real upgrade and close

**Files:** `docs/architecture/current-state.md` and the Archify memory diagram (validate → deliver
→ visual-check), `docs/runbooks/operator-manual.md` (`iroko-admin health`, the runtime floor, the
backup before an upgrade and its deletion), `docs/evals/0085-storage-foundation-acceptance.md`
(new, counts only), ADR 0038 (`Accepted`), ADR 0031 (a note on decisions 8 and 11), ADR 0027 (a
note: turns are rows), ADR 0032 (*C1 implemented*; stays `Proposed`), the ADR index, the plan
board, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, the roadmap (row 8 and
*Database hygiene*), both delivery maps, and Pipec's local `docs/roadmap/tabla-tareas.md`.

- [ ] **Step 1:** confirm on `main` that no migration was added since Task B0 (else rebase and
  re-run B8 and B11). With the server stopped: the backup of D-20; the rollback proof of D-20
  (the backup restored and opened at version 16); the rehearsal on
  `data/rehearsal-0085/` (health and per-table counts at 16, the upgrade, the same at 17, turn
  rows equal to the JSON turns); the copy deleted. Any difference stops the plan.
- [ ] **Step 2:** merge (push, PR, squash-merge with green CI); Pipec starts the server (the
  upgrade runs, then the 65 units are re-embedded, D-14) and the robot and speaks the script of
  Task A7 plus one sensitive read of the owner's own data; each answers as before; with the server
  stopped, `iroko-admin health` exits 0.
- [ ] **Step 3:** when Pipec accepts, delete the `pre-0085` backup and record it; update the
  documents above; move the plan to `completed/`; commit `docs: close plan 0085, the storage
  foundation`, push, PR, squash-merge, delete the branch, return to `main`.

---

## Completion criteria

1. Part A merged: the runtime checked at start on SQLite 3.53.1, pragmas read back, the
   transaction fix, one time format in the writers, one writer per table, the byte-level deletion
   test green.
2. Part B merged: the real database at version 17 through `upgrade_v16.sql`, with the rehearsal's
   counts equal (turns, units, episodes, facts, relations, candidates, topics, profiles, consents,
   audits) and the dead tables gone with 0 rows.
3. `iroko-admin health` exits 0 on the real database: 0 integrity errors, 0 foreign key
   violations, 0 orphans, 0 rows outside the formats, one `active` embedding space.
4. The golden schema, the schema guards, the dictionary coverage and the deletion test pass;
   the storage benchmark's baseline is recorded with its fingerprint.
5. The spoken scripts of Tasks A7 and B12 answered as before.
6. The `pre-0085` backup deleted after Pipec's acceptance; the documents of Task B12 updated; the
   plan in `completed/`.

## Non-goals

Correcting, archiving or deleting a memory by voice or PIN, the deletion register and its
protocol's code, the diary's retention and the episode key change (ADR 0032 decisions 2 to 7, Plan
0086); the export (Plan 0087); an «erase a person» order and the audits' retention (Plan 0086);
backups, restore, encryption (ADR 0033); documents (ADR 0034); a model name on face vectors; every
item of D-21; extracting the engine (ADR 0031 decision 11); any wire, route, prompt, robot or
dependency change beyond the Python patch and the `sqlite-vec` pin.

## Found for Plan 0086 (C2), not done here

`vec0` 0.1.9 zero-fills a deleted vector and FTS5 `secure-delete` removes a deleted text once the
WAL is checkpointed (verified by the reviews; proven by Task A5). The deletion protocol is fixed by
ADR 0038 decision 4 (register line with `fsync`, delete under `synchronous=FULL`, checkpoint,
replay at start-up); Plan 0086 implements it, on the `uid` keys of this plan.

## Self-review (2026-11-13)

- **Spec coverage.** ADR 0038: decision 1 (one file) → no attached database, Part B; 2 (runtime)
  → D-1, Task A1; 3 (pragmas, transaction) → D-2, D-3, Task A2; 4 (deletion protocol) → fixed by
  the ADR, built by Plan 0086; 5 (schema rules) → D-4, D-9, D-15, Tasks A3, B1, B7; 6 (shapes) →
  D-10 to D-14, Tasks B3 to B6; 7 (primary data) → the upgrade carries episodes and their
  sensitivity, Task B8; 8 (writers) → D-5, Task A4; 9 (migrations, deletion test) → D-6 to D-8,
  Tasks A5, B1, B8; 10 (health) → D-19, Task B9; 11 (later) → D-21. ADR 0032 decision 1: time,
  keys, indexes, constraints, normalization (D-10 removes the JSON turns; the other deliberate
  denormalizations stay and are justified in the dictionary), naming, dead tables, dictionary,
  health, guard test, the engine's guards, tuning by measurement → D-4, D-15 to D-19, D-21. ADR
  0031's C1 test consequences → Tasks B6 and B9.
- **For Pipec:** when the laptop switches Python (D-1). Everything else follows ADR 0038's nine
  decisions.
- **Type consistency.** `instant_text`, `parse_instant`, `day_text`, `validity_day`,
  `check_runtime`, `PRAGMAS`, `Migration`, `new_uid`, `model_digest`, `active_space`,
  `ensure_space`, `units_to_reindex`, `HealthReport`, `check_health` and `health_failed` are each
  defined once and named the same in later tasks.
- **Revision from Pipec's engine studies (2026-11-13).** Pipec's own studies of the memory
  engine (29 October to 6 November, kept locally) were read against this plan. Added from them:
  idempotency as a schema rule (D-11), the storage fingerprint for every before-and-after
  comparison (D-19), the rollback proven before the upgrade, with reset, restart and restore as
  three tests (D-20), the storage benchmark as the baseline for tuning (D-22, Task B10), the
  `VACUUM` after a rebuild (D-8), and `page_size`, Sqlean and R-Tree listed and `sqlite-zstd` not
  adopted (D-21). Already covered and not repeated: hybrid recall exists (Plan 0078), `PRAGMA
  optimize` already ran on close, no new database or framework, origins and transformations
  (D-11), the said, occurred and recorded times.
- **Proportion.** No SQL body is written here; each migration is fixed by its decisions and its
  tests, and the squash is proven by the golden schema.
