# 0076 — Conversation record and diary: hardware acceptance

> **Status:** **accepted** on 2026-10-30 by Pipec on the shared development laptop (webcam, microphone,
> `qwen2.5:3b`, Whisper `medium` on the GPU, streaming route). Code of
> [Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md). **Counts and yes/no
> only:** no transcript, no summary, no phrase and no household datum is written here. The exported
> files were deleted after reading, and the consent was revoked at the end (case 7), which deleted
> every stored conversation.

## Setup

- The database was copied to a local backup and migrated to schema 13 before the run (`iroko-admin`
  refuses a database behind the latest schema and never migrates one; the server migrates at start-up).
- `just admin conversations consent-grant` (notice v1, `SI`, the owner's PIN); `list` empty.
- `.env`: `CONVERSATION_RECORD_ENABLED=true`, `CONVERSATION_EPISODES_ENABLED=true`, face and speaker
  authentication on, memory candidates and the profile card on.

## Results

| # | Case | Result |
|---|---|---|
| 1 | Free conversation facing the camera | **Pass.** One segment, 8 exchanges, 2919 B, `elegible sí`; closed by itself 3 min after the last turn; the diary entry was written 53 s later |
| 2 | Conversation with no face in frame | **Pass.** A second segment, 3 exchanges, 982 B, `elegible no`, `diario skipped`; every turn `no_evidence` |
| 3 | The summary is faithful (no invented fact) | **Yes** (Pipec) |
| 4 | Voice-turn latency, record on vs off | **No visible cost.** Median `total` of the model turns, the cold first turn excluded: 16.4 s on (5 turns) vs 17.2 s off (3 turns); the spread is the model's (5 to 28 s). With the record on, the request ends 1.5 to 4.5 s after the reply, in the background, after the robot has spoken |
| 5 | Share of verified turns | **2 of the 6 model turns** of case 1 (33 %), close to the 35.5 % of Plan 0075; the 1.7 s greeting came back `unknown`, as short clips do |
| 6 | Size | About **365 B per exchange**; the 60-exchange / 64 KiB segment caps and the 200 MB total are far from reach |
| 7 | `consent-revoke` | **Pass.** «se borraron 3 conversaciones»; `list` empty |
| 8 | `CONVERSATION_RECORD_ENABLED=false` | **Pass.** No capture line, no diary job started, `list` unchanged |

## Found during the run

- **A fixed reply lost the owner's words (fixed the same day, with Pipec's OK).** In case 1 two turns
  were answered by the protected household rule with its fixed phrase; the fusion had verified the
  owner's face **and** voice on both, yet the record stored them `not_checked`, so they could never
  reach the diary. A fixed reply now carries the speaker the controller resolved. Re-checked on
  hardware: a third conversation with the same kind of turn stored it as `tu voz verificada` and the
  segment was eligible.
- **The protected household rule answers a mere mention.** Saying that one's children or the dog
  will do something triggers the fixed «La información familiar autorizada…» reply although nothing
  was asked. Outside this plan; it is a follow-up in the roadmap's cross-cutting table.
- Case 2 ran while the plan's tests ran on the same laptop, so its latencies (17 to 33 s of model time)
  are not used for case 4.
