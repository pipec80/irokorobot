# Plan 0072 — acceptance record: the commissioning session (outcomes only)

> **What this is.** The record of the rehearsal of the alta that closed
> [Plan 0072](../plans/completed/0072-commissioning-session.md) (2026-10-27). It holds counts and outcomes,
> never a household value, a name, a phone, a PIN or an installation id. Run by Pipec on his own
> machine, with the real camera, microphone and server, against the throwaway owner `Canary Owner` and
> the example seed file (`docs/examples/seed-household.example.toml`).

## How it ran

- Branch `feat/0072-commissioning-session`, code of Tasks 1 to 7 plus the fixes below.
- The rehearsal used the configured database path (`data/omnibot.db`), reset first with a backup
  (`just reset-db`). It did **not** use a scratch file, so that database is now a closed canary
  commissioning, so Pipec's real alta started with another `just reset-db` (below).
- `.env`: `FACE_AUTHENTICATION_ENABLED=true`, `SPEAKER_AUTHENTICATION_ENABLED=true`,
  `MEMORY_CANDIDATES_ENABLED=false`.

## Outcomes by step

| # | Step | Server | Result |
|---|---|---|---|
| 1 | `just reset-db` | off | passed; a backup of the earlier database was written |
| 2 | `just setup-personal` | off | passed (owner ready, no children) |
| 3 | `just commission`, face | on | 4 of 5 frames enrolled; the fifth was skipped because the PIN was left empty (the unlock answered 422 and the command aborted: fixed, see below) |
| 3 | `just commission`, voice | on | 3 of 3 references enrolled; the second run enrolled only the voice (the face was not repeated) |
| 4 | `just seed-import` (dry run, then `--apply`) | off | dry run 43 to write, 0 problems; applied (record 1) |
| 5 | verification turn | on | the children's count answered correctly by the deterministic tool; the owner identified by face (`face_only`); speaker verdict `unknown` on a 2.1 s clip |
| 6 | second dry run | off | 0 to write, 43 unchanged |
| 7 | baseline copy of the database | off | done (no `-wal` or `-shm` beside the file) |
| 8 | `just commission`, closing | off | backups, consents, readiness and acta written; the window closed |
| 9 | after the closing | off | `just seed-import` refused («el alta ya se cerró»), `just commission` reported the alta closed |

## The acta

Read after the closing. It holds the installation id, the date, the interviewer's label and role, the
confirmation mode, the disk declaration, the pool version, the file hash, the notice version, the three
consents and the destination label, the modalities (`face`, `pin`, `voice`, derived from the database),
the counts (`contacts` 2, `entities` 7, `literals` 27, `relations` 7, `written` 43), both backups with
their destruction date, the eleven section statuses and the readiness verdict of each of the six
capabilities. It holds **no household value**: no name, phone, address, medication or taste.

The readiness came out `ready` for all six capabilities because every hardware question was answered
yes, including «verified» for the voice (the verification turn gave `unknown`) and «configured» for
remembering a taste (`MEMORY_CANDIDATES_ENABLED=false`). The hardware side of the report is attested by a
person (ADR 0024 decision 14); the rehearsal answered it without checking.

## Defects found live and fixed, each with a failing test first

| Commit | Defect |
|---|---|
| `56a9af9` | the camera captured the instant the PIN was entered, the microphone recorded with no warning, the enrol step repeated a modality already done, the closing recorded no pre-reset backup and had no test, a wrong server state escaped as a traceback |
| `135d25d` | an empty or wrong PIN aborted the whole command; the recording was not announced; a refused enrolment showed only a status code |
| `df5e923` | the closing's three backup questions gave no example and an empty answer aborted |
| `d61c617` | a backup typed by its file name was stored without its folder |

## The real alta (Pipec, 2026-10-27, outcomes only)

Run the same day after the merge, from `main` with the `pre-step0` tag in place: `just reset-db` (with a
backup), `just setup-personal` with **no children** and his own PIN, his own seed file under `data/seed/`,
then the same steps. Counts and outcomes only; the file held his household data and was destroyed after the
closing.

| Step | Result |
|---|---|
| face session | 5 of 5 frames |
| voice session | 3 of 3 references |
| seed load | dry run 43 to write, 0 problems; applied (record 1) |
| verification turn | the children's count and list answered by the deterministic tools; speaker verdict `verified` and fusion `face_and_voice` on two clips of about 2 s |
| second dry run | 0 to write, 43 unchanged |
| baseline copy | made with the server stopped; its hash equals the database's |
| closing | acta written; modalities `face`, `pin`, `voice`; disk encryption declared `no` (BitLocker is in fact active on `C:`, seen afterwards in the control panel; the closed record keeps the wrong declaration); readiness: voice ready, remembering a taste and describing a scene blocked by hardware |
| after the closing | `seed-import` refused and `commission` reported it closed |

Two things cost a re-run and are kept here: `setup-personal` goes **without children** (the importer never
adopts an existing person, `entity_exists`), and a section status such as `allergies = "none"` goes under
`[status]`, not under `[owner]`. The acta kept three cosmetic slips from the closing prompts (an empty
pre-reset backup, two files typed on one line of the baseline backup, and «si» as the destination label); a
closed record cannot be edited and the information is still there.

## What this does not show

- Whether the household data in the real alta is complete or right: this record holds counts only.
- The voice verdict on a clip shorter than a few seconds is the known limit measured in Plans 0066 to
  0068; this rehearsal neither widens nor narrows it.
- The fifth face frame was not enrolled (`just face-auth-demo` adds frames); a face counts as enrolled
  once one frame was accepted.
- Camera device and microphone device were the system defaults.
