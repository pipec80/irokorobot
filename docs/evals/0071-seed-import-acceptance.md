# Plan 0071 — acceptance of the seed importer

> **Status:** run by Pipec on 2026-10-26 on a database kept apart (`data/scratch-0071.db`, gitignored,
> deleted afterwards), on branch `feat/0071-seed-file-importer`; outcomes checked read-only against the
> database by Claude Code after each step. [Plan 0071](../plans/completed/0071-seed-load-file-importer.md).
> **Outcomes only:** no name, phone, value or file content is recorded here.

## Procedure and outcomes

Every step ran from the repository root in PowerShell, with the server stopped.

| # | Step | Expected | Outcome |
|---|---|---|---|
| 1 | `$env:BRAIN_DB_PATH = "data/scratch-0071.db"` | — | Done |
| 2 | `just setup-personal` | `personal_security_ready=True` | `True`. Pipec entered the owner **and two children** (the plan recommends none); the file's children have other names, so no conflict |
| 3 | Copy the example to `data/seed/` | — | Done. The first dry run, with the template's owner name, was refused: «El nombre de la persona titular del archivo no coincide con el registrado.», exit 1, nothing written. With the owner's name set in the file it passed |
| 4 | Dry run | First line the scratch database; «0 problemas»; nothing written | As expected: 43 to write, 0 problems, no location warning (the file was under `data/`) |
| 5 | `--apply` with the declaration, answer `SI` | «Carga aplicada (acta 1).» | As expected. The database then held 43 new rows (7 entities, 7 relations, 27 literals, 2 contacts), every literal on `import_assisted` with the owner as asserter and confirmer; record 1 open with the hash, the counts and 11 section statuses; `secret_holder` stored `personal`/`security`. An earlier answer `si` (lower case) printed «Carga cancelada.», exit 1, nothing written |
| 6 | The same command again, `SI` | Every operation «sin cambios» | As expected: 0 to write, 43 unchanged; counts identical; the same record, its counts now `written: 0` |
| 7 | One birth date changed, dry run without `--replace` | `value_conflict`, nothing written, exit 1 | As expected: one `value_conflict` on the owner's birth date, 42 unchanged, exit 1 |
| 8 | `--replace` (dry run, then `--apply` and `SI`) | Applied; the new date replaces the old one | As expected: the dry run showed 43 to write and wrote nothing; the apply left one active birth-date row (the new one), the 7 imported entities re-created, the same counts, the same record (`written: 43`), the setup's owner, children and their two `child_of` rows untouched |
| 9 | Ask Iroko by voice for the number of children | The count | **Not run** (optional; the scratch database had no face enrolled) |
| 10 | `just reset-db` with `BRAIN_DB_PATH` still set | Prints the scratch path, backs it up, deletes only it | As expected: printed the scratch path, voided 0 candidates, printed the backup note, «DB reset OK»; the scratch file was gone afterwards |
| 11 | Unset the variable, delete the backup and the seed file | — | Done and verified: no scratch file, backup or seed file left |

## Findings

1. **The importer opens the database before it refuses an outdated schema.** In a terminal where the
   variable had been lost, the command pointed at `data/omnibot.db` (schema 9) and refused with «La
   base de datos no está en la última versión…», migrating and writing nothing (the schema stayed at
   9). Opening and closing it still let SQLite checkpoint the pending write-ahead log (committed
   transactions of 2026-10-21) into the main file, so the file's bytes changed; its contents did not.
   **Fixed** in `0ed2302`: the command now validates the file before touching the database and reads
   the schema version through a read-only connection, which never checkpoints; a test reproduces the
   case with a pending write-ahead log and checks the main file and the log byte for byte.
2. **The `-wal`/`-shm` copy of `just reset-db` was not exercised:** no sidecar existed at step 10
   (`scripts/scrub_candidates.py` runs first and removes them), so only the main file was backed up.
   **Covered** in `ec97762`: the copy moved into `Copy-DbWithSidecars`, and a test parses the script,
   defines only that function and `Resolve-DbPath`, and runs them on temporary files (the backup holds
   the `-wal` and `-shm` when they exist; the environment wins over `.env`; the default is
   `data/omnibot.db`).
3. `data/omnibot.db` was not changed by any step run with the variable set (same hash before and
   after steps 4 to 11).

## Result

Steps 1 to 8, 10 and 11 pass; step 9 (optional) was not run. Both findings are closed (1 fixed,
2 covered by an automated test); the review's minor findings were fixed in `ed0713c` and `fee6d92`.
