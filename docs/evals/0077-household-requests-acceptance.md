# 0077 — The household protection answers requests: hardware acceptance

> **Status:** **in progress.** Code of
> [Plan 0077](../plans/open/0077-household-requests-not-mentions.md), branch
> `feat/0077-household-requests`. Pipec runs every case; the agent starts nothing. **Counts and yes/no
> only:** no transcript, no reply, no name and no household datum is written here.

## Setup

- `.env`: memory on, face and speaker authentication on, `LOG_CONVERSATION_TEXT=true` (console only),
  memory candidates on for case 3. The conversation record had no active consent (revoked at the close
  of Plan 0076), so nothing was recorded and the diary half of case 11 is not measured.
- The owner's face and voice enrolled; a relative and a pet stored with a name (case 8).
- Streaming route only. The classic route is not run (Pipec, 2026-11-02): the robot uses streaming and
  both routes take the same controller decision.
- How to tell who answered: a fixed phrase is a rule; anything else is the model. On the server
  console, the `Turn decision` line of each turn says `need=protected_household` (or another need)
  for a fixed reply, and `outcome=no-plan-channel-generates` when the model answers; it holds no
  sentence.

## Round 1 (2026-11-02, rule of Tasks 2 to 4)

| # | Case | Result |
|---|---|---|
| 1 | Stories about the children and the family | **Pass**, 2 of 3: the model answered |
| 2 | Stories about the pet | **Pass**, 2 of 3. The refusal Pipec heard before Plan 0077 did **not** happen again (D-6) |
| 3 | A taste plus the children | **Pass**: the model answered; one candidate stored and promoted after a voice retry |
| 4 | Advice about a relative | **Pass**, 2 of 3 |
| 5 | Questions about famous people | **Pass**, 3: the model answered. It got two facts wrong (a birth month; a footballer's brother), a limit of the 3B model, not of the route |
| 6 | Stories with «años» | **Pass**, 1 of 4; «relación» and «¿cachai?» not run |
| 7 | Requests for a relative's or a pet's datum | **Pass**, 3 of 3: the fixed reply |
| 8 | A request by a stored first name | **Pass**: the fixed reply, through the stored-name path, on a sentence with no question mark |
| 9 | No face in view | 1 of 2: a request got the refusal for an unidentified speaker; the named request not run |
| 10 | Requests spoken normally | **6 of 8** reached the fixed reply; 7 of 8 written with a mark. **Under the bar of 4 of 5** |
| 11 | Something the model cannot know | 1 of 2 did not invent |
| 12 | A family story, then no face | The story was **not** repeated (the session stopped), but the model **invented** a relative |

**Stop rule met:** two real requests reached the model and it stated an invented household value as true
(case 10's two misses, one of them case 12). Pipec chose amendment D-22 (option B) the same day.

### Observations of round 1

- The model opened one reply with «Tú, muy bien.» and once voiced one of the owner's profile-card tastes
  as if it were its own; both are model behaviour, outside this plan.
- Three turns at the end were not heard: the robot sent 0.8 s of noise twice (`422`) and detected no
  speech for 30 s. Microphone placement, not this plan.

## Round 2 (rule of D-22, commit `134eba9`, `just gate` 5635 passed)

Run by Pipec on 2026-11-02 with the code of `134eba9`, streaming route, face and voice enrolled. Counts
only. The turns before the cases (greetings, follow-ups of the model) are not counted.

| # | Case | Result |
|---|---|---|
| 4 | Advice about a relative | **Pass**, 3 of 3: the model answered (a gift, what to cook, how to help with homework) |
| 6 | «relación» and «¿cachai?» | «relación»: **pass**, the model answered. «¿cachai?»: **fail**, the fixed reply: Whisper wrote the tag in a spelling the list did not know and opened the «¿» at the start of the sentence. Fixed in the next commit (`fix(server): cachai inside a wrapped question asks nothing`); re-run pending |
| 7 | Requests for a relative's or a pet's datum | **Pass**, 3 of 3 with the fixed reply, among them the two requests that the model answered by inventing in round 1 |
| 9 | Named request with no face | **Pass**: the model answered and stated nothing true about the household |
| 10 | Requests spoken normally | **6 of 6** reached the protected path (5 fixed replies and the authorized count of children); bar 4 of 5. Whisper wrote a question mark in 5 of the 6 |
| 12 | A family story, then no face | **Pass**: the story was not repeated; the reply was the refusal for an unidentified speaker, with no invented relative |

**Stop rule:** not met. No request reached the model in this round, and the model invented no household
value.

### Observations of round 2

- A long story that says «a ellos les gusta…» of the owner's parents reached the model; before Plan 0077 the
  word «gusta» alone would have cut it.
- The model produced a few odd sentences (one with the owner's nickname, one question about «mejorar tu
  relación» to a remark on neighbours); model behaviour, outside this plan.
- The classic route was dropped from the acceptance (Pipec, 2026-11-02).
