# 0076 — Conversation record and diary: hardware acceptance

> **Status:** pending. Run by Pipec on the real robot after the code of
> [Plan 0076](../plans/open/0076-cm4-conversation-record-and-diary.md) is merged or checked out.
> **Counts and yes/no only:** no transcript, no summary, no phrase and no household datum is written
> here. Delete the exported files after reading them.

## Setup

1. Server stopped. `just admin conversations consent-grant` (shows the notice, asks `SI` and the
   owner's PIN). `just admin conversations list` → «No hay conversaciones guardadas.»
2. In `.env`: `CONVERSATION_RECORD_ENABLED=true`, `CONVERSATION_EPISODES_ENABLED=true` (memory,
   face and speaker authentication on, as today). Start the server and the robot yourself.

## Cases

| # | Case | What to check | Result |
|---|---|---|---|
| 1 | About five minutes of conversation facing the camera | `list` shows one segment, `elegible sí`; the export shows the exchanges with their verdicts | |
| 2 | A conversation off camera, or with another person speaking | that segment is `elegible no`; it gets no summary (`diario skipped`) | |
| 3 | After 180 s of silence and one job tick (120 s) | the first segment has `diario done`; the summary in the export is faithful (no invented fact): yes/no | |
| 4 | Median voice-turn latency over 10 turns, record on vs off | the capture runs after the reply: the difference should be noise | |
| 5 | Share of `verified` turns over the session | compare with the 35.5 % of Plan 0075, which did not need the face | |
| 6 | Bytes per exchange and per conversation (from `list`) | revisit the caps of Plan 0076 D-8 | |
| 7 | `just admin conversations consent-revoke` | `list` is empty | |
| 8 | `CONVERSATION_RECORD_ENABLED=false` and a restart | nothing new is recorded | |

## Outcome

To be written after the run.
