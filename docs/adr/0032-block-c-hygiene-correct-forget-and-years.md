# 0032 — Block C: a clean database, correcting and forgetting, and memories that last for years

- **Status:** Proposed (2026-11-11). Written from the database review of 2026-11-03, the research of
  the memory engine (kept in the ignored `project-history/`), the code read that day and Pipec's
  four decisions of 2026-11-11 (see *Pipec's decisions and where they land*). **Amended by Pipec on
  2026-11-13** (decisions 1, 3 and 8 and the author's calls, rows 5 to 9 of that table): by voice a
  memory is only corrected or archived, a deletion for good needs the PIN, the database follows
  standard formats and good practices, and the owner's data can be exported. Delivered by three
  plans, one at a time: 0085 (C1), 0086 (C2) and 0087 (the export). It becomes `Accepted` when the
  last of them closes.
- **Date:** 2026-11-11
- **Builds on:** [ADR 0011](0011-sqlite-transaction-ownership.md),
  [ADR 0019](0019-personal-memory-capabilities.md) (the five capabilities),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md) (the closed answer dialogue),
  [ADR 0027](0027-conversation-record-and-the-diary.md) (the record, the diary, retention),
  [ADR 0028](0028-recall-what-the-owner-told.md) (recall units),
  [ADR 0031](0031-the-memory-engine-boundary.md) (decisions 4, 7, 8 and 12).
- **Supersedes:** [ADR 0026](0026-owner-profile-card-and-the-read-side-of-memory.md), Pipec's
  decision 4 (forgetting one thing needed face, voice and a spoken confirmation); the `forget` row of
  [ADR 0019](0019-personal-memory-capabilities.md) §3 for one ordinary memory (it required a spent
  PIN grant). Both are replaced by decision 3.
- **Amends:** [ADR 0027](0027-conversation-record-and-the-diary.md) decisions 6 and 9 (the diary
  outlives the raw record, decision 5).
- **Delivers:** row 8 of the
  [path to the finish line](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory):
  C1 the database with good practices (Plan 0085), then C2 correct, archive and delete (CM-6, Plan
  0086), then the export of the owner's data (Plan 0087). Reserved since 2026-11-06.

## Context

1. **The database is sound but uneven** (review of 2026-11-03): two timestamp formats live side by
   side (`YYYY-MM-DD HH:MM:SS` defaults and ISO 8601 with an offset, both in `literal_facts_v4`), so
   ordering across them is wrong; some foreign keys have no index (`superseded_by`,
   `asserted_by_entity_id`, `confirmed_by_entity_id`, `source_memory_id` and the audit tables), so
   a cascade scans; dead or future tables remain (`facts`, `events`, `memories`,
   `legacy_fact_migration_v4`, `outbox`, `sensor_*`); there is no data dictionary.
2. **A model change would mix vector spaces.** ADR 0031 decision 8 requires each vector to name its
   model and a verifiable re-index; the code does not hold it (ADR 0031 *Context* item 8).
3. **Correct and forget have no caller.** The policy exists (ADR 0019); nothing speaks them. A
   revoke today is a supersede to inactive, never a physical deletion, and an index row may outlive
   what it was built from only by accident, not by contract.
4. **Two earlier answers on forgetting disagree.** ADR 0026 recorded «face, voice and a spoken
   confirmation for one thing; the PIN only for olvida todo» (2026-10-28). The roadmap of November
   records «the owner's face and a closed spoken verb for one ordinary memory; the PIN in
   `iroko-admin` for a sensitive or security memory or olvida todo». The voice verifies on about one
   turn in three on the laptop (Plan 0075), which made the first version fail most of the time.
5. **Memories end with the year.** The eligible record lives 365 days (30 for the rest, 200 MB in
   total) and its episodes and recall units are deleted in cascade with it (migrations 013 and 014),
   so «¿qué hice hace dos años?» cannot work.
6. **A restore can bring back what was forgotten.** A cascade in the live database does not touch a
   backup taken before the deletion (ADR 0031 decision 7 leaves the design to this ADR and ADR 0033).
7. **The owner's data cannot be handed over.** Chile's Law 21.719 gives a person the right to see
   and to take away their data, and an audit may ask for everything the robot keeps about one
   person. `iroko-admin` lists and amends; it exports nothing a person can read.

## Decision

### 1. C1 first: the database follows standard formats and good practices (*Pipec, 2026-11-13*)

The plan audits the real schema first (structure and counts only) and lists every change against
it.

- **Time:** every instant is ISO 8601 in UTC with its offset
  (`2026-11-03T10:00:00.000000+00:00`) and every calendar day an ISO date (`2026-11-03`); the
  columns with another format are rewritten by a migration that rebuilds their tables, with a
  before-and-after row count and an ordering test.
- **Keys:** every table has a primary key; every relation is a declared foreign key with an
  explicit `ON DELETE` rule (cascade, restrict or set null), chosen and written down.
- **Indexes** on every foreign key a cascade or a join follows and on every column a frequent query
  filters or orders by, each listed in the plan with the query it serves.
- **Constraints:** `NOT NULL` and `CHECK` on states, sensitivities, kinds and days, so that a value
  the code would refuse cannot enter even through a bug.
- **Normalization:** third normal form where it applies; a deliberate denormalization (the turns of
  a conversation kept as one JSON array) is kept and justified in the dictionary.
- **Naming:** one convention for tables, columns and indexes, written in the dictionary.
- **Dead tables** are dropped after the plan proves no code or foreign key reads them; a table that
  something still names stays and is listed.
- **A data dictionary** in one tracked document: every table, what it is for, its owner module,
  its columns and keys, its classification and its retention.
- **A health check** (`PRAGMA integrity_check`, `foreign_key_check`, orphan and staleness counts):
  counts only, never a value.
- **A guard test** fails when a table has no primary key, a foreign key has no index or a table is
  missing from the dictionary.
- **The engine's guards** (ADR 0031): the architecture guard test, the integrity and staleness
  checks (counts only), and the embedding-model guard: each vector names its model, a vector search
  compares only vectors of the query's model, and a model change turns vector search off until a
  verifiable re-index finishes (lexical search keeps working).
- **Tuning only by measurement**, in ADR 0031 decision 12's order (an FTS5 `trigram` comparison on
  a Spanish corpus first).

### 2. Deleting is physical and complete

Deleting a memory (decision 3: only with the PIN) removes its source row and every projection: recall units, FTS5 rows,
vectors, cached embeddings, episodes built from it and any candidate or offer that points at it.
Only an audit row with no value remains (ADR 0031 decision 7). A test proves, for each kind, that
nothing searchable reappears after a restart.

- **What one memory is.** A V4 fact (a taste, the name, the form) is one row. A told story is the
  recall unit the owner picks; deleting it redacts that turn's text in the record to a marker and
  deletes the **whole episode** built from that segment, because a summary cannot be partly
  unsaid; the other turns of the segment stay in the record and searchable as turns. The plan says
  this to the owner in the confirmation.

### 3. By voice a memory is corrected or archived; a deletion needs the PIN (*Pipec, 2026-11-13*)

As a person's memory does, the robot replaces or sets aside what it knew; it does not destroy it on
a spoken word. Nothing is lost for good without the PIN.

| What | Needs | Effect |
|---|---|---|
| **Correct** one ordinary memory («ya no es así, ahora es…») | The owner's face (`basic`) and a **closed spoken verb** after the robot reads back the change, the closed answer dialogue of ADR 0021 | Decision 4: the old value becomes history, the new one is current |
| **Archive** one ordinary memory («no me lo recuerdes más») | The same: the face and a closed verb after the robot reads back what it will set aside | Not searched, not said, not offered; nothing is destroyed, and `iroko-admin` can bring it back |
| **Delete for good** one memory, a sensitive or security one, or «borra todo» | The PIN, in `iroko-admin`, server stopped (ADR 0025's local path) | Decisions 2 and 6: physical, complete, never revived by a restore |

The voice is not required: it verifies on about one turn in three on the laptop. The residual risk
(a photograph of the owner and someone saying the verb) is accepted for the home as in ADR 0029
decision 2, because correcting or archiving an ordinary memory reveals nothing and loses nothing.
Policy: correcting and archiving a `normal` memory need `basic`; anything above `normal`, and every
deletion for good, keep `strong` and the spent PIN grant (ADR 0019 §3). The voice route refuses a
sensitive memory and points to `iroko-admin`. `iroko-admin` stays a command line for now (row 8 of
*Pipec's decisions*).

### 4. Correcting applies to facts, never to the diary (*Pipec, 2026-11-11*)

«Ya no me gusta el té» or «me equivoqué, prefiero el café» supersedes the V4 fact through the same
closed dialogue as an offer (ADR 0021): the old value becomes `superseded`, the new one `active`,
the card and every reader see only the new one. The diary is what was said that day and is never
edited: a wrong story is archived or deleted (decisions 2 and 3) or a new statement is added. `correct_personal_memory`
keeps `basic`.

### 5. The diary lasts while the owner's consent stands (*Pipec, 2026-11-11*)

The raw record keeps its clocks (365 days eligible, 30 the rest, 200 MB). The **diary episodes and
their recall units no longer die with the record**: they are kept while the owner's
`conversation_storage` consent stands, until deleted (decision 2) or the consent is withdrawn
(which deletes them). A turn unit, which holds the raw words, still goes with its record. This is a
migration of the foreign keys of `conversation_episodes` and `recall_units` (from `CASCADE` to a
nullable reference) and a retention job that tells the two apart. A size cap for episodes is the
plan's, measured.

### 6. A restore never resurrects (*Pipec, 2026-11-11*)

Every physical deletion (decision 3: only with the PIN) appends one line to a **deletion
register**: what kind, which id, when; no
value, ever. The register is an append-only file kept beside the database in the data directory,
**not inside it**, so restoring an older database does not roll it back. A restore re-applies
every register line newer than the backup before the server answers a turn. ADR 0033 owns the
backups and calls this step; a test restores a backup taken before a deletion and finds nothing.

### 7. Durability: the last turn may be lost on a power cut, and that is written down

A turn is recorded after the reply is spoken. A power cut in between may lose that last exchange.
This is accepted (no added latency to every turn), documented in the operator manual, and tested in
block D with an injected failure.

### 8. The owner's data can be exported (*Pipec, 2026-11-13*)

`iroko-admin export`, with the PIN and the server stopped, writes everything the robot keeps, or
everything about one person, to a folder the operator names (never inside the repository), in two
forms: a **human-readable** document (sections and tables, in Spanish) and the same content as
**JSON**. It holds the person's entities and relations, facts with their history, the conversation
record and the diary, recall units, pending topics, consents, contacts, the alta's acta and the
audit rows about that data. A secret appears as its reference, never a value (the database holds no
value of one). Exporting one person never includes another adult's private data. Each export writes
one audit row (who, when, what scope; no value). The file holds personal data: keeping it safe is
the operator's, and the operator manual says so.

## Pipec's decisions and where they land

| # | Decision | Date | Where |
|---|---|---|---|
| 1 | Forgetting: the face and a closed verb for one ordinary memory; the PIN in `iroko-admin` for sensitive, security or everything | 2026-11-11 | Decision 3, *Supersedes* |
| 2 | The diary lasts while consent stands; the raw text keeps its 365 days | 2026-11-11 | Decision 5 |
| 3 | A deletion register re-applied on restore, not crypto-shredding | 2026-11-11 | Decision 6 |
| 4 | Only facts are corrected; the diary is forgotten or added to | 2026-11-11 | Decision 4 |
| 5 | By voice only correct and archive; a deletion for good only with the PIN in `iroko-admin` (it replaces row 1's spoken forgetting) | 2026-11-13 | Decision 3 |
| 6 | The database follows standard formats and good practices: ISO 8601 in UTC, keys, indexes, constraints, normalization, naming, a dictionary | 2026-11-13 | Decision 1 |
| 7 | The owner's data can be exported, all or one person, readable by a person and by a machine, for a legal audit | 2026-11-13 | Decision 8 |
| 8 | `iroko-admin` stays a command line for now; a web administration comes later | 2026-11-13 | *Not decided here* |
| 9 | The author's calls confirmed: the C1 list and order, deleting a story removes its whole episode, the register as a file outside the database, durability accepted and tested in block D | 2026-11-13 | Decisions 1, 2, 6 and 7 |

## Not decided here

| Subject | Owner |
|---|---|
| Where backups live, their encryption and the restore procedure | ADR 0033 (deployment) |
| Forgetting a document | ADR 0034 (documents), with this ADR's rules |
| Forgetting a pending topic or an occurred time by voice | C2's plan, with decision 2 here ([Plan 0084](../plans/open/0084-pending-topics-and-the-greeting.md) left it out, 2026-11-13); a pending topic already expires two days after its due day and goes with its record |
| Consolidating memories into new facts or reflections | Not planned (ADR 0031 *Not decided here*) |
| Third parties' text and Chile's Law 21.719 | Legal advice, pending (ADR 0027) |
| A web administration (the CRUD, the export and the deletion from a browser) | The remote dashboard, the remote half of ADR 0025, after the finish line (Pipec, 2026-11-13) |

## Alternatives considered

- **Forgetting with face, voice and confirmation (ADR 0026).** Rejected by Pipec: the voice
  verifies too rarely on the laptop to be a requirement for an ordinary memory.
- **Consolidating the essential into confirmed facts before the year ends.** Rejected for now: it
  needs a consolidation pipeline and many confirmations; keeping the owner's own summaries reaches
  «hace dos años» with what exists.
- **Crypto-shredding.** Rejected for now: it needs encryption at rest and key management first;
  the register is simple and testable, and crypto-shredding stays possible with ADR 0033.
- **Editing a diary summary by voice.** Rejected: an edited summary is no longer what was said.
- **Deleting for good by voice** (this ADR's decision 3 of 2026-11-11). Replaced by Pipec on
  2026-11-13: a spoken word only corrects or archives, as a person's memory replaces or sets aside;
  the law's deletion and «borra todo» need the PIN.

## Consequences

### Positive

- The database is uniform, keyed, indexed, constrained and documented before anything is deleted
  from it.
- Nothing is lost for good by voice; a deletion with the PIN is physical, complete and survives a
  restore; correcting and archiving are one closed dialogue.
- The owner's data can be handed over for an audit or a legal request.
- Memories last for years without keeping raw text for years.

### Negative

- A table-rebuild migration for the timestamps, and a foreign-key migration for the diary.
- Forgetting one story removes the whole episode summary of that segment.
- The diary grows with the years; its size is watched by a measured cap.
- A photograph and a spoken verb can archive an ordinary memory (accepted: it is reversible and
  nothing is revealed).
- An export file holds personal data; keeping it safe is the operator's.

## Test consequences

- C1: ordering across rewritten timestamps; cascade query plans use the new indexes; no code reads a
  dropped table; every table has a primary key, every foreign key an index and every table a
  dictionary entry (a guard test); the health check logs counts only; a model change disables
  vector search until the re-index ends.
- C2: a correction leaves one current value and the history; an archived memory is not searched,
  said or offered and comes back from `iroko-admin`; for each kind (fact, story, episode,
  candidate, offer) nothing searchable remains after a deletion with the PIN and a restart; a restore from a backup older than a deletion finds nothing; the voice
  route refuses a sensitive memory and points to `iroko-admin`; an episode outlives its record and
  dies with the consent.
- Export: the readable document and the JSON hold the same content; one person's export holds none
  of another adult's private data; no secret value; one audit row per export.

## Docs to update

The ADR index; the roadmap (row 8, *Memories for years*, *Database hygiene*); the data dictionary
(new); `current-state.md` and the architecture diagrams when each plan closes; the operator manual
(durability, `iroko-admin` delete and export, keeping an export safe); ADR 0019, 0026 and 0027 (a *Superseded/Amended by ADR 0032*
note each, when this ADR is accepted).
