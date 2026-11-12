# 0083 — When a told event happened: hardware acceptance

> **Status:** **accepted** on 2026-11-12 by Pipec (streaming route, laptop body), in three sittings
> the same afternoon. Code of [Plan 0083](../plans/completed/0083-spoken-time-and-when-it-happened.md),
> branch `feat/0083-when-it-happened`. Pipec runs every case; the agent starts nothing. **Counts,
> outcomes and yes/no only:** the stories were invented for the test (no household datum), and the
> only text quoted is the robot's fixed wording as it stands in the code.

## Setup

- `.env`: memory on, `CONVERSATION_RECORD_ENABLED=true`, `CONVERSATION_EPISODES_ENABLED=true`,
  `RECALL_ENABLED=true`, **`OCCURRED_TIME_ENABLED=true`**, face and voice authentication on,
  `HOUSEHOLD_TIMEZONE=America/Santiago`, `LOG_CONVERSATION_TEXT=true` (console only).
- A backup of the real database was taken with the server stopped (`user_version` 14, hash
  checked); the server then applied migration 015 on start (`user_version` 15).
- **Streaming route only**, as in Plans 0077 to 0082: both routes take the same controller decision
  and `tests/integration/test_occurred_routes.py` runs the cases on `/transcribe` and
  `/transcribe/stream`.
- How to tell what happened: the server's `conversation.capture` line (verdict and `occurred`, a
  yes/no) and `recall.read` line (outcome, hits, `windowed`, `when`, `occurred_first`), never a
  text or a date.

## Acceptance (second and third sittings, after the fixes of the first)

| # | Case | Result |
|---|---|---|
| 1 | A story with an ambiguous day and a past verb («el sábado fui…») | **Pass**: `verified`, `occurred=true` |
| 2 | A story with «el año pasado» | **Pass**: `verified`, `occurred=true` |
| 3 | A story with no time | **Pass**: `verified`, `occurred=false` |
| 4 | A story with two time phrases («ayer… y mañana…») | **Pass**: `verified`, `occurred=false` |
| 5 | A story with «hace tres días» (added from the first sitting) | **Pass**: `verified`, `occurred=true` |
| 6 | «¿Cuándo fui…?» about case 1 | **Pass**: «Fue el sábado 7 de noviembre. Hoy me contaste esto: …», `occurred_first=true` |
| 7 | The usted form «¿Se acuerda cuándo fui…?» about case 2 | **Pass**: «Fue en 2025. Hoy me contaste esto: …», `occurred_first=true` |
| 8 | «¿Cuándo fui…?» about case 3 | **Pass** (third sitting): «No tengo registrado cuándo fue. Sí recuerdo que hoy me contaste esto: …» |
| 9 | «¿Qué hice hoy?» | **Pass**: case 4's story; none of the stories that happened on another day (D-15 on hardware) |
| 10 | «¿Qué hice el año pasado?» | **Pass**: case 2's story (one speech-to-text slip on the first try, «¿Qué es…?», answered by the model as ordinary conversation) |
| 11 | «¿Qué hice hace tres días?» | **Pass** after a fix (third sitting): case 5's story; in the second sitting that day's diary entry hid it (*Found on hardware*) |
| 12 | «¿Tiene registrado cuándo fui…?» (Whisper's «tiene», usted) about case 4 | **Pass**: the told-day answer, `occurred_first=false` |
| 13 | «¿Cuándo fue eso?» (a short question with no topic) | **Pass**: ordinary conversation, no `recall.read` line |

The voice verified 5 of 5 stories in the second sitting (sentences over three seconds) and 3 of 7
in the first.

## Found on hardware, and fixed in this plan

- **The when-answer did not name its event** (first sitting). A story hidden by the rule below left
  the search a similar one (a vector hit under `RECALL_MAX_DISTANCE`), and «Fue el sábado 7 de
  noviembre. Me lo contaste hoy.» sounded right for the wrong event. Pipec's call: the answer quotes
  the memory, as the told-day answer does (`019b7e6`).
- **The relative forms an ordinary speaker uses** (Pipec, from the first sitting): «hace N días /
  semanas / meses / años», «en N días (más)», «dentro de N días» and «… del año pasado» joined the
  one reader (`9dc8ebf`); «el 3 de noviembre del año pasado» had read the current year.
- **A story dated in a window was hidden by that day's diary** (second sitting, case 11): a
  date-only question read the window's episodes first and its turns only when there were none. A
  turn whose occurred interval falls in the window but was told on another day is held by no
  episode of the window; it now comes first, beside them (`12f8a3f`).
- **One flaky test** of Plan 0082 (`test_no_value_reaches_a_log_line` read a log record's own time
  in milliseconds) failed once in the full suite; it now reads the message and the extra fields
  only (`c6e009d`).

## Known limits, not changed

- **A health word in a conversation hides its stories** (first sitting): the diary marks the whole
  conversation `medical` and raises every turn unit of its record to that level (Plan 0078), and
  recall reads `normal` only. The story about the snow, told beside «fui al médico», was not found
  until it was told again in another conversation.
- **Units written before migration 015 keep only the day they were told** (D-8, no backfill): an
  older story about the beach answered the told day.

## Not run

- Case 14 (the switch off): Pipec keeps the switch on, and the switch-off byte-identity is pinned
  by the route tests on both voice routes (`test_with_the_switch_off_every_route_is_byte_identical`).
- The classic route on hardware (the route tests cover it).
