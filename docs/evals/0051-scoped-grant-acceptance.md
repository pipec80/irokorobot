# Scoped owner grants: real-hardware acceptance (Plan 0051, Task 6)

> **Status:** Historical acceptance record, 2026-10-06. Outcomes only: no transcript,
> no name, no photo and no answer text appear here. The cases were written in
> [Plan 0051](../plans/completed/0051-scoped-owner-grants.md#task-6-real-hardware-acceptance)
> and corrected once before running (PIN cases with the face off, a separate face
> step, and the wire value `local_unlock`).

## Conditions

| Item | Value |
|---|---|
| Date | 2026-10-06 |
| Code under test | `53148e5` (branch `feat/0051-scoped-owner-grants`); the only later commit, `aaa4776`, changes the plan text |
| Machine | Pipec's development laptop, built-in camera and microphone, Whisper `small`, Piper, Ollama running |
| Who ran it | Pipec, locally, starting the server and the robot himself; the executor recorded outcomes only |
| Constant flags | `SPEAKER_AUTHENTICATION_ENABLED=true` (no voiceprint enrolled during the cases, speaker verdict `unknown`), `LOG_CONVERSATION_TEXT=true`, `ROBOT_OWNER_UNLOCK_PROMPT=true` for the robot runs |
| PIN-path runs (steps 4 to 9) | `FACE_AUTHENTICATION_ENABLED=false`, `ROBOT_FACE_AUTH_ENABLED=false`, server restarted after the change |
| Face-path runs (steps 6b, D1, D2) | `FACE_AUTHENTICATION_ENABLED=true`, `ROBOT_FACE_AUTH_ENABLED=true`, `ROBOT_STREAMING=true`, server and robot restarted |

## Cases

| # | Case | Outcome |
|---|---|---|
| 1 | `just setup-personal status` | `personal_security_ready=True`. |
| 2 | `just onboard`, face phase (script unlocks with `biometric_admin`) | Completed; enrolment route accepted the administration grant. |
| 3a | `speaker-auth-demo --enroll` | `POST /auth/owner/unlock` 200, `POST /auth/owner/voice/enroll` 200. |
| 3b | `speaker-auth-demo --revoke` | `POST /auth/owner/unlock` 200, `POST /auth/owner/voice/revoke` 204; voiceprints purged. |
| 4 | Read grant, one use, over `/chat` | Unlock echoes `personal_protected_read`; first read `authentication_consumed=true`, second `false`. |
| 5 | "Who am I" then the protected read, over `/chat` | "Who am I" answered, `authentication_consumed=false`; the read then answered, `true`. |
| 6 | Household question that reads nothing, then the protected read, over `/chat` | "Not connected yet" answer, `false`; the read then answered, `true`. |
| 7 | Administration grant presented to a protected read, over `/chat` | Unlock echoes `biometric_admin`; read refused, `authentication_consumed=false`; server logged only `Owner grant refused: scope_mismatch`. |
| 8 | Read grant presented to `POST /auth/owner/face/revoke` | HTTP 401; the same token still answered a protected read (`true`). |
| 9 | Unlock with an unknown scope (`root`) | HTTP 422; the response body does not contain the PIN. |
| 9b | Robot, classic mode (`ROBOT_STREAMING=false`), one PIN, four turns | "Who am I" named the owner; household question answered "not connected yet"; protected read answered (grant spent); the repeated read was denied. Fusion reasons `pin`, `pin`, `pin`, `no_evidence`. The repeated question was heard differently by the STT and fell on the protected-household branch; the denial is still the one-use denial. |
| 9c | Robot, streaming mode (`ROBOT_STREAMING=true`), one PIN, four turns | Same four outcomes; the repeated read fell on the own-children branch and was denied (`no_evidence`). |
| 12 | Plan 0054's optional PIN case, face off | The protected read was identified by `Identity fusion: pin`. The wire fields `identity_source` and `assurance` are not shown by the robot and were **not observed**; `local_unlock` and `strong` rest on the code and its automated tests. |
| D1 | Face only, no token left (face on, streaming) | The protected read was answered with `Identity fusion: face_only` (speaker verdict `unknown`, so assurance `basic`). |
| D2 | Face identified, token present, then camera covered (face on, streaming) | Read 1 answered with `face_only`; read 2 (camera covered) answered with `pin`, so the face-identified turn did not spend the grant; read 3 (camera covered) denied with `no_evidence`. An earlier run showed the same: a face-identified "not connected yet" turn left the token spendable by the next read. |
| 10 | Administration grant authorizing `face/revoke` (204) | **Not run**: it would revoke the owner's face and force a re-enrolment. Covered by `test_a_biometric_admin_grant_cannot_read_and_still_administers` and `test_an_administration_grant_is_one_use_even_after_a_refused_read`; the 204 path of the routes was exercised live by cases 2 and 3b. |

## Limitations

- One owner, one machine, one microphone and one camera.
- Replay, liveness and the bearer limit (a valid read grant still names and answers whoever
  presents it, ADR-0008) are not defended here and were not tested.
- Cases 4 to 9 went through loopback HTTP (`/chat` and the auth routes), not through the
  robot, which never asks for the administration scope; cases 9b to D2 went through the
  robot.
- The speaker verdict was `unknown` in every run: no voiceprint was enrolled while the
  turns ran, so `face_voice` (assurance `strong`) was not exercised.
- `identity_source` and `assurance` are not visible on the robot console; the fusion
  reason in the server log is the evidence for case 12.
