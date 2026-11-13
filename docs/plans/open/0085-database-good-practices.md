# 0085 — Block C1: the database with good practices

> **Waiting for [ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md)** (Proposed,
> 2026-11-13): after Pipec named the storage the core of the product, a deeper research round
> recommends designing a v2 schema from zero and carrying the data with one tested upgrade,
> instead of the three incremental migrations below. **Do not promote this text**: it is
> rewritten on ADR 0038 once Pipec answers its questions; its audit and decisions remain
> input to that rewrite.
>
> **Status:** **Draft** (2026-11-13) — written for Pipec's review; it becomes executable only when
> Pipec promotes it to `Ready` with the decisions marked *For Pipec* answered. Written from
> [ADR 0032](../../adr/0032-block-c-hygiene-correct-forget-and-years.md) (`Proposed`, amended by
> Pipec on 2026-11-13), **decision 1 only** — decisions 2 to 7 are Plan 0086 (C2) and decision 8 is
> Plan 0087 (the export) — plus [ADR 0031](../../adr/0031-the-memory-engine-boundary.md) decisions 4,
> 8, 9, 11 and 12, the code of `main` at `72b8711` and an audit of the real database's structure
> and counts (see *The audit*). **Revised the same day** after two independent read-only reviews
> (a SQLite review that tested the rebuild, the CHECKs and physical deletion on throwaway
> databases with SQLite 3.49.1 and sqlite-vec 0.1.9, and an architecture review against the ADRs):
> `STRICT` tables, an exact instant CHECK, `valid_from` written as a day, no `channel` CHECK, a
> per-table matrix, a golden schema test, the checkpoint and `optimize` after the rebuild, a
> trimmed health check, the full list of affected tests and the plan-contract headings. It is
> executed in a new Claude Code session, inline, with the
> whole-branch reviews of Task 8. Queue rule 4 applies at execution: Task 0 re-verifies every
> claim below against the merged code before any code, and **stops and reports** if one is false.
> ADR 0032 stays `Proposed` when this plan closes (it becomes `Accepted` with Plan 0087). Written
> for an executor who has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md` and
> every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS: `superpowers:executing-plans`
> (inline), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Task 8, and
> `superpowers:finishing-a-development-branch` for Task 9. The review agents of Task 8 and any
> other subagent run on the `sonnet` model and read `.claude/` (CLAUDE.md and `.claude/rules/`) in
> full before reading code. **Pipec's rules win over the skills:** one plain branch from `main`
> (`feat/0085-database-good-practices`), never a git worktree, this plan lives under `docs/plans/`.
> One commit per task; every test seen RED for the stated reason first. If evidence contradicts the
> plan, stop and report instead of redesigning. The Bash tool loses backslashes and non-ASCII
> characters in heredocs and arguments: use the Write and Edit tools (or a Python script written
> with Write). Commit titles: Conventional Commits, at most 72 characters, check `git log` after
> each commit (the hook rejects silently; a reformatting hook unstages the commit); never pipe
> `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI
> does. Never run `uv sync` without `--extra cuda`. Do not run `just gate` or the full suite in the
> background while Pipec rehearses (about 3.5 GB of RAM). The server and the robot are started by
> Pipec, never by the agent. **The real database is touched only in Task 9**, after its backup, and
> only by the server Pipec starts; every other task works on temporary databases. Throwaway scripts
> go to `.superpowers/sdd/0085-database-good-practices/`, never to `%TEMP%`; a copy of the real
> database goes under `data/rehearsal-0085/` (ignored by the tracked `.gitignore`, whereas
> `.superpowers/` is ignored only locally) and is deleted the same day. Before pushing, run
> `pyright`, `ruff` and `mypy` over the **whole** project, lint `scripts/` with explicit paths and
> `uv run ruff format --check .` (CI also checks python blocks in `docs/*.md`).

## The audit (2026-11-13, structure and counts only)

A copy of `data/omnibot.db` (5.98 MB, `user_version` 16, no `-wal`/`-shm`: the server was
stopped) was opened with `immutable=1` and compared with a clean database built by
`db.run_migrations` in a temporary file; both copies were deleted. No value was read.

1. **The real database and a clean install are the same schema.** Same 34 tables, 3 virtual
   tables (`vec_faces`, `recall_units_fts`, `recall_units_vec`), 4 triggers, identical DDL.
   `PRAGMA integrity_check` is `ok` and `PRAGMA foreign_key_check` returns nothing. SQLite 3.49.1.
2. **Every table has a primary key** except `sqlite_stat1` (SQLite's own, written by
   `PRAGMA optimize`).
3. **Two time formats.** Rows in the old SQLite format `YYYY-MM-DD HH:MM:SS` (19 characters, UTC):
   `entities.created_at` and `updated_at` (every row), `care_contacts.created_at` (2),
   `face_profiles.created_at` (5), `voice_profiles.created_at` (3),
   `face_consent_grants.granted_at` (1), `voice_consent_grants.granted_at` (1),
   `household_role_assignments.granted_at` (1), `owner_pin_credentials.created_at` and
   `updated_at` (1), `literal_facts_v4.superseded_at` (4). Every other instant in use is ISO 8601
   UTC with microseconds (`2026-11-03T10:00:00.000000+00:00`, 32 characters): 197 of 197 turn
   instants inside the record's JSON, 342 of 342 policy audit rows, every row of the conversation,
   recall, candidate, commissioning, admin-audit and pending tables, and
   `literal_facts_v4.asserted_at` beside the four old `superseded_at` of the same table. Days are
   ISO dates (`pending_topics.said_day`/`due_day`, `recall_units.occurred_*`, the acta's
   `*_destroy_by`). The old format comes from 19 `DEFAULT (datetime('now'))` columns and from code
   that writes `datetime('now')` (`biometric_consent`, `voice_consent`, `owner_credentials`,
   `household_authorization` revocations, `declarative.upsert_entity`, `meta.set_flag`, and
   `relational_v4` for `asserted_at`, `superseded_at`, `valid_from` and `valid_to`).
4. **The validity bounds mix three things.** `valid_from`/`valid_to` hold a day or a month
   (`YYYY-MM-DD`, `YYYY-MM`, accepted by `relational_v4._validity_bound` from the seed) **or** an
   instant: a temporal fact or relation gets `valid_from = COALESCE(asserted_at,
   datetime('now'))` when it is asserted without a bound (`_insert_literal_fact` and
   `_upsert_entity_relation`), and `valid_to = datetime('now')` when it is superseded (2 rows of
   `entity_relations_v4.valid_to` today; every other bound is NULL).
5. **32 foreign keys have no index a cascade can use** (a partial index does not serve a cascade):
   26 on live tables (`admin_audit`, `authorization_audit_events`, `care_contacts`,
   `literal_facts_v4`, `entity_relations_v4`, `memory_candidates`, `household_role_assignments`,
   `owner_pin_credentials` and the three consent tables) and 6 on dead ones. Two foreign keys have
   no explicit rule (`face_profiles.entity_id`, `voice_profiles.entity_id`: implicit `NO ACTION`).
6. **Dead tables, all with 0 rows.** `outbox` (only `retention` deletes from it),
   `sensor_current` (named by nothing), `sensor_readings` and `sensor_aggregates_hourly` (only
   `retention` deletes), `facts` (written by `declarative.assert_fact` and read by
   `get_active_facts`, neither with a caller, and by `legacy_v4_migration`, used only by
   `scripts/migrate_memory_v4.py`), `legacy_fact_migration_v4` (the same module), `memories`
   (retired by migration 013, kept only because `facts`, `events` and both V4 tables name it as
   the parent of `source_memory_id`; 0 non-NULL `source_memory_id` in V4). **Found beyond the
   ADR's list:** `embeddings_cache` (written and read only by `memory/embeddings.embed`, which has
   no caller; recall vectors go through `llm_transport.ollama_embed`) and `events` (written by
   `vision/perception._record_unknown_face`, **read by nothing**). `meta` has 0 rows but
   `personal_setup` reads it through `meta.get_flag`: it stays.
7. **The embedding model.** All 65 recall units name `granite-embedding:278m`; `recall_units_vec`
   has 65 rows; `recall_store.units_without_vector` selects only `embedding_model IS NULL` and
   `vector_hits` never compares the stored model with the query's (ADR 0031 *Context* item 8,
   still latent). Face vectors (`vec_faces`) name no model; voiceprints do (`voice_profiles.
   model_id`).
8. **The engine's boundary.** 26 of the 72 modules of `server/memory/` import `server.cognition`
   (ADR 0031 counted 20 on 2026-11-09; Plans 0080 to 0084 added `contact_access`,
   `household_time`, `own_read_consent`, `pending_capture`, `pending_follow_up` and
   `pending_store`). The guard ADR 0031 decision 11 asks for does not exist yet.

Nothing contradicts ADR 0032 decision 1; items 4, 6 (the two tables found), 7 (faces) and 8 are
the builder's calls below, each marked *For Pipec*.

## Decisions

Pipec's decisions are ADR 0032 decision 1 (*Pipec, 2026-11-13*) and its table rows 6 and 9 (the C1
list and order confirmed). The calls below fill in what the ADR leaves to the plan. **None is
confirmed yet**; the *For Pipec* notes say what he is asked.

- **D-1 Three migrations, in this order, each atomic and each with a before-and-after count
  test.** 017 `migration_017_retire_dead_tables.sql` (D-4); 018
  `migration_018_one_time_format_and_keys.sql`, the rebuild of the 21 live tables of *The
  table matrix* (D-2, D-3, D-5, D-6, D-10, D-19), which also drops `memories` once no table names
  it and renames every index to D-10; 019 `migration_019_indexes.sql` (D-7: an index needs no
  rebuild). Three small steps are reviewed and rolled back by version more easily than one large
  script. At Task 9 the agent re-verifies that 017 to 019 are still the next free numbers on
  `main` (Plan 0084's fixes may add a migration). *For Pipec:* three, or one migration 017 with
  everything.
- **D-2 One time format.** An **instant** is ISO 8601 in UTC with microseconds and the offset,
  32 characters (`2026-11-03T10:00:00.000000+00:00`); a **day** is an ISO date (`2026-11-03`), a
  local household day where it is a day the owner lives (`HOUSEHOLD_TIMEZONE`), as migrations 015
  and 016 already do. Rules:
  - one Python module, `server/timestamps.py`, formats and parses both; the private `_iso`
    helpers and inline `isoformat(timespec="microseconds")` calls that do it today
    (`candidates`, `conversation_consent`, `conversation_record`, `conversation_episodes`,
    `recall_store`, `spoken_dates`, `admin_cli`) and `household_authorization`'s `isoformat()`
    without `timespec` call it (DRY);
  - no code writes `datetime('now')` any more (a guard test); revocations, `updated_at`,
    `superseded_at` and the V4 `asserted_at` fallback take the time from Python;
  - every `DEFAULT (datetime('now'))` becomes `DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00',
    'now'))` (32 characters, milliseconds padded), so a writer that omits the column still stores
    the format;
  - every instant column gets an exact CHECK: `x IS NULL OR (length(x) = 32 AND x GLOB
    '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    AND strftime('%Y-%m-%dT%H:%M:%S', substr(x, 1, 19)) IS substr(x, 1, 19))` — six explicit
    digits and a real calendar instant (a bare `[0-9]*` would accept `2026-13-45T99:99:99.0abcde`,
    seen in the SQLite review); every day column `CHECK (date(x) IS x)` (airtight, tested). So an
    old or impossible format cannot enter even through a bug;
  - migration 018 rewrites a 19-character value to `replace(x, ' ', 'T') || '.000000+00:00'` and a
    25-character ISO value without fraction to `substr(x, 1, 19) || '.000000+00:00'`; **any other
    format makes the CHECK fail and the migration abort** (version stays 017), never a truncation
    (`strftime('%f')` keeps milliseconds only and is never used to convert).
  *For Pipec:* confirm the CHECK on every instant column (the ADR asks it for days, states and
  kinds; this extends it to instants, which costs nothing once D-19 rebuilds every live table).
- **D-3 The validity bounds are ISO calendar dates, never instants.** `valid_from` and `valid_to`
  hold a day (`2018-03-15`) or a month (`2018-03`, ISO 8601's reduced precision, as the seed
  states it and `_validity_bound` already reads it); a temporal fact or relation asserted without
  a bound opens on the **household day** of its assertion (`valid_from`, today an instant from
  `COALESCE(asserted_at, datetime('now'))`), and an automatic close at a supersede writes the
  household day of the supersede (`valid_to`, today `datetime('now')`). Without both changes the
  day CHECK would refuse every temporal assertion. CHECK: `x IS NULL OR date(x) IS
  x OR (length(x) = 7 AND date(x || '-01') IS x || '-01')`. Migration 018 is plain SQL and knows
  no household zone, so it rewrites the 2 existing instants to their **UTC day**
  (`substr(x, 1, 10)`): a bound closed between local midnight and UTC midnight moves one day, which
  the plan accepts for those 2 rows; from Task 1 on, a new close writes the household day. *For
  Pipec:* a day or a month as said (recommended), or days only (a month becomes its first or last
  day and loses its precision).
- **D-4 The dead tables.** Migration 017 drops `outbox`, `sensor_current`, `sensor_readings`,
  `sensor_aggregates_hourly`, `legacy_fact_migration_v4`, `facts`, `embeddings_cache` and `events`;
  018 drops `memories` (and its trigger `memories_retired`) after the V4 rebuild. A dead table that
  holds a row makes 017 abort (a temporary `CHECK (n = 0)` table filled with each table's count),
  so nothing is destroyed silently. The code that names them goes in the same task:
  `retention`'s four deletes, `memory/embeddings.embed` and its cache helpers (`EMBEDDING_DIM`
  stays), `declarative.assert_fact` and `get_active_facts`, `memory/legacy_v4_migration.py`,
  `scripts/migrate_memory_v4.py` and their tests, the `facts`/`embeddings_cache`/`outbox` part of
  `scripts/memory_test.py --show-db` (it prints the health counts of D-12 instead, never a value),
  and `perception._record_unknown_face` (the `unknown_person` log line stays). `meta` stays and is
  listed. *For Pipec:* `embeddings_cache` and `events` were not in the ADR's list; `events` has a
  writer that nothing reads; drop both (recommended) or keep `events` and list it.
- **D-5 `source_memory_id` leaves the V4 tables.** Its parent is retired, every value is NULL and
  provenance of a promoted fact already lives in `memory_candidates.promoted_fact_id`; the
  dataclass fields and parameters of `relational_v4` named so go with it. *For Pipec:* drop
  (recommended) or keep the column without a foreign key.
- **D-6 Every foreign key has an explicit rule, written in the dictionary.** All keep today's rule
  except `face_profiles.entity_id` and `voice_profiles.entity_id`, which become `RESTRICT`: a
  person's biometrics are deleted only by the consent revocation, which also purges `vec_faces`
  (a virtual table no cascade reaches). The rules, by parent:
  - `entities` → `CASCADE`: the subject of a V4 fact, both ends of a V4 relation, a candidate's
    subject and asserter, the owner of a record, an episode, a recall unit and a pending topic;
    `RESTRICT`: a role, a PIN, the three consents, a care contact's owner and contact, a face or
    voice profile; `SET NULL`: every `asserted_by`, `confirmed_by`, `grantor` and an audit row's
    actor and target (an audit outlives the person, with no value);
  - `literal_facts_v4`/`entity_relations_v4` → `SET NULL`: `superseded_by`,
    `memory_candidates.promoted_fact_id`;
  - `conversation_records` → `CASCADE`: episode, recall unit, pending topic; `SET NULL`:
    `previous_id` (C2 changes the episode and unit rules, ADR 0032 decision 5; not here);
  - `conversation_episodes` → `CASCADE`: its recall unit; `commissioning_records` → `CASCADE`: its
    sections.
  *For Pipec:* confirm `RESTRICT` on the two profiles.
- **D-7 Indexes, each with the query it serves** (migration 019; the dictionary lists the query of
  every index, and Task 4 proves each with `EXPLAIN QUERY PLAN`):
  - 21 new single-column indexes on foreign keys a cascade, a `SET NULL` or a `RESTRICT` check
    follows when a person, a fact or a record is deleted: `admin_audit.target_entity_id`;
    `authorization_audit_events.actor_entity_id`, `.target_entity_id`; `care_contacts.
    owner_entity_id`, `.contact_entity_id`, `.asserted_by_entity_id`, `.confirmed_by_entity_id`;
    `conversation_consent_grants`, `face_consent_grants`, `voice_consent_grants` and
    `owner_pin_credentials` `.person_entity_id`; `household_role_assignments.person_entity_id`,
    `.grantor_entity_id`; `literal_facts_v4.asserted_by_entity_id`, `.confirmed_by_entity_id`,
    `.superseded_by`; `entity_relations_v4.asserted_by_entity_id`, `.confirmed_by_entity_id`,
    `.superseded_by`; `memory_candidates.asserted_by_person_id`, `.promoted_fact_id`;
  - three partial indexes become full, because they lead with a cascading key and a full index
    serves both the cascade and today's `lifecycle = 'active'` queries:
    `literal_facts_v4 (subject_entity_id, predicate)`, `entity_relations_v4 (source_entity_id,
    predicate)` and `(target_entity_id, predicate)`; the partial **unique** ones stay (they are
    rules, not speed);
  - `entities_name_idx` is dropped (the unique `(name, type)` index already leads with `name`);
    `entities_type_idx` stays only if Task 0 finds the query that filters by type, else it goes;
  - the frequent filters and orders already have their index, and Task 0 confirms each against
    its query: the record's expiry and pending episode (`retention`, `conversation_jobs`:
    `conversation_records_expiry_idx`, `_pending_idx`), live candidates by expiry and by subject
    (`candidates`: `memory_candidates_live_expiry_idx`, `_subject_status_idx`), the due pending
    topic (`pending_store.due_topic`: `pending_topics_owner_state_due_idx`), recall by told and by
    occurred day (`recall_store`: `recall_units_owner_time_idx`, `_owner_occurred_idx`), the
    admin audit listing (`admin_audit_recorded_at_idx`) and the policy audit by correlation; a
    frequent query Task 0 finds without an index gets one in 019, named in the dictionary;
  *For Pipec:* 21 indexes on tables of tens of rows cost nothing measurable and the ADR asks for
  them; confirm.
- **D-8 Constraints.** New in 018: the instant and day CHECKs (D-2, D-3); `json_valid` on
  `entities.attributes` and `.aliases` and on the acta's four `*_json` columns; every existing
  CHECK on a state, sensitivity, visibility or kind kept as it is. Two vocabularies stay in Python
  on purpose, because SQLite cannot alter a CHECK and each new value would cost a table rebuild:
  the write `channel` (`WriteChannel` has grown with the importer and the admin; migration 010
  chose this) and the policy audit's `action`, `policy_id` and `reason` (they grow with each
  policy, and an audit row must never fail the decision it records). `db_health` counts stored
  channels outside `WriteChannel` instead (D-12).
- **D-9 Normalization: no schema change.** The deliberate denormalizations are kept and justified
  in the dictionary: the turns of a record as one JSON array, with `turn_count` and `byte_count`
  beside it (the retention cap reads them without parsing); `owner_entity_id` repeated on
  episodes, recall units and pending topics (the policy filters by owner in the statement that
  returns the text, Plan 0080); `sensitivity` copied into `recall_units_vec` by a trigger (the KNN
  filters inside the vector index); `entities.attributes`/`aliases` as JSON; the acta's JSON
  snapshots (an acta is frozen, ADR 0024); `authorization_audit_events.data_categories` as text (a
  snapshot of the request). *For Pipec:* confirm.
- **D-10 One naming convention, written in the dictionary.** Tables: `snake_case`, plural nouns.
  Columns: `snake_case`; a key to `entities` is `<role>_entity_id` (or `<role>_person_id` where it
  is always a person, as today), any other key `<parent singular>_id` or a verb past participle
  (`superseded_by`); an instant ends in `_at`; a day in `_day` or is a named bound (`valid_from`,
  `occurred_start`, `*_destroy_by`); a boolean is `INTEGER` 0/1 with its CHECK and a predicate name
  (`has_key`, `may_…`, `eligible`). Indexes: `<table>_<columns or purpose>_idx`. Triggers:
  `<table>_<ai|ad|au_column>`. **Only indexes are renamed** to it (`idx_face_profiles_entity` →
  `face_profiles_entity_idx`, `idx_voice_profiles_entity` → `voice_profiles_entity_idx`,
  `conversation_consent_active_idx` → `conversation_consent_grants_active_idx`); tables and
  columns keep their names (`meta`, the `_v4` suffix, `memory_candidates.subject_person_id`),
  because a rename ripples through every query, guard and test for no gain. A guard test holds the
  convention for every new object. *For Pipec:* confirm that existing table and column names stay.
- **D-11 The dictionary** is `docs/architecture/data-dictionary.md`, one section per table
  (`### table_name`, virtual tables included, SQLite's own and FTS5/vec0 shadow tables excluded):
  what it is for, the owner module (the only module whose SQL touches it, as the guards already
  say), a column table (name, type, null, rule or format), keys and their `ON DELETE`, indexes
  with the query each serves, classification (`personal`, `biometric`, `credential`, `audit`,
  `operational`) and retention (the ADR or setting that sets it). Then the convention (D-10), the
  time format (D-2) and the deliberate denormalizations (D-9). The guard checks every table **and
  every column** against it. *For Pipec:* the place.
- **D-12 The health check** is `server/memory/db_health.py` (SQL counts only, never a value) and
  `iroko-admin health` (no PIN: it shows no value; server stopped, like every `iroko-admin`
  command; `just db-health` is its alias). It measures what ADR 0031 decision 9 gives C1,
  integrity and staleness, and nothing of product policy: `integrity_check` ok or not;
  `foreign_key_check` violations by table; rows per table; FTS5 `integrity-check` of
  `recall_units_fts` (an `INSERT` command that takes the write lock and changes no row);
  orphans (vector rows without a unit, units without an FTS row, `vec_faces` rows without a
  profile and profiles without a vector, biometric profiles without an active consent);
  staleness (units without a vector older than `STALE_VECTOR_AFTER`, units of another embedding
  model, closed records whose episode is `pending` older than `STALE_EPISODE_AFTER`, both named
  constants of the module); rows outside the formats of D-2 and D-3; stored channels outside
  `WriteChannel` (D-8). Exit code 1 when integrity fails or any violation, orphan, bad format or
  unknown channel is counted. *For Pipec:* `iroko-admin health` (recommended) or a `just` script
  only; and whether the server also logs these counts at start-up (not recommended now: YAGNI).
- **D-13 The guard tests** (`tests/unit/test_schema_guards.py` and `test_architecture_guards.py`),
  each with a leak test that proves it fails: every table has a primary key; every foreign key
  has an explicit `ON DELETE` and a full index whose first column is that key; every table and
  column is in the dictionary and the dictionary names no table that does not exist; every index
  and trigger follows D-10; every live table is `STRICT` (D-19); every instant and day column
  **refuses a bad value when one is inserted** (a behaviour test per column, not a parse of the
  DDL text); no `datetime\(\s*'now'` in any `.py` under `server/src` (the regex also catches
  `datetime('now', ?)`; `.sql` files are out of scope, their comments name it); the **golden
  schema**: a committed snapshot of the normalized `sqlite_master`, `table_xinfo`,
  `foreign_key_list` and `index_list` at version 19, equal both for a fresh install (0 to 19) and
  for a version-16 canary database migrated up, so no drift between upgrade and install can pass;
  and the ADR 0031 decision 11 guard, the modules of `memory/` that import `server.cognition`,
  **frozen as today's 26 explicit names** (the list may shrink, never grow). *For Pipec:* freeze
  at 26, knowing ADR 0031 wrote 20.
- **D-14 The embedding-model guard** (ADR 0031 decision 8), for recall only. Already true and
  kept: `store_vector` deletes and re-inserts the `vec0` row and sets the unit's
  `embedding_model` in one transaction. The changes:
  `recall_store.vector_search_ready(model)` is true when no unit holds a vector of another model;
  `recall_search` skips the vector arm while it is false (lexical search keeps working; one log
  line `recall.vector off reason=model_changed remaining=N`, a count); `units_without_vector`
  selects units with no vector **or** a vector of another model (the partial index
  `recall_units_unembedded_idx` then serves only half of that predicate, harmless at this size;
  it stays); `vector_hits` also joins `recall_units.embedding_model = ?` (defence in depth); the
  re-index is verifiable because
  `db_health` counts the units left and `recall_index` logs the count after each pass. A model of
  another dimension fails its insert into `float[768]`, is logged by class and leaves vector
  search off. Face vectors (`vec_faces`) name no model and stay out of this plan: the dictionary
  lists it as a known gap. *For Pipec:* faces out (recommended) or a `model_id` on
  `face_profiles` now.
- **D-15 Proving no row is lost.** In tests: a database at version 16 filled with invented canary
  rows in every live table, old and new formats mixed, is migrated to 019; every table has the same
  count before and after, every converted value is the expected one, the foreign keys and the FTS
  index are intact, `sqlite_sequence` keeps each `AUTOINCREMENT` counter (a rebuilt table never
  reuses an id), and an ordering test sorts a mixed set wrongly at 016 and rightly at 019. On the
  real data (Task 9): the agent copies the backup to `data/rehearsal-0085/`, runs `db_health` and
  per-table counts at 016, migrates the copy with `run_migrations`, runs them again, compares
  (equal except the dropped tables, all 0 rows; 0 rows outside the format), then deletes the copy.
- **D-16 The backup and the timing.** The real migration runs at the first server start after the
  merge. So the PR is merged, and the real database migrated, **only after Plan 0084's acceptance
  closes** (the greeting days run to 2026-11-19 on that database). Before that start, with the
  server stopped, the agent copies `data/omnibot.db` (and any sidecar) to
  `data/backups/pre-0085-<YYYYMMDD-HHMMSS>/` and rehearses on a copy (D-15); Pipec starts the
  server and the robot; the agent runs `iroko-admin health` after Pipec stops it again. The
  rollback is restoring that backup (no migration has a down-step). That backup is a plain copy
  that would still hold anything a later deletion with the PIN removes (ADR 0032 decision 6), so
  it is **deleted when Pipec accepts this plan** and the operator manual says so for every
  pre-upgrade backup until ADR 0033 owns backups. *For Pipec:* confirm the wait for 0084 and the
  deletion of the backup at acceptance.
- **D-17 `run_migrations` and foreign keys.** A rebuild needs `PRAGMA foreign_keys = OFF`, which
  SQLite ignores inside a transaction: 018 starts with it before `BEGIN`, ends with `PRAGMA
  foreign_keys = ON` after `COMMIT`, and checks `pragma_foreign_key_check` inside its transaction
  (a temporary `CHECK (n = 0)` table, so a violation aborts it). `db.run_migrations` turns foreign
  keys back on after every script, whether it passed or failed, so a failed rebuild never leaves
  the connection without them. The rebuild of each table follows SQLite's own procedure with two
  rules the SQLite review found by test: **capture each rebuilt table's `sqlite_sequence` value
  before the `DROP`** and set it back after the rename (copying rows resets it to `max(id)`, and a
  deleted top id would be reused), and **create the triggers after the copy** (created before,
  the FTS5 insert trigger indexes every row twice). After the last migration of a start,
  `run_migrations` calls `db.checkpoint_wal()` (the write-ahead log still holds the old frames of
  every rebuilt row) and `PRAGMA optimize=0x10002` (a `DROP TABLE` removes that table's
  statistics, and the server is long-lived); `open_db` also runs `PRAGMA optimize=0x10002`, as
  SQLite recommends for a long-lived connection.
- **D-18 Tuning is only listed** (ADR 0031 decision 12, step 2 is this plan's hygiene): the FTS5
  `trigram` comparison on a Spanish corpus, the per-connection pragmas in settings rather than in
  `db.py`, `int8` vectors and durability pragmas wait for a measure that asks for them; the
  dictionary names them under *Not tuned yet*. Reviewed and **not adopted**: `WITHOUT ROWID`
  (the tables use `AUTOINCREMENT` and FTS5 external content needs the rowid), `auto_vacuum`
  (freed pages are already zeroed by `secure_delete`; 6 MB), JSONB (text JSON stays exportable
  and readable by older SQLite), `cell_size_check` and `trusted_schema=OFF` (no hostile file in
  this threat model); `quick_check` at start-up and `VACUUM INTO` backups belong to ADR 0033.
- **D-19 `STRICT` tables, and all 21 live tables rebuilt.** Every table 018 rebuilds is declared
  `STRICT`, so SQLite itself refuses a text in an `INTEGER` column or a float in a `TEXT` one,
  under every CHECK (every declared type today is `INTEGER`, `TEXT`, `REAL` or `BLOB`, so the
  DDL needs no type change). Rebuilding all 21 live tables, not only the 12 that need it (the 11
  with a `datetime('now')` default, which hold every old-format row, `source_memory_id` and the
  two implicit rules, plus `commissioning_records` for its day CHECKs), is what makes
  `STRICT` and the CHECKs uniform; the risk of rebuilding `recall_units` (FTS5 external content,
  three triggers, `AUTOINCREMENT`) was tested by the SQLite review on the installed versions and
  is pinned by Task 3 and the golden schema (D-13). `STRICT` needs SQLite 3.37 or later to open
  the file: Raspberry Pi OS Bookworm (3.40) and Ubuntu 22.04 / JetPack 6 (3.37.2) can, JetPack 5
  (3.31) cannot; the dictionary says it, and `iroko-admin health` prints the library version.
  `PRAGMA application_id` is set to one fixed number in 018 and checked by `open_db`, which
  refuses a file that is not Iroko's (the «two databases» confusion `db.py` already guards
  against by path). *For Pipec:* all 21 with `STRICT` (recommended; the architecture review
  preferred rebuilding only the 12 to touch less), and `application_id` (optional, low value).

### The table matrix (migration 018)

Every row is rebuilt `STRICT` (D-19) with its indexes renamed to D-10 and its triggers recreated
after the copy. **Instants** get the D-2 CHECK and **days** the day CHECK (D-3 for validity
bounds); «default» marks a `DEFAULT (datetime('now'))` replaced by the D-2 expression; «old rows»
marks columns whose values 018 converts (*The audit* item 3).

| Table | Instants | Days | Beyond `STRICT` and the time CHECKs |
|---|---|---|---|
| `entities` | `created_at`, `updated_at` (default, old rows) | — | `json_valid` on `attributes`, `aliases` |
| `meta` | `updated_at` (default) | — | — |
| `literal_facts_v4` | `asserted_at` (default), `confirmed_at`, `superseded_at` (old rows) | `valid_from`, `valid_to` | `source_memory_id` dropped (D-5) |
| `entity_relations_v4` | `asserted_at` (default), `confirmed_at`, `superseded_at` | `valid_from`, `valid_to` (2 instants → day) | `source_memory_id` dropped (D-5) |
| `household_role_assignments` | `granted_at` (default, old rows), `revoked_at` | — | — |
| `owner_pin_credentials` | `created_at`, `updated_at` (default, old rows), `revoked_at` | — | — |
| `face_consent_grants` | `granted_at` (default, old rows), `revoked_at` | — | — |
| `voice_consent_grants` | `granted_at` (default, old rows), `revoked_at` | — | — |
| `face_profiles` | `created_at` (default, old rows) | — | `entity_id` `RESTRICT` (D-6); index renamed |
| `voice_profiles` | `created_at` (default, old rows) | — | `entity_id` `RESTRICT` (D-6); index renamed |
| `care_contacts` | `confirmed_at`, `created_at` (default, old rows), `revoked_at` | — | — |
| `commissioning_records` | `started_at`, `closed_at` | `backup_destroy_by`, `baseline_destroy_by` | `json_valid` on the four `*_json` |
| `commissioning_sections` | `recorded_at` | — | — |
| `memory_candidates` | `proposed_at`, `offered_at`, `resolved_at`, `expires_at` | — | — |
| `admin_audit` | `recorded_at` | — | — |
| `authorization_audit_events` | `evaluated_at`, `expires_at` | — | — |
| `conversation_consent_grants` | `granted_at`, `revoked_at` | — | index renamed |
| `conversation_records` | `started_at`, `last_turn_at`, `closed_at`, `expires_at` | — | — |
| `conversation_episodes` | `created_at`, `expires_at` | — | — |
| `recall_units` | `said_at` | `occurred_start`, `occurred_end` | FTS5 content kept; triggers `recall_units_ai`, `_ad`, `_au_sensitivity` after the copy |
| `pending_topics` | `created_at`, `asked_at` | `said_day`, `due_day` | — |

The JSON turns of `conversation_records` keep their `at` instants as they are (197 of 197 already
in the D-2 format); `db_health` counts any that is not.

**Goal.** The database follows one time format, keys, explicit delete rules, indexes,
constraints, `STRICT` types and one naming convention; dead tables are gone with the code that
named them; a
dictionary documents every table and column; a health check counts integrity, orphans and
staleness; guard tests keep all of it true; and a change of embedding model can no longer compare
vectors of two spaces.

**Architecture.** One time module (`server/timestamps.py`) used by every writer; three migrations
(017 retire, 018 rebuild of every live table as `STRICT`, 019 indexes) with `run_migrations`
restoring foreign keys, checkpointing the log and refreshing the planner's statistics; a
counts-only health module behind `iroko-admin health`; the embedding guard inside
`recall_store`, `recall_search` and `recall_index`; schema guards and a golden schema snapshot
read from both a fresh and an upgraded database, and the dictionary.

**Tech stack.** Python 3.12, aiosqlite, SQLite 3.49 (FTS5, `sqlite-vec`), pytest. No new
dependency, no setting, no wire, route, prompt or robot change.

**Spec.** [ADR 0032](../../adr/0032-block-c-hygiene-correct-forget-and-years.md) decision 1 and
its *Test consequences* (C1); [ADR 0031](../../adr/0031-the-memory-engine-boundary.md) decisions 4,
8, 9, 11 and 12 and its *Test consequences* (C1); [ADR 0011](../../adr/0011-sqlite-transaction-ownership.md)
(one transaction owner); [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md)
decision 6 (`secure_delete`); [current state](../../architecture/current-state.md);
[guardrails](../../architecture/implementation-guardrails.md).

**Required reading.** The above, then the code: `db.py` (`_MIGRATIONS`, `run_migrations`,
`open_db`), every `memory/migration_*.sql` and `memory/schema.sql`, `memory/relational_v4.py`
(the V4 writers, `_validity_bound`, `_closing_value`), `memory/declarative.py`,
`memory/retention.py`, `memory/embeddings.py`, `memory/recall_store.py`,
`memory/recall_search.py`, `memory/recall_index.py`, `vision/perception.py`, `admin_cli.py`,
`scripts/memory_test.py`, `tests/unit/test_architecture_guards.py` (`_sources`, `_outside`) and
the schema tests under `tests/integration/`.

## Global constraints

- English code, comments and docstrings (Google style); no `Any`, no `print`, no `os.path`, no
  bare `except`; logging with `%`.
- Counts only: no value of the database in a log line, a health report, a test output, an
  exception message or this plan's evidence.
- Every migration is atomic, sets its own `user_version` and has no down-step; the rollback is the
  backup (D-16).
- With `MEMORY_ENABLED=false` every turn is byte-identical to `main`; with it on, every route,
  prompt and reply is too (this plan changes storage, not behaviour), except the log lines of
  D-14 and the removed `events` row (D-4).
- No real household data: invented canaries only; `scripts/check_reserved_terms.py` passes.

## Review focus

1. **A value in a third format** in the real database (a hand edit, an old tool): 018 must abort
   and leave version 017, never truncate or guess (Task 3, a canary in a 23-character format).
2. **A rebuild that loses the side structures** of a table: the FTS5 external content and the
   three triggers of `recall_units`, the partial unique indexes, the `AUTOINCREMENT` counters;
   recall must still find a unit by its words and by its vector after 018 (Task 3).
3. **Foreign keys left off** after a failed migration (Task 3, a script made to fail).
4. **A model change in the middle of a re-index**: half the units on the new model, a query
   arrives; nothing compares across models and the lexical answer still comes (Task 5).
5. **A reader of a converted column**: code that parsed `YYYY-MM-DD HH:MM:SS` got a naive
   datetime and now gets an aware one; a comparison with a naive value would raise. Every reader
   Task 0 lists keeps working on converted rows (Tasks 1 and 3).

---

## Permitted files

Only these files change (paths under `server/src/server/` unless they start with `tests/`,
`scripts/`, `docs/` or the root); a need outside the list stops the plan for Pipec.

| File | Responsibility | Task |
|---|---|---|
| `timestamps.py` (new); the writers named in D-2 and D-3 (`memory/candidates.py`, `conversation_consent.py`, `conversation_record.py`, `conversation_episodes.py`, `recall_store.py`, `household_authorization.py`, `biometric_consent.py`, `voice_consent.py`, `owner_credentials.py`, `declarative.py`, `meta.py`, `relational_v4.py`, `cognition/spoken_dates.py`, `admin_cli.py`); `tests/unit/test_timestamps.py` (new), the tests of those writers | One instant and day format; no `datetime('now')` | 1 |
| `memory/migration_017_retire_dead_tables.sql` (new), `db.py`, `memory/retention.py`, `memory/embeddings.py`, `memory/declarative.py`, `vision/perception.py`, `scripts/memory_test.py`, `justfile`; delete `memory/legacy_v4_migration.py`, `scripts/migrate_memory_v4.py`; the tests listed in Task 2 | Dead tables and their code | 2 |
| `memory/migration_018_one_time_format_and_keys.sql` (new), `db.py`, `memory/relational_v4.py`, `tests/fixtures/migration_canaries.py` (new), `tests/integration/test_migration_018_rebuild.py` (new), the schema tests under `tests/integration/` | The rebuild; foreign keys, checkpoint, `optimize`, `application_id` | 3 |
| `memory/migration_019_indexes.sql` (new), `db.py`, `tests/integration/test_migration_019_indexes.py` (new) | Indexes | 4 |
| `memory/recall_store.py`, `memory/recall_search.py`, `memory/recall_index.py`, `tests/integration/test_recall_embedding_model_guard.py` (new), the recall tests | The embedding-model guard | 5 |
| `memory/db_health.py` (new), `admin_cli.py`, `justfile`, `scripts/memory_test.py`, `tests/integration/test_db_health.py` (new) | The health check | 6 |
| `docs/architecture/data-dictionary.md` (new), `tests/unit/test_schema_guards.py` (new), `tests/fixtures/schema_v19.json` (new), `tests/unit/test_architecture_guards.py` | Dictionary, guards, golden schema | 7 |
| The documents of Task 9 | Truth, rehearsal, close | 9 |

**Rollback boundary.** Before Task 9 every change lives on the branch and touches no real data:
the rollback is the branch. After the merge, the real database's rollback is the backup of D-16,
restored with the server stopped, together with the previous `main` (no migration has a
down-step).

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** `git checkout main && git pull`, then create `feat/0085-database-good-practices`.
- [ ] **Step 2:** Verify, and **stop and report** if any is false (throwaway scripts under
  `.superpowers/sdd/0085-database-good-practices/`, structure and counts only):
  - `db._MIGRATIONS` ends at 16; a clean database has the tables, foreign keys and indexes of
    *The audit* items 1, 2 and 5;
  - the callers of item 6: `assert_fact`, `get_active_facts` and `embeddings.embed` have none in
    `server/src`; `legacy_v4_migration` is imported only by `scripts/migrate_memory_v4.py`;
    `events` is written only by `perception._record_unknown_face` and read by nothing;
    `meta.get_flag` is read by `personal_setup`;
  - which query, if any, filters `entities` by `type`, and each frequent query of D-7 with the
    index it uses (`EXPLAIN QUERY PLAN` on a clean database);
  - the `datetime\(\s*'now'` writers of item 3 (including `retention`'s `datetime('now', ?)`,
    which Task 2 removes with the dead tables), the `_iso` helpers of D-2 and the two
    `valid_from` writers of item 4;
  - every **reader** of a column with old-format rows (*The audit* item 3) and how it parses it
    (Review focus 5);
  - the installed SQLite is 3.37 or later (`STRICT`, D-19) and the vec0 extension loads in a
    `STRICT` database;
  - the 26 modules of item 8, by name.
- [ ] **Step 3:** Baseline (not in the background if Pipec is rehearsing), the count in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`.

---

### Task 1: One way to write a time

**Files:** Create `server/src/server/timestamps.py`, `tests/unit/test_timestamps.py`; modify the
writers of D-2 (`memory/candidates.py`, `conversation_consent.py`, `conversation_record.py`,
`recall_store.py`, `cognition/spoken_dates.py`, `admin_cli.py`, `household_authorization.py`,
`biometric_consent.py`, `voice_consent.py`, `owner_credentials.py`, `declarative.py`, `meta.py`,
`relational_v4.py`); `tests/unit/test_architecture_guards.py`.

**Interfaces:**
- Produces: `INSTANT_LENGTH: Final = 32`; `def instant_text(moment: datetime) -> str` (UTC,
  microseconds, `+00:00`; `ValueError` for a naive datetime); `def parse_instant(text: str) ->
  datetime` (aware UTC; `ValueError` outside the format); `def day_text(day: date) -> str`;
  `def validity_close_day(moment: datetime, zone: ZoneInfo) -> str` (D-3, the household day).
  `timestamps` imports no settings, no database and no FastAPI (the cognitive core may use it).

- [ ] **Step 1: Write the failing tests:** `instant_text` of a `+03:00` moment is its UTC
  instant in 32 characters; a naive moment raises; `parse_instant(instant_text(m)) == m`; ordering
  of `instant_text` equals ordering of the moments (a microsecond apart, across a day);
  `validity_close_day` at 02:30 UTC is the previous day in `America/Santiago`; a temporal V4 fact
  and a temporal relation asserted without a bound store a household **day** in `valid_from`,
  and a supersede stores one in `valid_to` (D-3); `test_no_server_module_writes_datetime_now`
  (the regex `datetime\(\s*'now'` matches no `.py` under `server/src`, except `retention`'s dead
  deletes, which Task 2 removes and then the exception goes; with a leak test);
  `test_the_instant_format_is_defined_once` (no other module calls
  `isoformat(timespec="microseconds")`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement and move every writer to it (a revocation,
  `updated_at`, `superseded_at` and the V4 `asserted_at` fallback take the time from
  `cognition.clock.utc_now()` through `instant_text`; the V4 `valid_from` opening and `valid_to`
  close take `validity_close_day` with `settings.household_timezone`). **Step 4:** Run → PASS;
  every existing test of those writers passes unchanged in what it asserts.
- [ ] **Step 5:** commit `refactor: write every time in one format (plan 0085)`.

---

### Task 2: Migration 017 and the dead tables

**Files:** Create `server/src/server/memory/migration_017_retire_dead_tables.sql`,
`tests/integration/test_migration_017_dead_tables.py`; modify `db.py`, `memory/retention.py`,
`memory/embeddings.py`, `memory/declarative.py`, `vision/perception.py`,
`scripts/memory_test.py`, `justfile` (only if a task named a removed script); delete
`memory/legacy_v4_migration.py` and `scripts/migrate_memory_v4.py`. The tests, found by the
architecture review and re-listed by Task 0:
- **deleted** (they test only removed code): `tests/integration/test_memory_v4_migration.py`,
  `test_legacy_migration_pool_predicates.py`, `test_legacy_migration_subject_types.py`, and the
  `embed` cases of `tests/unit/test_embeddings.py` (the `EMBEDDING_DIM` case stays);
- **reseeded through `relational_v4`** (they used `assert_fact`/`get_active_facts` or a dead
  table only to set up a scenario): `test_household_authorization_schema.py`,
  `test_memory_v4_schema.py`, `test_memory_relational.py`, `test_owner_stranger_matrix.py`,
  `test_memory_integration.py`, `test_conversation_schema.py` (its `memories` trigger case moves
  to Task 3, where `memories` goes), `test_retention.py` (its sensor cases go);
- **updated**: `tests/unit/test_architecture_guards.py`, which names `legacy_v4_migration`.

**Interfaces:**
- Produces: version 17 without the eight tables of D-4; the code of D-4 removed; `EMBEDDING_DIM`
  kept.

- [ ] **Step 1: Write the failing tests:** on a database at 16, 017 leaves version 17 and none of
  the eight tables, and every other table's count unchanged; a canary row in any one of the eight
  makes 017 abort and leaves version 16 with the row (parametrized over the eight);
  `test_the_dead_tables_are_named_nowhere` (no SQL on them in `server/src` or `scripts/`, leak
  test); `retention` runs without them; `perception` records no event and still logs the unknown
  face; `memory_test --show-db` prints counts only.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the schema tests
  that pin the latest version move to their own fixture version, as Plans 0083 and 0084 did.
- [ ] **Step 5:** commit `feat: retire the dead tables (plan 0085)`.

---

### Task 3: Migration 018, one time format and the keys

**Files:** Create `server/src/server/memory/migration_018_one_time_format_and_keys.sql`,
`tests/integration/test_migration_018_rebuild.py`, `tests/fixtures/migration_canaries.py` (the
invented rows); modify `db.py` (`run_migrations`, D-17), `memory/relational_v4.py`
(`source_memory_id` gone, D-5).

**Interfaces:**
- Consumes: Task 1's format; Task 2's version 17.
- Produces: version 18. The 21 tables of *The table matrix* rebuilt `STRICT` by the procedure of
  SQLite's *ALTER TABLE* page (create `<t>_new`, copy with the conversion of D-2/D-3, capture the
  old `sqlite_sequence` value, drop, rename, set the counter back, recreate the indexes with D-10
  names and **then** the triggers), with the DDL of D-2, D-3, D-5, D-6, D-8 and D-19, `memories`
  dropped last, `pragma_foreign_key_check` empty or abort, `PRAGMA application_id` set if Pipec
  keeps it (D-19). `run_migrations` restores `PRAGMA foreign_keys = ON` after every script and,
  after the last one, calls `checkpoint_wal()` and `PRAGMA optimize=0x10002`; `open_db` runs
  `PRAGMA optimize=0x10002` and checks `application_id` (D-17, D-19).

- [ ] **Step 1: Write the failing tests** (on a database built to 17 and filled from the canary
  fixture, old and new formats mixed): every table's count equal after 018; each 19- and
  25-character instant converted exactly; the 2 kinds of validity bound kept and an instant bound
  turned to its UTC day; `test_ordering_across_formats` (a mixed set ordered by `asserted_at`/
  `superseded_at` is wrong at 17 and right at 18); a value in a third format aborts 018 and keeps
  17 (Review focus 1); after 18 an insert is refused for an old format, an impossible instant
  (`2026-13-45T99:99:99.0abcde+00:00`, `2026-02-31T…`), a bad day, invalid JSON, and a text in
  an `INTEGER` column (`STRICT`), one parametrized case per table of the matrix;
  `face_profiles` and `voice_profiles` refuse the deletion of their person; after 18 recall
  finds a canary unit by its words and its vector, the three triggers exist, every unit is
  indexed **once** in FTS5, the FTS `integrity-check` passes and a new unit gets the id after the
  old counter even when the top id had been deleted (Review focus 2);
  `test_a_failed_migration_leaves_foreign_keys_on` (Review focus 3); after the start the log is
  truncated (`checkpoint_wal` called) and `sqlite_stat1` is refreshed; a file with another
  `application_id` is refused by `open_db`; every reader Task 0 listed parses a converted row
  (Review focus 5); `relational_v4` works without `source_memory_id`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the whole V4,
  contact, candidate, record, recall and pending suites unchanged.
- [ ] **Step 5:** commit `feat: one time format and explicit keys in the schema (plan 0085)`.

---

### Task 4: Migration 019, the indexes

**Files:** Create `server/src/server/memory/migration_019_indexes.sql`,
`tests/integration/test_migration_019_indexes.py`; modify `db.py`.

**Interfaces:**
- Produces: version 19 with D-7's indexes, named per D-10 (the renames of existing indexes
  happen in 018, which recreates them).

- [ ] **Step 1: Write the failing tests:** each new index exists and is not partial;
  `EXPLAIN QUERY PLAN` of the child lookup SQLite runs for a `DELETE FROM entities WHERE id = ?`
  (one `SELECT … FROM <child> WHERE <fk> = ?` per foreign key) shows `USING INDEX` (or `USING
  COVERING INDEX`) for each of the 21, and the three full V4 indexes serve the
  `lifecycle = 'active'` reads of `relational_v4` (their SQL taken from the module); counts
  unchanged.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: index every foreign key (plan 0085)`.

---

### Task 5: The embedding-model guard

**Files:** Modify `memory/recall_store.py`, `memory/recall_search.py`, `memory/recall_index.py`;
tests `tests/integration/test_recall_embedding_model_guard.py` (new) and the recall suites.

**Interfaces:**
- Produces: `async def vector_search_ready(model: str) -> bool`; `async def
  count_units_to_reindex(model: str) -> int`; `units_without_vector(limit: int, *, model: str)`
  (no vector or another model); `store_vector(unit_id, vector, *, model)` replaces the `vec0`
  row; `vector_hits(…, model: str)` joins on the model; `recall_search` skips the vector arm when
  not ready and logs `recall.vector off reason=model_changed remaining=%d`.

- [ ] **Step 1: Write the failing test first, RED for the stated reason** (ADR 0031 *Test
  consequences*): units embedded with model A; the configured model becomes B; a search calls no
  vector comparison and still returns the lexical hit; one backfill pass re-embeds the units (a
  double embedder), after which vector search is on and every unit names B. Then: half
  re-indexed, a query compares nothing across models (Review focus 4); a vector of another
  dimension is refused, logged by class, and leaves vector search off; `test_no_text_in_the_log`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the recall and
  hardware-calibrated threshold tests unchanged.
- [ ] **Step 5:** commit `feat: never compare vectors of two embedding models (plan 0085)`.

---

### Task 6: The health check

**Files:** Create `server/src/server/memory/db_health.py`, `tests/integration/test_db_health.py`;
modify `admin_cli.py` (`health`), `justfile` (`db-health`), `scripts/memory_test.py` (Task 2's
`--show-db` calls it).

**Interfaces:**
- Produces: `@dataclass(frozen=True) class HealthReport` (only `int`/`bool` fields and a
  `dict[str, int]` of rows per table; no text from the database); `STALE_VECTOR_AFTER:
  Final[timedelta]` and `STALE_EPISODE_AFTER: Final[timedelta]`; `async def check_health(conn:
  aiosqlite.Connection, *, now: datetime, embedding_model: str) -> HealthReport` (D-12; it
  changes no row: the FTS5 `integrity-check` command takes the write lock and writes nothing);
  `def health_failed(report: HealthReport) -> bool`; `iroko-admin health` prints the report as
  Spanish labels and numbers, plus the SQLite library version (D-19), and exits 1 when
  `health_failed`.

- [ ] **Step 1: Write the failing tests:** a clean database reports zeros and passes; one test per
  measure plants its fault in a temporary database (a vector row without a unit, a unit without an
  FTS row, a face profile without a vector, a profile without consent, a stale unit, a unit of
  another model, a stuck episode, a foreign key violation with foreign keys off, an impossible
  instant and an unknown channel written through a schema without the CHECK) and sees its count;
  `check_health` changes no row (every table's content hash is the same before and after; a
  `total_changes` count alone would not see the FTS command); `test_no_value_reaches_the_output`
  (canary values absent from the printed report).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: a counts-only health check of the database (plan 0085)`.

---

### Task 7: The dictionary and the guards

**Files:** Create `docs/architecture/data-dictionary.md`, `tests/unit/test_schema_guards.py`,
`tests/fixtures/schema_v19.json`; modify `tests/unit/test_architecture_guards.py`.

**Interfaces:**
- Produces: the dictionary of D-11 for version 19 (with the SQLite floor of D-19 and *Not tuned
  yet* of D-18); the guards of D-13, which build a clean database at the latest version in a
  temporary file and read `sqlite_master` and the `PRAGMA` lists (SQLite's own tables and the
  FTS5/vec0 shadow tables excluded by name); `schema_v19.json`, the normalized golden schema.

- [ ] **Step 1: Write the failing guards** (each with its leak test on a planted schema or
  dictionary): primary key, explicit `ON DELETE`, full index per foreign key, `STRICT`,
  dictionary coverage of tables and columns (both ways), names per D-10, the frozen 26 names of
  `memory/` modules importing `server.cognition`; and `test_the_schema_matches_the_golden_file`,
  run for a fresh install and for the version-16 canary database of Task 3 migrated up (a
  snapshot regenerated only on purpose, by a documented helper in the test module). The instant
  and day CHECKs are proven by behaviour in Task 3, not parsed here.
- [ ] **Step 2:** Run → FAIL (no dictionary). **Step 3:** write the dictionary from the schema at
  19 and the code (owner module from the store guards, each index with its query, classification
  and retention from the ADRs and settings). **Step 4:** Run → PASS;
  `uv run python scripts/check_reserved_terms.py` passes (the dictionary holds no value).
- [ ] **Step 5:** commit `docs: the data dictionary and the schema guards (plan 0085)`.

---

### Task 8: Verification and the whole-branch review

- [ ] **Step 1:** `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval"
  -q -n auto`, `uv run pyright`, `uv run mypy server/src robot/src`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`, `just gate` — all pass; the count in the PR.
- [ ] **Step 2: Simplify, then review the whole branch** (`git diff main...HEAD`), each agent on
  `sonnet`, reading `.claude/` first, read-only, briefed with this plan and its review focus: the
  `simplify` skill (four angles); then, in parallel, `database-architect`, `architect-reviewer`,
  `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:silent-failure-hunter`,
  `pr-review-toolkit:pr-test-analyzer` and `security-auditor`. Each finding verified against the
  code (`superpowers:receiving-code-review`) and fixed with its RED test (Pipec's fix-everything
  rule), in `fix: … (plan 0085)` commits; then Step 1 again.

---

### Task 9: Rehearsal, the real migration and close

**Files:** `docs/architecture/current-state.md` and the Archify memory diagram (validate →
deliver → visual-check), `docs/runbooks/operator-manual.md` (`iroko-admin health`, the backup
before an upgrade), `docs/evals/0085-database-acceptance.md` (new, counts only), ADR 0032 (*C1
implemented in Plan 0085*; stays `Proposed`), ADR 0031 (*Notes added after acceptance*: Context
item 8's first bullet fixed, the guard of decision 11 at 26), the ADR index, the plan board,
`docs/plans/open/README.md`, `docs/plans/completed/README.md`, the roadmap (row 8 and *Database
hygiene*), both delivery maps, and Pipec's local `docs/roadmap/tabla-tareas.md`.

- [ ] **Step 1: Wait for Plan 0084's close** (D-16). Rebase on `main` and confirm that 017 to 019
  are still the next migration numbers (D-1); if `main` gained one, renumber and re-run Task 8's
  Step 1 first. Then, with the server stopped, the agent backs up the real database to
  `data/backups/pre-0085-<YYYYMMDD-HHMMSS>/`, copies the backup to `data/rehearsal-0085/`, and
  rehearses on the copy (D-15): `db_health` and per-table counts at 16, the migrations, the same
  at 19, the comparison; the copy is deleted the same day. Any difference stops the plan.
- [ ] **Step 2: Merge** (push, PR, squash-merge with green CI; GitHub is delegated), then Pipec
  starts the server (the migrations run) and the robot, and speaks a short script the agent
  gives: a greeting, «¿qué sabes de mí?», one recall question about something told before, one
  sensitive read of the owner's own data; each answers as before. The agent reads
  `logs/server.log` (closed values only) and, with the server stopped again, runs
  `iroko-admin health` (exit 0, counts recorded).
- [ ] **Step 3:** When Pipec accepts, delete the `pre-0085` backup (D-16) and record that it was
  deleted. Update the documents above; move the plan to `completed/`; commit
  `docs: close plan 0085, the database with good practices`, push, PR, squash-merge, delete the
  branch, return to `main`.

---

## Completion criteria

The plan is complete when all of these hold, each with its evidence in the PR or the acceptance
record (counts only):

1. Tasks 1 to 7 merged, each with its RED-then-GREEN tests; Task 8's commands all pass and its
   review findings are fixed.
2. The real database is at version 19: `iroko-admin health` exits 0, with 0 integrity errors,
   0 foreign key violations, 0 orphans, 0 rows outside the formats and 0 units of another model.
3. The rehearsal of D-15 showed equal per-table counts at 16 and at 19 (except the dropped
   tables, all 0 rows), and its copy is deleted.
4. The four spoken cases of Task 9 Step 2 answered as before.
5. The data dictionary exists and the schema guards and golden schema pass.
6. The `pre-0085` backup is deleted after Pipec's acceptance.
7. The documents of Task 9 are updated and the plan sits in `completed/`.

## Found for Plan 0086 (C2), not done here

The SQLite review tested physical deletion on the installed versions: a vec0 (sqlite-vec 0.1.9)
`DELETE` zeroes the vector bytes, and FTS5 `secure-delete` with `secure_delete=ON` removes both
token and text, once the write-ahead log is checkpointed. One risk it found belongs to C2: with
`synchronous=NORMAL`, a power cut can undo the last commit, including a deletion with the PIN,
which would bring a forgotten memory back. ADR 0032 decision 7 accepts losing a turn, not a
deletion. So C2's deletion should commit, then `checkpoint_wal()` (which syncs), then append the
register line. Plan 0086 decides it.

---

## Non-goals

Correcting, archiving or deleting a memory, the deletion register and the diary's retention
(ADR 0032 decisions 2 to 7, Plan 0086); the export (decision 8, Plan 0087); changing the foreign
keys of episodes and recall units (decision 5); renaming tables or columns (D-10); a model name on
face vectors (D-14); the FTS5 `trigram` comparison, pragmas in settings, `int8` vectors (D-18);
encryption at rest and backups (ADR 0033); the extraction of the engine (ADR 0031 decision 11);
any wire, route, prompt, robot or dependency change.

## Self-review (2026-11-13)

- **Spec coverage.** ADR 0032 decision 1, item by item: time (one format, the rebuild, before and
  after counts, an ordering test) → D-2, D-3, D-15 and Tasks 1, 3; keys (a primary key on every
  table, every relation a declared foreign key with an explicit rule) → D-5, D-6 and Tasks 3, 7;
  indexes with their queries → D-7 and Task 4; constraints → D-2, D-3, D-8 and Task 3;
  normalization → D-9 and Task 7; naming → D-10 and Tasks 3, 7; dead tables with proof → D-4 and
  Task 2; the dictionary → D-11 and Task 7; the health check → D-12 and Task 6; the guard test →
  D-13 and Task 7; the engine's guards (the architecture guard, integrity and staleness, the
  embedding model) → D-12, D-13, D-14 and Tasks 5 to 7; tuning by measurement → D-18; types
  enforced by SQLite itself → D-19 and Tasks 3, 7. Its *Test
  consequences* (C1): ordering → Task 3; cascade query plans → Task 4; no code reads a dropped
  table → Task 2; the guard test → Task 7; counts-only health → Task 6; a model change disables
  vector search → Task 5. ADR 0031's *Test consequences* (C1) → Tasks 5 to 7.
- **Where the plan goes beyond or departs from the ADR, for Pipec:** instants get a format CHECK
  too (D-2); validity bounds keep month precision and open and close on a household day (D-3);
  `embeddings_cache` and `events` are added to the dead tables, and `events` loses its writer
  (D-4); `source_memory_id` is dropped (D-5); the two biometric profiles become `RESTRICT` (D-6);
  the channel stays without a CHECK, as migration 010 chose (D-8); only indexes are renamed
  (D-10); faces stay out of the model guard (D-14); the boundary guard freezes 26, not 20
  (D-13); the real migration waits for Plan 0084 and its backup is deleted at acceptance (D-16);
  all 21 live tables become `STRICT`, with an optional `application_id` (D-19).
- **Revision after the reviews (2026-11-13).** Applied: the exact instant CHECK (D-2), the
  `valid_from` writers (audit item 4, D-3, Task 1), no `channel` CHECK (D-8), the frequent-query
  list (D-7), the trimmed health check with named constants (D-12), behaviour tests for CHECKs,
  the wider `datetime('now')` regex and the golden schema (D-13), what `store_vector` already
  does (D-14), the rebuild rules found by test, the checkpoint and `optimize` (D-17), the
  reviewed and rejected features (D-18), `STRICT` (D-19), the table matrix, the full list of
  affected tests (Task 2), the migration-number check and the rehearsal folder under `data/`
  (Task 9), and the *Permitted files*, *Rollback boundary* and *Completion criteria* sections.
  Left to Pipec: rebuilding all 21 tables (the SQLite review) or only the 12 that need it (the
  architecture review), D-19.
- **Type consistency.** `instant_text`, `parse_instant`, `day_text`, `validity_close_day`,
  `INSTANT_LENGTH`, `vector_search_ready`, `count_units_to_reindex`, `HealthReport`,
  `check_health` and `health_failed` are each defined once and named the same in every later
  task; migration file names match D-1 and *Permitted files*; `STALE_VECTOR_AFTER` and
  `STALE_EPISODE_AFTER` live only in `db_health`.
- **Proportion.** No SQL body is written here: each migration is fixed by its rules (D-2 to D-10,
  D-17, D-19), *The table matrix* and its tests; the executor writes the DDL from the schema at
  016 and those rules.
