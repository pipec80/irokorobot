# 0039 — C2: the cheapest forms of correcting, archiving and deleting a memory

- **Status:** **Accepted (2026-11-18)**, when [Plan 0086](../plans/completed/0086-c2-correct-archive-delete.md)
  closed, accepted on real hardware ([record](../evals/0086-c2-acceptance.md)). Proposed
  2026-11-17; **Pipec confirmed its six decisions that day** with the plan's eleven («apruebo
  todo»). See *Implementation* for what execution added. Written from the code of `main` at
  `c4667fe` (schema version 20) under Pipec's scope rule of 2026-11-16 (*the cheapest form that
  holds the guarantee wins*) and Pipec's model of forgetting of 2026-11-17 (*a person replaces or
  sets aside a memory; the robot may also delete for good, rarely, on purpose*).
- **Date:** 2026-11-17
- **Builds on:** [ADR 0032](0032-block-c-hygiene-correct-forget-and-years.md) (decisions 2 to 6,
  confirmed by Pipec on 2026-11-11 and 2026-11-13), [ADR 0038](0038-the-memory-engines-storage-foundation.md)
  (decision 4 and the *Amendment of 2026-11-16*), [ADR 0019](0019-personal-memory-capabilities.md)
  (the capabilities), [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md) decision 9
  (the closed answer), [ADR 0026](0026-owner-profile-card-and-the-read-side-of-memory.md) decision 9
  (third parties by voice after CM-7).
- **Amends:** ADR 0038 decision 5 (*the register keys on `uid`*) and decision 6 (`episode_sources`,
  a fact's own link to its turn); ADR 0032 decision 2 (*a deleted story's turn is redacted to a
  marker*) and the mechanism of decision 5 (*a migration of the foreign keys*); ADR 0019 §3 (a sixth
  capability, `archive_personal_memory`).

## Context

ADR 0032 fixed **what** C2 does; ADR 0038's amendment deferred four storage pieces to Plan 0086,
each with a trigger. Reading the merged code (schema 20) shows that a cheaper form holds each
guarantee:

1. **The register and reissued ids.** ADR 0038 keyed the deletion register on a `uid` because
   integer ids are reissued after a restore. The danger is narrower: a line replayed **again** at a
   later start, after a restored database reissued its id to a new row. A replay marker kept inside
   the database, written in the same transaction as each deletion, makes every line apply once per
   database lineage: lines newer than a restored backup's marker name rows of that backup's own
   lineage (an id that never existed there is a no-op). `uid` needs a column on about ten tables, a
   UUIDv7 writer in every insert (Python 3.12 has none) and deterministic UUIDv8 for carried rows.
2. **The diary outliving its record.** ADR 0032 decision 5 asked for a migration of the
   `conversation_episodes` and `recall_units` foreign keys; SQLite cannot change a foreign key
   without rebuilding the table, and `recall_units` is the riskiest table (FTS5 and `vec0`
   triggers). The raw text is in `conversation_turns`, not in the record row. Purging a record's
   **turns** and keeping its row while it holds a written episode lets the episode and its recall
   unit live on with no key changed; the turn units, candidates and pending topics still go with
   their turns (Plan 0085's `CASCADE`). `episode_sources` is then the record's own turns.
3. **A confirmed fact's link to its turn.** ADR 0038 feared a fact losing its only link to its
   story when its candidate is cleaned up. No code deletes a candidate row except the `CASCADE`
   from its turn or its person (`candidates.py` has no `DELETE`): while the turn lives, turn →
   candidate → `promoted_fact_id` names the fact; when the turn goes, the candidate goes and the
   fact stays (ADR 0038 row 10 holds today).
4. **Archiving has no capability.** ADR 0032 decision 3 sets archiving at `basic`; ADR 0019's five
   actions have no archive, and reusing `correct` would audit an archive as a correction.
5. **«Everything about one person».** The registry has no friend relation: a third party the owner
   only talked about lives only in the diary (ADR 0026 decision 9), and one loaded at the alta is an
   entity with relations, facts and perhaps a care contact.

## Decision

1. **The register keys on the table and the integer id, with a replay marker.** One JSON line per
   deleted row (`seq`, `kind`, `id`, `at`; never a value) in `deletions.jsonl` beside the database.
   The deletion writes the marker (`meta.deletion_register_seq`) in its own transaction; a start
   replays only the lines after the marker, in order, then moves it. `uid` stays deferred; its
   trigger becomes *two databases merged, or a register replayed across a reset*.
2. **The diary outlives its record by keeping the record row.** The purge (expiry and the space
   cap) deletes a record's turns and keeps the row while its episode is written; a record without
   a written episode goes whole, as today. A recall reads an episode unit whatever its record's
   expiry. Withdrawing the consent or deleting with the PIN still deletes both. No foreign key
   changes; `episode_sources` stays deferred (trigger: an episode built from turns of more than one
   record).
3. **A fact's link to its turn stays through its candidate.** No column is added. The deletion of a
   story names the facts confirmed from its turn (turn → candidate → fact) and keeps them. Trigger
   for the column: a job that deletes candidate rows before their turn.
4. **Archiving is its own capability**, `archive_personal_memory`: `basic`, consent applies, no
   unlock, `personal` only, as `correct_personal_memory`. Anything above `normal` is refused by
   voice and pointed to `iroko-admin`.
5. **A deleted story's turn is deleted, not redacted.** The turn row goes (with its unit, its
   candidate and its pending topic) and the whole episode of its record with it (ADR 0032
   decision 2); the record's other turns stay. No `redacted_at` column.
6. **«Everything about one person» today** is: the entity and what hangs from it (its relations,
   its facts, its care contacts), and the turns, episodes, recall units and pending topics whose
   words name it (folded, as whole words, with and without one final «s»), and, for a deletion,
   the owner's own facts whose value names it. By voice it is **archived** (never said, offered or
   searched; recoverable), only for `normal` and `personal` rows; with the PIN in `iroko-admin` it
   is **deleted** in the order the `RESTRICT` keys need (contacts first, then the diary, then the
   facts and relations, then the entity). A person with a role, a credential, a biometric profile or a
   consent is an enrolled member: neither path touches them until those are revoked by their own
   commands.

## Alternatives considered

- **`uid` on every durable row (ADR 0038 decision 5).** Holds the same guarantee at many times the
  cost; kept as the target for a merge of databases.
- **Rebuild `recall_units` and `conversation_episodes` with nullable keys (ADR 0032 decision 5 as
  written).** Rejected: a rebuild of the FTS5 and `vec0` table for a guarantee the record row gives.
- **Redact a deleted turn to a marker.** Rejected: a column and a marker the export would show, for
  nothing a deleted row does not already give.
- **Reuse `correct_personal_memory` for archiving.** Rejected: the audit would call an archive a
  correction.

## Consequences

### Positive

- C2 needs one `ADD COLUMN` migration and no table rebuild.
- A restore never resurrects a deletion, and a reissued id is never deleted by a second replay.
- The diary reaches «hace dos años» while the raw text keeps its 365 days.

### Negative

- A record row with no turns stays while its episode lives (times and counters only, no text).
- The register is tied to one database lineage; a merge of two databases needs `uid` first.
- Archiving a person also sets aside every episode whose summary names them, with the other
  memories of that day.

## Review

Revisit decision 1 when two databases must be merged; decision 2 when an episode spans records;
decision 3 when candidate rows are cleaned up before their turn; decision 6 when third parties are
learned from conversation (after CM-7).

## Implementation (2026-11-18)

Built by Plan 0086 (PR #285, `fac1817`) with the fixes its review and its hardware sitting found
(PR #286 to #288). What execution added to the decisions above:

- **Decision 1.** A deletion is **probed** in a rolled-back savepoint before its line is appended,
  so a deletion a `RESTRICT` key refuses (a revoked role, a consent, a profile) writes nothing and
  never stops a start. On a replay into a restored backup a line a key refuses is kept in
  `meta.deletion_register_waiting`, tried again at every start, logged
  (`deletion.replay waiting lines=%d`) and announced by `iroko-admin` until it applies. The next
  number follows both the file and the marker, so a lost register reuses no number. The deletion
  and its audit row commit in one transaction under `synchronous=FULL`.
- **Decision 2.** Deleting an episode sets its record's status to `skipped`, so the purge takes a
  record kept only for its episode.
- **Decision 6.** As written above: the name variants and the owner's own facts were found in the
  review and on hardware. A voice change also refuses a `medical` pending topic and a fact or
  relation that is not `personal`; a correction's new value must pass the preference gate; a
  message with a secret is never a change; a spoken change is never itself a recall unit.
