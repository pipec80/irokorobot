# 0052 — Opt-in conversation text log

> **Status:** Implemented on `feat/0052-conversation-text-log` (2026-09-24), on
> Pipec's explicit request; not merged. Pipec chose this scope after the first
> real `just run-server` + `just run-robot` session, where the logs showed only
> character counts and the synthesized voice was hard to understand.

**Goal:** Let the operator read, on their own machine, exactly what Iroko heard
and what it says, without weakening the rule that household content is never
logged (Plans 0031 and 0032).

**Amends:** the global constraint "do not log transcripts, model output, TTS
sentences…" of [Plan 0031](../completed/0031-server-production-baseline-design.md). The
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

## Not logged, on purpose

PINs and tokens (they never pass through STT or TTS text), biometrics, memory
layer values, raw model output before validation, and the robot's own console
(the server already shows both sides of every turn).

## Verification

- `tests/integration/test_conversation_text_log.py`: off by default; disabled
  until opted in; off prints nothing to console or file; on prints to the console
  and never to `server.log`; each of the four call sites emits; nothing
  propagates to the root logger. One site was mutation-checked (removing the
  deterministic-plan call fails its test).
- `tests/integration/test_sensitive_logging.py` still passes unchanged: with the
  setting off nothing reaches any handler.

## Operator use

Set `LOG_CONVERSATION_TEXT=true` in `.env`, restart `just run-server`, and read
`Heard:` / `Spoken:` lines on that console. Turn it off again afterwards. Do not
say a PIN aloud while it is on: speech is transcribed before anything else.
