# 0080 — The MVP phrase session (Task 0), outcomes only

> **Status:** run by Pipec on 2026-11-09 in two sittings (18:16-18:27 and 21:13-21:24, local
> time), streaming route, on the branch `feat/0080-mvp-recall` (the new grammar, not `main`).
> **Counts, routes and yes/no only:** no transcript, no reply, no name, no place and no household
> datum is written here. Pipec's sheet with the heard text stays local and untracked.

## Setup

- `.env`: memory, conversation record, diary, `RECALL_ENABLED`, face and speaker authentication
  on; `LOG_CONVERSATION_TEXT=true` for the sittings only, back to `false` afterwards.
- Stories told first (more than 4 s each); one about a beach outing, told in the second sitting.
- Routes read from `logs/server.log` with `scripts/mvp_session_report.py`.
- Pipec's alta at the time held unlabelled parents (`has_parent`) and children with no side marker:
  the expected answer to «mi mamá» / «mi hija» was the honest fallback of D-5.

## Results by question family

| Family | Said | Route as expected | Notes |
|---|---:|---:|---|
| Children list («¿quiénes son…?», «¿cómo se llaman mis hijos?») | 2 | 2 | `own_children_list` |
| One child («¿cómo se llama mi hija?», «¿cuál es el nombre de mi hijo?») | 2 | 2 | `relatives_names`, the fallback while unmarked |
| Parents («el nombre de mi papá/mamá», «cómo se llama mi papá», «mis papás», «dime el nombre de mi mamá») | 5 | 5 | one said with the face out of view got the standard refusal, which is correct; the others the fallback or the whole list |
| Days («¿qué hice ayer / la semana pasada / el sábado?») | 4 | 2 | «ayer» twice: nothing that day, «No me acuerdo de eso.» (correct); the other two were STT failures |
| «¿Cuándo fui / estuve …?» | 2 | 2 | `recall`, strong, `happened`, found (best distance 0.215 and 0.245); the answer said the date was not recorded and quoted the told day |
| «¿Cuándo hablamos / te conté …?» | 1 | 0 | STT failure (the «cuándo» was lost); the `told` answer was not exercised on hardware: the acceptance covers it |
| General knowledge («¿cuándo fue el mundial…?») | 1 | 1 | ordinary conversation |
| Sensitive and profile («¿cuándo nació mi hijo?», «¿qué sabes de mí?») | 2 | 2 | `sensitive_read`, `profile_summary` |
| Measured phrasings («cuéntame cuándo fui…») | 1 | 0 | intention: not a cue at the time; the model asked for more and did not invent |

## Failures by stage

| Stage | Count | Shapes (canary form) | Disposition |
|---|---:|---|---|
| STT | 3 | «¿Qué hice la semana pasada?» heard as «Y hasta la semana pasada.»; «¿Qué hice el sábado?» heard as «¿Qué dice el sábado?»; «¿Cuándo hablamos de la playa?» heard as «Hablamos de la playa.» | left: each slip is a valid sentence of its own, so a tolerance would catch other speech (D-11); Plan 0069 owns STT |
| Intention | 1 | «Cuéntame cuando fui a la playa.» (no accent, no question mark) | fixed: request openers before «cuando» + a listed verb (`360a31f`) |
| Retrieval | 0 | — | — |
| Generation | 1 | the `happened` answer quoted a whole 28-second story | fixed: at most two sentences, under 200 characters (`b2ec8a8`) |

## Other findings of the session, all fixed in this plan

| Finding | Fix |
|---|---|
| A story longer than 30 s was refused by the server before Whisper (HTTP 422) and the robot logged it as «no speech» | the robot closes a turn at `MAX_UTTERANCE_S` = 28 s and logs a non-no-speech 422 apart (`6a68f0f`); seen working in the second sitting |
| The profile summary listed one taste twice (with and without an article) | one taste per comparison key (`b18c0d7`) |
| Ctrl+C while the robot spoke ended in a traceback | clean stop (`406cad7`) |
| A generic reply spoke the word «Tuteo» (the prompt shows through) on a turn without face evidence | not this plan: step 4 of the path to the MVP (the prompt) |

## Canonical phrases (seed of the spoken-command row of the roadmap)

| Question | Worked as said | Did not |
|---|---|---|
| Children | «¿Quiénes son mis hijos?», «¿Cómo se llaman mis hijos?» | — |
| One child | «¿Cómo se llama mi hija?», «¿Cuál es el nombre de mi hijo?» | — |
| A parent | «¿Cuál es el nombre de mi mamá?», «Dime el nombre de mi mamá», «¿Cómo se llama mi papá?» | — |
| Both parents | «¿Cómo se llaman mis papás?» | — |
| A day | «¿Qué hice ayer?» | «¿Qué hice la semana pasada?», «¿Qué hice el sábado?» (STT) |
| When it happened | «¿Cuándo fui a la playa?», «¿Cuándo estuve en la playa?» | «Cuéntame cuándo fui…» (fixed after the session) |
| When it was told | — | «¿Cuándo hablamos de …?» (STT) |
