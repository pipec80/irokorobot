# 0084 — Pending topics and the greeting: hardware acceptance

> **Status:** **closed 2026-11-16 by Pipec's decision.** Day 1 (2026-11-13, the telling) **passed**,
> 9 of 9; the greeting with nothing due (case 10, 2026-11-16) **passed** on hardware; cases 11 to 17
> were **not run on hardware** and are covered by automated tests (below). Code of
> [Plan 0084](../plans/completed/0084-pending-topics-and-the-greeting.md), merged 2026-11-13
> (`6a17e38`, PR #264). Pipec ran every hardware case on the streaming route with the laptop body;
> the agent started nothing. **Counts, outcomes and yes/no only:** the plans were invented for the
> test (no household datum), and the only text quoted is the robot's fixed wording as it stands in
> the code.

## Setup

- `.env`: memory on, `CONVERSATION_RECORD_ENABLED=true`, `CONVERSATION_EPISODES_ENABLED=true`,
  `RECALL_ENABLED=true`, **`PENDING_TOPICS_ENABLED=true`**, face and voice authentication on,
  `MEMORY_CANDIDATES_ENABLED=true`, `HOUSEHOLD_TIMEZONE=America/Santiago`, the naming model
  `CONSOLIDATION_MODEL` (qwen3 4B instruct), `LOG_CONVERSATION_TEXT=true` (console only).
- A backup of the real database was taken with the server stopped (`user_version` 15, hash
  checked); the server then applied migration 016 on start (`user_version` 16, no error).
- **Reorganized around a weekend** (Pipec, 2026-11-13): a topic is asked one or two days after its
  due day and then expires, so the plans told on Friday name the next Monday, Tuesday and
  Wednesday, and the greeting was to be heard from Monday to Thursday.
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

## The greeting (2026-11-16 to 2026-11-19)

| # | Day | Case | Expected | Result |
|---|---|---|---|---|
| 10 | Mon 16 | «Hola» | no question (the Monday topic is due that day) | **Pass** on hardware: no question; `pending.follow_up none_due` at 17:53:10 |
| 11 | Tue 17 | «Hola» | the reply, then «¿Cómo te fue ayer con …?» for Monday's plan | **Not run on hardware** (Pipec closed the acceptance on 2026-11-16); covered by tests |
| 12 | Tue 17 | the owner answers | the next reply follows the answer | **Not run on hardware** (same); covered by tests, with the limit below |
| 13 | Tue 17 | «Hola» three minutes later | no question (`already_today`) | **Not run on hardware** (same); covered by tests |
| 14 | Wed 18 | «Hola» with a second face in view | no question | **Not run on hardware** (same); covered by tests |
| 15 | Wed 18 | «Hola» alone | «¿Cómo te fue ayer con …?» for Tuesday's plan | **Not run on hardware** (same); covered by tests |
| 16 | Thu 19 | «Hola» alone | the health plan, the alta being closed | **Not run on hardware** (same); covered by tests |
| 17 | Thu 19 | the conversation record | no follow-up sentence in it | **Not run on hardware** (same); covered by tests, with the limit below |

**Case 10, as it happened.** On 2026-11-16 the first turn (17:51) ran with Ollama not yet up, so the
reply was the fallback phrase; its `pending.follow_up` outcome was `none_due`. The «Hola» of
17:53 heard no question, `none_due`, as expected: the topic told for that Monday was due that day
and a topic is never asked on its due day. A second greeting later the same day, on another
branch, was `none_due` too. Three first turns that day, three `none_due` (read in
`logs/server.log`, closed values only), no question heard.

### Cases covered by automated tests instead

Each name was found in `tests/` and its assertions read before citing it.

| # | Covered by | What it pins |
|---|---|---|
| 10 | `test_a_topic_due_today_or_three_days_ago_is_never_due` (`tests/integration/test_pending_store.py`); `test_nothing_due_says_nothing` (`tests/unit/test_pending_follow_up.py`) | a topic due today (or three days back) is never returned; nothing due prepares nothing and logs `none_due` |
| 11, 15 | `test_a_new_session_of_the_face_owner_is_asked_once` (`tests/unit/test_pending_follow_up.py`); `test_the_classic_route_says_it_once` and `test_the_stream_says_it_once_and_done_gains_no_field` (`tests/integration/test_pending_routes.py`); `test_may_follow_up` and `test_the_sentence` (`tests/unit/test_pending_topics.py`); `test_due_topic_picks_the_oldest_in_the_window` (`tests/integration/test_pending_store.py`) | the first turn of a new session of the face-identified owner is asked once, after the reply, the audit row before the state `asked`; on both routes the first turn hears the reply and «¿Cómo te fue ayer con el banco?», the second hears none, and the stream's `done` gains no field; the window is the day after the due day to two days after, never the due day or the third day after; the sentence says «ayer» or «anteayer»; the oldest topic in the window is picked |
| 12 | `test_the_next_model_turn_hears_the_question_and_this_one_never_reads_it` (`tests/integration/test_pending_routes.py`); `test_the_follow_up_is_said_after_the_reply_and_joins_the_session` (`tests/unit/test_text_turn_follow_up.py`) | the model's next turn finds the question in the session history beside the reply, and the turn that speaks it reads no topic |
| 13 | `test_not_twice_the_same_day` (`tests/unit/test_pending_follow_up.py`); `test_only_one_topic_is_asked_per_household_day` (`tests/integration/test_pending_store.py`) | a day that already asked says nothing and logs `already_today`; a second topic cannot be marked asked the same household day, and can the next one |
| 14 | `test_a_guest_in_view_hears_nothing` (`tests/integration/test_pending_routes.py`) | with a second face in view, on both routes, only the reply is spoken and the topic stays `open` |
| 16 | `test_a_medical_topic_needs_the_closed_alta` (`tests/unit/test_pending_follow_up.py`); `test_a_health_topic_needs_the_closed_alta_on_the_route` and `test_a_health_topic_is_never_said_with_a_guest_in_view` (`tests/integration/test_pending_routes.py`) | a health topic is refused (consent missing, no `mark_asked`) with the alta open and said with it closed; on the route it is spoken only with the alta closed, and never with a second face in view |
| 17 | `test_the_follow_up_is_said_after_the_reply_and_joins_the_session` (`tests/unit/test_text_turn_follow_up.py`); `test_the_follow_up_is_one_more_audio_event_and_joins_the_session` (`tests/integration/test_stream_follow_up.py`) | the record callback receives the owner's words and the reply only, on the classic and the stream path; the sentence joins the session and never the spoken-text log |

**Limits, stated and not hidden.**

- *Case 12:* the tests pin that the session holds the question when the next model turn runs. How
  well the 3B model follows the answer is its own behavior and was not measured.
- *Case 17:* the pin is at the record callback (`record_turn`), not an end-to-end read of the stored
  conversation record after a follow-up; `iroko-admin conversations` was not run on a real follow-up.
- Cases 11 to 16 have never been heard on the real body with a real stored topic: the first real
  follow-up is the observation below.

## The decision (2026-11-16)

Pipec closed this acceptance on 2026-11-16 instead of running the greeting days of 17, 18 and 19
November on hardware, so that the other work stops waiting for them. The evidence that stands is
day 1 (the telling, 9 of 9) and case 10 on hardware; the rest is covered by the tests above. The
greeting days become **observation in normal use, non-blocking**: if Pipec greets on those days
and something is wrong, it is a defect, found and fixed then, with its test. With this, ADR 0037
decision 2 is implemented and the ADR is `Accepted`.
