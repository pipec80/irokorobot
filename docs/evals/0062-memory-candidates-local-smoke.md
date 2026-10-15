# Memory candidates, local smoke (Plan 0062)

Outcomes only: no sentence, value, name or token is recorded here. This is **not** the hardware
acceptance of ADR 0021 (the offer, the answer and the cases of its *Acceptance* section are
Plan 0063). It proves, on the real database and the real start-up path, what the tests prove on
temporary ones.

- date: 2026-10-15
- code: branch `feat/0062-cm3a-candidates-and-writer` at `0539f2d` (14 task commits, 4
  review-fix commits and the closing docs commit)
- database: the real `data/omnibot.db` at schema version 8 before the run (backed up with the
  SQLite backup API first), migrated by the server itself
- chat model: `qwen2.5:3b`; Ollama started by the lead, server started by the lead with
  `just run-server` and stopped after each step

| # | Step | Expected | Outcome |
|---:|---|---|---|
| 1 | `just gate` | green | **pass**: 2972 tests (2955 under the CI selection; baseline 2597), pyright 0 errors, mypy 115 files, pip-audit clean |
| 2 | Start-up with `MEMORY_CANDIDATES_ENABLED=false` (the default) | migration 9 applied, `Candidates voided at start-up: 0`, ONLINE | **pass**: migration 9 applied over the version-8 database, the line appeared with `0`, server ONLINE |
| 3 | Start-up with `MEMORY_CANDIDATES_ENABLED=true` | ONLINE, nothing voided | **pass**: ONLINE; the server logs `Candidates reconciled at start-up: 0 expired` (a line the plan text did not predict; it is information, not a void) |
| 4 | A matching sentence with the owner's face in frame, voice not enrolled | normal reply, `Candidate proposal: dropped (strong_unreachable)`, `SELECT COUNT(*) FROM memory_candidates` is 0 | **pass**: normal reply, the proposal was scheduled for the face-identified speaker, the voice verdict was `unknown` and the log read `Candidate proposal: dropped (strong_unreachable)`; the table holds 0 rows |
| 5 | A non-matching sentence | `dropped (gate_no_match)`, no voice check, no model call | **pass**: `Candidate proposal: dropped (gate_no_match)`; no voice check, no model call |
| 6 | Voice enrolled, the stored case | `stored=1`, one `proposed` row | **pass** (2026-10-15, after enrolling the voice with 3 references): the voice check returned `verified` in the background, `Candidate insert: inserted`, `Candidate proposal: stored=1 dropped=0`, one `proposed` row (`likes`, channel `voice_stream`). Voice check to insert: about 66 s on the shared laptop, with the chat model resident and the extraction model loading |
| 7 | Void the live candidate before a backup | `Voided 1 live candidate(s)`, exit 0 | **pass**, with the scrub script alone (`scripts/scrub_candidates.py`, server stopped): `Voided 1 live candidate(s)`, exit code 0. Before it the value was in the write-ahead log (1 occurrence) and not yet in the main file; after it the log was gone and the row read `expired` with no value and no key. `just reset-db` itself was **not** run on the real database: it backs up and then deletes the file, which would have removed the enrolments |

## Notes

- Observations for the Plan 0063 acceptance: (a) a sentence with a filler, «la verdad **es que** me
  gusta el mate», is refused by the gate (`not_a_taste`) because `es que` is not a known lead-in;
  «la verdad me gusta el mate» passes. (b) The request log line of a stream turn reports the
  total of the background proposal too (87 s here), while the robot got its answer in 20 s and
  went back to listening: a measurement must not read that line as the user's latency. (c) The
  first chat turn after a cold start took 78 s of model time, the next ones 3-19 s.

- The switch is read from the app's own settings object at start-up; the run used the process
  environment (`MEMORY_CANDIDATES_ENABLED=true`) so `.env` stayed untouched.
- The real database now carries the empty `memory_candidates` table (schema version 9). The 14
  backups already in `data/backups` predate it and hold no candidate table.
- Not measured here, and owned by the Plan 0063 acceptance: how many of Pipec's real sentences the
  closed grammar keeps, the extraction duration of the real model on the shared laptop (about
  41 s per call in the CM-0 benchmark) and the voice check under room noise.
