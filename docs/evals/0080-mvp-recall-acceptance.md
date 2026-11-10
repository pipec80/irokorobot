# 0080 — The memory MVP phrasings and the sides of the family: hardware acceptance

> **Status:** **accepted** on 2026-11-10 by Pipec (streaming route, laptop body), in two rounds
> (11:00-11:07 and, after three fixes, 11:44-11:46 local time). Code of
> [Plan 0080](../plans/completed/0080-mvp-recall-phrasings.md), branch `feat/0080-mvp-recall`; the
> earlier real-speech session is in [its own record](0080-mvp-recall-session.md). Pipec runs every
> case; the agent starts nothing. **Counts, outcomes and yes/no only:** no transcript, no reply, no
> name, no place and no household datum is written here. The only text quoted is a fixed phrase of
> the robot, as it stands in the code, and the questions Pipec asked in their canonical form.

## Setup

- `.env`: memory, conversation record, diary, `RECALL_ENABLED`, `PROFILE_CARD_ENABLED`, face and
  speaker authentication on; `LOG_CONVERSATION_TEXT=true` for the sittings only (console, never the
  log file), back to `false` afterwards; no console capture shared.
- Pipec's alta held parents with no recorded side and children with no side marker. The sides were
  recorded with `iroko-admin label-parent` and `label-child` (server stopped, the owner's PIN and
  `SI`), not by editing a file.
- **Streaming route only.** The classic route is not run on hardware: the robot uses streaming and
  both routes take the same controller decision, which the route tests cover. Same call as Plans
  0077 to 0079.
- How each case was confirmed: `logs/server.log` read with `scripts/mvp_session_report.py` (one row of
  closed values per turn: route, `recall.read` outcome, the `when` kind, the number of hits and the
  best distance) and the admin audit (rows with no name or value). None of them holds a text.

## Acceptance

| # | Case | Result |
|---|---|---|
| 1 | `label-parent` for the mother and for the father | **Pass**: both applied |
| 2 | `label-child` for the son | **Pass**: applied |
| 3 | `label-child` for the daughter | **Fixed**: refused with `role_conflict` because the child is also a care contact; `71945d3` lets a child who is a contact carry a side marker; applied on the second round |
| 4 | «¿Cuál es el nombre de mi mamá?» and «¿cómo se llama mi papá?» | **Pass**: one name each |
| 5 | «¿Cuál es el nombre de mi hijo?» | **Pass**: one name |
| 6 | «¿Cómo se llama mi hija?» | **Pass** on the second round, after case 3 (no marker could be applied before the fix) |
| 7 | «¿Cómo se llaman mis papás?» | **Pass**: both names |
| 8 | «¿Quiénes son mis hijos?» | **Pass**: the list |
| 9 | «¿Cuándo te conté de la playa?» (the story told the day before, in a new process) | **Pass**: `told`, found 2 (best distance 0.289), «Ayer me contaste esto: …», two sentences; the story survives a restart |
| 10 | «¿Cuándo fui a la playa?» | **Pass**: `happened`, found 3 (best 0.215), «No tengo registrado cuándo fue. Sí recuerdo que ayer…» |
| 11 | «Cuéntame cuándo fui a la playa» | **Pass**: `happened` (this phrasing missed the grammar in the session and was fixed in `360a31f`) |
| 12 | «¿Qué hice ayer?» | **Fixed**: found; first round an episode summary was quoted as the owner's words («me contaste esto»); after `fe3da94` it is quoted «Ayer hablamos de esto: …» (ADR 0031 decision 6). One misheard attempt on the first round, the repeat passed |
| 13 | «¿Qué hice la semana pasada?» | **Left**: speech-to-text heard a different verb twice; each slip is a valid sentence of its own (D-11) |
| 14 | A relatives question with the camera covered | **Pass**: the standard refusal |
| 15 | «¿Qué sabes de mí?» | **Fixed**: a taste appeared twice (one stored value was a comma list); after `b18c0d7` and `a2d8677` each taste is said once |
| 16 | Ctrl+C on the robot | **Pass**: a clean stop (`just` still prints its own exit line) |

Results: 12 pass, 3 fixed and re-run green (cases 3, 12 and 15), 1 left on a speech-to-text failure
(case 13).

## Found on hardware and fixed in this plan

| Finding | Fix |
|---|---|
| A turn longer than 30 s was refused by the server before Whisper and the robot logged it as «no speech» (session) | `6a68f0f`: the robot closes a turn at `MAX_UTTERANCE_S` = 28 s and logs a non-no-speech 422 apart; no server or wire change |
| A `happened` answer quoted a whole 28-second story (session) | `b2ec8a8`: at most two sentences, under 200 characters |
| «Cuéntame cuándo fui a la playa» was not a when question (session) | `360a31f`: request openers before «cuando» and a listed verb |
| The profile summary listed one taste twice (session and case 15) | `b18c0d7`, then `a2d8677` (a comma list is split before the comparison) |
| Ctrl+C while the robot spoke ended in a traceback (session) | `406cad7` |
| A daughter who is also a care contact could not carry a side marker (case 3) | `71945d3` |
| A diary summary was quoted as the owner's words (case 12) | `fe3da94` |
| The cognitive core imported the storage types of the sides; the seed schema was not regenerated after a docstring change (found by the full suite, not on hardware) | `8405b0e`, `d4b250e` |

## Not this plan

- **The prompt (step 4 of the path to the MVP).** Generic replies voice the owner's tastes as the
  robot's own or bring them into a greeting («¿aún te gusta …?»), and the word «Tuteo» was spoken
  once. Pipec's proposal for step 4 (2026-11-10): tastes only when relevant, not in the greeting; a
  greeting may pick up an open topic of the last one or two days («¿cómo te fue ayer en el cine?»
  after «mañana te cuento»). That needs remembering pending topics: a new design, not built.
- **Speech-to-text slips** (case 13 and one misheard «¿qué hice ayer?»): recorded and left (D-11);
  Plan 0069 owns the transcription, and the roadmap row *Spoken command vocabulary* is the systematic
  answer.
- **The date of the event** («¿cuándo fui…?» says the day it was told, never when it happened) and
  deletion by voice stay with ADR 0031 decision 5 and CM-6.
- **Replay** of a recording of the question stays measured, not defended (ADR 0029 decision 2).

## Checks

The CI selection (`MEMORY_ENABLED=false pytest -m "not slow and not hardware and not eval" -n auto`)
ran **6937** tests green at `d4b250e`, before the three acceptance fixes (baseline 6438 on `main`
before the plan); the count on the closing commit is in the PR. `pyright`, `mypy server/src
robot/src`, `ruff check .` and `ruff format --check .` are clean over the whole project, as is
`scripts/check_reserved_terms.py`.
