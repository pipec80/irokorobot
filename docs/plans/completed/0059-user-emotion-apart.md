# 0059 — The user's emotion is decided apart from the streamed reply

> **Status:** `Closed 2026-10-08` — code complete, the gate of Task 6 **met in both seeds**
> ([record](../../evals/0059-user-emotion-apart.md)); the branch awaits Pipec's PR. Pipec's
> acceptance on real hardware was done on 2026-10-08 (cases 1, 3, 4 and 5; case 2 cannot be
> exercised until CM-2; one reply in French is an open finding, see *Closure*). Written 2026-10-08 after Plan 0058
> closed without meeting its gate, and **promoted by Pipec on 2026-10-08** ("avancemos con esas 7
> tareas"), who fixed decisions D-1 to D-8 in the planning conversation. The protocol it
> implements is [ADR 0018](../../adr/0018-user-emotion-decided-apart.md) (`Accepted` by the gate);
> it supersedes the never-accepted [ADR 0017](../../adr/0017-streaming-reply-protocol.md).

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

Branch `feat/0059-user-emotion-apart`, from `main` at `eaabbe1`. One plain branch, no worktree.
Pipec authorised subagents (Sonnet) for this plan: one for the classifier, one for ADR 0018, one
for the core streaming change; none committed, the executor did. Two further read-only agents
audited the finished branch (see *Audit*).

| Part | Commit | RED observed (reason) | GREEN |
|---|---|---|---|
| Plan + skeleton | `6a11fac` | n/a | n/a |
| ADR 0018, ADR index, ADR 0017 status | `74d4f2b` | n/a (docs) | `ruff`, reserved terms clean |
| Task 2 classifier | `e02c49d` | 34 failing (`'neutral' == '<label>'`: the skeleton never fires) | 115 |
| Task 2 audit fix | `2edb49d` | 4 failing: three false positives found by the executor's adversarial audit ("quiero llorar de risa" read as sadness, "qué pena tengo de preguntarte" read as sadness, "dime qué rabia da esto" read as anger) | 118 |
| Tasks 1, 3, 4 and the instrument adaptation of 5 | `9739ea7` | 33 failing + 53 errors (the fixture patches `streaming.classify_user_emotion`, absent) + 2 collection `ImportError` | `just gate` 2289 passed; mypy, pyright, ruff, `check_reserved_terms`, `pip-audit` clean |

Checks by the executor beyond the tests: 20 000 random replies cut at random points give the same
verdict (speak or fall back) as the whole text, 0 mismatches; a 300 KB utterance classifies in
about 200 ms; the OpenAPI is identical (`test_api_contract`, 9 passed); `robot/` and
`.env.example` untouched.

### Rulings

- **R-1.** The plan said "cherry-pick Tasks 1, 2, 4 and 5 of Plan 0058". That was wrong:
  0058's Task 4 counted *tolerated* tags (no meaning once no tag is requested) and its Tasks 1 and
  2 sit on the tag-start grammar that this plan removes. They were re-implemented on the
  plain-text design, using the abandoned branch only as a reference.
- **R-2.** Five files outside *Permitted files* were touched, all trivially:
  `server/src/server/llm.py` (a stale comment about the tag protocol) and four tests that fed
  `EMOTION:joy` deltas into fake replies (`test_diagnose_stream_protocol.py`,
  `test_stream_diagnosis_variants.py`, `tests/integration/test_conversation_text_log.py`,
  `test_sensitive_logging.py`). They are accepted as part of this plan.
- **R-3.** The core commit groups Tasks 1, 3, 4 and the instrument adaptation (D-8).

### Audit (two read-only agents on the finished branch, plus the executor)

No Critical finding: in 2067 targeted cases and 19 000 random delta sequences through the real
pipeline there was never zero or a second `emotion` event, audio before `emotion`, a stream
without audio or terminal event, or a recorded fallback; the evaluator and production agreed in
every case. Findings, all to be fixed with a test seen RED first **after** Pipec's measurements
of `9739ea7` finish (so that the measured code does not change under the run):

| # | Severity | Finding | Fix |
|---|---|---|---|
| A-1 | Medium (proved) | A tag wrapped in underscores (`_EMOTION_: joy`, `EMOTION_:`, and a reply that *starts* `_EMOTION:joy_`) is spoken, recorded and counted VALID: `_` is a word character for the regex. Contradicts D-6. | `(?<![^\W_])emotion[\W_]{0,3}...` and a start check that strips leading `_*`. |
| A-2 | Important (test gap, proved by mutation) | Nothing pins the `emotion` event emitted at the end of a stream that ends on an undecided prefix (`E`, a backtick). | Integration tests for `["E"]` and `["`"]`. |
| A-3 | Minor | Emotion is promoted at the first non-blank content, not "just before the first audio after a validated batch": ADR 0018 §3, the `_consume_body` docstring and a test comment say otherwise. The wire is valid; the *value* on a fallback depends on how tokens split. | Reword the three texts. |
| A-4 | Minor | Tag guard bypasses: four or more symbols between `EMOTION` and the colon, fullwidth Latin letters, zero-width characters, a sentence terminator between them (`EMOTION.: x`, the splitter cuts first). | NFKC and drop format characters before matching; document the rest as limits. |
| A-5 | Minor | The classifier reads quoted or requested text as the user's feeling ("Traduce estoy triste al inglés", "Repite después de mí estoy furioso", "Mi madre piensa que estoy enojado", "Traduce: me alegra verte", "tengo ganas de llorar de la risa"); the neutral set was tuned in-sample. | More blockers (`traduce`, `repite`, `di`, `diga`, `llame`, `lee`, `cita`, `piensa`, `cree`, `opina`), `:` no longer splits clauses, `de la risa`; the audit's phrases join the neutral set. |
| A-6 | Minor | Classifier time is quadratic in the number of matches (100 KB of `no estoy triste ` took 12.5 s); not reachable today (STT is capped at 30 s, `MAX_TURN_MESSAGE_CHARS` is 4000). | Cap the text it reads. |
| A-7 | Minor, latent | `_consume_body` sets `state.emotion = None` when `pending_emotion` is `None`. Unreachable through the pipeline. | Raise `RuntimeError`. |
| A-8 | Minor | `text_turn.record_text_turn` docstring still says "Emotion detected during generation". | Reword (one file outside *Permitted files*, ruling R-2). |
| A-9 | Decision kept | A stream cut inside a forbidden prefix (`E`, a lone backtick) is spoken and recorded, as ADR 0018 §4 says. | Stays; listed under *Known limits*. |
| A-10 | Accepted | `llm_elapsed_ms` is a drive-by extraction from the audit of Plan 0058 (F-7), not a task of this plan (ruling R-4). | None. |

### Known limits and what is left undone

- A fence or JSON in the **middle** of a reply is still spoken (non-goal).
- A reply that **starts** with a tag still falls back (D-6); none did in the 480 streams of Task 6.
- The classifier is silent for most turns (precision-first); it does not read sarcasm or
  context ("estoy feliz porque murió un perro" is read as joy: the user said it).
- The tag guard does not catch more than three symbols between `EMOTION` and the colon, nor a
  sentence terminator between them (`EMOTION.:`); ADR 0018 §4 lists them as known limits.
- `scripts/stream_diagnosis_report.py` keeps prose about "the `llm_streaming.py` claim", which the
  new header no longer makes (harmless; to clean up).
- The robot's facial *expression* is not designed (name `expression` reserved by ADR 0018).
- No end-to-end rate of a spoken turn is measured (the instrument runs the generator only).
- The classifier was measured on a labelled set of invented sentences (66 plus the audit's), not
  on real speech; its recall on explicit statements was 85.7 % of 28 in the first set.
- Hardware acceptance (completion criterion 6) was done by Pipec on 2026-10-08 with the
  limits recorded in *Closure*.

## Closure

**Measurement (Task 6, 2026-10-08, final code `228b146`).** `full` fell back in 0 of 60 context
and 0 of 60 public streams in seed 57 and in seed 59 (gate: at most 3 of 60); 0 undue accepts, 0
split-dependent replies, no stream started with a tag anyway; time to first speech did not get
slower (indicative only). Record: [`docs/evals/0059-user-emotion-apart.md`](../../evals/0059-user-emotion-apart.md).

**Verification.** `just gate` 2315 passed (2099 on `main` when Plan 0057 closed), ruff, ruff
format, mypy, pyright, `check_reserved_terms` and `pip-audit` clean; OpenAPI byte-identical
(`test_api_contract`); `robot/`, `.env.example`, the settings and the dependencies untouched.

**Commits** (branch `feat/0059-user-emotion-apart`): `6a11fac` plan and skeleton, `74d4f2b` ADR
0018, `e02c49d` and `2edb49d` classifier, `9739ea7` core change, `8c63cbb` audit fixes, `228b146`
audit record, plus the documentation commit of this closure. PR: to be opened for Pipec's review and
merge (the PR number is in the PR itself).

**What remains open (so it is not forgotten):**

1. **Pipec's acceptance on real hardware (criterion 6): done 2026-10-08, with two limits.**
   Two sessions on the development laptop (microphone, Piper, Ollama `qwen2.5:3b`, streaming on),
   13 turns, every one ended `outcome=ok` with no `protocol_fallback`; the robot received exactly
   one `emotion` before the first audio each time (`neutral` in 11 turns, `joy` in one and
   `sadness` for a sentence in which the user said they were a little sad); with
   `LOG_CONVERSATION_TEXT=true` the spoken sentences of three turns carried no tag, label or
   fallback phrase. **Not exercised:** the turn with memory (production sends no history or memory
   to the prompt without a verified identity, so it cannot be tested before CM-2), and the spoken
   text of the first ten turns was not logged.
2. **Plan 0058's evidence PR** (#170, docs only) is separate and unmerged; this branch cites its
   record in backticks, not as a link.
3. **The robot's facial expression** (a transient reaction for the future face, which need not
   equal the user's feeling): no plan; ADR 0018 reserves the name `expression`.
4. **A model-based classifier** behind `classify_user_emotion`, when a larger model exists; today
   most turns are `neutral`.
5. **The end-to-end rate** of a spoken turn (STT → controller → TTS → robot) is not measured; the
   instrument covers the generator only.
6. **Known limits of the tag guard** (above) and of the middle-of-reply JSON or code fence, which
   is still spoken.
7. **Cleanup:** the report prose about the old `llm_streaming.py` header in
   `scripts/stream_diagnosis_report.py`; the diagnosis instrument's `undue_accept` and
   `contract_first` variant now describe a protocol that no longer exists and could be simplified.
8. **The language of the reply (found in acceptance, open).** In one turn the model answered
   in French although the transcript was Spanish. The benchmark does not measure the language of a
   reply, and neither the old nor the new streaming contract (nor the character prompt) tells the
   model to answer in Spanish, so it is not known whether it predates this plan; Pipec's rule is that
   all voice is in Spanish. Candidate fix, not done: one sentence in the streaming contract, with a
   test, and a language check in the instrument. It changes the prompt that was measured, so one seed
   would have to be repeated.
9. **CM-2 is unblocked** by this plan (the streaming repair was its hard gate) but is not started;
   the next free plan number is 0060.
