# Memory candidates, local smoke (Plan 0062)

Outcomes only: no sentence, value, name or token is recorded here. This is **not** the hardware
acceptance of ADR 0021 (the offer, the answer and the cases of its *Acceptance* section are
Plan 0063). It proves, on the real database and the real start-up path, what the tests prove on
temporary ones.

- date: 2026-10-15
- code: branch `feat/0062-cm3a-candidates-and-writer` at `1d65c01` (14 task commits and 4
  review-fix commits)
- database: the real `data/omnibot.db` at schema version 8 before the run (backed up with the
  SQLite backup API first), migrated by the server itself
- chat model: `qwen2.5:3b`; Ollama started by the lead, server started by the lead with
  `just run-server` and stopped after each step

| # | Step | Expected | Outcome |
|---:|---|---|---|
| 1 | `just gate` | green | **pass**: 2972 tests (2955 under the CI selection; baseline 2597), pyright 0 errors, mypy 115 files, pip-audit clean |
| 2 | Start-up with `MEMORY_CANDIDATES_ENABLED=false` (the default) | migration 9 applied, `Candidates voided at start-up: 0`, ONLINE | **pass**: migration 9 applied over the version-8 database, the line appeared with `0`, server ONLINE |
| 3 | Start-up with `MEMORY_CANDIDATES_ENABLED=true` | ONLINE, nothing voided | **pass**: ONLINE; the server logs `Candidates reconciled at start-up: 0 expired` (a line the plan text did not predict; it is information, not a void) |
| 4 | A matching sentence with the owner's face in frame, voice not enrolled | normal reply, `Candidate proposal: dropped (strong_unreachable)`, `SELECT COUNT(*) FROM memory_candidates` is 0 | PENDING |
| 5 | A non-matching sentence | `dropped (gate_no_match)`, no voice check, no model call | PENDING |
| 6 | Voice enrolled, the stored case | `stored=1`, one `proposed` row | not run (optional; the voice is not enrolled; belongs to the Plan 0063 acceptance) |
| 7 | `just reset-db` with a live candidate | `Voided 1 live candidate(s)`, then the backup | not run (needs step 6) |

## Notes

- The switch is read from the app's own settings object at start-up; the run used the process
  environment (`MEMORY_CANDIDATES_ENABLED=true`) so `.env` stayed untouched.
- The real database now carries the empty `memory_candidates` table (schema version 9). The 14
  backups already in `data/backups` predate it and hold no candidate table.
- Not measured here, and owned by the Plan 0063 acceptance: how many of Pipec's real sentences the
  closed grammar keeps, the extraction duration of the real model on the shared laptop (about
  41 s per call in the CM-0 benchmark) and the voice check under room noise.
