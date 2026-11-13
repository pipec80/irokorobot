# 0038 — The memory engine's storage foundation: one SQLite file for every kind of memory, built to last years

- **Status:** Proposed (2026-11-13). Written at Pipec's request after he named the storage the core
  of the product («estamos montando un motor de memoria sobre SQLite»: relational, vector, full
  text, graph and document memory all on SQLite; starting the schema from zero is acceptable in
  the MVP). It rests on seven independent read-only reviews of 2026-11-13: two of Plan 0085's
  first draft, then two research rounds (*Context*), and on the code of `main` at `8b37846`. It becomes `Accepted` when the plan that
  implements it closes. **Pipec confirmed all nine recommendations of *Pipec's decisions* the same
  day**; Plan 0085 is rewritten on them, in two parts.
- **Date:** 2026-11-13
- **Builds on:** [ADR 0011](0011-sqlite-transaction-ownership.md) (one transaction owner),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md) (decision 6, `secure_delete`),
  [ADR 0027](0027-conversation-record-and-the-diary.md) (the record and the diary),
  [ADR 0028](0028-recall-what-the-owner-told.md) (recall units),
  [ADR 0031](0031-the-memory-engine-boundary.md) (decisions 4 to 9 and 12),
  [ADR 0032](0032-block-c-hygiene-correct-forget-and-years.md) (decision 1, and the storage that
  decisions 2, 3, 5, 6 and 8 will need).
- **Amends:** [ADR 0031](0031-the-memory-engine-boundary.md) decision 8 («an index can be rebuilt
  from its source»: a recall unit's and an episode's sensitivity and an episode's summary are
  primary data, decision 7 here); [ADR 0027](0027-conversation-record-and-the-diary.md) (the turns
  of a record become rows, decision 6, if Pipec accepts it).
- **Delivers:** the foundation under row 8 of the
  [path to the finish line](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory):
  Plan 0085 (C1) is rewritten on it, and Plans 0086 (C2) and 0087 (the export) build on the same
  schema; C2 changes at most the key of the small episodes table, never the recall or record
  tables again.

## Context

**What the engine stores.** One file, `data/omnibot.db`, 21 live tables, 3 virtual tables and 9
dead ones (the audit of Plan 0085): the conversation record (its turns as one JSON array), the
diary, recall units with FTS5 and `sqlite-vec`, the V4 graph of facts and relations, candidates,
pending topics, identity and consent, contacts, the acta and two audits.

**The research (2026-11-13).** Round 1 ran four reviews in parallel: vectors and hybrid search on
SQLite; graphs, documents and time on SQLite; SQLite operation, durability and migrations; and the
engine's own storage code. Round 2 verified fourteen claims against primary sources (sqlite.org
pages and release logs, the `python-build-standalone` and `sqlite-vec` repositories, Ollama's
source) and ran small tests on throwaway databases. The facts that decide something:

1. **No other store or extension wins.** Kuzu (the embedded graph database) was archived in
   October 2025; `sqlite-graph` is a 0.1.0 alpha; temporal knowledge graphs in agent memory
   (Zep/Graphiti, arXiv 2501.13956) use the same edge shape as V4 with two times per edge (valid
   and recorded). `sqlite-vec` 0.1.9 (2026-03-31) is the latest stable release, pre-1.0, with ANN
   only in alphas; `vec1` (0.8, a loadable extension in the SQLite tree since 2026-09-30) has no
   partition keys and ships in no release; `sqlite-vss` is abandoned. SQLite stays the one store,
   as [ADR 0031](0031-the-memory-engine-boundary.md) decision 12 says.
2. **The SQLite comes with Python, not with the OS.** The project uses uv-managed CPython
   (`python-preference = "managed"`, `python-build-standalone`), which bundles its own SQLite: 3.49.1
   on today's 3.12.11 (built 2025-08-06). Every `python-build-standalone` release since 20260602
   bundles **3.53.1**, with FTS5, RTREE, DBSTAT and loadable extensions on Linux; uv 0.10.11 (here)
   only knows 3.12.13, so getting it needs a newer uv and `uv python upgrade`. The OS SQLite would
   be wrong on the Pi: Raspberry Pi OS Bookworm ships 3.40.1, which **cannot read** the FTS5
   `secure-delete` index this database already uses (3.42+). JetPack 5 (3.31) cannot open a
   `STRICT` table (3.37+).
3. **A real corruption bug sits under our version.** The WAL-reset bug affects 3.7.0 to 3.51.2 and
   is fixed in 3.51.3 (2026-03-13); it needs two connections writing or checkpointing at the same
   instant. One connection under one lock (ADR 0011) keeps us outside it, but `iroko-admin`,
   backups and the export open a second one.
4. **SQLite 3.53.0 (2026-04-09) can add and drop `CHECK` and `NOT NULL` with `ALTER TABLE`**,
   validating existing rows; fixes to `DROP CONSTRAINT` landed after 3.53.1. A closed vocabulary in
   a `CHECK` is no longer frozen for ever, but the table rebuild stays the safe path until the
   runtime has those fixes.
5. **`synchronous=NORMAL` in WAL can roll back a committed transaction after a power cut** (FULL
   cannot). [ADR 0032](0032-block-c-hygiene-correct-forget-and-years.md) decision 7 accepts losing
   a turn; a deletion that rolls back brings a forgotten memory back.
6. **Physical deletion holds on the installed versions, with conditions.** `sqlite-vec` 0.1.9's
   `DELETE` zero-fills the vector, rowid and metadata slots (source read and tested; issue #54 is
   stale), but space is reclaimed only when a whole chunk empties. FTS5 needs its own
   `secure-delete=1` besides `PRAGMA secure_delete`. Old page images stay in the WAL until a
   checkpoint; a checkpoint releases blocks on flash, it does not overwrite them.
7. **`trusted_schema=OFF` breaks our recall trigger.** SQLite recommends turning it off, but a
   trigger that writes to a `vec0` table then fails with «unsafe use of virtual table» (tested);
   `recall_units_ad` deletes from `recall_units_vec`.
8. **The code has defects a storage foundation must close.** `db.transaction()` awaits
   `BEGIN IMMEDIATE` before its `try`, so a cancellation in that window leaves a transaction open;
   migrations 1 to 9 are not atomic; a rebuild with foreign keys on would fire cascades on
   `DROP TABLE` (confirmed); `UPDATE recall_units SET body` silently desynchronises FTS5 (tested);
   `face_profiles` reuses a deleted top id, and `vec_faces.rowid` follows it (tested).
9. **Derivation is held by soft pointers.** A turn lives inside a JSON array; recall units,
   candidates and pending topics point at it by a text correlation id with no foreign key and no
   index; a V4 fact has no pointer to the candidate or turn it came from. Deleting «everything
   derived from this turn» (ADR 0032 decision 2) cannot be proven from the schema.
10. **Time and ids.** Two instant formats live side by side (Plan 0085's audit); `recall_units`
    has no `recorded_at` or `embedded_at`; integer ids are unique only within one database
    lineage, so a deletion register keyed on them breaks once a backup is restored and ids are
    reissued.
11. **Ollama.** `/api/embed` (the one the code calls) returns L2-normalised vectors; a model's
    `digest` comes from `/api/tags`. A tag name can be re-pushed and is not a vector space's
    identity.
12. **Why not a blank database.** The seed file and the record cannot rebuild the biometric
    profiles, the dated consents, the audit evidence, the facts confirmed by dialogue, the
    candidates, or the diary's model-written episodes and their raised sensitivity. Data must be
    carried.

The research notes themselves are working files of the session and are not required reading; this
*Context* is what any plan may cite.

## Decision

### 1. One SQLite file is the single store of every kind of memory

Relational rows, full text (FTS5), vectors (`sqlite-vec`), the knowledge graph (edge rows walked by
recursive CTEs) and documents (JSON) all live in `data/omnibot.db`. No second store, no graph
extension, no attached database (foreign keys and atomic commits do not cross files). A new kind
of memory is a new table of this file under the same rules. Revisit when `sqlite-vec` stays
unmaintained through 2027, when `vec1` reaches 1.0 with partition keys, or when a measured graph
query exceeds its latency budget.

### 2. The runtime is pinned and checked at start-up

- SQLite comes **only** from the uv-managed `python-build-standalone` CPython, on every host (the
  laptop, the Pi, a Jetson), never from the OS. The floor is **SQLite 3.51.3** (the WAL-reset fix);
  the target is the bundled **3.53.1**, reached by upgrading uv and running `uv python upgrade`.
- `sqlite-vec` is pinned to an exact version (`==0.1.9` today); an upgrade is its own change with
  the physical-deletion test of decision 9.
- `open_db` asserts the floor, the compile options the engine needs (FTS5, loadable extensions)
  and the `sqlite-vec` version, and logs `sqlite_version`, `vec_version` and the compile options
  once. A host below the floor does not start.

### 3. One connection, explicit pragmas, read back

The single writer connection of ADR 0011 stays; a pool of read-only connections waits for a
measurement. `open_db` sets, then **reads back and refuses to start on a mismatch**:
`journal_mode=WAL`, `synchronous=NORMAL` (decision 4 raises it for deletions),
`foreign_keys=ON`, `secure_delete=ON` (never `FAST`), `busy_timeout=5000`,
`wal_autocheckpoint=1000`, `journal_size_limit=67108864`, `temp_store=MEMORY` (no temp file holds
deleted text), `cell_size_check=ON`, `recursive_triggers=OFF`, and `PRAGMA optimize=0x10002`; the
retention job runs `PRAGMA optimize` every few hours and `close_db` once more. `trusted_schema`
stays **ON**, written down with its reason (decision 7 of *Context*: the `vec0` trigger; this
database never opens a file it did not create). The file carries a fixed `application_id`, and
`open_db` refuses a file with another one. `transaction()` opens `BEGIN IMMEDIATE` inside its
`try`, so a cancellation always rolls back; no model, embedding or network call is awaited inside
a write transaction.

### 4. Durability: a turn may be lost, a deletion may not

A conversational turn commits under `synchronous=NORMAL` (ADR 0032 decision 7). A **physical
deletion** follows one protocol: append its line to the deletion register and `fsync` it (file
and directory); delete in one transaction under `synchronous=FULL`; checkpoint with `TRUNCATE`;
at start-up, replay every register line (idempotent). A power cut at any step leaves the memory
either deleted or deleted again at the next start. Plan 0086 implements it; this ADR fixes the
order.

### 5. Schema rules for every table

- **`STRICT`** on every ordinary table (virtual tables cannot be).
- **Keys.** An `INTEGER PRIMARY KEY` (FTS5 and `vec0` map rows by it) with `AUTOINCREMENT` on every
  table whose id another row, a vector, an audit or the register names, so a deleted id is never
  reused. A **`uid`** (`TEXT`, UUIDv7, unique) on every row the deletion register, an export or a
  future merge names: entities, facts, relations, records, turns, episodes, recall units,
  candidates, pending topics, contacts and profiles. The register and the export key on `uid`.
- **Time.** An instant is ISO 8601 UTC with microseconds, 32 characters
  (`2026-11-03T10:00:00.000000+00:00`), behind an exact `CHECK`; a calendar day is an ISO date
  (`date(x) IS x`), a household day where the owner lives it; a validity bound is an ISO date at
  day or month precision; written by one Python module, never `datetime('now')`.
- **Constraints.** `NOT NULL` and `CHECK` on states, sensitivities, visibilities and kinds (3.53
  can alter them; the rebuild stays the fallback); the write channel and the policy audit's action
  and policy stay closed lists in Python. `json_valid` on every JSON column.
- **Naming.** As Plan 0085 D-10; written in the data dictionary.

### 6. The shape of each kind of memory

- **The graph.** `literal_facts_v4` and `entity_relations_v4` stay two edge tables (a literal and
  an entity target differ). Each edge carries **world time** (`valid_from`, `valid_to`) and
  **record time** (`recorded_at`, `retracted_at`), as a temporal knowledge graph does; a
  correction closes the old edge and adds a new one, never edits it. Traversal is a recursive CTE
  with `UNION ALL`, a depth cap and a visited path; a closure table or a graph extension only
  when a measured query asks.
- **The record.** **The turns become rows** (`conversation_turns`: the record, a `uid`, the
  correlation id, unique, `said_at`, the speaker's verdict, the words heard and said, the
  sensitivity, `redacted_at`); the record keeps its segment fields and counters. A deletion,
  redaction or sensitivity then applies to one turn by key, not by rewriting a JSON array.
- **Derivation is typed.** A recall unit points at its turn **or** its episode by foreign key; an
  episode lists its turns in `episode_sources` (a link row goes with its turn, the episode does
  not, so C2 can let an episode outlive its record, ADR 0032 decision 5, by changing only the
  episode's own key to its record); a candidate and a pending topic point at their turn; a fact
  points at the candidate it was promoted from. Facts, units and episodes carry ADR 0031 decision
  6's **origin** and **transformation**. An index or projection is reached by key, so «everything
  derived from this turn» is one query.
- **Archive.** `archived_at` on facts, relations, episodes and recall units (ADR 0032 decision 3);
  archived rows are filtered by every reader and come back by clearing the column.
- **Full text.** FTS5 external content, `unicode61 remove_diacritics 2`, `secure-delete=1` on
  **every** FTS5 table, and a trigger that refuses an `UPDATE` of an indexed body (a unit is
  replaced, never edited). `trigram` or Spanish stemming only after a measurement on a real
  corpus.
- **Vectors.** An `embedding_spaces` table names each space (the Ollama tag, its `digest`, the
  dimension, the metric, normalised or not, and a state: `building`, `active`, `retired`). One
  `vec0` table per dimension holds the vectors with **the owner and the space as partition keys**
  and the sensitivity and the told day as metadata, so a query compares only the active space's
  vectors and filters the window inside the KNN. A model change builds the new space beside the
  old one, verifies the count, flips `active` and deletes the old space's rows; vector search is
  off for the owner while no space is active (lexical search keeps working). A recall unit records
  `recorded_at` and `embedded_at`.
- **Documents.** JSON stays for attribute bags (an entity's attributes, the acta's snapshots), as
  text, never JSONB (an export must read it outside SQLite); a field filtered twice gets a
  `VIRTUAL` generated column and an index. Anything searched, deleted or access-checked one by one
  is a row. Documents as a RAG source (ADR 0034) follow these rules.

### 7. What is primary and what is a projection

The record's turns, the facts, the relations, the episodes' summaries and **the sensitivity a
diary job assigned** are primary data: they are backed up and exported, never rebuilt. FTS5 rows
and vectors are projections: rebuilt from their source, never outliving it. This amends ADR 0031
decision 8, which called every index rebuildable.

### 8. Writers and boundaries

Every table has one owner module, the only one whose SQL touches it, held by a guard test for
**every** table (today eight are guarded). All SQL lives in `server/memory/`: the biometric
inserts of `vision/faces.py` and `voice/voiceprints.py` move behind the consent stores,
`personal_setup` reads through the stores, and `owner_pin_credentials` gets one writer.

### 9. Migrations, and how the current database reaches the new shape

- The runner owns atomicity: `BEGIN IMMEDIATE`, the script, `PRAGMA user_version`,
  `foreign_key_check`, `COMMIT`; a rebuild runs with `PRAGMA foreign_keys=OFF` set outside the
  transaction and turned back on whatever happens. Forward only; a golden-schema test compares a
  fresh install with an upgraded database.
- **The v2 schema is designed from zero, and the data is carried, not re-typed.** Fresh installs
  start from one baseline script (`schema_v2.sql`); the one real database reaches it through one
  tested upgrade migration from version 16, rehearsed on a copy with per-table counts and the
  health check before it runs; the old migration files leave the tree (git keeps them). After a
  successful upgrade the pre-upgrade backup is deleted once Pipec accepts (it would hold what a
  later deletion removes).
- **Physical deletion is tested at the byte level**: for a table row, an FTS5 row and a `vec0`
  row, a unique canary is written, deleted and checkpointed, and neither the database file nor the
  WAL holds its bytes. The test runs again whenever SQLite or `sqlite-vec` changes.

### 10. Health and observability

`iroko-admin health` (counts only): `integrity_check`, `foreign_key_check`, FTS5
`integrity-check`, orphans of every projection, staleness, rows outside the formats, `page_count`
and `freelist_count`, and the versions of decision 2. `open_db` runs `quick_check` once.

### 11. Measured later, never by default

A read-only connection pool (retrieval p95 under writes); `synchronous=FULL` for everything (its
cost measured on the Pi); `cache_size` and `mmap_size`; `int8` or binary vectors with re-ranking
(a 100k-vector benchmark on the Pi first, then a new gate calibration); FTS5 `trigram` or stemming;
a second embedding model (Granite R2 with Matryoshka is a candidate); `vec1` or `sqlite-vector`
when they mature. Backups by `VACUUM INTO` or the backup API, and encryption (LUKS first; SQLCipher
or SQLite3MultipleCiphers tested with FTS5 and `sqlite-vec` before any choice) belong to
[ADR 0033](0033-the-home-server-in-a-container.md). Not adopted: Litestream (it replicates old
pages a deletion must remove), `secure_delete=FAST`, `synchronous=OFF`, `WITHOUT ROWID` on these
tables, JSONB for exported data, a raw second copy of every vector.

## Pipec's decisions (2026-11-13)

Pipec confirmed every recommendation as written («Confirm all 9»).

| # | Decision | Where |
|---|---|---|
| 1 | Turns become rows (`conversation_turns`) instead of one JSON array per record | Decision 6 |
| 2 | The v2 schema is designed from zero and the data is carried by one tested upgrade from version 16, instead of Plan 0085's three incremental migrations | Decision 9 |
| 3 | A `uid` (UUIDv7) beside the integer key on every durable personal row; the register and the export key on it | Decision 5 |
| 4 | Record time (`recorded_at`, `retracted_at`) on facts and relations, beside world time | Decision 6 |
| 5 | `embedding_spaces` with the Ollama digest, and `vec0` partitioned by owner and space | Decision 6 |
| 6 | SQLite only from uv's CPython, floor 3.51.3, target 3.53.1 (a uv upgrade and `uv python upgrade` on the laptop, and the same on the Pi) | Decision 2 |
| 7 | The deletion protocol: register first, `FULL`, checkpoint, replay at start-up | Decision 4 |
| 8 | `trusted_schema` stays ON for the `vec0` trigger, with the reason written | Decision 3 |
| 9 | Delivery: Plan 0085 rewritten on this ADR in two parts, A (the runtime, the pragmas, the transaction, one writer per table, the deletion test) and B (the v2 schema and the upgrade), each its own branch and PR | Plan 0085 |

## Not decided here

| Subject | Owner |
|---|---|
| Correcting, archiving and deleting by voice or PIN, the register's file format, the diary's retention | ADR 0032, Plan 0086 |
| The export's format and scope | ADR 0032 decision 8, Plan 0087 |
| An «erase a person» order across the `RESTRICT` keys, and the retention of the two audits | Plan 0086, then Plan 0087 |
| Backups, restore, encryption at rest | ADR 0033 |
| Documents as a source | ADR 0034, with these rules |
| Extracting the engine into its own package | ADR 0031 decision 11 |

## Alternatives considered

- **Plan 0085 as drafted (three in-place migrations).** Sound mechanics, but it keeps the turns in
  JSON and the soft pointers, so C2 would rebuild the same tables again, the riskiest
  (`recall_units`) among them.
- **A blank database re-filled from the seed file.** Rejected: biometrics, consents, audits,
  confirmed facts and the diary cannot be re-created (*Context* item 12).
- **A graph database or graph extension** (Kuzu and its forks, `sqlite-graph`, GraphQLite, Neo4j).
  Rejected: archived, alpha, unverified on ARM64, or a second store (ADR 0031 decision 12).
- **Another vector extension** (`vec1`, `sqlite-vector`, `vectorlite`, libSQL). Watched, not
  adopted: none replaces `sqlite-vec`'s partition keys and metadata today.
- **Lookup tables instead of `CHECK` vocabularies.** Rejected for now: 3.53 alters a `CHECK`, and a
  lookup table adds joins to every reader.
- **The OS SQLite.** Rejected: Bookworm's 3.40 cannot read the FTS5 index this database already
  uses.

## Consequences

### Positive

- One rebuild brings the database to the shape C1, C2 and the export need; deleting, exporting
  and archiving become queries by key.
- The runtime is the same SQLite on every host, above a known corruption fix, checked at start.
- A deletion survives a power cut and a restore; the byte-level test proves it on the installed
  versions.

### Negative

- A larger first plan: a new schema, an upgrade migration with its rehearsal, and changes in about
  fifteen store modules and many tests.
- A uv and Python patch upgrade before the work, verified with the voice and face models (the
  Dependabot rule for runtimes).
- `trusted_schema` stays on against SQLite's general advice, for a written reason.

## Test consequences

The byte-level deletion test (decision 9); the start-up assertions and the pragma read-back
(decisions 2, 3); `transaction()` cancelled after `BEGIN` rolls back; a failed migration leaves
foreign keys on and the version unchanged; the upgrade from a version-16 canary database keeps
every count and equals a fresh install (golden schema); the guards of decisions 5 and 8; a model
change never compares two spaces and leaves lexical search on; an `UPDATE` of an indexed body is
refused.

## Docs to update

The ADR index; ADR 0031 (a note on decision 8) and ADR 0027 (the turns, if decision 6 is
accepted) when this is accepted; Plan 0085 (rewritten); the roadmap (row 8, *Database hygiene*);
`current-state.md`, the data dictionary and the memory diagram when the plan closes.
