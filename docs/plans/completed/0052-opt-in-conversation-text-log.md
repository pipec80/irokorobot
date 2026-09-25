# 0052 — Opt-in conversation text log

> **Status:** Completed 2026-09-24 — merged as PR #132 (`a12ef8a`). Done on
> Pipec's explicit request after the first real `just run-server` +
> `just run-robot` session, where the logs showed only character counts and the
> synthesized voice was hard to understand. Real acceptance: Pipec confirmed
> `Heard:` / `Spoken:` on both consoles, including the owner's own-children
> answer. Historical evidence only — this document authorizes nothing.

**Goal:** Let the operator read, on their own machine, exactly what Iroko heard
and what it says, without weakening the rule that household content is never
logged (Plans 0031 and 0032).

**Amends:** the global constraint "do not log transcripts, model output, TTS
sentences…" of [Plan 0031](0031-server-production-baseline-design.md). The
constraint stays the default; this plan adds one deliberate, off-by-default
exception.

## Design

- Setting `LOG_CONVERSATION_TEXT` (default `false`) in `server.settings` and
  `.env.example`.
- New module `server/conversation_log.py` with `log_heard(text)`,
  `log_spoken(text)` and `set_enabled(enabled)`. Its logger
  (`server.conversation_text`) is **disabled** until enabled — pytest's caplog
  attaches to non-propagating loggers, so "no handler" would not have kept the
  text out of the privacy sentinels — and has `propagate=False`, so it never
  reaches the root handlers and therefore never the JSON Lines file.
- `configure_logging` attaches the console handler to that logger only when the
  setting is on, enables it, and logs one content-free WARNING saying so.
- Call sites: `pipeline._run_stt` (heard), `pipeline._run_tts` (spoken, classic
  and vision routes), `streaming_render.synthesize_sentence` (spoken, streamed
  sentences) and `streaming.stream_response_plan` (spoken, deterministic answers
  such as the owner's own children).
- The robot has the same pair: `robot/conversation_log.py` (a deliberate small
  copy — the two packages share only the API contract), the same setting in
  `robot.settings`, enabled from `robot.app.main` with its own console handler
  and warning. Call sites: `app_streaming.on_thinking_stream` (heard),
  `app_streaming._audio_chunks` (each spoken sentence), and the classic
  `app._on_thinking` / `_on_looking` (heard and replied). Added after the first
  real run showed the robot console still printing only counts.

## Not logged, on purpose

PINs and tokens (they never pass through STT or TTS text), biometrics, memory
layer values, and raw model output before validation.

## Verification

- `tests/integration/test_conversation_text_log.py`: off by default; disabled
  until opted in; off prints nothing to console or file; on prints to the console
  and never to `server.log`; each of the four call sites emits; nothing
  propagates to the root logger. One site was mutation-checked (removing the
  deterministic-plan call fails its test).
- `tests/unit/test_robot_conversation_log.py`: the same contract for the robot
  (off and disabled by default; console only, never the root handlers; heard
  and spoken wired in streaming and classic turns).
- `tests/__init__.py` pins `LOG_CONVERSATION_TEXT=false` for the suite. Found
  the hard way: with the flag on in the developer's own `.env`, the module-level
  `settings` singletons read it and five tests failed, the privacy sentinels
  among them. The suite must not depend on a local `.env`.
- `tests/integration/test_sensitive_logging.py` still passes unchanged: with the
  setting off nothing reaches any handler.

## Operator use

Set `LOG_CONVERSATION_TEXT=true` in `.env`, restart `just run-server` and
`just run-robot`, and read `Heard:` / `Spoken:` lines on either console. Turn it off again afterwards. Do not
say a PIN aloud while it is on: speech is transcribed before anything else.
