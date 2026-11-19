# Plan 0087 — hardware acceptance of the export (2026-11-19)

Outcomes and counts only; no value, no name of the household. Laptop server, streaming route,
memory, record and recall on. Backup `pre-0087` made and proven before the merge (integrity ok,
schema 21); `main` at `7a2a44b` (PR #294).

| # | Step | Outcome |
|---|---|---|
| — | Server start | Migration 022 applied, schema 22, no error in `logs/server.log`; `health` sana |
| 1 | The canary sentence (one long sentence) | Heard whole, an ordinary reply |
| 2 | `export all` (PIN, `SI`) | 20 count lines, both files in `data/exports/<instante>-todo/` |
| 3 | The JSON | Counts equal to the printed ones; no key `salt`, `verifier`, `embedding`, `vector`, `parameters_json`; no bytes; `borrados` equal to the 16 register lines; glossary present |
| 4 | The Markdown read by the owner | Opened |
| 5 | `export person 1` and `export person 2` | Both written; every fact's subject is the person; turn verdicts only `verified` / `not_verified`; the owner's export left out 13 other-voice turns and 6 facts of other subjects |
| 6 | `export person --name` the canary, then `forget person --dry-run` | 2 turns (step 1's and an earlier one), 1 unit, 2 records: equal to the forget counts; the forget's «2 resúmenes» counts records, one had no episode yet (the export showed the 1 that exists) |
| 7 | `--out data` and `--out` step 2's folder | Refused (`place`): «base de datos» and «ya tiene algo adentro»; nothing written |
| 8 | Wrong PIN three times | Refused, no count shown |
| 9 | `audit` | One `export` / `household_data` row per attempt: 5 applied, 2 `place`, 1 `pin`; no value |
| 10 | `forget person --name` the canary, exports deleted, `health`, backup `post-0087` | 3 rows deleted; `data/exports/` deleted; health sana; `post-0087` proven (integrity ok, schema 22) |

Found on hardware and fixed: after a dry run or an expected refusal `just admin` added «error:
recipe `admin` failed», which reads like a fault; the recipe line now carries just's `-` prefix
(the command's own exit code is unchanged when run directly).

Result: **pass**, accepted by Pipec on 2026-11-19; the `pre-0087` backup was deleted that day.
