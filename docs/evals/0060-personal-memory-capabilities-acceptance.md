# Personal-memory capabilities: runtime acceptance (Plan 0060, Task 8)

> **Status:** Historical acceptance record, 2026-10-09. Outcomes only: no transcript, no name,
> no PIN, no token and no answer text appear here. The cases were written in
> [Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md#task-8-real-runtime-acceptance).
> Nothing consumes the new capabilities, so there is no spoken turn that reaches them; the
> check is that the unlock endpoint issues and echoes the two new scopes, keeps the default,
> and that the voice path behaves as before.

## Conditions

| Item | Value |
|---|---|
| Date | 2026-10-09 |
| Code under test | `17d5cb6` (branch `feat/0060-personal-memory-capabilities`, code complete); later commits change documents only |
| Machine | Pipec's development laptop, built-in camera and microphone, Whisper `small`, Piper |
| Who ran it | Pipec, locally, starting the server and the robot himself; the executor recorded outcomes only |
| Flags | `LOG_CONVERSATION_TEXT=true`; face authentication on (the owner was identified by `face_only`); no voiceprint enrolled (speaker verdict `unknown`); `ROBOT_STREAMING` on |
| PIN handling | Typed by Pipec as a hidden prompt into a local script that prints only status codes, the echoed scope and yes/no flags; never written down or logged |

## Cases

| # | Case | Outcome |
|---|---|---|
| 1 | Unlock with `scope: "personal_memory_read"` | HTTP 200; the response echoes `personal_memory_read` and carries a token. |
| 2 | Unlock with `scope: "personal_memory_forget"` | HTTP 200; the response echoes `personal_memory_forget` and carries a token. |
| 3 | Unlock with an unknown scope | HTTP 422 in 4 ms; no token; the response body does not contain the PIN. |
| 4a | Unlock with no scope | HTTP 200; the response echoes `personal_protected_read` (the default is unchanged). |
| 4b | Robot, streaming: "which are my children?" (owner identified by `face_only`) | Answered by the deterministic own-children branch (`need=own_children_list`, `llm_ms=0`), as before. |
| 4c | Robot, streaming: an ambiguous date question, then "give me today's date" | The first was asked to be rephrased and the second answered with the date, both deterministic (`llm_ms=0`), as before. |
| 4d | Robot, streaming: a greeting, first with Ollama not running | The model transport failed (`Streaming LLM unreachable`, `reason=llm_error`) and the server spoke its fallback phrase, twice. Confirmed afterwards: the Ollama port refused the connection. The branch changes no LLM, streaming or controller code, so this was the environment. |
| 4e | Robot, streaming: the same greeting with Ollama running | Answered normally: `outcome=ok`, 4 spoken fragments, no fallback. The LLM took 39 s and the first audio came at 43 s (one sample; probably the model loading cold after Ollama was started). |

The four `POST /auth/owner/unlock` requests of cases 1 to 4a appear in the server log as
200, 200, 422 and 200.

## Limitations

- One owner, one machine, one microphone and one camera.
- Cases 1 to 4a went through loopback HTTP, not through the robot, which never asks for the new
  scopes (a test pins that the robot and `scripts/` never mention them).
- No case spends a `personal_memory_read` or `personal_memory_forget` token: no operation
  consumes them yet. Their refusal by the wrong resolver, their one-use spending and the
  denial of a merely peeked grant are covered by `tests/unit/test_personal_memory_grants.py`
  with the real resolvers.
- Case 4e is a single sample; its latency says nothing about the steady state.
- The server did not warn that Ollama was down: the health check passed and the first two greetings
  spoke the fallback phrase (a follow-up with no plan yet).
- Replay, liveness and the bearer limit stay as in Plan 0051's record and were not tested.
