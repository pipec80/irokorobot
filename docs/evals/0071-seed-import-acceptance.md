# Plan 0071 — acceptance of the seed importer (pending)

> **Status:** pending Pipec's run. Prepared 2026-10-26 with the execution of
> [Plan 0071](../plans/open/0071-seed-load-file-importer.md). Record **outcomes only** (an exit
> code, a count, «unchanged», «refused»): never a name, a phone, a value or the file's content.

## Procedure (on a database kept apart)

Run every step from the repository root in PowerShell, with the server stopped unless a step says
otherwise. `<scratch>` is a file under `data/` (gitignored), for example `data/scratch-0071.db`.

| # | Step | Expected | Outcome |
|---|---|---|---|
| 1 | `$env:BRAIN_DB_PATH = "<scratch>"` | — | |
| 2 | `just setup-personal` with the owner and a PIN, **no children** | `personal_security_ready=True` | |
| 3 | Copy `docs/examples/seed-household.example.toml` to `data/seed/` and set `[owner] name` to the owner's name of step 2 (invented data are fine) | — | |
| 4 | `just seed-import data/seed/<file>.toml` | First line is the scratch database; a report; «0 problemas»; exit 0; nothing written | |
| 5 | `just seed-import data/seed/<file>.toml --apply --interviewer <label> --role builder --mode builder_is_owner --disk-encryption yes`, answer `SI` | The review question, then «Carga aplicada (acta 1).» | |
| 6 | The same command again, answer `SI` | Every operation «sin cambios»; the acta reused | |
| 7 | Change one birth date in the file; dry run without `--replace` | A `value_conflict`, «no se escribió nada», exit 1 | |
| 8 | The same with `--replace` (dry run, then `--apply` and `SI`) | Applied; the new date replaces the old one | |
| 9 | Start the server (`just run-server`) and ask Iroko how many children the owner has | The count of the file's children | |
| 10 | Stop the server; `just reset-db` with `BRAIN_DB_PATH` still set | It prints the scratch path, backs it up and deletes **only** the scratch file; `data/omnibot.db` untouched | |
| 11 | `Remove-Item Env:BRAIN_DB_PATH`, destroy the scratch backup and `data/seed/<file>.toml` | — | |

Everything else the file holds cannot be asked by voice until CM-5 (only the children's list and
count are served today); that is expected, not a failure.

## Known gap to check by hand

The `-wal` and `-shm` copy of `just reset-db` could not be exercised during the execution:
`scripts/scrub_candidates.py` runs first and removes the sidecars, so a sidecar survives only while
another process holds the database, which the scrub refuses. Step 10 records whether a sidecar was
present.

## Result

Pending.
