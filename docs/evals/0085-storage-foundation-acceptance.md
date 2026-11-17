# 0085 — The storage foundation: acceptance

> **Status:** **accepted 2026-11-17 by Pipec.** Part A merged 2026-11-16 (PR #279, `6660f85`) and
> Part B merged 2026-11-17 (PR #282, `c21b2b9`); both of the plan's hardware checks passed, the
> real database is at schema version 20 and `iroko-admin health` exits 0 on it. Code of
> [Plan 0085](../plans/completed/0085-database-good-practices.md),
> [ADR 0038](../adr/0038-the-memory-engines-storage-foundation.md) as amended on 2026-11-16.
> Pipec ran every hardware step and started the server himself; the agent started nothing.
> **Counts, outcomes and yes/no only:** no value of the database, no household datum and nothing a
> person said is recorded here; the spoken turns were the plan's script (a greeting, three
> questions), and the only text quoted is the robot's fixed wording as it stands in the code.

## Setup

- The server and the robot on the laptop body, streaming route, memory on, the conversation
  record, recall and pending topics on (the settings of the previous plans).
- Part A touched no table; Part B ran four ordinary migrations on the real database
  (017 to 020) at its first start, after a backup.
- Counts come from the server's start-up lines (the runtime line, the migrations) and from
  `iroko-admin health`, which prints counts only and changes no row.

## Part A: the safety fixes (2026-11-16)

| # | Case | Result |
|---|---|---|
| 1 | The runtime check at start | **Pass**: the runtime line (SQLite, `sqlite-vec`) logged once, no warning |
| 2 | Three spoken turns after the start | **Pass**: three turns answered 200, recall found, no warning or error |
| 3 | One time format in every writer | **Pass**: on a copy of the database (deleted the same day), 0 time values written that day outside 32 characters; `integrity_check` ok |
| 4 | The byte-level deletion test | **Pass** in CI: a canary written to a plain row and to a recall unit is absent from the database file and its WAL after the deletion and a completed checkpoint |

Part A also closed the transaction window of `transaction()`, the half-started connection of
`open_db` and a failed `COMMIT` that left a transaction open, and moved `care_contacts.py` to the
one time format (added to the plan's files by Pipec on 2026-11-16). The CI selection was 8153
passed (baseline 8108).

## Part B: the schema (2026-11-17)

**Automated.** CI selection **8296 passed** (baseline 8173, the code of `main` before the plan).
`pyright`, `mypy`, `ruff`, the format check, the reserved-terms guard and `just audit` clean. The
whole-branch reviews (five read-only agents, security included) found no critical defect and no
data loss; each accepted finding was fixed with its failing test first. Pipec's decisions are in
the plan: both segment limits kept (60 rows **or** 64 KB, both measured as the bytes of the heard
and said text), the orphans removed (`sensor_retention_hours`, `FactRecord`), and
`llm_transport.py` and `conversation_types.py` cleaned.

**Rehearsal on a copy of the real database** (server stopped, twice; the last on 2026-11-17 at
17:54, on the code that was merged). The copy was deleted the same day.

| # | Step | Result |
|---|---|---|
| 5 | Backup `pre-0085` and its restore | **Pass**: the backup restored into a copy opens at version 16 with `integrity_check` ok and every table count equal |
| 6 | The migrations on a copy | **Pass**: version 20, `integrity_check` ok, no foreign key violation |
| 7 | The turns as rows | **Pass**: 202 turn rows equal the 202 JSON turns |
| 8 | The dead tables | **Pass**: the 8 dead tables held 0 rows and are gone; `memories` stays, as the plan says |
| 9 | Every other table | **Pass**: the same row count as before |
| 10 | `iroko-admin health` on the copy | **Pass**: every measure 0 |

**The real upgrade (2026-11-17, 18:22; Pipec started the server).**

| # | Case | Result |
|---|---|---|
| 11 | Migrations 17 to 20 on the real database | **Pass**: applied on start, schema version 20, the runtime line logged, no warning or error |
| 12 | The greeting | **Pass**: 200; the pending-topic follow-up of [Plan 0084](../plans/completed/0084-pending-topics-and-the-greeting.md) was asked, the first time on hardware |
| 13 | «¿Qué sabes de mí?» | **Pass**: 200, and it no longer says «Te trato de tú» (the change of PR #281) |
| 14 | «¿Te acuerdas de lo que te conté el viernes?» | **Pass**: 200, answered in the third person, «El viernes me contaste que…» (the change of PR #281) |
| 15 | The owner's own sensitive read (medications) | **Pass**: 200, answered as before the migration |
| 16 | The first turn | **Note**: it took 99 s, the local model cold after a restart; unrelated to the migration |
| 17 | `iroko-admin health`, server stopped | **Pass**: exit 0, every measure 0 (0 integrity errors, 0 foreign key violations, 0 orphans, 0 rows outside the time format) |
| 18 | The `post-0085` backup | **Pass**: `data/backups/post-0085-20261117-182748` restored into a copy opens at version 20 with health 0; the copy was deleted |

## The `pre-0085` backups

The plan keeps a `pre-0085` backup until a `post-0085` backup has been restored and opened with
health exiting 0 (case 18) and the owner accepts. Pipec accepted on 2026-11-17 and **the three
`pre-0085` backups were deleted that day**: `pre-0085-20261117-130025`,
`pre-0085-20261117-175416` and the Part A one, `pre-0085a-20261116-175616`. The `post-0085` backup
stays. The plan's rollback boundary (the previous `main` with a `pre-0085` backup) is therefore
closed: from here a rollback is the `post-0085` backup.

## Completion criteria

| # | Criterion | Result |
|---|---|---|
| 1 | Part A merged: runtime checked at start, transaction and start-up gaps closed, one time format in every writer, the byte-level deletion test green | **Met** (PR #279, `6660f85`; cases 1 to 4) |
| 2 | Part B merged and the real database at version 20, rehearsal counts equal, the eight dead tables gone with 0 rows | **Met** (PR #282, `c21b2b9`; cases 5 to 11) |
| 3 | `iroko-admin health` exits 0 on the real database | **Met** (case 17) |
| 4 | The guards, the dictionary coverage and the deletion test pass; the spoken scripts answered as before | **Met** (CI 8296 passed; cases 12 to 15) |
| 5 | A proven `post-0085` backup exists and the `pre-0085` backup is deleted after Pipec's acceptance; the documents of Task B8 updated; the plan in `completed/` | **Met** (case 18 and the section above; this record and the documents of the close) |

## Limits, stated and not hidden

- The spoken script is four turns on one real conversation; it shows that the answers did not
  change, not a measured rate.
- The database file proves nothing about the storage medium: the byte-level deletion test covers
  the SQLite file and its WAL, not the disk (that is encryption, ADR 0033).
- Everything the plan defers waits for its trigger in ADR 0038's amendment (`uid` keys, `archived_at`,
  a fact's link to its turn, the deletion durability protocol, the Python patch with SQLite 3.53.1,
  a second embedding model, the storage benchmark). Correcting, archiving and deleting a memory is
  Plan 0086; the export is Plan 0087.
