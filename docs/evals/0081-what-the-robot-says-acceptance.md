# 0081 — What the robot says: hardware acceptance

> **Status:** **accepted** on 2026-11-11 by Pipec (streaming route, laptop body, `qwen2.5:3b`), in
> two sittings (14:57-15:02 and 15:10-15:12 local time). Code of
> [Plan 0081](../plans/completed/0081-what-the-robot-says.md), local branch
> `feat/0081-what-the-robot-says` (GitHub on stand-by that day). Pipec runs every case; the agent
> starts nothing. **Counts, outcomes and yes/no only:** no transcript, no reply, no name and no
> household datum is written here; the questions are quoted in their canonical form.

## Setup

- `.env`: memory, profile card, conversation record, recall and sensitive read on, face and speaker
  authentication on; `LOG_CONVERSATION_TEXT=true` for the sittings only (console, never the log
  file), back to `false` afterwards; no console capture shared.
- The owner's card held a preferred name, the `tu` form, five `likes` and one `dislikes` (counted,
  not read). For case 6 the form was set to `usted` with `iroko-admin change address_form`
  (server stopped, `SI`) and set back to `tu` the same way after the sitting. A copy of the database
  was taken first.
- Every phrase was first resolved by the plan's Task 0 script (all generic conversation except
  «¿qué sabes de mí?»). Each case was confirmed in `logs/server.log` by its closed values:
  `card.prompt` (`tastes` and `address_form`), `turn.actor`, `turn.decision`, `turn.memory`.

## Acceptance

| # | Case | Log | Result |
|---|---|---|---|
| 1 | A greeting with the owner's face and an empty session | `tastes=withheld`, history 0 | **Pass**, 1 of 1: no taste in the reply |
| 2a | «¿qué me recomiendas comer hoy?» | `tastes=included` | No taste used (two food tastes in the card). Allowed: the card is offered, never imposed |
| 2b | «¿qué música me gusta?» | `tastes=included` | **Pass**: no music taste in the card; the reply said it did not know and invented none |
| 3 | «¿y a ti qué música te gusta?», one turn after the owner told his music tastes | `tastes=included` | **Fail**: the reply took the tastes the owner had just said in the conversation as the robot's own. The source is the session history, not the card's lines |
| 4a | No face (camera covered), a greeting | actor `unknown`, no `card.prompt`, memory skipped | **Pass** |
| 4b | No face, «¿qué me gusta comer?» | actor `unknown`, no `card.prompt` | **Partial**: no owner value invented (no card was read), but the model took «me» as itself instead of saying it did not know |
| 4c | No face, «¿quién soy yo?» | `active_identity`, deterministic | **Pass**: the fixed reply |
| 5 | «tuteo» heard in a reply | — | **Pass**: 0 of 13 turns |
| 6 | The `usted` form, three ordinary turns (two of the five planned phrases not said) | `address_form=usted` ×3 | **Gate not met, D-8 applies**: coherent 3 of 3 (the incoherence of Plan 0074, 2 of 2, is gone), but in `usted` 0 of 3 |
| 7 | «¿qué sabes de mí?» | `profile_summary`, deterministic | **Pass**: the fixed summary, which states the `usted` form |

## What closed, and what stays a limit of the 3B model

- **Closed by the code:** the greeting never carries a taste (a deterministic gate, logged on every
  card read); the word of the old language rule no longer reaches the replies; the card no longer
  holds a line that fights the language rule, which made `usted` coherent.
- **Limits of `qwen2.5:3b`, recorded for the model evaluation (P4.1), not patched** (Pipec,
  2026-11-11: the plan fixes our code and prompt, not the model's output): it mirrors what the owner
  just said as its own taste (case 3); it ignores the `usted` register although the rule asks for it
  (case 6, D-8); it reads «¿qué me gusta…?» as a question about itself when it has no card (4b). It
  also stated a wrong time to «¿qué hora es?» (the prompt holds no clock): the model's own answers,
  outside this plan.
- Two observations only, not gates: a turn took 97 s in the model (the shared laptop); the robot
  answered «¿recuerdas cómo te llamas?» with its own name.

## Checks

The CI selection (`MEMORY_ENABLED=false pytest -m "not slow and not hardware and not eval" -n auto`)
ran **7005** tests green at `aa59f51` (baseline 6957 at `bba6d28`); `pyright`, `mypy server/src
robot/src`, `ruff check .`, `ruff format --check .` and `scripts/check_reserved_terms.py` clean.
