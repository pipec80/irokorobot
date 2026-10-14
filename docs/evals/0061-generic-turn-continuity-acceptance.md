# Short-term continuity of the identified person: runtime acceptance (Plan 0061, Task 9)

> **Status:** Historical acceptance record, 2026-10-13. Outcomes only: no transcript, no name,
> no PIN, no token and no answer text appear here. The cases were written in
> [Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md#task-9-real-runtime-acceptance)
> from [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) §10. The two protocol
> measurements are the reports [`0061-stream-history-run1.md`](0061-stream-history-run1.md) and
> [`0061-stream-history-run2.md`](0061-stream-history-run2.md) (renamed from the runner's
> timestamped names, `2026-10-14-000334` and `2026-10-14-002134`).

## Conditions

| Item | Value |
|---|---|
| Date | 2026-10-13 (the two measurement reports are stamped 2026-10-14 by their runner) |
| Code under test | Branch `feat/0061-cm2-generic-turn-continuity`, code complete at `6cb3299` (tasks 0 to 8); later commits change documents only |
| Machine | Pipec's development laptop (shared with Docker and the editor, no GPU), built-in camera and microphone, Whisper `small`, Piper, `qwen2.5:3b` |
| Who ran it | Pipec, locally, starting the server and the robot himself; the executor recorded outcomes only |
| Flags | `MEMORY_ENABLED=true`, `FACE_AUTHENTICATION_ENABLED=true`, `ROBOT_FACE_AUTH_ENABLED=true`, `ROBOT_STREAMING` on, `LOG_CONVERSATION_TEXT=true` (so the console printed what was heard and said); no voiceprint enrolled (the voice is not consulted on a generic turn) |
| Token | **None presented** by the robot. The `/chat` cases of step 7 used the owner's token, which Pipec obtained from a hidden prompt |
| PIN handling | Typed by Pipec at the `just chat-test` hidden prompt; never written down or logged |
| Second person | None was available: a face shown on an iPad stood in for them (see the limitations) |

## Cases (voice, `/transcribe/stream`, face resolved on every turn)

| # | Case | Outcome |
|---|---|---|
| a | A sentence, then a question that depends on it, asked about two and a half minutes later with three suspended turns in between | **Pass.** The server log shows `Generic identification: identified`, `Continuity: started` on the sentence and `Continuity: continued` with `history_turns=2` on the question; the answer used the sentence. The three suspended turns did not extend or erase the silence (the question came 147 s after the last write, under 180 s). |
| b1 | The same question with a second face (on the iPad) in frame beside the owner | **Pass with a substitute.** `Generic identification: veto_multiple_faces`, `Continuity: suspended`, `history_turns=0`; the answer did not use the session. |
| b2 | The same question with no evidence of the owner in frame | **Pass with a substitute.** `Generic identification: no_evidence`, `Continuity: suspended`; the answer did not use the session. The owner resumed afterwards (case a). |
| c | The question again after more than 180 s of silence (223 s since the last write) | **Pass.** `Continuity: expired` then `Continuity: started`, `history_turns=0`; the identified owner's context was gone. |
| d | Cost and counts | See below. |

One more turn in the same run was a Whisper echo of its own prompt: it found no face evidence
(`no_evidence`, 201 ms), was suspended, and the owner's session survived it.

## Case d: cost of the face check and counts

Voice route, one server run, six generic identifications (every transition below has its
`Generic identification:` line just before it):

| Measure | Value |
|---|---|
| Identifications | 6 (`identified` 3, `no_evidence` 2, `veto_multiple_faces` 1) |
| `elapsed_ms`, sorted | 201, 522, 721, 1034, 1260, 1612 |
| Median / maximum | about 880 ms / 1612 ms |
| Whole turn, for scale | 7 to 19 s (stt 1.9 to 4.2 s, llm 3.7 to 16 s, tts 0.4 to 1.2 s) |
| Transitions | `started` 2, `continued` 1, `expired` 1, `replaced` 0, `suspended` 3 (`no_evidence` 2, `veto_multiple_faces` 1) |

`/chat`, token only (no frame), the `just chat-test` runs: 6 identifications at 0 to 2 ms
(median 1 ms); `started` 1, `continued` 1, `suspended` 4 (`no_evidence`); the token was
observed on two turns and never spent. The cost of the face check is therefore the detector and
the matcher, not the fusion.

## Measurement of ADR 0020 §7 (`just eval-chat --provider ollama --mode stream --runs 5`, twice)

Model `qwen2.5:3b`, 5 runs, 180 graded observations per run.

| Run | Fallback `history` | Not Spanish, `history` | Not Spanish, `public` | Not Spanish, all |
|---|---:|---:|---:|---:|
| 1 (`0061-stream-history-run1`) | 0.00 % (0 of 60) | 0 of 50 judged | 1 of 55 | 1 of 147 |
| 2 (`0061-stream-history-run2`) | 0.00 % (0 of 60) | 1 of 53 judged | 2 of 60 | 3 of 164 |

The gate of D-9 (at most 5 % in both runs) is met: 0.00 % twice. The one `history` reply the
word-list heuristic judged not Spanish was **not located** (the report keeps counts only, by
design) and was accepted by Pipec as the heuristic's documented limit rather than read; the
heuristic returns *undetermined* for fewer than four words or a tie, which is why fewer than 60
replies are judged per set.

## `just chat-test`

| Run | Contract | A/B isolation | Continuity of A |
|---|---|---|---|
| With the owner PIN | PASS | PASS | **PASS** |
| Empty PIN | PASS | PASS | **SKIP** ("sin PIN no hay token del dueño ni continuidad que medir") |

The exit status of the empty-PIN run was not captured in the session; the script's contract is
exit 0 for a skipped continuity check.

## Gate

`just gate` on the code of this branch (run by the executor, 2026-10-13): **2597 passed**
(baseline 2515 at `838a44f`), `ruff`, `ruff format`, `mypy`, `ruff --select S` and `pip-audit`
clean.

## Limitations

- One owner, one machine, one microphone and one camera; the face check was measured on a laptop
  shared with other work, not on the homelab server.
- Cases b1 and b2 used a face shown on an iPad instead of a second person. The detector counted
  two faces in b1, so the veto path was exercised; a real second household member, enrolled or
  not, was not tried. The veto of another *enrolled* person is covered by tests with real role
  rows.
- No liveness or replay defence: a photograph of the owner identifies at `basic` and would get
  the owner's session (ADR 0016 §9, documented and unchanged).
- Case c answered with an invented value instead of admitting it did not remember: the session
  was empty, so this is the model's confabulation (the finding left open by Plan 0059), not a
  continuity defect. The language and confabulation follow-ups are in the roadmap's
  cross-cutting table.
- The face check adds about 0.2 to 1.6 s to a generic turn on this machine. ADR 0020 asked for
  it to be measured and recorded, not for a limit.
- `/vision/respond` turns are the public unknown by design and were not part of the acceptance
  (a real-route test pins that they neither read nor write the session).
