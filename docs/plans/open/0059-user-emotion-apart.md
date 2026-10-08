# 0059 — The user's emotion is decided apart from the streamed reply

> **Status:** `Ready` — written 2026-10-08 after Plan 0058 closed without meeting its gate, and
> **promoted by Pipec on 2026-10-08** ("avancemos con esas 7 tareas"), who fixed decisions D-1 to
> D-8 in the planning conversation. It is the `NOW` item. The protocol it implements is
> [ADR 0018](../../adr/0018-user-emotion-decided-apart.md), `Proposed` until Task 6 passes; it
> supersedes the never-accepted [ADR 0017](../../adr/0017-streaming-reply-protocol.md).

> **For agentic workers:** REQUIRED SUB-SKILLS: `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main` (`git checkout -b`), never a
> git worktree, and this plan lives under `docs/plans/`. Pipec authorised subagents for this plan
> only (D-8): agents edit their own files and **never commit, stash or switch branches**; the
> executor commits. Implement exactly the tasks below. If evidence contradicts the plan, stop and
> report instead of redesigning. Pipec runs every local process (Ollama, the measurements, the
> server and robot); you record what they print, outcomes only.

**Goal:** Stop asking the 3B model to write a protocol tag. Plan 0058 measured that even after
tolerating most shapes, 35 % of the context turns of seed 57 still fell back to the "still waking
up" phrase, 20 of 21 because of a tag that shares its line with a word that is not an emotion. The
model speaks plain text; the emotion event is decided by a cheap deterministic function of what
the **user** said; no second LLM call is made. After this plan the fallback rate of the
baseline is at or below 5 % and the robot receives the same wire as today.

**Architecture:** `llm_streaming` sends a plain-text contract with no `EMOTION:`. A new pure
module `user_emotion` maps the user's text to one of `VALID_EMOTIONS` (`neutral` unless the user
states a feeling explicitly). `streaming` presets `state.pending_emotion` from it at the start of
the turn; `streaming_render` keeps promoting it to the one `emotion` event just before the first
audio. `streaming_protocol` loses the tag-start grammar and keeps the body guards (structure,
undecided prefixes, a tag is never spoken). The wire, the robot, the schemas, the settings and the
dependencies do not change.

**Spec:** [ADR 0018](../../adr/0018-user-emotion-decided-apart.md); the Plan 0058 record
(`docs/evals/0058-stream-protocol-repair.md`, in the evidence PR) for the measured shapes; the
code and tests of `main` outrank any stale statement.

## Global Constraints

- Audio contract everywhere: WAV · 16 000 Hz · mono · int16. This plan touches no audio.
- No real household data, voice or name in any tracked file, test, prompt, doc or commit message;
  every example is invented (`scripts/check_reserved_terms.py` guards this).
- Ollama stays the only LLM runtime; no cloud provider (ADR-0004); **no extra LLM call** (D-3).
- The API contract does not change: no field, event, status code or route added or removed, the
  generated OpenAPI is byte-identical, the robot is not touched.
- No `print()`; type hints on every signature; Google docstrings on public APIs; `ruff` clean over
  the **explicit paths** of every `scripts/` file touched; `mypy server/src robot/src` clean.
- A log line, an exception message, an `Observation` or a report never carries any part of a user
  utterance or a model reply: only closed enums, counts, flags, lengths and milliseconds.
- Every new test is observed RED for the stated reason before its implementation.
- A commit title is at most 72 characters: check `git log -1` after every commit.
- `.env.example` does not change (no new variable).
- The Bash tool of this environment loses backslashes: write files with the Write/Edit tools, or
  build a backslash with `chr(92)` inside a script.

## Decisions

| ID | Decision | Source |
|---|---|---|
| D-1 | The model answers in plain text; the streaming contract no longer mentions `EMOTION:`. | Pipec, 2026-10-08 |
| D-2 | The `emotion` of a turn is the **user's** emotion (as the classic prompt already defines it), decided by a pure function of the user's text; default `neutral`. | Pipec, 2026-10-08 |
| D-3 | Hardware reality: no second LLM call, no new setting, no wire or robot change. A model-based classifier is a later plug-in behind the same function when a larger model exists. | Pipec, 2026-10-08 |
| D-4 | The robot's facial expression (a transient reaction for the future face) is out of scope; ADR 0018 reserves the name `expression` for it. The wire keeps `emotion`. | Pipec, 2026-10-08 |
| D-5 | Gate: the fallback rate of `full` is at or below **5 %** in context turns and in public turns, in seeds 57 and 59, with 0 undue accepts and 0 split-dependent replies. Same rules as Plan 0058 (at most 3 fallbacks of 60; exactly 4 may repeat once with `--runs 10`, at most 6 of 120). | Pipec, 2026-10-08 |
| D-6 | A tag the model writes anyway is never spoken, at any position; a reply that *starts* with one falls back (conservative: measured, a later plan may rescue it). | executor, confirmed by Pipec's "conservative" brief |
| D-7 | The classifier is precision-first: it fires only on an explicit statement of a feeling; sarcasm and social nuance stay `neutral`. | Pipec, 2026-10-08 |
| D-8 | Subagents (model Sonnet) work in parallel on disjoint files; they never commit. Tasks 1, 3, 4 and the instrument adaptation of Task 5 land as **one** commit because removing the tag grammar leaves no intermediate state that passes its tests. | Pipec, 2026-10-08 |

## Rules fixed before the run

- **Gate (D-5)** exactly as above, per seed, generator only (`--variants full full_repeat`).
- **Classifier set (Task 5).** A labelled set of at least 40 invented Spanish sentences covers the
  five emotions and many neutral ones. Rules: **0 false positives** on the sentences labelled
  `neutral` (anything non-neutral there fails) and at least **60 %** of the explicit-feeling
  sentences classified as their label.
- **Reported, not gated:** time to first speech (`full`, valid) against Plan 0058's seed 57
  measurement (p50 2739 ms, p95 7131 ms); the share of replies that start with a tag anyway.
- **If the gate fails:** stop, report the numbers, do not merge, leave ADR 0018 `Proposed`.

## Required reading

`AGENTS.md`, `CLAUDE.md` and **all** of `.claude/rules/`; [ADR 0017](../../adr/0017-streaming-reply-protocol.md),
[ADR 0012](../../adr/0012-line-delimited-stream-terminal-events.md);
`server/src/server/streaming_protocol.py`, `streaming_render.py`, `streaming.py`, `llm_streaming.py`,
`llm.py` (`VALID_EMOTIONS`, `FALLBACK_EMOTION`, the classic contract), `memory/working.py`;
`robot/src/robot/stream_validation.py` (read-only); `scripts/eval_stream_protocol.py`,
`stream_failure_shapes.py`, `eval_stream_diagnosis.py`. The abandoned code of Plan 0058 is on the
branch `feat/0058-stream-protocol-repair` (`git show <commit>:<path>` to read, never to merge):
its Tasks 1 and 2 are the model for this plan's Task 1.

## Permitted files

- `server/src/server/user_emotion.py` (new), `streaming_protocol.py`, `streaming_render.py`,
  `streaming.py`, `llm_streaming.py`.
- `scripts/eval_stream_protocol.py`, `stream_failure_shapes.py`, `eval_stream_diagnosis.py`,
  `stream_diagnosis_report.py`, `stream_diagnosis_stats.py` (only what the removal of the tag
  grammar forces).
- Tests: `tests/unit/test_user_emotion.py` (new), `test_streaming_protocol.py`,
  `test_streaming_render_decisions.py` (new), `test_llm_streaming.py`, `test_eval_stream_protocol.py`,
  `test_stream_fragmentation.py`, `test_stream_failure_shapes.py`, `test_eval_stream_diagnosis.py`,
  `tests/integration/test_transcribe_stream.py`, `test_transcribe_stream_resilience.py`.
- Docs: this plan, ADR 0017 (status line only), ADR 0018 (new), `docs/adr/README.md`,
  `docs/evals/0059-user-emotion-apart.md` (new), `docs/architecture/current-state.md` and its
  diagram, `docs/roadmap/cognitive-roadmap.md`, `docs/plans/README.md`, `docs/plans/open/README.md`,
  `docs/plans/completed/README.md`.

Anything else is a conflict to report.

## Tasks

**Task 1 — Guards that outlive the tag (core commit).** Port the idea of Plan 0058 Tasks 1 and 2
without the tag grammar: `is_body_start_undecided` (a body that is still a proper prefix of
`EMOTION:` or of a code fence waits), `StreamProtocolError(LLMError)`, `reject_embedded_tag` (no
spoken sentence or tail mentions `EMOTION` plus a colon, any case, up to three symbols between,
either colon width), `classify_stream_end(buffer, state)` as the single end-of-stream judgement
shared by `streaming_render` and `scripts/eval_stream_protocol`, and `_consume_body` that promotes
the pending emotion only after the whole batch passed (a rejected batch promotes nothing, so the
fallback can still send the one `emotion` event).

**Task 2 — `user_emotion.classify_user_emotion` (own commit).**
`def classify_user_emotion(text: str) -> str` in `server/src/server/user_emotion.py`: pure, no I/O,
no logging, returns a member of `VALID_EMOTIONS`, `FALLBACK_EMOTION` by default, accents and case
ignored, deterministic. Fires only on explicit statements (for example "estoy triste", "me alegra",
"qué rabia", "no puedo creerlo"); a negation or a question stays `neutral` (D-7). Table-driven
tests with invented sentences, including the false-positive traps (negation, quotation, "no estoy
triste", a question about feelings).

**Task 3 — Plain-text prompt and a smaller parser (core commit).** `_STREAMING_OUTPUT_CONTRACT`
says only "plain text, no JSON, no tags"; `streaming_protocol` drops `parse_streaming_emotion`, the
`EMOTION:` start regex and any `Preamble`; the body validators stay.

**Task 4 — Orchestration (core commit).** At the start of the turn `streaming` sets
`state.pending_emotion = classify_user_emotion(message)`; the preamble step disappears;
`_consume_body` promotes it just before the first audio; `record_text_turn` receives that emotion;
every other streaming entry point behaves as before.

**Task 5 — Instruments (classifier set in the Task 2 commit, adaptation in the core commit).** The
labelled set above lives in the tests of Task 2 and reports its agreement. The scripts under
`scripts/` keep running without the tag grammar (the strict 0057 shape names stay: they now name
what a model wrote although it was not asked to).

**Task 6 — Measurement (Pipec).**

```powershell
just diagnose-stream --variants full full_repeat --seed 57 --structured-runs 0 --output docs/evals/0059-user-emotion-seed57.md
just diagnose-stream --variants full full_repeat --seed 59 --structured-runs 0 --output docs/evals/0059-user-emotion-seed59.md
```

The executor writes `docs/evals/0059-user-emotion-apart.md` (conditions table as in the 0058 record,
the gate table by the rules above, time to first speech, tag-anyway share). Numbers only.

**Task 7 — Documentation truth (after the gate).** ADR 0018 `Accepted`, ADR 0017
`Superseded by 0018`, `current-state.md` and its diagram, the roadmap row of the streaming
repair, the plan boards and indexes (`NOW` empty, next free number 0060), this plan moved to
`completed/`.

## Non-goals

The robot's expression and its event; a model-based classifier; any retry; a schema-constrained
stream; rescuing a reply that starts with a tag; touching the classic `/transcribe` route; a
metadata field on stored turns; guarding JSON or a fence in the middle of a reply.

## Verification

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy --config-file=pyproject.toml server/src robot/src
uv run pyright
uv run pytest -m "not slow and not hardware and not eval"
uv run python scripts/check_reserved_terms.py
just gate
```

plus `ruff check` and `ruff format --check` over the explicit paths of every `scripts/` file touched.

## Completion criteria

1. Tasks 1 to 5 landed (commit grouping per D-8), each new test observed RED first.
2. `just gate` green; the test count recorded against `main`.
3. OpenAPI byte-identical (`test_api_contract`); `robot/` untouched; `.env.example` untouched.
4. Task 6's gate met in both seeds, recorded in `docs/evals/0059-user-emotion-apart.md`.
5. ADR 0018 `Accepted`; state, diagram, roadmap, boards and indexes agree.
6. Pipec's acceptance on real hardware: five small-talk turns and one turn with memory with no
   fallback phrase, the console turns end `outcome=ok`, nothing like a tag is spoken.

## Rollback

Each commit is independent enough to revert in reverse order; nothing under `server/src` merges
unless Task 6 met its gate. The wire, the schema, the robot and the settings are untouched.

## Execution record

*(Filled in during execution.)*

## Closure

*(Filled in when the plan closes.)*
