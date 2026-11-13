# 0084 — Pending topics and the greeting: hardware acceptance

> **Status:** **in progress.** Day 1 (2026-11-13, the telling) **passed**; the greeting days run
> 2026-11-16 to 2026-11-19 and are recorded here as they happen. Code of
> [Plan 0084](../plans/open/0084-pending-topics-and-the-greeting.md), merged 2026-11-13 (`6a17e38`,
> PR #264). Pipec runs every case on the streaming route with the laptop body; the agent starts
> nothing. **Counts, outcomes and yes/no only:** the plans were invented for the test (no household
> datum), and the only text quoted is the robot's fixed wording as it stands in the code.

## Setup

- `.env`: memory on, `CONVERSATION_RECORD_ENABLED=true`, `CONVERSATION_EPISODES_ENABLED=true`,
  `RECALL_ENABLED=true`, **`PENDING_TOPICS_ENABLED=true`**, face and voice authentication on,
  `MEMORY_CANDIDATES_ENABLED=true`, `HOUSEHOLD_TIMEZONE=America/Santiago`, the naming model
  `CONSOLIDATION_MODEL` (qwen3 4B instruct), `LOG_CONVERSATION_TEXT=true` (console only).
- A backup of the real database was taken with the server stopped (`user_version` 15, hash
  checked); the server then applied migration 016 on start (`user_version` 16, no error).
- **Reorganized around a weekend** (Pipec, 2026-11-13): a topic is asked one or two days after its
  due day and then expires, so the plans told on Friday name the next Monday, Tuesday and
  Wednesday, and the greeting is heard from Monday to Thursday.
- How to tell what happened: the server's `pending.capture`, `pending.named` and
  `pending.follow_up` lines (closed outcomes) and the voice verdict of `conversation.capture`; the
  topics are counted in a copy of the database (state, sensitivity, due day and word count only).

## Day 1 — telling the plans (2026-11-13): passed

| # | Case | Result |
|---|---|---|
| 1 | Migration 016 on the real database | **Pass**: applied on start, schema version 16 |
| 2 | A plan for Monday with a first-person verb | **Pass**: `kept`, voice `verified`, then `named` |
| 3 | A plan for Tuesday | **Pass**: `kept`, `named` |
| 4 | A health plan for Wednesday | **Pass after a fix**: first `kept` then deleted at naming (the model answered five words, over the limit); the naming prompt now asks for one or two words, probed 10 of 10 on the real model; said again, `kept` and `named` |
| 5 | A negated plan («no voy») | **Pass**: `no_verb`, no topic |
| 6 | Someone else's plan («viene mi hija») | **Pass**: `no_verb`, no topic |
| 7 | A question with two days | **Pass**: no topic (`no_phrase`) |
| 8 | Turns whose voice did not verify (short clips) | **Pass**: `not_verified`, never a topic |
| 9 | The store after the job | **Pass**: 3 `open` (2 `normal`, 1 `medical`), due 2026-11-16, -17 and -18; every topic two words; no turn's words kept after naming |

Found on the way and fixed with its test: the routes read «today» from the machine's clock, not the
household's day (the PR's CI ran in UTC at 23:15 in Santiago); and the naming prompt above.

## The greeting (2026-11-16 to 2026-11-19): pending

| # | Day | Case | Expected | Result |
|---|---|---|---|---|
| 10 | Mon 16 | «Hola» | no question (the Monday topic is due that day) | pending |
| 11 | Tue 17 | «Hola» | the reply, then «¿Cómo te fue ayer con …?» for Monday's plan | pending |
| 12 | Tue 17 | the owner answers | the next reply follows the answer | pending |
| 13 | Tue 17 | «Hola» three minutes later | no question (`already_today`) | pending |
| 14 | Wed 18 | «Hola» with a second face in view | no question | pending |
| 15 | Wed 18 | «Hola» alone | «¿Cómo te fue ayer con …?» for Tuesday's plan | pending |
| 16 | Thu 19 | «Hola» alone | the health plan, the alta being closed | pending |
| 17 | Thu 19 | the conversation record | no follow-up sentence in it | pending |
