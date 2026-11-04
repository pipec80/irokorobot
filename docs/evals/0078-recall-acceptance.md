# 0078 — Recall what the owner told: calibration and hardware acceptance

> **Status:** **accepted** on 2026-11-04 by Pipec (calibration on 2026-11-03, acceptance rounds on
> 2026-11-03 and 2026-11-04, streaming route). Code of
> [Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md), branch `feat/0078-recall`.
> Pipec runs every case; the agent starts nothing. **Counts, distances and yes/no only:** no
> transcript, no reply, no name and no household datum is written here.

## Setup

- `.env`: memory on, face and speaker authentication on, conversation record on (consent granted by
  Pipec before the first run), diary on, `RECALL_ENABLED=true`,
  `EMBEDDING_MODEL=granite-embedding:278m`, `HOUSEHOLD_TIMEZONE=America/Santiago`,
  `LOG_CONVERSATION_TEXT=true` (console only; a recall answer prints `[recuerdo leído]` and a
  relatives answer `[parientes leídos]`).
- Migration 014 rehearsed on a copy, then applied to the live database (13 → 14, integrity ok, row
  counts kept). Backups taken before the migration and before each deletion below.
- The owner's face (5 samples) and voice (3 samples) enrolled at the alta (Plan 0072).
- **Streaming route only.** The classic route is not run on hardware (Pipec, 2026-11-04): the robot
  uses streaming, and both routes take the same controller decision; `tests/integration/test_recall_routes.py`
  runs every recall case on `/transcribe` and `/transcribe/stream`. Same call as Plan 0077.
- How to tell who answered: the server's `Recall:` line gives the outcome, the cue strength and the
  hit count; `Turn decision` gives `need=recall` or `need=relatives_names` and `source=deterministic`.

## Calibration (Task 12 step 1, 2026-11-03)

Pipec told stories for a day, then asked his own questions. Read from the logged `recall.read`
lines (route, outcome, hits, `best_distance`), never a text.

| Question kind | Outcome | Best distance |
|---|---|---|
| Strong, about a topic told (two questions) | found, 2 hits | 0.395, 0.414 |
| Strong, about a topic never told | nothing | 0.469, 0.480, 0.517 |
| Weak (general knowledge) | nothing, converses | 0.472, 0.513 |
| Strong with a day and nothing that day | nothing | none (no vector compared) |

**`RECALL_MAX_DISTANCE = 0.43`** (Pipec, 2026-11-03): between the true hits (≤ 0.414) and the
misses (≥ 0.469). The plan's starting value 0.30 would have dropped both true hits to words only.
The data are thin (two true points): revisit with use (ADR 0028 *Review*).

## Acceptance (Task 12 step 2)

| # | Case | Result |
|---|---|---|
| 1 | A strong cue that finds | **Pass** (2026-11-04): found, strong, 3 hits. The 3B model kept the owner's first person in one verb; fixed in `84bcf1b` (an answer that speaks as the owner gets the template) |
| 2 | A strong cue that does not find | **Pass**: «No me acuerdo de eso.» (twice, 2026-11-03 and 2026-11-04) |
| 3 | «¿Te acuerdas de Mozart?» | **Pass**: weak cue, nothing found, ordinary conversation |
| 4 | The sushi story with «mis hijos» | **Pass**: ordinary conversation; the voice verified and the turn became a unit |
| 5 | «¿Qué te conté ayer?» | **Pass**: a date-only question read that day's two summaries (decision 6.6) |
| 6 | Without the owner's face | **Pass**: no evidence, the refusal phrase, nothing read |
| 7 | «¿Cómo se llaman mis papás?» | **Pass** (twice): deterministic, both parents by design (decision 9) |
| 8 | A protected sentence said earlier | **Pass**: a story the word classifier marked `location` (an address word) was not said; the answer came from a `normal` story of the same place. A `medical` turn of the calibration day was never read either |
| 9 | Ollama's embedding model absent | **Pass**: searched by words only, the template answered, found |

All nine cases pass. Voice verified on 3 of 9 owner turns in the 2026-11-04 round, every one a clip
of 2.9 s or more; recall questions of 1.6–2.6 s stayed `unknown`, as Plan 0075 measured, and were
answered on the face alone (decision 5).

## Found on hardware and fixed in this plan

| Finding | Fix | Amends |
|---|---|---|
| The owner's own recall questions became units and were read back as «me contaste…» | `1d01f00`: only a turn that resolves to ordinary conversation becomes a unit | ADR 0028 decision 1 |
| The diary marked ordinary family life `private`, so nothing told was readable | `80260be`: the diary prompt names daily life as `normal` and lists what is private | ADR 0028 decision 3 |
| «hoy día» was searched as a topic | `6ee72cb` | — |
| The wording model wrote «No me acuerdo de eso.» 12 of 12 times with two hits in front of it | `b56741a`: the recall prompt has no such exit; a fixed phrase that still comes back gets the template | ADR 0028 decision 8 |
| A diary summary of a conversation made only of questions became a unit | `55122a2`: such a summary is no memory | ADR 0028 decision 3 |
| Whisper heard «se conté» and «se llama a mis», so the cue was missed | `6dc3cfa`: two known slips tolerated | ADR 0028 decision 4 |
| The 3B model answered in the owner's first person and repeated a «hoy» of another day | `84bcf1b`: the prompt asks for tú and the labelled day; such an answer gets the template | ADR 0028 decision 8 |

Units stored by the server before these fixes were deleted from the live database with Pipec's OK
(backups first): four question units and one summary on 2026-11-03, one question unit and one
summary on 2026-11-04. The diary rows stay; only their units went.

## Observations (outside this plan; follow-ups in the roadmap)

- **The profile card opens a cold greeting.** On «hola» with no history, the 3B model brought up a
  stored taste and claimed to have observed it, although the card says to use it only when relevant.
- **The generic prompt leaks into replies** (a reply opened with the word of the language rule and
  the card's quoted name), and the `usted` form fights the language rule.
- **Ollama down is silent.** One round started with Ollama stopped: `/health` passed and the robot
  spoke the warm-up phrase.
- **Whisper's hallucination filter discarded a 21.6 s story**, and the shared laptop GPU made two
  turns slow (24–60 s) while Whisper, the chat model, candidate extraction and the embeddings
  competed. The diary job cannot be interrupted once it starts summarizing.
- **Names in the registry are lowercase** (seed data), so the relatives template says them lowercase.
- **The local suite downloads Whisper medium** in `tests/slow/test_stt_transcription.py` when the
  cache is empty, although the `slow` marker promises a skip.

## Checks

`MEMORY_ENABLED=false just gate`, `pyright`, `mypy server/src robot/src`, `ruff check .`,
`ruff format --check .`, `ruff check scripts/*.py` and `scripts/check_reserved_terms.py` all pass
on the closing commit (2026-11-04): the gate ran 5993 tests, all passed (baseline 5623 on `main`).
