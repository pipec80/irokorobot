# 0057 — Streaming-protocol fallback diagnosis

> **Status:** `Closed` 2026-10-06 — written 2026-10-05 after Plan 0056 closed and two
> reviews of its follow-up (an author analysis and an independent senior audit), and
> revised the same day after an independent review of this draft. **Promoted by Pipec
> on 2026-10-06**, who confirmed decisions D-1 to D-7 exactly as written below, and
> executed the same day from `feat/0057-stream-protocol-diagnosis` (see the execution
> record at the end). The PR number and squash SHA are added after the merge.
>
> **Queue position (Pipec, 2026-10-05):** after CM-1 (Plan 0051, closed 2026-10-06) and before CM-2. The
> streaming repair that follows this diagnosis is a hard gate of CM-2, the first slice
> that puts memory or history in the prompt; nothing in CM-1 depends on it.
>
> The review found, and this revision fixes: a probe that counted errors and cut
> streams as runs; a rule that read a long first wait as a withheld stream; a headline
> and a dominant shape that mixed production with experiments; ten duplicate variants;
> over-reading of small samples; "in every run" claimed over failed runs; a percentile
> one rank short; and a dependence on a historical plan for a current rule.
>
> A second review of the revision found, and this one fixes (plus a wording point: a
> spread-out arrival at the client is *compatible with* incremental generation, never
> proof of when it ended): a probe that crashed on a
> reply whose `emotion` is a list or a dict (losing every stream measured before it); a
> noise control aggregated across turns instead of measured on each comparison's own
> turns (and absent for public turns); and a burst read as proof that Ollama withholds
> the reply.

> **For agentic workers:** REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. Execute only while this is the
> explicitly authorized `NOW` item, in a new session. **Pipec's rules win over the
> skills:** one plain branch from `main` (`git checkout -b`), never a git worktree
> (treat any "create a worktree" instruction as "create the branch"), no subagents
> unless Pipec asks, and this plan lives under `docs/plans/`, not
> `docs/superpowers/plans/`. Implement exactly the tasks below, in order, one commit
> per task. If evidence contradicts the plan, stop and report the conflict instead of
> redesigning. Pipec runs every local process (Ollama, the diagnosis itself); you
> record what it prints, outcomes only.

**Goal:** Say, with counts and without guessing, **why** the streaming protocol drops
to the fallback phrase: which shapes the failures take, which factor of a turn
causes them, whether the validation depends on how the tokens are split, and whether
the premise behind the protocol (Ollama withholds schema-constrained output until the
end) is true. Nothing is repaired here.

**Architecture:** Read-only toward production. A new command (`just diagnose-stream`)
streams the golden and public turns through the **unchanged** production generator
under variants that each remove or move one factor, in a seeded shuffled order, and
reduces every reply in memory to closed values (an enum for the failure shape, the
verdict of the whole text against the verdict production reached, timings, counts).
Eight small modules under `scripts/`, each with one responsibility; the existing
stream evaluator gains one counter and `eval_chat` exports one helper. The baseline is
the `full` variant (production's own prompt): the headline rate and the dominant shape
describe it alone, and every other variant is an intervention read apart, against
`full` on the very turns it ran. Every rule that turns a number into a reading is a
constant fixed **before** the run.

**Tech Stack:** Python 3.12, httpx, pydantic, pytest (+ xdist). No new dependency.

**Spec:** the roadmap row
[*Streaming-protocol fallback repair*](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio),
[0056 measurements](../../evals/0056-voice-pipeline-measurements.md#1-streaming-protocol-fallback-0049-o-04),
[0049 O-04](../open/0049-server-objective-conformance-audit.md), and the rules in
*Protocol rules this plan relies on* below. Those rules are stated here from the code
and its tests, which outrank a plan under the repository's own order, and from
[`current-state.md`](../../architecture/current-state.md); no historical plan is a
source of this plan.

**Rehearsal (2026-10-05).** Every code block below was applied onto a scratch state of
`main` (`4078aba`) and reverted. With them applied: `just gate` passed **2038 tests**
(baseline 1807, so +231: 230 in the seven new test files and one for the classifier's
counter), `ruff check` and `ruff format --check` over the explicit file paths, `mypy` and
`pyright` were clean. The first draft's blocks had their RED written together with
their code; after each of the two reviews, every corrected behaviour was written
test-first and its RED was observed for the stated reason (`ImportError: cannot import
name 'VARIANT_DESCRIPTIONS'`, `'ArrivalPattern'`, `'baseline_observations'`,
`'probe_reading'`; `TypeError: unhashable type: 'list'` and `'dict'` from a reply whose
`emotion` is a list or a dict; `AttributeError: ... no attribute 'noise_pp'`; a `TypeError`
from the old probe result in the CLI tests; the closing log line asserting
`baseline_fallback_rate`; the CLI call that did not pass `constrained`). The other
tasks' RED steps must still be observed during execution. One full `just gate` run
during the rehearsal reported
`tests/slow/test_speaker_embedding_real_model.py::test_the_real_encoder_returns_the_frozen_shape`
failing; it passed alone and in the next full runs and touches none of this plan's files
(its workers copy the same model files in parallel, the leading but unproven hypothesis):
recorded, not attributed. Not rehearsed: the live path against a real Ollama (it was not
running), Task 8 and Task 9. Treat the blocks as rehearsed code, not as a substitute for
the RED/GREEN record each task requires.

## Global Constraints

- Audio contract everywhere: WAV · 16 000 Hz · mono · int16. This plan touches no audio;
  nothing here may start touching it.
- No real household data, voice or name in any tracked file, test, prompt, doc or
  commit message; the golden turns and the public turns are the synthetic ones that
  already exist (`scripts/check_reserved_terms.py` guards this).
- Ollama stays the only LLM runtime; no cloud provider (ADR-0004).
- No `print()` in `server/src` or `robot/src`; this plan edits neither.
- Type hints on every signature, Google docstrings on public APIs, `ruff` clean over
  the **explicit paths** of every `scripts/` file touched (`just lint` skips `scripts/`
  but the pre-commit hook does not), `mypy server/src robot/src` clean.
- Neither a log line, an exception message, an `Observation`, a report nor a commit
  message may carry any part of a model reply: only closed enums, counts, flags,
  lengths and milliseconds.
- Every new test is observed RED for the stated reason before its implementation.
- A commit title is at most 72 characters (commitizen rejects longer ones silently):
  check `git log -1` after every commit.

## Review Focus

Inputs the spec implies that are most likely to bite, each pinned by a test in its
owning task:

1. A reply whose tag or fence is split across deltas (`EMO` + `TION:`) must be compared
   with the verdict of the whole text, and production speaking what the whole text
   rejects must be counted as an *undue accept*, never as a pass (Task 4; the defect
   itself is pinned in Task 2).
2. The probe must never turn an error into a quiet run, nor a bad reply into a crash: an
   `{"error": ...}` line after a `200`, a stream that ends without `done`, a malformed
   line and a reply outside the schema are four different closed statuses; a reply whose
   `emotion` is a list, a dict, `null` or a number is *off-schema*, not an exception; an
   unexpected failure inside a run is an *incomplete* run, logged by type, and the report
   of the streams already measured is still written. None of them votes in the verdict
   (Tasks 5 and 7).
3. A burst at the client is not proof that Ollama withholds the reply: fast generation
   and buffering look the same. The pattern reads the spacing between chunks, a long wait
   before the first chunk counts for nothing, unclear evidence is *inconclusive*, and the
   report reads a burst only against the plain-text control and never as "the header is
   right" (Tasks 5 and 6).
4. The headline rate and the dominant failure shape describe `full` only, per source; an
   intervention's shape or rate can never become the baseline's (Task 6).
5. A comparison is made only on turns where `full`, the variant and the `full_repeat`
   control all have every expected run graded; the noise is measured on exactly those
   turns, turn by turn, so opposite swings never cancel; without a complete control the
   row is *incomplete*, never a signal; the reading is *exploratory*, never a cause
   (Tasks 3 and 6).
6. A variant that sends the same inputs as another must not run (a bare question on a
   turn with no person and no history equals `no_context`), every turn, public ones
   included, has its own noise control, and the variants are interleaved by a seed
   (Task 3).
7. "Fell back in every run" requires every expected run to be graded and to have fallen
   back; a turn with one fallback and four provider errors is *incomplete* (Task 6).
8. Percentiles are nearest-rank for p50 and p95, checked on sizes where rounding and the
   ceiling differ (Task 6).
9. No model text anywhere: the classifier returns only enum members, an `Observation`
   has no text field and a canary reply never reaches one (Tasks 1 and 4); the report
   only ever receives observations, so it cannot carry a reply (Task 6).
10. `prompt_chars` must equal what the generator really sends, for production's
    generator and for the contract-first one (Task 3), and
    `python scripts/diagnose_stream_protocol.py` must start under direct execution
    (Plan 0056 found the same bug in `eval_chat.py`; Task 7).

---

## Why this plan exists

| Claim in the follow-up | What the evidence supports | Kind |
|---|---|---|
| The streaming fallback is 29.17 % | 35 of 120 observations of **the generator** with `qwen2.5:3b`, on a synthetic set; not telemetry of microphone → server → audio | measured, limited |
| "It is the memory context" (56.67 % vs 1.67 %) | The "context" set mixes four factors (memory block, active person, history, the question itself) and runs first, all together; the cause is unknown | **unknown → ablation** |
| "A few cases fail every time" | 34 failures over 12 cases × 5 runs imply **at least 7** cases failed at least once (ceil(34/5)); not which, not why | partly known |
| What shape the failures take | The report counts "invalid protocol" only | **unknown → failure shapes** |
| Production validates the reply like the whole text would | It does not: `_consume_body` validates the start of the body once, with the first fragment (Plan 0056's own test pins `["EMOTION:joy\nEMO", "TION:anger\nhola"]` as **valid** while the whole text is invalid) | **defect → pinned here, repaired later** |
| Ollama withholds schema-constrained output until the end | A statement in the header of `llm_streaming.py`; never measured with this Ollama and model | **unmeasured → probe** |
| What was measured | Ollama version, model digest, generation options and prompt length were not recorded | **unknown → facts** |

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | Closed failure shapes | "what shape do the failures take" |
| 2 | Fragmentation consistency, defect pinned | "does the verdict depend on the split" |
| 3 | Variants, seeded order, contract-first prompt | "which factor causes it" |
| 4 | One closed observation per streamed reply | per-reply facts, timings, undue accept |
| 5 | Ollama facts and the structured-stream probe | "what ran" and the unmeasured premise |
| 6 | Aggregation and counts-only report | the readings |
| 7 | `just diagnose-stream` | the instrument |
| 8 | Run it, record it, apply the rules | the evidence |
| 9 | Documentation truth | the corrections |

## Protocol rules this plan relies on

As implemented today (`server/src/server/streaming_protocol.py`, `streaming_render.py`,
`llm_streaming.py`) and pinned by `tests/unit/test_streaming_protocol.py`,
`tests/unit/test_eval_stream_protocol.py` and the streaming integration tests;
[`current-state.md`](../../architecture/current-state.md) states that `done` is guarded
behind at least one audio chunk and that a failed stream speaks a fallback phrase:

1. The model is asked, in the last paragraph of the system prompt, to answer in plain
   text whose first line is exactly `EMOTION:<emotion>`.
2. A reply is valid when its start matches `^EMOTION:\s*(\w+)\s*\n` (position 0, a
   line break right after the word) and the body that follows, once leading blanks are
   stripped, does not start with `{`, `[`, a code fence or another `EMOTION:`.
3. While the start does not match, production keeps reading to the end of the stream; at
   the end it falls back. An invalid body start falls back at once. An unknown emotion
   becomes `neutral`.
4. A fallback discards the whole reply and speaks the fixed phrase; nothing invalid is
   spoken and there is no retry. Plain text without the tag is therefore a fallback.
5. The body start is validated once, with the first non-blank fragment (the defect this
   plan pins and measures).

A rescue of plain text, or any other change of rule 4, is a decision the repair plan
must state and, because the rule lives in code and tests, record in an ADR.

## Decisions

Proposed 2026-10-05; **confirmed by Pipec on 2026-10-06** (D-1 to D-7, exactly as
written) when he promoted the plan; they are not asked again.

1. **D-1 — Diagnosis only.** No file under `server/src` is edited: not
   `streaming*.py`, `llm_streaming.py`, `llm.py`, `characters/` nor anything else.
   The fallback behaviour Pipec hears is unchanged by this plan.
2. **D-2 — The whole text is the reference.** A reply is *correct* when it is judged
   valid as one single delta (rules 2 to 4 above, and the unit test of Plan 0056 that
   pins this). Production speaking a reply the whole text would reject is an **undue
   accept**; the verdict changing with the split is **split-dependent**.
3. **D-3 — The ablation and its control.** Per golden turn: `full`, a `full_repeat` that
   measures the noise of repeating one condition, `no_context`, `contract_first`, and
   `question_only`, `no_person` and `no_history` only where they send something the
   other variants do not (a turn with no person and no history has no distinct
   `question_only`: it equals `no_context`). Per public turn: `full`, `full_repeat`,
   `contract_first` and `public_with_context` (the public question with a golden context
   borrowed in rotation). Every turn has its own control, because the noise of a
   comparison is measured on that comparison's turns. Default **5 runs**, seed **57**:
   100 units, 500 streams, plus the probes. `question_only` removes three factors at
   once; it is not an estimate of the question's own effect, which `public_with_context`
   approaches from the other side.
4. **D-4 — Baseline and interventions.** The headline rate, the dominant shape and the
   concentration describe `full` alone. Every intervention is compared with `full` on
   the turns where both have every expected run graded, and its reading is
   *exploratory*: a signal must be confirmed with another seed before the record
   attributes a cause. The rules below decide a *reading*, never an automatic repair;
   the repair plan is written only when Pipec asks for it.
5. **D-5 — The fragmentation defect is documented and pinned, not repaired here.** It
   lives in `streaming_render.py` and `streaming_protocol.py`, outside this plan's
   permitted files, and keeping diagnosis and repair in separate plans keeps each
   conclusion independent of the other. The pre-repair behaviour stays measurable at its
   commit in Git. The defect becomes the **first task of the repair plan** and is
   recorded as such in the roadmap in Task 9. (Pipec's standing "fix everything found"
   policy applies inside the permitted files; this finding exceeds them, so it is
   reported and given an owner, as that policy asks.)
6. **D-6 — No repair option is pre-decided.** Retry once, a tolerant tag grammar,
   rescuing plain text as `neutral` (a change of rule 4), removing the emotion from the
   LLM in streaming, a schema-constrained stream or another model: all stay open until
   the readings exist.
7. **D-7 — The facts are part of the evidence.** Every report states the Ollama
   version, the model digest, that production passes no generation options, the shuffle
   seed, the variants and the prompt size per variant.

## Rules fixed before the run

Constants in `scripts/stream_diagnosis_stats.py` and `scripts/stream_diagnosis_probes.py`.

| Id | Reading | Rule |
|---|---|---|
| R-1 | The fragmentation defect on live traffic | Count `undue_accept` and `split-dependent` observations (all variants). Any above 0 confirms it on real model output. It enters the repair plan whatever the number: it is a correctness defect, not a rate. |
| R-2 | The dominant failure shape | In `full`, per source: a shape holding **at least 50 %** of that source's fallbacks is *dominant*; otherwise *mixed*. Shapes of an intervention are shown apart and never feed this. The candidate it points to is in the table below. |
| R-3 | An intervention shows a signal | On the turns where `full`, the variant and the `full_repeat` control all have every expected run graded: removing a factor lowers the fallback rate by **at least 15 percentage points** (adding the context, for `public_with_context`, raises it by that much) **and** the change exceeds the noise **of those very turns**: the mean absolute difference, turn by turn, between `full` and `full_repeat` (opposite swings on two turns never cancel). A row with no complete control is *incomplete*, never a signal. The reading is *exploratory signal*; **confirm with another seed** (`--variants full full_repeat <variant> --seed 58`) before the record calls it a cause. With one turn per factor (`no_person`, `no_history`), one fallback is already 20 points: read those two as hints only. |
| R-4 | Concentration | Report, in `full`, the turns with at least one fallback, the turns that fell back in **every expected run** (all runs graded and all fallbacks) and the **incomplete** turns. (0056's arithmetic floor was 7 of 12 turns affected.) |
| R-5 | Execution order | If the best and the worst **quarter** of the execution order differ by **at least 15 points**, repeat once with `--seed 58`; both runs are recorded, neither decides alone. |
| R-6 | Do the chunks of a schema-constrained reply arrive spread over time | Per run: it must end `done`, with no error event, and its assembled reply must satisfy the schema (a non-text `emotion` is off-schema, never a crash), else it is an error, incomplete or off-schema run and never votes. Pattern of a complete run: from five chunks, **at least half** of the gaps between chunks spaced 20 ms or more is *incremental*; **a quarter or fewer** is a *burst at the client*; between is *inconclusive*; a long wait before the first chunk counts for nothing. Verdict: at least **three complete runs** and a majority. *Incremental*: the reply reached this client spread over time, which is compatible with incremental generation: streaming with a JSON schema is a candidate protocol and this is evidence against the `llm_streaming.py` claim, though a client cannot see when generation ended. *Burst*: **unproven**: a burst at the client is what a withheld reply, fast generation and buffering all look like; it is read only against the plain-text control run alongside (the same question without `format`): a control that arrives spread over time while the schema reply arrives as a burst *differs* and is consistent with withholding, still not a proof of the cause; two bursts say this client cannot tell. *Inconclusive*: **no conclusion**, never "the header is right". |
| R-7 | Cost of a fallback | Record p50 / p95 (nearest rank) of the time at which production would hand its first sentence, or the fallback, to TTS (TTS excluded), per variant, for valid and for fallback replies. No threshold: it says how long a useless turn lasts. |

Shape → candidate repair (a pointer for the repair plan, **not** a decision):

| Shapes | Candidate |
|---|---|
| `tag_wrapped`, `tag_punctuation`, `tag_same_line`, `leading_whitespace`, `other_label` | a tolerant tag grammar, specified with valid and invalid examples |
| `no_tag`, `text_before_tag`, `tag_truncated` | retry once, or rescue the text as `neutral` (a change of rule 4) |
| `json_start`, `body_json`, `fence_start`, `body_fence` | keep rejecting; look at the prompt or the model |
| `second_tag` | the prefix validation (the fragmentation defect) |
| `empty`, `tag_only` | retry once |

## Required reading

- `AGENTS.md` and `docs/architecture/implementation-guardrails.md`.
- ADR-0004 (local-only runtime), ADR-0012 (the terminal `done`/`error` event; it does
  **not** govern the tag rules).
- *Protocol rules this plan relies on*, above, and the code and tests they cite.
  [Plan 0022](../completed/0022-p0-reliable-streaming-output.md) and
  [Plan 0056](../completed/0056-voice-pipeline-reliability-and-diagnostics.md) Task 4 are
  history that explains how the protocol and its evaluator came to be; no decision in
  this plan depends on them.
- `docs/architecture/current-state.md` (Working memory and Episodic memory rows: today
  every turn runs with `history=None` and no memory context).
- `server/src/server/{llm_streaming,streaming,streaming_protocol,streaming_render,sentences}.py`
  (read-only), `scripts/{eval_chat,eval_stream_protocol,longitudinal_eval_metadata}.py`.

## Permitted files

- New: `scripts/stream_failure_shapes.py`, `scripts/stream_fragmentation.py`,
  `scripts/stream_diagnosis_variants.py`, `scripts/eval_stream_diagnosis.py`,
  `scripts/stream_diagnosis_probes.py`, `scripts/stream_diagnosis_stats.py`,
  `scripts/stream_diagnosis_report.py`, `scripts/diagnose_stream_protocol.py`.
- Modified: `scripts/eval_stream_protocol.py` (one counter), `scripts/eval_chat.py`
  (one extracted helper), `justfile` (one recipe).
- Tests: `tests/unit/test_stream_failure_shapes.py`,
  `test_stream_fragmentation.py`, `test_stream_diagnosis_variants.py`,
  `test_eval_stream_diagnosis.py`, `test_stream_diagnosis_probes.py`,
  `test_stream_diagnosis_report.py`, `test_diagnose_stream_protocol.py`; edits to
  `test_eval_stream_protocol.py`.
- Docs: `docs/evals/0056-voice-pipeline-measurements.md` (two corrections),
  new `docs/evals/0057-stream-protocol-diagnosis.md` and its raw run reports,
  `docs/evals/README.md`, `docs/roadmap/cognitive-roadmap.md`,
  `docs/architecture/current-state.md` and
  `docs/architecture/diagrams/current-state.{json,html}`,
  `docs/runbooks/operator-manual.md`, `docs/plans/README.md`,
  `docs/plans/open/README.md`, this plan, and the O-04 note in
  `docs/plans/open/0049-server-objective-conformance-audit.md`.

No URL, status code, response field, streaming event, audio contract, database schema,
migration or dependency changes. **`server/src/**` is read-only.**

---

## Task 0: Revalidate the baseline

**Files:** this plan's evidence note only. No production change.

- [ ] **Step 1: Branch.** `git checkout main && git pull`, confirm a clean tree, then
  `git checkout -b feat/0057-stream-protocol-diagnosis`. Record the base SHA. Do not
  discard other uncommitted work.
- [ ] **Step 2: Baseline.** Run `just gate`; record its outcome and test count (the
  baseline after Plan 0056 was 1807). A pre-existing failure is reported, not hidden.
- [ ] **Step 3: Symbols.** Confirm each symbol this plan imports exists as described,
  and note any difference:
  `rg -n "class _StreamClassifier|def classify_deltas|def public_turns|class StreamTurn" scripts/eval_stream_protocol.py`,
  `rg -n "def _consume_body|def _consume_preamble|class StreamState" server/src/server/streaming_render.py`,
  `rg -n "def parse_streaming_emotion|def validate_streaming_body_start" server/src/server/streaming_protocol.py`,
  `rg -n "_STREAMING_OUTPUT_CONTRACT|def _build_messages|def _build_streaming_base_prompt|def _stream_local_response|def _streaming_system_prompt|ollama_chat_stream" server/src/server/llm_streaming.py`,
  `rg -n "_OLLAMA_RESPONSE_SCHEMA" server/src/server/llm.py`,
  `rg -n "_GOLDEN_PATH|_REPORT_DIRECTORY|def load_suite|def select_cases|def write_report|async def _run_stream_mode" scripts/eval_chat.py`,
  `rg -n "def sanitize_url" scripts/longitudinal_eval_metadata.py`.
- [ ] **Step 4: Docs inventory.** Record
  `rg -n "29[.,]17|56[.,]67|golden cases repeated|streaming-protocol fallback" docs --glob "*.md"`
  so Task 9 knows every sentence to review.
- [ ] **Step 5: Known intermittent.** During the rehearsal one full run failed
  `tests/slow/test_speaker_embedding_real_model.py::test_the_real_encoder_returns_the_frozen_shape`
  and passed alone and in the next full run. If it reappears, capture the traceback first
  and do not attribute it to this plan without evidence.
- [ ] **Step 6: Ollama is not needed yet.** Only Task 8 runs it, and Pipec starts it.
  `server/src/**` stays untouched from here to the end: `git diff --stat main -- server`
  must stay empty.

---

## Task 1: Closed failure shapes

**Files:**
- Create: `scripts/stream_failure_shapes.py`
- Test: `tests/unit/test_stream_failure_shapes.py`

**Interfaces:**
- Consumes: `server.streaming_protocol.parse_streaming_emotion(buffer) -> tuple[str, str] | None`.
- Produces: `FailureShape` (a closed `StrEnum`) and
  `classify_failure_shape(text: str) -> FailureShape`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_stream_failure_shapes.py`:

```python
"""Closed failure shapes of a streamed reply (Plan 0057, Task 1)."""

import pytest

from scripts.eval_stream_protocol import StreamOutcome, classify_deltas
from scripts.stream_failure_shapes import FailureShape, classify_failure_shape

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

_CASES = [
    ("EMOTION:joy\nHola, ¿cómo estás?", FailureShape.VALID),
    ("EMOTION: joy \nHola", FailureShape.VALID),
    ("EMOTION:unknownemotion\nHola", FailureShape.VALID),
    ("", FailureShape.EMPTY),
    ("  \n", FailureShape.EMPTY),
    ("Hola sin etiqueta", FailureShape.NO_TAG),
    ('{"response": "x", "emotion": "joy"}', FailureShape.JSON_START),
    ("[1, 2]", FailureShape.JSON_START),
    (f"{_FENCE}json\n{{}}\n{_FENCE}", FailureShape.FENCE_START),
    ("\nEMOTION:joy\nHola", FailureShape.LEADING_WHITESPACE),
    (" EMOTION:joy\nHola", FailureShape.LEADING_WHITESPACE),
    ("Claro. EMOTION:joy\nHola", FailureShape.TEXT_BEFORE_TAG),
    ("**EMOTION:** joy\nHola", FailureShape.TEXT_BEFORE_TAG),
    ("EMOCIÓN: joy\nHola", FailureShape.OTHER_LABEL),
    ("Emotion - joy\nHola", FailureShape.OTHER_LABEL),
    ("EMOTION:<joy>\nHola", FailureShape.TAG_WRAPPED),
    ("EMOTION: [joy]\nHola", FailureShape.TAG_WRAPPED),
    ("EMOTION: joy ¡Hola!", FailureShape.TAG_SAME_LINE),
    ("EMOTION:joy Hola\nmás", FailureShape.TAG_SAME_LINE),
    ("EMOTION:joy.\nHola", FailureShape.TAG_PUNCTUATION),
    ("EMOTION:joy,Hola", FailureShape.TAG_PUNCTUATION),
    ("EMOTION:joy", FailureShape.TAG_TRUNCATED),
    ("EMOTION:joy  ", FailureShape.TAG_TRUNCATED),
    ("EMOTION:", FailureShape.TAG_TRUNCATED),
    ("EMOTION: -\nHola", FailureShape.OTHER),
    ("EMOTION:joy\n", FailureShape.TAG_ONLY),
    ("EMOTION:joy\n   ", FailureShape.TAG_ONLY),
    ('EMOTION:joy\n{"response": "x"}', FailureShape.BODY_JSON),
    ("EMOTION:joy\n[1]", FailureShape.BODY_JSON),
    (f"EMOTION:joy\n{_FENCE}json\n{{}}\n{_FENCE}", FailureShape.BODY_FENCE),
    ("EMOTION:joy\nEMOTION:anger\nhola", FailureShape.SECOND_TAG),
    ("EMOTION:joy\n  emotion: anger\nhola", FailureShape.SECOND_TAG),
]


@pytest.mark.unit
@pytest.mark.parametrize("text, shape", _CASES)
def test_every_shape_is_named_exactly(text: str, shape: FailureShape) -> None:
    assert classify_failure_shape(text) is shape


@pytest.mark.unit
@pytest.mark.parametrize("text, shape", _CASES)
def test_valid_shape_agrees_with_the_whole_text_protocol(text: str, shape: FailureShape) -> None:
    """The shape table and the protocol never disagree about speakable text."""
    whole = classify_deltas([text] if text else [])

    assert (shape is FailureShape.VALID) == (whole is StreamOutcome.VALID)


@pytest.mark.unit
def test_the_enum_is_closed_and_every_member_is_exercised() -> None:
    assert {case[1] for case in _CASES} == set(FailureShape)


@pytest.mark.unit
def test_the_classifier_returns_only_enum_members_and_never_echoes_text() -> None:
    canary = "CANARIO-INVENTADO-731"
    for text in (canary, f"EMOTION:{canary}\nHola", f"EMOTION:joy {canary}", f"<{canary}>"):
        shape = classify_failure_shape(text)

        assert isinstance(shape, FailureShape)
        assert canary not in shape.value
```

- [ ] **Step 2: Run it to see it fail.**
  `uv run pytest tests/unit/test_stream_failure_shapes.py -q -p no:cacheprovider`.
  Expected: collection error `ModuleNotFoundError: No module named
  'scripts.stream_failure_shapes'`.

- [ ] **Step 3: Write the implementation**

`scripts/stream_failure_shapes.py`:

```python
"""Closed, content-free classification of a streamed reply (Plan 0057).

The output is one member of a fixed enum, never a slice of the reply: a report can
count shapes without ever holding, logging or storing model text.
"""

from __future__ import annotations

import enum
import re

from server.streaming_protocol import parse_streaming_emotion

_TAG_PREFIX = "EMOTION:"
_WRAPPERS = "<[({\"'«*_`"
_JSON_STARTS = ("{", "[")
_FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
_LABEL_RE = re.compile(r"^\W*(?:emoci[oó]n|emotion|mood|sentimiento|estado)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"\w+")


class FailureShape(enum.StrEnum):
    """Why a streamed reply is, or is not, speakable. Closed: never carries text."""

    VALID = "valid"
    EMPTY = "empty"
    NO_TAG = "no_tag"
    JSON_START = "json_start"
    FENCE_START = "fence_start"
    LEADING_WHITESPACE = "leading_whitespace"
    TEXT_BEFORE_TAG = "text_before_tag"
    OTHER_LABEL = "other_label"
    TAG_WRAPPED = "tag_wrapped"
    TAG_SAME_LINE = "tag_same_line"
    TAG_PUNCTUATION = "tag_punctuation"
    TAG_TRUNCATED = "tag_truncated"
    TAG_ONLY = "tag_only"
    BODY_JSON = "body_json"
    BODY_FENCE = "body_fence"
    SECOND_TAG = "second_tag"
    OTHER = "other"


def _body_shape(body: str) -> FailureShape:
    """Classify what follows a well-formed ``EMOTION:<x>`` line."""
    stripped = body.lstrip()
    if not stripped:
        return FailureShape.TAG_ONLY
    if stripped.startswith(_JSON_STARTS):
        return FailureShape.BODY_JSON
    if stripped.startswith(_FENCE):
        return FailureShape.BODY_FENCE
    if stripped.upper().startswith(_TAG_PREFIX):
        return FailureShape.SECOND_TAG
    return FailureShape.VALID


def _malformed_tag_shape(text: str) -> FailureShape:
    """Classify a reply that starts with ``EMOTION:`` but is not a well-formed line."""
    rest = text[len(_TAG_PREFIX) :].lstrip()
    if not rest:
        return FailureShape.TAG_TRUNCATED
    if rest[0] in _WRAPPERS:
        return FailureShape.TAG_WRAPPED
    word = _WORD_RE.match(rest)
    if word is None:
        return FailureShape.OTHER
    tail = rest[word.end() :]
    if not tail.strip():
        return FailureShape.TAG_TRUNCATED
    if tail[0] in " \t":
        return FailureShape.TAG_SAME_LINE
    return FailureShape.TAG_PUNCTUATION


def _tag_prefixed_shape(text: str, stripped: str) -> FailureShape:
    """Classify a reply whose first non-blank text is ``EMOTION:`` but is not a valid line."""
    if stripped is not text and parse_streaming_emotion(stripped) is not None:
        return FailureShape.LEADING_WHITESPACE
    return _malformed_tag_shape(stripped)


def _unparsed_shape(text: str) -> FailureShape:
    """Classify a reply that does not open with a well-formed ``EMOTION:<x>`` line."""
    stripped = text.lstrip()
    if stripped.startswith(_JSON_STARTS):
        return FailureShape.JSON_START
    if stripped.startswith(_FENCE):
        return FailureShape.FENCE_START
    if stripped.upper().startswith(_TAG_PREFIX):
        return _tag_prefixed_shape(text, stripped)
    if _TAG_PREFIX in text.upper():
        return FailureShape.TEXT_BEFORE_TAG
    if _LABEL_RE.match(stripped):
        return FailureShape.OTHER_LABEL
    return FailureShape.NO_TAG


def classify_failure_shape(text: str) -> FailureShape:
    """Name the shape of one streamed reply, or the part of it production read.

    Args:
        text: The reply as received (may be partial when production stopped reading).

    Returns:
        A ``FailureShape``. ``VALID`` means the text, taken whole, passes the protocol.
    """
    if not text.strip():
        return FailureShape.EMPTY
    parsed = parse_streaming_emotion(text)
    if parsed is not None:
        return _body_shape(parsed[1])
    return _unparsed_shape(text)
```

- [ ] **Step 4: Run it to see it pass, then lint the explicit paths.**
  `uv run pytest tests/unit/test_stream_failure_shapes.py -q -p no:cacheprovider` (66 pass),
  `uv run ruff check scripts/stream_failure_shapes.py tests/unit/test_stream_failure_shapes.py`
  and `uv run ruff format --check` on the same two paths.

- [ ] **Step 5: Commit** — `feat(scripts): classify streaming failure shapes`.

---

## Task 2: Fragmentation consistency, defect pinned

**Files:**
- Create: `scripts/stream_fragmentation.py`
- Test: `tests/unit/test_stream_fragmentation.py`
- Modify: `tests/unit/test_eval_stream_protocol.py` (uses the shared helper)

**Interfaces:**
- Consumes: `scripts.eval_stream_protocol.classify_deltas(deltas) -> StreamOutcome`.
- Produces: `reply_fragmentations(text) -> list[list[str]]`,
  `fragmentation_outcomes(text) -> set[StreamOutcome]`,
  `is_fragmentation_consistent(text) -> bool`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_stream_fragmentation.py`:

```python
"""Fragmentation consistency of the streaming protocol (Plan 0057, Task 2)."""

import pytest

from scripts.eval_stream_protocol import StreamOutcome, classify_deltas
from scripts.stream_fragmentation import (
    fragmentation_outcomes,
    is_fragmentation_consistent,
    reply_fragmentations,
)

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

# Replies production judges the same way however the tokens split.
_CONSISTENT = [
    "EMOTION:joy\nHola, ¿cómo estás?",
    "EMOTION:joy\n",
    "EMOTION:joy",
    "Hola sin etiqueta",
    'EMOTION:joy\n{"response": "x"}',
    "EMOTION:joy\n[1]",
    "",
]

# Replies whose verdict depends on the split TODAY: production validates the start of the
# body once, with the first fragment, so a prefix that is still undecidable ("E", "`")
# is accepted and the rest is never checked. Plan 0057 pins this defect; the repair plan
# flips these into ``_CONSISTENT``.
_INCONSISTENT_TODAY = [
    "EMOTION:joy\nEMOTION:anger\nhola",
    f"EMOTION:joy\n{_FENCE}json\n{{}}\n{_FENCE}",
]


@pytest.mark.unit
def test_every_fragmentation_re_delivers_the_same_text() -> None:
    text = "EMOTION:joy\nHola. ¿Cómo estás? Muy bien."

    for fragments in reply_fragmentations(text):
        assert "".join(fragments) == text
        assert all(fragments)


@pytest.mark.unit
def test_the_family_includes_word_and_punctuation_tokens() -> None:
    assert ["EMOTION", ":", "joy", "\n", "Hola"] in reply_fragmentations("EMOTION:joy\nHola")


@pytest.mark.unit
@pytest.mark.parametrize("reply", _CONSISTENT)
def test_a_reply_judged_the_same_under_every_split_is_consistent(reply: str) -> None:
    assert is_fragmentation_consistent(reply)
    assert len(fragmentation_outcomes(reply)) == 1


@pytest.mark.unit
@pytest.mark.parametrize("reply", _INCONSISTENT_TODAY)
def test_the_known_fragmentation_defect_is_pinned_until_the_repair_plan(reply: str) -> None:
    """Whole, the reply is rejected; split inside its first body token, it is spoken."""
    assert classify_deltas([reply]) is StreamOutcome.INVALID_PROTOCOL
    assert fragmentation_outcomes(reply) == {StreamOutcome.VALID, StreamOutcome.INVALID_PROTOCOL}
    assert not is_fragmentation_consistent(reply)
```

- [ ] **Step 2: Run it to see it fail.**
  `uv run pytest tests/unit/test_stream_fragmentation.py -q -p no:cacheprovider`.
  Expected: `ModuleNotFoundError: No module named 'scripts.stream_fragmentation'`.

- [ ] **Step 3: Write the implementation**

`scripts/stream_fragmentation.py`:

```python
"""How the same streamed reply is judged under different token splits (Plan 0057).

A reply is a protocol property, not a delivery accident: the verdict must not change
with where the model's tokens happen to split. These helpers re-deliver one reply in
several fragmentations through the evaluator that mirrors production's consumer.
"""

from __future__ import annotations

import re

from scripts.eval_stream_protocol import StreamOutcome, classify_deltas

_TOKEN_RE = re.compile(r"\w+|\W")


def reply_fragmentations(text: str) -> list[list[str]]:
    """Several ways a model's tokens could split one reply (empty deltas never occur).

    Args:
        text: One complete reply.

    Returns:
        Fragmentations: whole, one character at a time, pairs, triples, lines, halves
        and word/punctuation tokens.
    """
    ways = [
        [text],
        list(text),
        [text[i : i + 2] for i in range(0, len(text), 2)],
        [text[i : i + 3] for i in range(0, len(text), 3)],
        text.splitlines(keepends=True),
        [text[: len(text) // 2], text[len(text) // 2 :]],
        _TOKEN_RE.findall(text),
    ]
    return [[piece for piece in way if piece] for way in ways]


def fragmentation_outcomes(text: str) -> set[StreamOutcome]:
    """Return the distinct outcomes one reply gets across ``reply_fragmentations``."""
    return {classify_deltas(fragments) for fragments in reply_fragmentations(text)}


def is_fragmentation_consistent(text: str) -> bool:
    """Return whether every fragmentation of ``text`` is judged the same way."""
    return len(fragmentation_outcomes(text)) == 1
```

- [ ] **Step 4: Make the existing equivalence test use the shared family.** In
  `tests/unit/test_eval_stream_protocol.py` delete the private `_fragmentations`
  helper and import `reply_fragmentations` (the family gains the word/punctuation
  split, so the equivalence against the real consumer now covers it too):

```diff
@@ from scripts.eval_stream_protocol import (
     stream_exit_code,
 )
+from scripts.stream_fragmentation import reply_fragmentations
 from server import streaming, tts
@@
-def _fragmentations(text: str) -> list[list[str]]:
-    """Several ways the model's tokens could split one reply (empty deltas never occur)."""
-    ways = [
-        [text],
-        list(text),
-        [text[i : i + 2] for i in range(0, len(text), 2)],
-        [text[i : i + 3] for i in range(0, len(text), 3)],
-        text.splitlines(keepends=True),
-        [text[: len(text) // 2], text[len(text) // 2 :]],
-    ]
-    return [[piece for piece in way if piece] for way in ways]
-
-
@@
-    for fragments in _fragmentations(reply):
+    for fragments in reply_fragmentations(reply):
```

- [ ] **Step 5: Run, lint, commit.**
  `uv run pytest tests/unit/test_stream_fragmentation.py tests/unit/test_eval_stream_protocol.py -q -p no:cacheprovider`
  (the existing equivalence test must still pass: it is the proof that the evaluator
  keeps mirroring production), then `uv run ruff check` and `uv run ruff format --check`
  over the three files. Commit — `feat(scripts): measure streaming fragmentation consistency`.

---

## Task 3: Variants, seeded order, contract-first prompt

**Files:**
- Create: `scripts/stream_diagnosis_variants.py`
- Test: `tests/unit/test_stream_diagnosis_variants.py`

**Interfaces:**
- Consumes: `scripts.eval_stream_protocol.StreamTurn`;
  `server.llm_streaming` private helpers (`_STREAMING_OUTPUT_CONTRACT`,
  `_build_messages`, `_build_streaming_base_prompt`, `_stream_local_response`,
  `_streaming_system_prompt`) and `generate_response_stream`.
- Produces: `StreamVariant` (including `FULL_REPEAT`, the noise control every turn has),
  `VARIANT_DESCRIPTIONS`, `DiagnosisUnit(variant, turn)`,
  `build_units(golden, public, variants=None) -> list[DiagnosisUnit]` (it drops a
  variant that sends the same inputs as `full` or as an earlier one),
  `plan_runs(units, runs, seed) -> list[tuple[DiagnosisUnit, int]]`,
  `contract_first_system_prompt(base_prompt) -> str`,
  `generate_contract_first(client, text, *, context, history, active_person)`,
  `generator_for(variant) -> StreamGenerator`, `prompt_chars(unit) -> int`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_stream_diagnosis_variants.py`:

```python
"""How diagnosis turns are varied, ordered and prompted (Plan 0057, Task 3)."""

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import httpx
import pytest
from server.schemas import ConversationTurn, MemoryContext

from scripts.eval_stream_protocol import StreamTurn
from scripts.stream_diagnosis_variants import (
    VARIANT_DESCRIPTIONS,
    DiagnosisUnit,
    StreamVariant,
    build_units,
    generate_contract_first,
    generator_for,
    plan_runs,
    prompt_chars,
)
from server import llm_streaming

if TYPE_CHECKING:
    from server.cognition.identity import ActivePersonContext

type StreamGenerator = Callable[..., AsyncIterator[str]]


def _client() -> httpx.AsyncClient:
    return cast("httpx.AsyncClient", Mock(spec=httpx.AsyncClient))


def _turn(
    label: str = "t", *, source: str = "context", person: bool = False, history: bool = False
) -> StreamTurn:
    return StreamTurn(
        label=label,
        source=source,
        text="hola",
        context=MemoryContext() if source == "context" else None,
        history=[ConversationTurn(role="user", content="antes")] if history else None,
        active_person=cast("ActivePersonContext", Mock()) if person else None,
    )


def _unit(variant: StreamVariant = StreamVariant.FULL) -> DiagnosisUnit:
    return DiagnosisUnit(variant, _turn())


@pytest.mark.unit
def test_units_skip_variants_that_would_change_nothing() -> None:
    golden = [_turn("g1"), _turn("g2", person=True), _turn("g3", history=True)]
    public = [_turn("p1", source="public"), _turn("p2", source="public")]

    units = build_units(golden, public)
    names = [(u.turn.label, u.variant.value) for u in units]

    # g1: full, full_repeat, no_context, contract_first. g2 and g3 add question_only and
    # no_person / no_history. Each public turn: full, full_repeat, contract_first and
    # public_with_context.
    assert len(units) == 4 + 6 + 6 + 2 * 4
    assert ("g1", "no_person") not in names
    assert ("g2", "no_person") in names
    assert ("g1", "no_history") not in names
    assert ("g3", "no_history") in names
    assert ("p1", "no_context") not in names


@pytest.mark.unit
def test_a_bare_question_is_not_run_when_it_equals_dropping_the_context() -> None:
    """Without a person or a history, ``question_only`` sends what ``no_context`` sends."""
    golden = [_turn("g1"), _turn("g2", person=True), _turn("g3", history=True)]

    names = [(u.turn.label, u.variant.value) for u in build_units(golden, [])]

    assert ("g1", "question_only") not in names
    assert ("g2", "question_only") in names
    assert ("g3", "question_only") in names


@pytest.mark.unit
def test_no_two_interventions_of_a_turn_send_the_same_inputs() -> None:
    golden = [_turn("g1"), _turn("g2", person=True), _turn("g3", history=True)]
    public = [_turn("p1", source="public")]
    seen: dict[str, list[str]] = {}

    for unit in build_units(golden, public):
        if unit.variant is StreamVariant.FULL_REPEAT:
            continue  # the noise control repeats ``full`` on purpose
        turn = unit.turn
        key = repr((unit.variant is StreamVariant.CONTRACT_FIRST, turn.context, turn.history))
        key += f"|{id(turn.active_person)}"
        seen.setdefault(turn.label, []).append(key)

    assert all(len(keys) == len(set(keys)) for keys in seen.values())


@pytest.mark.unit
def test_every_turn_gets_the_noise_control_and_it_repeats_full() -> None:
    """The noise is read per comparison, so each turn needs its own control."""
    golden = [_turn("g", person=True, history=True)]
    public = [_turn("p", source="public")]

    units = build_units(golden, public)
    repeats = {u.turn.label: u.turn for u in units if u.variant is StreamVariant.FULL_REPEAT}

    assert repeats == {"g": golden[0], "p": public[0]}


@pytest.mark.unit
def test_every_variant_says_what_it_changes() -> None:
    assert set(VARIANT_DESCRIPTIONS) == set(StreamVariant)
    assert all(text.strip() for text in VARIANT_DESCRIPTIONS.values())


@pytest.mark.unit
def test_each_variant_changes_exactly_the_factor_it_names() -> None:
    golden = [_turn("g", person=True, history=True)]

    by_variant = {u.variant: u.turn for u in build_units(golden, [])}

    assert by_variant[StreamVariant.FULL] is golden[0]
    assert by_variant[StreamVariant.FULL_REPEAT] is golden[0]
    assert by_variant[StreamVariant.NO_CONTEXT].context is None
    assert by_variant[StreamVariant.NO_CONTEXT].history is not None
    assert by_variant[StreamVariant.NO_PERSON].active_person is None
    assert by_variant[StreamVariant.NO_PERSON].context is not None
    assert by_variant[StreamVariant.NO_HISTORY].history is None
    assert by_variant[StreamVariant.NO_HISTORY].active_person is not None
    only = by_variant[StreamVariant.QUESTION_ONLY]
    assert (only.context, only.history, only.active_person) == (None, None, None)
    assert by_variant[StreamVariant.CONTRACT_FIRST] is golden[0]


@pytest.mark.unit
def test_a_public_question_borrows_a_golden_context_in_rotation() -> None:
    golden = [_turn("g1"), _turn("g2")]
    public = [_turn(f"p{i}", source="public") for i in range(3)]

    borrowed = [
        u.turn
        for u in build_units(golden, public)
        if u.variant is StreamVariant.PUBLIC_WITH_CONTEXT
    ]

    assert [t.context for t in borrowed] == [
        golden[0].context,
        golden[1].context,
        golden[0].context,
    ]
    assert all(t.source == "public" for t in borrowed)


@pytest.mark.unit
def test_the_variant_filter_keeps_only_what_was_asked() -> None:
    units = build_units([_turn("g")], [_turn("p", source="public")], {StreamVariant.NO_CONTEXT})

    assert [u.variant for u in units] == [StreamVariant.NO_CONTEXT]


@pytest.mark.unit
def test_the_plan_is_seeded_complete_and_interleaved() -> None:
    units = build_units([_turn("g1"), _turn("g2")], [])

    first = plan_runs(units, 3, seed=57)

    assert first == plan_runs(units, 3, seed=57)
    assert first != plan_runs(units, 3, seed=58)
    assert sorted(first, key=lambda item: (id(item[0]), item[1])) == sorted(
        [(unit, run) for unit in units for run in (1, 2, 3)],
        key=lambda item: (id(item[0]), item[1]),
    )
    variants_in_order = [unit.variant for unit, _run in first]
    assert variants_in_order != sorted(variants_in_order, key=lambda v: v.value)


async def _captured_messages(
    generate: StreamGenerator, unit: DiagnosisUnit, monkeypatch: pytest.MonkeyPatch
) -> list[dict[str, str]]:
    captured: list[list[dict[str, str]]] = []

    async def fake_stream(
        _client: httpx.AsyncClient, messages: list[dict[str, str]], **_kwargs: object
    ) -> AsyncIterator[str]:
        captured.append(messages)
        yield "EMOTION:joy\nHola."

    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", fake_stream)
    turn = unit.turn
    async for _delta in generate(
        _client(),
        turn.text,
        context=turn.context,
        history=turn.history,
        active_person=turn.active_person,
    ):
        pass
    return captured[0]


@pytest.mark.unit
@pytest.mark.parametrize("variant", [StreamVariant.FULL, StreamVariant.CONTRACT_FIRST])
async def test_prompt_chars_equals_what_the_generator_really_sends(
    variant: StreamVariant, monkeypatch: pytest.MonkeyPatch
) -> None:
    unit = DiagnosisUnit(variant, _turn(history=True))

    sent = await _captured_messages(generator_for(variant), unit, monkeypatch)

    assert prompt_chars(unit) == sum(len(m["content"]) for m in sent)


@pytest.mark.unit
async def test_contract_first_moves_the_contract_and_changes_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = _unit()
    production = await _captured_messages(llm_streaming.generate_response_stream, unit, monkeypatch)
    moved = await _captured_messages(generate_contract_first, unit, monkeypatch)
    contract = llm_streaming._STREAMING_OUTPUT_CONTRACT.strip()

    assert production[0]["content"].endswith(contract)
    assert moved[0]["content"].startswith(contract)
    assert moved[0]["content"].count(contract) == 1
    assert sorted(moved[0]["content"].split()) == sorted(production[0]["content"].split())
    assert moved[1:] == production[1:]
```

- [ ] **Step 2: Run it to see it fail.**
  `uv run pytest tests/unit/test_stream_diagnosis_variants.py -q -p no:cacheprovider`.
  Expected: `ModuleNotFoundError: No module named 'scripts.stream_diagnosis_variants'`.

- [ ] **Step 3: Write the implementation**

`scripts/stream_diagnosis_variants.py`:

```python
"""How a diagnosis turn is varied, ordered and prompted (Plan 0057).

Each variant removes or moves one factor of a turn (memory context, active person,
history, the contract's position) so that the fallback rate can be attributed to a
factor instead of guessed. The order of the runs is seeded and shuffled.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import enum
import random
from typing import TYPE_CHECKING

from server.llm_streaming import (
    _STREAMING_OUTPUT_CONTRACT,
    _build_messages,
    _build_streaming_base_prompt,
    _stream_local_response,
    _streaming_system_prompt,
)

from server import llm_streaming

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Collection, Sequence

    import httpx
    from server.cognition.identity import ActivePersonContext
    from server.schemas import ConversationTurn, MemoryContext

    from scripts.eval_stream_protocol import StreamTurn

    type StreamGenerator = Callable[..., AsyncIterator[str]]


class StreamVariant(enum.StrEnum):
    """One way of presenting a turn; each removes, moves or repeats a single factor."""

    FULL = "full"
    FULL_REPEAT = "full_repeat"
    NO_CONTEXT = "no_context"
    NO_PERSON = "no_person"
    NO_HISTORY = "no_history"
    QUESTION_ONLY = "question_only"
    CONTRACT_FIRST = "contract_first"
    PUBLIC_WITH_CONTEXT = "public_with_context"


VARIANT_DESCRIPTIONS: dict[StreamVariant, str] = {
    StreamVariant.FULL: "the turn exactly as `just eval-chat --mode stream` sends it (the baseline)",
    StreamVariant.FULL_REPEAT: "`full` again, interleaved: the noise of repeating one condition",
    StreamVariant.NO_CONTEXT: "the memory block removed; person and history kept",
    StreamVariant.NO_PERSON: "the active person removed; memory and history kept",
    StreamVariant.NO_HISTORY: "the history removed; memory and person kept",
    StreamVariant.QUESTION_ONLY: "memory, person and history all removed (several factors at once)",
    StreamVariant.CONTRACT_FIRST: "the output contract moved to the start of the system prompt",
    StreamVariant.PUBLIC_WITH_CONTEXT: "a public question with a golden memory block borrowed in rotation",
}


@dataclass(frozen=True)
class DiagnosisUnit:
    """One turn to stream under one variant."""

    variant: StreamVariant
    turn: StreamTurn


def _same_inputs(first: StreamTurn, second: StreamTurn) -> bool:
    """Whether two turns send the model the same context, history and person."""
    return (
        first.context == second.context
        and (first.history or []) == (second.history or [])
        and first.active_person == second.active_person
    )


def _golden_units(turn: StreamTurn) -> list[DiagnosisUnit]:
    """Return the variants of one golden turn, skipping those that would change nothing.

    A variant is dropped when it sends the same inputs as ``full`` or as a variant kept
    before it (for example ``question_only`` on a turn that has no person and no
    history, where it equals ``no_context``). ``full_repeat`` and ``contract_first``
    keep the same inputs on purpose: one is the noise control, the other moves the
    contract.
    """
    units = [
        DiagnosisUnit(StreamVariant.FULL, turn),
        DiagnosisUnit(StreamVariant.FULL_REPEAT, turn),
        DiagnosisUnit(StreamVariant.CONTRACT_FIRST, turn),
    ]
    candidates = [
        (StreamVariant.NO_CONTEXT, replace(turn, context=None)),
        (StreamVariant.NO_PERSON, replace(turn, active_person=None)),
        (StreamVariant.NO_HISTORY, replace(turn, history=None)),
        (
            StreamVariant.QUESTION_ONLY,
            replace(turn, context=None, history=None, active_person=None),
        ),
    ]
    kept = [turn]
    for variant, candidate in candidates:
        if any(_same_inputs(candidate, earlier) for earlier in kept):
            continue
        kept.append(candidate)
        units.append(DiagnosisUnit(variant, candidate))
    return units


def build_units(
    golden: Sequence[StreamTurn],
    public: Sequence[StreamTurn],
    variants: Collection[StreamVariant] | None = None,
) -> list[DiagnosisUnit]:
    """Expand the golden and public turns into the units of one diagnosis.

    Args:
        golden: The golden context turns (``source == "context"``).
        public: The synthetic context-free turns (``source == "public"``).
        variants: Keep only these variants; every variant when ``None``.

    Returns:
        Units in a fixed order. A variant that would leave a turn unchanged is omitted
        (for example ``NO_PERSON`` on a turn that has no active person).
    """
    units = [unit for turn in golden for unit in _golden_units(turn)]
    for index, turn in enumerate(public):
        units.append(DiagnosisUnit(StreamVariant.FULL, turn))
        units.append(DiagnosisUnit(StreamVariant.FULL_REPEAT, turn))
        units.append(DiagnosisUnit(StreamVariant.CONTRACT_FIRST, turn))
        if golden:
            donor = golden[index % len(golden)].context
            units.append(
                DiagnosisUnit(StreamVariant.PUBLIC_WITH_CONTEXT, replace(turn, context=donor))
            )
    if variants is None:
        return units
    return [unit for unit in units if unit.variant in variants]


def plan_runs(
    units: Sequence[DiagnosisUnit], runs: int, seed: int
) -> list[tuple[DiagnosisUnit, int]]:
    """Return every ``(unit, run)`` once, in an order shuffled by ``seed``.

    Interleaving the variants keeps a slow machine or a warming model from being
    mistaken for a variant effect.
    """
    plan = [(unit, run) for unit in units for run in range(1, runs + 1)]
    random.Random(seed).shuffle(plan)  # noqa: S311  # a reproducible order, not security
    return plan


def contract_first_system_prompt(base_prompt: str) -> str:
    """Put the streaming contract before the base prompt instead of after it."""
    return _STREAMING_OUTPUT_CONTRACT.lstrip("\n") + "\n\n" + base_prompt


async def generate_contract_first(
    client: httpx.AsyncClient,
    text: str,
    *,
    context: MemoryContext | None = None,
    history: list[ConversationTurn] | None = None,
    active_person: ActivePersonContext | None = None,
) -> AsyncIterator[str]:
    """Stream like production does, with the contract at the start of the system prompt."""
    if not text:
        raise ValueError("Input text is empty")
    base_prompt = _build_streaming_base_prompt(
        context,
        onboarding=False,
        onboarding_slot=None,
        user_emotion=None,
        active_person=active_person,
    )
    system_prompt = contract_first_system_prompt(base_prompt)
    messages = _build_messages(text, history)
    async for delta in _stream_local_response(
        client, [{"role": "system", "content": system_prompt}, *messages]
    ):
        yield delta


def generator_for(variant: StreamVariant) -> StreamGenerator:
    """Return the streaming generator a variant is measured with."""
    if variant is StreamVariant.CONTRACT_FIRST:
        return generate_contract_first
    return llm_streaming.generate_response_stream


def prompt_chars(unit: DiagnosisUnit) -> int:
    """Return the characters sent to the model for one unit (system plus messages)."""
    turn = unit.turn
    base_prompt = _build_streaming_base_prompt(
        turn.context,
        onboarding=False,
        onboarding_slot=None,
        user_emotion=None,
        active_person=turn.active_person,
    )
    if unit.variant is StreamVariant.CONTRACT_FIRST:
        system_prompt = contract_first_system_prompt(base_prompt)
    else:
        system_prompt = _streaming_system_prompt(base_prompt)
    messages = _build_messages(turn.text, turn.history)
    return len(system_prompt) + sum(len(message["content"]) for message in messages)
```

- [ ] **Step 4: Run, lint, commit.**
  `uv run pytest tests/unit/test_stream_diagnosis_variants.py -q -p no:cacheprovider`
  (the equivalence tests `test_prompt_chars_equals_what_the_generator_really_sends` and
  `test_contract_first_moves_the_contract_and_changes_nothing_else` are the ones that
  would catch a drift from production's prompt), then `ruff check` and
  `ruff format --check` over both paths. Commit —
  `feat(scripts): add streaming diagnosis variants`.

---

## Task 4: One closed observation per streamed reply

**Files:**
- Create: `scripts/eval_stream_diagnosis.py`
- Modify: `scripts/eval_stream_protocol.py` (one counter)
- Test: `tests/unit/test_eval_stream_diagnosis.py`; edit `tests/unit/test_eval_stream_protocol.py`

**Interfaces:**
- Consumes: Task 1 `FailureShape`, `classify_failure_shape`; Task 2
  `is_fragmentation_consistent`; Task 3 `DiagnosisUnit`, `StreamVariant`, `plan_runs`,
  `generator_for`, `prompt_chars`; `eval_stream_protocol._StreamClassifier`,
  `classify_deltas`, `StreamOutcome`.
- Produces: `Observation` (frozen; properties `fell_back`, `undue_accept`),
  `observe_once(unit, *, run, position, client, generate, clock) -> Observation`,
  `run_diagnosis(units, *, client, runs, seed, generate_for) -> list[Observation]`,
  and `_StreamClassifier.sentences_seen`.

- [ ] **Step 1: Write the failing tests.** First the counter the observation needs.
  Append to `tests/unit/test_eval_stream_protocol.py` (and add `_StreamClassifier` to
  its existing `from scripts.eval_stream_protocol import (...)` list):

```python
@pytest.mark.unit
def test_the_classifier_counts_the_sentences_production_would_speak() -> None:
    classifier = _StreamClassifier()

    classifier.feed("EMOTION:joy\nHola. ¿Cómo")
    assert classifier.sentences_seen == 1

    classifier.feed(" estás? Bien")
    assert classifier.sentences_seen == 2
```

  Then the observation tests:

`tests/unit/test_eval_stream_diagnosis.py`:

```python
"""Streaming-protocol diagnosis: one observation per reply (Plan 0057, Task 3)."""

from collections.abc import AsyncIterator, Callable
import dataclasses
import itertools
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import httpx
import pytest
from server.exceptions import LLMError
from server.schemas import ConversationTurn, MemoryContext

from scripts.eval_stream_diagnosis import Observation, observe_once, run_diagnosis
from scripts.eval_stream_protocol import StreamOutcome, StreamTurn
from scripts.stream_diagnosis_variants import DiagnosisUnit, StreamVariant
from scripts.stream_failure_shapes import FailureShape

if TYPE_CHECKING:
    from server.cognition.identity import ActivePersonContext

_CANARY = "CANARIO-INVENTADO-731"

type StreamGenerator = Callable[..., AsyncIterator[str]]


def _client() -> httpx.AsyncClient:
    return cast("httpx.AsyncClient", Mock(spec=httpx.AsyncClient))


def _turn(
    label: str = "t", *, source: str = "context", person: bool = False, history: bool = False
) -> StreamTurn:
    return StreamTurn(
        label=label,
        source=source,
        text="hola",
        context=MemoryContext() if source == "context" else None,
        history=[ConversationTurn(role="user", content="antes")] if history else None,
        active_person=cast("ActivePersonContext", Mock()) if person else None,
    )


def _unit(variant: StreamVariant = StreamVariant.FULL) -> DiagnosisUnit:
    return DiagnosisUnit(variant, _turn())


class _FakeStream:
    """A generator stand-in that records whether it was closed and whether it resumed."""

    def __init__(self, *fragments: str, fail: bool = False) -> None:
        self._fragments = fragments
        self._fail = fail
        self.closed = False
        self.resumed = False

    async def __call__(
        self, _client: httpx.AsyncClient, _text: str, **_kwargs: object
    ) -> AsyncIterator[str]:
        try:
            for index, fragment in enumerate(self._fragments):
                if index and self.closed:
                    self.resumed = True
                yield fragment
            if self._fail:
                raise LLMError("provider failed")
        finally:
            self.closed = True


async def _observe(generate: _FakeStream, unit: DiagnosisUnit | None = None) -> Observation:
    ticks = itertools.count(0.0, 0.01)
    return await observe_once(
        unit or _unit(),
        run=1,
        position=0,
        client=_client(),
        generate=generate,
        clock=lambda: next(ticks),
    )


@pytest.mark.unit
async def test_a_valid_reply_starts_speaking_at_its_first_closed_sentence() -> None:
    obs = await _observe(_FakeStream("EMOTION:joy\nHola. ", "¿Cómo estás?"))

    assert obs.outcome is StreamOutcome.VALID
    assert obs.shape is FailureShape.VALID
    assert obs.whole_text_outcome is StreamOutcome.VALID
    assert obs.fragmentation_consistent is True
    assert obs.first_delta_ms == 10
    assert obs.speech_start_ms == 10  # the first delta already closes "Hola."
    assert obs.end_ms == 30
    assert obs.delta_count == 2
    assert obs.reply_chars == len("EMOTION:joy\nHola. ¿Cómo estás?")
    assert not obs.fell_back
    assert not obs.undue_accept


@pytest.mark.unit
async def test_a_prefix_split_across_deltas_is_an_undue_accept() -> None:
    """Production speaks what the whole text would reject: the 0057 fragmentation defect."""
    obs = await _observe(_FakeStream("EMOTION:joy\nEMO", "TION:anger\nhola"))

    assert obs.outcome is StreamOutcome.VALID
    assert obs.whole_text_outcome is StreamOutcome.INVALID_PROTOCOL
    assert obs.fragmentation_consistent is False
    assert obs.undue_accept


@pytest.mark.unit
async def test_an_invalid_body_start_decides_at_once_and_closes_the_stream() -> None:
    generate = _FakeStream("EMOTION:joy\n{", "never consumed")

    obs = await _observe(generate)

    assert obs.outcome is StreamOutcome.INVALID_PROTOCOL
    assert obs.shape is FailureShape.BODY_JSON
    assert obs.fell_back
    assert obs.speech_start_ms == obs.first_delta_ms == 10
    assert obs.delta_count == 1
    assert (generate.closed, generate.resumed) == (True, False)


@pytest.mark.unit
async def test_a_reply_without_the_tag_waits_for_the_end_of_the_stream() -> None:
    obs = await _observe(_FakeStream("Hola ", "sin etiqueta."))

    assert obs.outcome is StreamOutcome.INVALID_PROTOCOL
    assert obs.shape is FailureShape.NO_TAG
    assert obs.speech_start_ms == obs.end_ms == 30
    assert obs.first_delta_ms == 10


@pytest.mark.unit
async def test_an_empty_stream_is_an_empty_observation() -> None:
    obs = await _observe(_FakeStream())

    assert obs.outcome is StreamOutcome.EMPTY_STREAM
    assert obs.shape is FailureShape.EMPTY
    assert obs.first_delta_ms is None
    assert obs.fell_back


@pytest.mark.unit
async def test_a_provider_error_is_an_error_not_a_protocol_verdict() -> None:
    obs = await _observe(_FakeStream("EMOTION:joy\nHola", fail=True))

    assert obs.outcome is StreamOutcome.ERROR
    assert obs.shape is None
    assert obs.whole_text_outcome is None
    assert obs.fragmentation_consistent is None
    assert not obs.fell_back
    assert not obs.undue_accept


@pytest.mark.unit
async def test_an_observation_never_holds_the_reply_text() -> None:
    obs = await _observe(_FakeStream(f"EMOTION:joy\n{_CANARY}. ", f"{_CANARY}."))

    assert _CANARY not in repr(obs)
    text_fields = [
        field.name
        for field in dataclasses.fields(Observation)
        if field.type in ("str", str) and field.name not in {"source", "label"}
    ]
    assert text_fields == []


@pytest.mark.unit
async def test_the_diagnosis_runs_every_unit_and_keeps_provider_errors_apart() -> None:
    replies: list[str | Exception] = ["EMOTION:joy\nHola.", LLMError("boom"), "sin etiqueta"]
    queue = iter(replies)

    def generate_for(_variant: StreamVariant) -> StreamGenerator:
        async def generate(
            _client: httpx.AsyncClient, _text: str, **_kwargs: object
        ) -> AsyncIterator[str]:
            reply = next(queue)
            if isinstance(reply, Exception):
                raise reply
            yield reply

        return generate

    units = [_unit(), _unit(StreamVariant.NO_CONTEXT), _unit(StreamVariant.QUESTION_ONLY)]
    observations = await run_diagnosis(
        units, client=_client(), runs=1, seed=1, generate_for=generate_for
    )

    assert sorted(o.position for o in observations) == [0, 1, 2]
    assert {o.outcome for o in observations} == {
        StreamOutcome.VALID,
        StreamOutcome.ERROR,
        StreamOutcome.INVALID_PROTOCOL,
    }
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_eval_stream_protocol.py tests/unit/test_eval_stream_diagnosis.py -q -p no:cacheprovider`.
  Expected: the new counter test fails with `AttributeError: '_StreamClassifier' object
  has no attribute 'sentences_seen'`; the observation file fails to import
  (`ModuleNotFoundError: No module named 'scripts.eval_stream_diagnosis'`).

- [ ] **Step 3: Add the counter** to `scripts/eval_stream_protocol.py` (behaviour of
  `feed` is unchanged; the existing equivalence tests prove it):

```diff
@@ class _StreamClassifier:
     def __init__(self) -> None:
         self._state = StreamState(request_start=0.0)
         self._buffer = ""
+        self.sentences_seen = 0
@@
-            self._buffer, _sentences = _consume_body(self._buffer, self._state)
+            self._buffer, sentences = _consume_body(self._buffer, self._state)
         except LLMError:
             return StreamOutcome.INVALID_PROTOCOL
+        self.sentences_seen += len(sentences)
         return None
```

- [ ] **Step 4: Write the observation module**

`scripts/eval_stream_diagnosis.py`:

```python
"""Streaming-protocol diagnosis: one observation per streamed reply (Plan 0057).

Runs the production streaming generator over the units built by
``stream_diagnosis_variants`` and consumes each reply the way ``server.streaming`` does.
Every reply is classified in memory (failure shape, whole-text verdict, fragmentation
consistency) and dropped: an ``Observation`` carries closed enums, flags, counts and
milliseconds, never a character of model output.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING

from scripts.eval_stream_protocol import StreamOutcome, _StreamClassifier, classify_deltas
from scripts.stream_diagnosis_variants import (
    DiagnosisUnit,
    StreamVariant,
    generator_for,
    plan_runs,
    prompt_chars,
)
from scripts.stream_failure_shapes import FailureShape, classify_failure_shape
from scripts.stream_fragmentation import is_fragmentation_consistent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    import httpx

    type StreamGenerator = Callable[..., AsyncIterator[str]]
    type Clock = Callable[[], float]

logger = logging.getLogger(__name__)

_MS_PER_SECOND = 1000
_PROGRESS_EVERY = 25


@dataclass(frozen=True)
class Observation:
    """One streamed reply, reduced to closed values. Never holds model text."""

    variant: StreamVariant
    source: str
    label: str
    run: int
    position: int
    outcome: StreamOutcome
    shape: FailureShape | None
    whole_text_outcome: StreamOutcome | None
    fragmentation_consistent: bool | None
    prompt_chars: int
    reply_chars: int
    delta_count: int
    first_delta_ms: int | None
    speech_start_ms: int
    end_ms: int

    @property
    def fell_back(self) -> bool:
        """Whether production would have spoken the fallback phrase."""
        return self.outcome in (StreamOutcome.INVALID_PROTOCOL, StreamOutcome.EMPTY_STREAM)

    @property
    def undue_accept(self) -> bool:
        """Production spoke a reply that the whole text would have rejected."""
        return (
            self.outcome is StreamOutcome.VALID
            and self.whole_text_outcome is not None
            and self.whole_text_outcome is not StreamOutcome.VALID
        )


def _ms(seconds: float) -> int:
    return round(seconds * _MS_PER_SECOND)


def _speech_start_ms(
    outcome: StreamOutcome, first_sentence_ms: int | None, decided_ms: int | None, end_ms: int
) -> int:
    """When production would hand its first sentence, or the fallback, to TTS.

    A valid reply starts at its first closed sentence (or the end of the stream when it
    never closes one); a rejected reply starts the fallback the moment production
    decides, which for a reply without the tag is only the end of the stream.
    """
    if outcome is StreamOutcome.VALID:
        return end_ms if first_sentence_ms is None else first_sentence_ms
    return end_ms if decided_ms is None else decided_ms


async def observe_once(
    unit: DiagnosisUnit,
    *,
    run: int,
    position: int,
    client: httpx.AsyncClient,
    generate: StreamGenerator,
    clock: Clock = time.perf_counter,
) -> Observation:
    """Stream one reply the way production consumes it and reduce it to closed values.

    Production stops reading at an invalid body start, so this does too (and closes the
    stream); every other reply is read to its end. The reply text lives only inside this
    call.
    """
    turn = unit.turn
    started = clock()
    classifier = _StreamClassifier()
    pieces: list[str] = []
    first_delta_ms: int | None = None
    first_sentence_ms: int | None = None
    decided_ms: int | None = None
    decided: StreamOutcome | None = None
    stream = generate(
        client,
        turn.text,
        context=turn.context,
        history=turn.history,
        active_person=turn.active_person,
    )
    failed = False
    try:
        async for delta in stream:
            if not delta:
                continue
            now_ms = _ms(clock() - started)
            if first_delta_ms is None:
                first_delta_ms = now_ms
            pieces.append(delta)
            decided = classifier.feed(delta)
            if first_sentence_ms is None and classifier.sentences_seen:
                first_sentence_ms = now_ms
            if decided is not None:
                decided_ms = now_ms
                break
    except Exception as exc:
        logger.warning("Provider call failed for %s (%s)", turn.label, type(exc).__name__)
        failed = True
    finally:
        # Stop the model generating: an abandoned async generator keeps Ollama running.
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()
    end_ms = _ms(clock() - started)
    text = "".join(pieces)
    outcome = StreamOutcome.ERROR
    shape: FailureShape | None = None
    whole: StreamOutcome | None = None
    consistent: bool | None = None
    speech_start_ms = end_ms
    if not failed:
        outcome = decided if decided is not None else classifier.finish()
        shape = classify_failure_shape(text)
        whole = classify_deltas([text] if text else [])
        consistent = is_fragmentation_consistent(text)
        speech_start_ms = _speech_start_ms(outcome, first_sentence_ms, decided_ms, end_ms)
    return Observation(
        variant=unit.variant,
        source=turn.source,
        label=turn.label,
        run=run,
        position=position,
        outcome=outcome,
        shape=shape,
        whole_text_outcome=whole,
        fragmentation_consistent=consistent,
        prompt_chars=prompt_chars(unit),
        reply_chars=len(text),
        delta_count=len(pieces),
        first_delta_ms=first_delta_ms,
        speech_start_ms=speech_start_ms,
        end_ms=end_ms,
    )


async def run_diagnosis(
    units: Sequence[DiagnosisUnit],
    *,
    client: httpx.AsyncClient,
    runs: int,
    seed: int,
    generate_for: Callable[[StreamVariant], StreamGenerator] = generator_for,
) -> list[Observation]:
    """Stream every unit ``runs`` times, sequentially, in the seeded shuffled order.

    Args:
        units: The units to measure (see ``build_units``).
        client: Run-owned HTTP client, passed first to the generator (Plan 0039).
        runs: Repetitions per unit.
        seed: Seed of the shuffle, recorded in the report.
        generate_for: Maps a variant to its generator; production's unless a test
            injects one.

    Returns:
        One observation per ``(unit, run)``, in execution order. A provider error is an
        ``ERROR`` observation, never a protocol failure or a pass.
    """
    plan = plan_runs(units, runs, seed)
    observations: list[Observation] = []
    for position, (unit, run) in enumerate(plan):
        observations.append(
            await observe_once(
                unit,
                run=run,
                position=position,
                client=client,
                generate=generate_for(unit.variant),
            )
        )
        if (position + 1) % _PROGRESS_EVERY == 0:
            logger.info("Diagnosis progress: %d/%d", position + 1, len(plan))
    return observations
```

- [ ] **Step 5: Run, lint, commit.**
  `uv run pytest tests/unit/test_eval_stream_protocol.py tests/unit/test_eval_stream_diagnosis.py -q -p no:cacheprovider`,
  then `ruff check` and `ruff format --check` over the four files. Commit —
  `feat(scripts): observe streamed replies as closed values`.

---

## Task 5: Ollama facts and the structured-stream probe

**Files:**
- Create: `scripts/stream_diagnosis_probes.py`
- Test: `tests/unit/test_stream_diagnosis_probes.py`

**Interfaces:**
- Consumes: `server.settings.settings` (`ollama_url`, `ollama_model`,
  `ollama_timeout_s`), `server.llm._OLLAMA_RESPONSE_SCHEMA`.
- Produces: `OllamaFacts(reachable, version, model, digest)`,
  `fetch_ollama_facts(client) -> OllamaFacts`, `parse_version`, `parse_digest`;
  `ArrivalPattern` (`incremental` / `burst` / `inconclusive`),
  `ArrivalSummary` (property `pattern`), `summarize_arrivals(arrivals_ms, total_ms)`;
  `conforms_to_schema(text) -> bool` (a non-text `emotion` is `False`, never a
  `TypeError`); `RunStatus` (`complete` / `provider_error` / `incomplete` /
  `off_schema`), `StructuredRun(status, arrivals)` (property `pattern`),
  `StructuredProbeResult(runs, constrained=True)` (`count(status)`, `errors`,
  `verdict`),
  `probe_structured_stream(client, *, runs, clock, constrained=True) -> StructuredProbeResult`
  (`constrained=False` is the plain-text control: no `format`; an unexpected failure in a
  run is an `incomplete` run, never an exception).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_stream_diagnosis_probes.py`:

```python
"""Ollama facts and the structured-stream probe (Plan 0057, Task 5)."""

from collections.abc import Callable
import itertools
import json

import httpx
import pytest
from server.settings import settings

from scripts import stream_diagnosis_probes as probes
from scripts.stream_diagnosis_probes import (
    ArrivalPattern,
    ArrivalSummary,
    RunStatus,
    StructuredProbeResult,
    StructuredRun,
    conforms_to_schema,
    fetch_ollama_facts,
    parse_digest,
    parse_version,
    probe_structured_stream,
    summarize_arrivals,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body, expected",
    [
        ({"version": "0.34.4"}, "0.34.4"),
        ({}, "unknown"),
        ([], "unknown"),
        ({"version": 3}, "unknown"),
    ],
)
def test_parse_version_is_tolerant(body: object, expected: str) -> None:
    assert parse_version(body) == expected


@pytest.mark.unit
def test_parse_digest_finds_the_model_by_name_or_model_and_truncates() -> None:
    body = {
        "models": [
            {"name": "other:1b", "digest": "ffff" * 16},
            {"name": "qwen2.5:3b", "model": "qwen2.5:3b", "digest": "abcdef012345" + "0" * 52},
        ]
    }

    assert parse_digest(body, "qwen2.5:3b") == "abcdef012345"
    assert parse_digest({"models": [{"model": "m", "digest": "1234567890123456"}]}, "m") == (
        "123456789012"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "body", [None, {}, {"models": []}, {"models": ["x"]}, {"models": [{"name": "m"}]}]
)
def test_parse_digest_is_unknown_when_ollama_does_not_say(body: object) -> None:
    assert parse_digest(body, "m") == "unknown"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.unit
async def test_facts_report_version_and_digest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.34.4"})
        return httpx.Response(
            200, json={"models": [{"name": settings.ollama_model, "digest": "a" * 64}]}
        )

    async with _client(handler) as client:
        facts = await fetch_ollama_facts(client)

    assert (facts.reachable, facts.version, facts.model, facts.digest) == (
        True,
        "0.34.4",
        settings.ollama_model,
        "a" * 12,
    )


@pytest.mark.unit
async def test_facts_say_unreachable_when_ollama_is_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with _client(handler) as client:
        facts = await fetch_ollama_facts(client)

    assert (facts.reachable, facts.version, facts.digest) == (False, "unknown", "unknown")


@pytest.mark.unit
@pytest.mark.parametrize(
    "arrivals, expected",
    [
        ([5000, 5100, 5200, 5300, 5400], ArrivalPattern.INCREMENTAL),  # a long first wait
        ([100, 200, 300, 400, 1000], ArrivalPattern.INCREMENTAL),
        ([0, 30, 60, 61, 62], ArrivalPattern.INCREMENTAL),  # half of the gaps are paced
        ([1, 1, 1, 1, 2], ArrivalPattern.BURST),  # a burst at the client
        ([900, 900, 901, 901, 902], ArrivalPattern.BURST),
        ([0, 0, 0, 0, 0], ArrivalPattern.BURST),
        ([0, 25, 25, 25, 25], ArrivalPattern.BURST),  # one paced gap in four: a burst after a wait
        ([0, 10, 20, 30, 40], ArrivalPattern.BURST),  # fast generation looks like this too
        ([0, 30, 31, 61, 62], ArrivalPattern.INCREMENTAL),
        ([0, 30, 31, 32, 33, 34, 70], ArrivalPattern.INCONCLUSIVE),  # 2 paced gaps in 6
        ([100, 200, 300, 400], ArrivalPattern.INCONCLUSIVE),  # too few chunks to tell
        ([], ArrivalPattern.INCONCLUSIVE),
    ],
)
def test_the_pattern_reads_the_spacing_between_chunks_not_when_the_first_arrived(
    arrivals: list[int], expected: ArrivalPattern
) -> None:
    summary = summarize_arrivals(arrivals, arrivals[-1] + 10 if arrivals else 10)

    assert summary.pattern is expected
    assert summary.chunks == len(arrivals)


@pytest.mark.unit
def test_an_empty_arrival_list_has_no_first_or_last_chunk_and_no_gaps() -> None:
    assert summarize_arrivals([], 7) == ArrivalSummary(0, None, None, 0, 0, 7)


@pytest.mark.unit
def test_gaps_are_counted_between_consecutive_chunks() -> None:
    summary = summarize_arrivals([0, 10, 40, 100], 120)

    assert (summary.gaps, summary.paced_gaps) == (3, 2)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"response": "Hola", "emotion": "joy"}', True),
        ('{"response": "Hola", "emotion": "neutral", "extra": 1}', True),
        ('{"response": "Hola"}', False),
        ('{"response": "", "emotion": "joy"}', False),
        ('{"response": "  ", "emotion": "joy"}', False),
        ('{"response": 3, "emotion": "joy"}', False),
        ('{"response": "Hola", "emotion": "furious"}', False),
        ('{"response": "Hola", "emotion": 4}', False),
        ('{"response": "Hola", "emotion": []}', False),
        ('{"response": "Hola", "emotion": {}}', False),
        ('{"response": "Hola", "emotion": null}', False),
        ('{"response": "Hola", "emotion": true}', False),
        ("[1, 2]", False),
        ("not json", False),
        ("", False),
    ],
)
def test_the_assembled_reply_must_satisfy_the_schema(text: str, expected: bool) -> None:
    assert conforms_to_schema(text) is expected


_VALID = '{"response": "Hola, como estas", "emotion": "joy"}'


def _stream(*events: object, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    body = "".join(json.dumps(event) + "\n" for event in events)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body.encode(), request=request)

    return handler


def _pieces(text: str, size: int = 8) -> list[dict[str, object]]:
    return [{"message": {"content": text[i : i + size]}} for i in range(0, len(text), size)]


def _ticker(step: float) -> Callable[[], float]:
    ticks = itertools.count(0.0, step)
    return lambda: next(ticks)


async def _probe(
    handler: Callable[[httpx.Request], httpx.Response], *, runs: int = 1, step: float = 0.05
) -> StructuredProbeResult:
    async with _client(handler) as client:
        return await probe_structured_stream(client, runs=runs, clock=_ticker(step))


@pytest.mark.unit
async def test_a_complete_schema_conforming_stream_is_complete_and_paced() -> None:
    result = await _probe(_stream(*_pieces(_VALID), {"done": True}))

    [run] = result.runs
    assert run.status is RunStatus.COMPLETE
    assert run.arrivals is not None
    assert run.arrivals.chunks == len(_pieces(_VALID))
    assert run.pattern is ArrivalPattern.INCREMENTAL
    assert result.errors == 0


@pytest.mark.unit
async def test_chunks_that_arrive_together_are_a_burst() -> None:
    result = await _probe(_stream(*_pieces(_VALID), {"done": True}), step=0.0001)

    assert result.runs[0].status is RunStatus.COMPLETE
    assert result.runs[0].pattern is ArrivalPattern.BURST


@pytest.mark.unit
async def test_the_probe_asks_for_a_schema_and_a_stream() -> None:
    seen: list[dict[str, object]] = []
    lines = _stream(*_pieces(_VALID), {"done": True})

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return lines(request)

    await _probe(handler)

    assert seen[0]["stream"] is True
    assert isinstance(seen[0]["format"], dict)
    assert seen[0]["model"] == settings.ollama_model


@pytest.mark.unit
async def test_an_error_event_after_a_200_is_a_provider_error_not_a_quiet_run() -> None:
    result = await _probe(_stream({"error": "model runner crashed"}))

    assert [r.status for r in result.runs] == [RunStatus.PROVIDER_ERROR]
    assert result.runs[0].arrivals is None
    assert result.errors == 1


@pytest.mark.unit
async def test_an_error_event_in_the_middle_of_the_reply_is_a_provider_error() -> None:
    result = await _probe(_stream(*_pieces(_VALID)[:2], {"error": "boom"}))

    assert [r.status for r in result.runs] == [RunStatus.PROVIDER_ERROR]


@pytest.mark.unit
async def test_a_stream_that_ends_without_done_is_incomplete() -> None:
    result = await _probe(_stream(*_pieces(_VALID)))

    assert [r.status for r in result.runs] == [RunStatus.INCOMPLETE]
    assert result.runs[0].arrivals is None
    assert result.errors == 1


@pytest.mark.unit
async def test_a_malformed_line_makes_the_run_incomplete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"message": {"content": "{"}}\nnot json\n')

    result = await _probe(handler)

    assert [r.status for r in result.runs] == [RunStatus.INCOMPLETE]


@pytest.mark.unit
async def test_a_non_text_content_is_not_a_chunk() -> None:
    events = [{"message": {"content": 5}}, {"message": {"content": None}}, {"done": True}]

    result = await _probe(_stream(*events))

    [run] = result.runs
    assert run.status is RunStatus.OFF_SCHEMA
    assert run.arrivals is not None
    assert run.arrivals.chunks == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "reply",
    [
        '{"foo": 1}',
        '{"response": "Hola", "emotion": "furious"}',
        '{"response": "Hola", "emotion": []}',
        '{"response": "Hola", "emotion": {}}',
        '{"response": "',
        "plain text",
    ],
)
async def test_a_reply_outside_the_schema_is_off_schema_and_not_an_error(reply: str) -> None:
    result = await _probe(_stream(*_pieces(reply), {"done": True}))

    assert [r.status for r in result.runs] == [RunStatus.OFF_SCHEMA]
    assert result.errors == 0
    assert result.runs[0].pattern is None


@pytest.mark.unit
async def test_an_http_error_status_is_a_provider_error() -> None:
    result = await _probe(_stream(status=500))

    assert [r.status for r in result.runs] == [RunStatus.PROVIDER_ERROR]


@pytest.mark.unit
async def test_a_refused_connection_is_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    result = await _probe(handler, runs=2)

    assert [r.status for r in result.runs] == [RunStatus.PROVIDER_ERROR] * 2
    assert result.errors == 2


def _run(status: RunStatus, pattern: ArrivalPattern | None = None) -> StructuredRun:
    arrivals = None
    if pattern is ArrivalPattern.INCREMENTAL:
        arrivals = summarize_arrivals([0, 100, 200, 300, 400], 410)
    if pattern is ArrivalPattern.BURST:
        arrivals = summarize_arrivals([0, 1, 1, 2, 2], 12)
    return StructuredRun(status, arrivals)


@pytest.mark.unit
@pytest.mark.parametrize(
    "runs, expected",
    [
        ([_run(RunStatus.COMPLETE, ArrivalPattern.INCREMENTAL)] * 3, ArrivalPattern.INCREMENTAL),
        ([_run(RunStatus.COMPLETE, ArrivalPattern.BURST)] * 3, ArrivalPattern.BURST),
        ([_run(RunStatus.COMPLETE, ArrivalPattern.BURST)] * 2, ArrivalPattern.INCONCLUSIVE),
        (
            [
                _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
                _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
                _run(RunStatus.PROVIDER_ERROR),
                _run(RunStatus.INCOMPLETE),
                _run(RunStatus.OFF_SCHEMA),
            ],
            ArrivalPattern.INCONCLUSIVE,
        ),
        (
            [
                _run(RunStatus.COMPLETE, ArrivalPattern.INCREMENTAL),
                _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
                _run(RunStatus.COMPLETE, ArrivalPattern.INCREMENTAL),
                _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
            ],
            ArrivalPattern.INCONCLUSIVE,
        ),
        ([], ArrivalPattern.INCONCLUSIVE),
    ],
)
def test_the_verdict_needs_three_complete_runs_and_a_majority(
    runs: list[StructuredRun], expected: ArrivalPattern
) -> None:
    assert StructuredProbeResult(tuple(runs)).verdict is expected


@pytest.mark.unit
def test_the_probe_result_counts_each_status() -> None:
    result = StructuredProbeResult(
        (
            _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
            _run(RunStatus.PROVIDER_ERROR),
            _run(RunStatus.INCOMPLETE),
            _run(RunStatus.OFF_SCHEMA),
        )
    )

    assert result.count(RunStatus.COMPLETE) == 1
    assert result.count(RunStatus.OFF_SCHEMA) == 1
    assert result.errors == 2


@pytest.mark.unit
async def test_an_unexpected_failure_inside_a_run_is_an_incomplete_run_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe bug must not lose the observations measured before it."""

    def explode(_text: str) -> bool:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(probes, "conforms_to_schema", explode)

    result = await _probe(_stream(*_pieces(_VALID), {"done": True}), runs=2)

    assert [r.status for r in result.runs] == [RunStatus.INCOMPLETE] * 2
    assert result.errors == 2


@pytest.mark.unit
async def test_the_plain_text_control_asks_for_no_schema_and_needs_no_json() -> None:
    seen: list[dict[str, object]] = []
    lines = _stream(*_pieces("Una frase. Otra frase. Y otra.", 4), {"done": True})

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return lines(request)

    async with _client(handler) as client:
        result = await probe_structured_stream(
            client, runs=1, clock=_ticker(0.05), constrained=False
        )

    assert "format" not in seen[0]
    assert seen[0]["stream"] is True
    assert result.constrained is False
    assert [r.status for r in result.runs] == [RunStatus.COMPLETE]
    assert result.runs[0].pattern is ArrivalPattern.INCREMENTAL


@pytest.mark.unit
async def test_a_plain_text_control_that_says_nothing_is_incomplete() -> None:
    async with _client(_stream({"done": True})) as client:
        result = await probe_structured_stream(
            client, runs=1, clock=_ticker(0.05), constrained=False
        )

    assert [r.status for r in result.runs] == [RunStatus.INCOMPLETE]


@pytest.mark.unit
async def test_the_constrained_probe_is_the_default() -> None:
    result = await _probe(_stream(*_pieces(_VALID), {"done": True}))

    assert result.constrained is True
```

- [ ] **Step 2: Run it to see it fail.**
  `uv run pytest tests/unit/test_stream_diagnosis_probes.py -q -p no:cacheprovider`.
  Expected: `ModuleNotFoundError: No module named 'scripts.stream_diagnosis_probes'`.

- [ ] **Step 3: Write the implementation**

`scripts/stream_diagnosis_probes.py`:

```python
"""Facts about the local Ollama and one arrival-time probe (Plan 0057).

The diagnosis must say which Ollama and which model it measured, and whether Ollama
streams a reply constrained by a JSON schema chunk by chunk or withholds it until the
end. ``llm_streaming`` states the second as a fact; nobody has measured it. Only closed
statuses, counts and milliseconds are kept, never model text.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
from itertools import pairwise
import json
import logging
import time
from typing import TYPE_CHECKING

import httpx
from server.llm import _OLLAMA_RESPONSE_SCHEMA, VALID_EMOTIONS
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

_UNKNOWN = "unknown"
_DIGEST_CHARS = 12
_MS_PER_SECOND = 1000
# Rules fixed before measuring (Plan 0057, R-6). Chunks of a burst reach the client
# within a few milliseconds; a model generating on this machine spaces its chunks by
# tens. A burst can be withheld output, fast generation or buffering: it proves nothing.
_PACED_GAP_MS = 20
_MIN_CHUNKS = 5
_INCREMENTAL_MIN_PACED_SHARE = 0.5
_BURST_MAX_PACED_SHARE = 0.25
_MIN_COMPLETE_RUNS = 3
_PROBE_SYSTEM = "Eres un robot doméstico llamado Iroko. Responde siempre en español."
_PROBE_QUESTION = "Cuéntame algo interesante en tres frases."


@dataclass(frozen=True)
class OllamaFacts:
    """What the diagnosis ran against; ``unknown`` when Ollama did not say."""

    reachable: bool
    version: str
    model: str
    digest: str


def parse_version(body: object) -> str:
    """Return ``version`` from an ``/api/version`` body, or ``unknown``."""
    if isinstance(body, dict) and isinstance(body.get("version"), str):
        return body["version"]
    return _UNKNOWN


def parse_digest(body: object, model: str) -> str:
    """Return the first characters of ``model``'s digest from an ``/api/tags`` body."""
    models = body.get("models") if isinstance(body, dict) else None
    for entry in models if isinstance(models, list) else []:
        if not isinstance(entry, dict) or model not in (entry.get("name"), entry.get("model")):
            continue
        digest = entry.get("digest")
        if isinstance(digest, str) and digest:
            return digest[:_DIGEST_CHARS]
    return _UNKNOWN


async def _get_json(client: httpx.AsyncClient, path: str) -> object | None:
    """GET one Ollama path as JSON; ``None`` on any transport, status or JSON failure."""
    try:
        response = await client.get(f"{settings.ollama_url.rstrip('/')}{path}")
        response.raise_for_status()
        body: object = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Ollama %s unavailable (%s)", path, type(exc).__name__)
        return None
    return body


async def fetch_ollama_facts(client: httpx.AsyncClient) -> OllamaFacts:
    """Read the Ollama version and the configured model's digest.

    Args:
        client: Run-owned HTTP client.

    Returns:
        The facts; ``reachable`` is False when ``/api/version`` did not answer.
    """
    version_body = await _get_json(client, "/api/version")
    tags_body = await _get_json(client, "/api/tags")
    return OllamaFacts(
        reachable=version_body is not None,
        version=parse_version(version_body),
        model=settings.ollama_model,
        digest=parse_digest(tags_body, settings.ollama_model),
    )


class ArrivalPattern(enum.StrEnum):
    """How the chunks of one reply were spread in time."""

    INCREMENTAL = "incremental"
    BURST = "burst"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ArrivalSummary:
    """When the content chunks of one streamed reply arrived, as gaps between chunks."""

    chunks: int
    first_chunk_ms: int | None
    last_chunk_ms: int | None
    gaps: int
    paced_gaps: int
    total_ms: int

    @property
    def pattern(self) -> ArrivalPattern:
        """Read the spacing between chunks, never how long the first one took to come.

        Rule fixed before measuring: fewer than five chunks tell nothing; at least half
        of the gaps paced (20 ms or more) is an arrival spread over time, compatible with
        incremental generation; a quarter or fewer is a burst at the client, which a
        withheld reply, fast generation and buffering all produce; anything between is
        inconclusive. Arrivals at the client never show when generation ended.
        """
        if self.chunks < _MIN_CHUNKS or not self.gaps:
            return ArrivalPattern.INCONCLUSIVE
        share = self.paced_gaps / self.gaps
        if share >= _INCREMENTAL_MIN_PACED_SHARE:
            return ArrivalPattern.INCREMENTAL
        if share <= _BURST_MAX_PACED_SHARE:
            return ArrivalPattern.BURST
        return ArrivalPattern.INCONCLUSIVE


def summarize_arrivals(arrivals_ms: Sequence[int], total_ms: int) -> ArrivalSummary:
    """Reduce chunk arrival times (ms since the request) to an ``ArrivalSummary``."""
    gaps = [later - earlier for earlier, later in pairwise(arrivals_ms)]
    return ArrivalSummary(
        chunks=len(arrivals_ms),
        first_chunk_ms=arrivals_ms[0] if arrivals_ms else None,
        last_chunk_ms=arrivals_ms[-1] if arrivals_ms else None,
        gaps=len(gaps),
        paced_gaps=sum(1 for gap in gaps if gap >= _PACED_GAP_MS),
        total_ms=total_ms,
    )


def conforms_to_schema(text: str) -> bool:
    """Whether the assembled reply satisfies the classic response schema.

    The text is judged in memory and dropped; only the boolean leaves this function.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    response = data.get("response")
    emotion = data.get("emotion")
    return (
        isinstance(response, str)
        and bool(response.strip())
        and isinstance(emotion, str)  # a list or a dict is unhashable: look it up only as text
        and emotion in VALID_EMOTIONS
    )


class RunStatus(enum.StrEnum):
    """How one schema-constrained stream ended. Only ``COMPLETE`` runs reach the verdict."""

    COMPLETE = "complete"
    PROVIDER_ERROR = "provider_error"
    INCOMPLETE = "incomplete"
    OFF_SCHEMA = "off_schema"


@dataclass(frozen=True)
class StructuredRun:
    """One run: a closed status and, when the stream finished, its arrival summary."""

    status: RunStatus
    arrivals: ArrivalSummary | None

    @property
    def pattern(self) -> ArrivalPattern | None:
        """The arrival pattern of a ``COMPLETE`` run; ``None`` for any other status."""
        if self.status is RunStatus.COMPLETE and self.arrivals is not None:
            return self.arrivals.pattern
        return None


@dataclass(frozen=True)
class StructuredProbeResult:
    """The runs of one probe: schema-constrained, or the plain-text control."""

    runs: tuple[StructuredRun, ...]
    constrained: bool = True

    def count(self, status: RunStatus) -> int:
        """How many runs ended with ``status``."""
        return sum(1 for run in self.runs if run.status is status)

    @property
    def errors(self) -> int:
        """Provider errors plus incomplete streams: runs that say nothing about Ollama."""
        return self.count(RunStatus.PROVIDER_ERROR) + self.count(RunStatus.INCOMPLETE)

    @property
    def verdict(self) -> ArrivalPattern:
        """The reading of R-6: needs three complete runs and a majority.

        Errors, incomplete streams and off-schema replies never vote; an unclear mix is
        ``INCONCLUSIVE``. ``BURST`` is a burst *at the client*: it cannot tell a withheld
        reply from fast generation or from buffering, so it never proves the header.
        """
        patterns = [run.pattern for run in self.runs if run.status is RunStatus.COMPLETE]
        if len(patterns) < _MIN_COMPLETE_RUNS:
            return ArrivalPattern.INCONCLUSIVE
        for candidate in (ArrivalPattern.INCREMENTAL, ArrivalPattern.BURST):
            if patterns.count(candidate) * 2 > len(patterns):
                return candidate
        return ArrivalPattern.INCONCLUSIVE


def _content(event: dict[str, object]) -> str:
    """Return the text of one stream event, or ``""`` when it carries none."""
    message = event.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    return ""


async def _stream_once(
    client: httpx.AsyncClient, clock: Callable[[], float], *, constrained: bool
) -> StructuredRun:
    """Stream one reply, constrained by the schema or as plain text, and classify its end."""
    payload: dict[str, object] = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": _PROBE_SYSTEM},
            {"role": "user", "content": _PROBE_QUESTION},
        ],
        "stream": True,
    }
    if constrained:
        payload["format"] = _OLLAMA_RESPONSE_SCHEMA
    url = f"{settings.ollama_url.rstrip('/')}/api/chat"
    started = clock()
    arrivals: list[int] = []
    pieces: list[str] = []
    saw_done = False
    received = False
    try:
        async with client.stream(
            "POST", url, json=payload, timeout=settings.ollama_timeout_s
        ) as response:
            response.raise_for_status()
            received = True
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("stream line is not an object")
                if "error" in event:
                    return StructuredRun(RunStatus.PROVIDER_ERROR, None)
                if piece := _content(event):
                    arrivals.append(round((clock() - started) * _MS_PER_SECOND))
                    pieces.append(piece)
                saw_done = saw_done or event.get("done") is True
    except httpx.HTTPError as exc:
        # Before the headers it is the provider; after them the stream was cut.
        logger.warning("Stream probe failed (%s)", type(exc).__name__)
        failed = RunStatus.INCOMPLETE if received else RunStatus.PROVIDER_ERROR
        return StructuredRun(failed, None)
    except ValueError as exc:
        logger.warning("Stream probe failed (%s)", type(exc).__name__)
        return StructuredRun(RunStatus.INCOMPLETE, None)
    if not saw_done:
        return StructuredRun(RunStatus.INCOMPLETE, None)
    total_ms = round((clock() - started) * _MS_PER_SECOND)
    summary = summarize_arrivals(arrivals, total_ms)
    text = "".join(pieces)
    if constrained:
        return StructuredRun(
            RunStatus.COMPLETE if conforms_to_schema(text) else RunStatus.OFF_SCHEMA, summary
        )
    return StructuredRun(RunStatus.COMPLETE if text.strip() else RunStatus.INCOMPLETE, summary)


async def _structured_run(
    client: httpx.AsyncClient, clock: Callable[[], float], *, constrained: bool
) -> StructuredRun:
    """Run one probe stream; an unexpected failure is an incomplete run, never a crash.

    The probe runs after the diagnosis has measured hundreds of streams: a bug here must
    cost one run, not the report of everything measured before it. It is logged by type
    and counted as an error, so it is never silent.
    """
    try:
        return await _stream_once(client, clock, constrained=constrained)
    except Exception as exc:
        logger.warning("Stream probe crashed (%s)", type(exc).__name__)
        return StructuredRun(RunStatus.INCOMPLETE, None)


async def probe_structured_stream(
    client: httpx.AsyncClient,
    *,
    runs: int,
    clock: Callable[[], float] = time.perf_counter,
    constrained: bool = True,
) -> StructuredProbeResult:
    """Measure how the chunks of a streamed reply arrive at this client.

    Args:
        client: Run-owned HTTP client.
        runs: How many times to stream the same synthetic question.
        clock: Monotonic clock in seconds; injectable for tests.
        constrained: Ask for the response schema (``format``) when True; stream plain
            text when False, the control that makes a burst readable.

    Returns:
        One closed ``StructuredRun`` per run; see ``RunStatus`` for how a run can end.
    """
    return StructuredProbeResult(
        tuple([await _structured_run(client, clock, constrained=constrained) for _ in range(runs)]),
        constrained,
    )
```

- [ ] **Step 4: Run, lint, commit.**
  `uv run pytest tests/unit/test_stream_diagnosis_probes.py -q -p no:cacheprovider`
  (68 pass), then `ruff check` and `ruff format --check` over both paths.
  Commit — `feat(scripts): add Ollama facts and structured-stream probe`.

---

## Task 6: Aggregation and counts-only report

**Files:**
- Create: `scripts/stream_diagnosis_stats.py`, `scripts/stream_diagnosis_report.py`
- Test: `tests/unit/test_stream_diagnosis_report.py`

**Interfaces:**
- Consumes: Task 4 `Observation`; Task 3 `StreamVariant`; Task 5
  `StructuredProbeResult`; `StreamOutcome`.
- Produces (stats): `GroupSummary`, `summarize`, `baseline_observations`,
  `group_by_variant_and_source`, `shape_counts`, `dominant_shape`,
  `CaseCounts` / `per_case_counts(observations, variant, runs)`,
  `Comparison` (with `noise_pp`) / `compare_to_full(observations, variant, runs)` /
  `comparisons(observations, runs)`,
  `drift_rates`, `drift_flagged`, `percentiles` (nearest rank), and the constants
  `PERCENT`, `SIGNAL_THRESHOLD_PP`, `DRIFT_THRESHOLD_PP`, `DOMINANT_SHAPE_SHARE`.
  Produces (report): `ReportContext(model, ollama_version, model_digest, runs, seed)`,
  `probe_reading(constrained, plain) -> str`,
  `render_diagnosis_report(observations, context, probe, plain_control=None) -> str`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_stream_diagnosis_report.py`:

```python
"""Aggregation and report of the streaming diagnosis (Plan 0057, Task 6)."""

import pytest

from scripts.eval_stream_diagnosis import Observation
from scripts.eval_stream_protocol import StreamOutcome
from scripts.stream_diagnosis_probes import (
    ArrivalPattern,
    RunStatus,
    StructuredProbeResult,
    StructuredRun,
    summarize_arrivals,
)
from scripts.stream_diagnosis_report import (
    ReportContext,
    probe_reading,
    render_diagnosis_report,
)
from scripts.stream_diagnosis_stats import (
    baseline_observations,
    compare_to_full,
    comparisons,
    dominant_shape,
    drift_flagged,
    drift_rates,
    per_case_counts,
    percentiles,
    shape_counts,
    summarize,
)
from scripts.stream_diagnosis_variants import StreamVariant
from scripts.stream_failure_shapes import FailureShape

_RUNS = 5


def _obs(
    *,
    variant: StreamVariant = StreamVariant.FULL,
    label: str = "case_a",
    source: str = "context",
    outcome: StreamOutcome = StreamOutcome.VALID,
    shape: FailureShape | None = FailureShape.VALID,
    whole: StreamOutcome | None = StreamOutcome.VALID,
    consistent: bool | None = True,
    position: int = 0,
) -> Observation:
    return Observation(
        variant=variant,
        source=source,
        label=label,
        run=1,
        position=position,
        outcome=outcome,
        shape=shape,
        whole_text_outcome=whole,
        fragmentation_consistent=consistent,
        prompt_chars=500,
        reply_chars=40,
        delta_count=8,
        first_delta_ms=50,
        speech_start_ms=100,
        end_ms=200,
    )


def _ok(
    label: str = "case_a", variant: StreamVariant = StreamVariant.FULL, position: int = 0
) -> Observation:
    return _obs(label=label, variant=variant, position=position)


def _bad(
    label: str = "case_a",
    variant: StreamVariant = StreamVariant.FULL,
    shape: FailureShape = FailureShape.NO_TAG,
    position: int = 0,
    source: str = "context",
) -> Observation:
    return _obs(
        label=label,
        variant=variant,
        source=source,
        outcome=StreamOutcome.INVALID_PROTOCOL,
        shape=shape,
        whole=StreamOutcome.INVALID_PROTOCOL,
        position=position,
    )


def _err(label: str = "case_a", variant: StreamVariant = StreamVariant.FULL) -> Observation:
    return _obs(
        label=label,
        variant=variant,
        outcome=StreamOutcome.ERROR,
        shape=None,
        whole=None,
        consistent=None,
    )


def _case(
    variant: StreamVariant, label: str, fallbacks: int, runs: int = _RUNS
) -> list[Observation]:
    """``runs`` complete observations of one turn, ``fallbacks`` of them fallbacks."""
    return [_bad(label, variant) for _ in range(fallbacks)] + [
        _ok(label, variant) for _ in range(runs - fallbacks)
    ]


@pytest.mark.unit
def test_summarize_counts_each_outcome_and_keeps_errors_out_of_the_rate() -> None:
    summary = summarize(
        [
            _ok(),
            _bad(),
            _obs(outcome=StreamOutcome.EMPTY_STREAM, shape=FailureShape.EMPTY),
            _err(),
            _obs(whole=StreamOutcome.INVALID_PROTOCOL, consistent=False),
        ]
    )

    assert (summary.valid, summary.invalid_protocol, summary.empty_stream, summary.errors) == (
        2,
        1,
        1,
        1,
    )
    assert summary.undue_accept == 1
    assert summary.inconsistent == 1
    assert summary.graded == 4
    assert summary.fallback_rate == pytest.approx(2 / 4)


@pytest.mark.unit
def test_the_rate_is_none_when_nothing_was_graded() -> None:
    assert summarize([]).fallback_rate is None


@pytest.mark.unit
def test_the_baseline_is_only_the_full_variant() -> None:
    observations = [
        _ok(),
        _ok(variant=StreamVariant.FULL_REPEAT),
        _bad(variant=StreamVariant.NO_CONTEXT),
    ]

    assert [o.variant for o in baseline_observations(observations)] == [StreamVariant.FULL]


@pytest.mark.unit
def test_shapes_count_only_fallbacks_and_name_the_dominant_one() -> None:
    observations = [
        _bad(shape=FailureShape.TAG_WRAPPED),
        _bad(shape=FailureShape.TAG_WRAPPED),
        _bad(shape=FailureShape.NO_TAG),
        _ok(),
    ]

    counts = shape_counts(observations)

    assert counts == {"tag_wrapped": 2, "no_tag": 1}
    assert dominant_shape(counts) == "tag_wrapped"
    assert dominant_shape({"a": 1, "b": 1, "c": 1}) is None
    assert dominant_shape({}) is None


@pytest.mark.unit
def test_per_case_counts_distinguish_errors_from_missing_and_from_fallbacks() -> None:
    observations = [
        *_case(StreamVariant.FULL, "all_bad", _RUNS),
        _bad("one_bad_four_errors"),
        *[_err("one_bad_four_errors")] * 4,
        *_case(StreamVariant.FULL, "partial", 2, runs=3),
        _bad("other_variant", StreamVariant.NO_CONTEXT),
    ]

    cases = per_case_counts(observations, StreamVariant.FULL, _RUNS)

    assert list(cases) == ["all_bad", "one_bad_four_errors", "partial"]
    assert cases["all_bad"].fell_every_run
    assert cases["all_bad"].complete
    assert cases["one_bad_four_errors"].fallbacks == 1
    assert cases["one_bad_four_errors"].errors == 4
    assert not cases["one_bad_four_errors"].fell_every_run
    assert not cases["partial"].complete
    assert not cases["partial"].fell_every_run


@pytest.mark.unit
def test_removing_a_factor_that_fixes_a_turn_is_an_exploratory_signal_with_its_denominators() -> (
    None
):
    observations = [
        *_case(StreamVariant.FULL, "a", 4),
        *_case(StreamVariant.FULL_REPEAT, "a", 4),
        *_case(StreamVariant.FULL, "b", 0),
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)

    assert result.paired_cases == 1  # only turn "a" was run under the variant
    assert (result.baseline_fallbacks, result.baseline_graded) == (4, 5)
    assert (result.variant_fallbacks, result.variant_graded) == (0, 5)
    assert result.change_pp == pytest.approx(80.0)
    assert result.noise_pp == pytest.approx(0.0)
    assert result.reading == "exploratory signal"


@pytest.mark.unit
def test_a_difference_inside_the_noise_of_its_own_turns_is_no_signal() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 2),
        *_case(StreamVariant.FULL_REPEAT, "a", 4),  # repeating `full` alone moved it 40 points
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)

    assert result.change_pp == pytest.approx(40.0)
    assert result.noise_pp == pytest.approx(40.0)
    assert result.reading == "no signal"  # not above what repeating `full` alone moved


@pytest.mark.unit
def test_noise_is_measured_on_each_comparisons_own_turns_and_does_not_cancel() -> None:
    """Opposite swings on two turns must not average into a quiet control."""
    observations = [
        *_case(StreamVariant.FULL, "a", 5),
        *_case(StreamVariant.FULL_REPEAT, "a", 0),
        *_case(StreamVariant.FULL, "b", 0),
        *_case(StreamVariant.FULL_REPEAT, "b", 5),
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
        *_case(StreamVariant.CONTRACT_FIRST, "a", 0),
        *_case(StreamVariant.CONTRACT_FIRST, "b", 0),
    ]

    only_a = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)
    both = compare_to_full(observations, StreamVariant.CONTRACT_FIRST, _RUNS)

    assert only_a.noise_pp == pytest.approx(100.0)  # turn "a" alone swung 100 points
    assert only_a.change_pp == pytest.approx(100.0)
    assert only_a.reading == "no signal"
    assert both.noise_pp == pytest.approx(100.0)  # 100 on each turn, never averaged to 0
    assert both.change_pp == pytest.approx(50.0)
    assert both.reading == "no signal"


@pytest.mark.unit
def test_a_change_below_the_threshold_is_no_signal() -> None:
    one_in_ten = [*[_bad("a")] * 1, *[_ok("a")] * 9]
    observations = [
        *one_in_ten,
        *[_bad("a", StreamVariant.FULL_REPEAT)] * 1,
        *[_ok("a", StreamVariant.FULL_REPEAT)] * 9,
        *[_ok("a", StreamVariant.NO_CONTEXT)] * 10,
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, 10)

    assert result.change_pp == pytest.approx(10.0)
    assert result.reading == "no signal"


@pytest.mark.unit
def test_a_case_with_a_missing_or_failed_observation_is_excluded_not_compared() -> None:
    observations = [
        *_case(StreamVariant.FULL, "complete", 5),
        *_case(StreamVariant.FULL_REPEAT, "complete", 5),
        *_case(StreamVariant.NO_CONTEXT, "complete", 0),
        *_case(StreamVariant.FULL, "with_error", 5),
        *_case(StreamVariant.FULL_REPEAT, "with_error", 5),
        *_case(StreamVariant.NO_CONTEXT, "with_error", 0, runs=4),
        _err("with_error", StreamVariant.NO_CONTEXT),
        *_case(StreamVariant.FULL, "never_ran_full", 0, runs=3),
        *_case(StreamVariant.FULL_REPEAT, "never_ran_full", 0),
        *_case(StreamVariant.NO_CONTEXT, "never_ran_full", 0),
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)

    assert result.paired_cases == 1
    assert result.excluded_cases == 2
    assert (result.baseline_fallbacks, result.baseline_graded) == (5, 5)
    assert (result.variant_fallbacks, result.variant_graded) == (0, 5)


@pytest.mark.unit
def test_a_turn_without_a_complete_control_is_excluded_and_without_any_it_is_incomplete() -> None:
    observations = [
        *_case(StreamVariant.FULL, "controlled", 3),
        *_case(StreamVariant.FULL_REPEAT, "controlled", 3),
        *_case(StreamVariant.NO_CONTEXT, "controlled", 0),
        *_case(StreamVariant.FULL, "uncontrolled", 3),
        *_case(StreamVariant.NO_CONTEXT, "uncontrolled", 0),
    ]

    partial = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)
    nothing = compare_to_full(
        [o for o in observations if o.variant is not StreamVariant.FULL_REPEAT],
        StreamVariant.NO_CONTEXT,
        _RUNS,
    )

    assert (partial.paired_cases, partial.excluded_cases) == (1, 1)
    assert nothing.paired_cases == 0
    assert nothing.reading == "incomplete"  # no control: never a signal
    assert nothing.change_pp is None
    assert nothing.noise_pp is None


@pytest.mark.unit
def test_no_complete_pair_is_incomplete_and_never_a_signal() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 5),
        *_case(StreamVariant.FULL_REPEAT, "a", 5),
        _err("a", StreamVariant.NO_CONTEXT),
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)

    assert result.paired_cases == 0
    assert result.reading == "incomplete"
    assert result.change_pp is None


@pytest.mark.unit
def test_adding_a_context_to_a_public_question_is_read_in_the_other_direction() -> None:
    observations = [
        *_case(StreamVariant.FULL, "p1", 0),
        *_case(StreamVariant.FULL_REPEAT, "p1", 0),
        *_case(StreamVariant.PUBLIC_WITH_CONTEXT, "p1", 5),
    ]

    result = compare_to_full(observations, StreamVariant.PUBLIC_WITH_CONTEXT, _RUNS)

    assert result.change_pp == pytest.approx(100.0)
    assert result.reading == "exploratory signal"


@pytest.mark.unit
def test_comparisons_cover_every_intervention_that_ran_and_not_the_baseline() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 3),
        *_case(StreamVariant.FULL_REPEAT, "a", 3),
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
        *_case(StreamVariant.CONTRACT_FIRST, "a", 3),
    ]

    result = comparisons(observations, _RUNS)

    assert [c.variant for c in result] == [
        StreamVariant.FULL_REPEAT,
        StreamVariant.NO_CONTEXT,
        StreamVariant.CONTRACT_FIRST,
    ]
    assert result[0].reading == "control"  # the control never counts as a factor
    assert result[0].noise_pp is None
    assert result[1].reading == "exploratory signal"
    assert result[1].noise_pp == pytest.approx(0.0)
    assert result[2].reading == "no signal"


@pytest.mark.unit
def test_drift_splits_the_execution_order_into_quarters() -> None:
    observations = [_ok(position=i) if i < 6 else _bad(position=i) for i in range(8)]

    rates = drift_rates(observations)

    assert rates == [0.0, 0.0, 0.0, 1.0]
    assert drift_flagged(rates)
    assert not drift_flagged([0.1, 0.1, 0.2, 0.1])
    assert not drift_flagged([None, None])
    assert drift_rates([]) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "values, expected",
    [
        ([], None),
        ([10], (10, 10)),
        (list(range(1, 11)), (5, 10)),  # p50: 5th of 10; p95: ceil(9.5) = 10th
        (list(range(1, 12)), (6, 11)),  # p95: ceil(10.45) = 11th; rounding gave the 10th
        (list(range(1, 21)), (10, 19)),
        (list(range(1, 101)), (50, 95)),
        ([30, 10, 20], (20, 30)),
    ],
)
def test_percentiles_use_the_nearest_rank_for_both_p50_and_p95(
    values: list[int], expected: tuple[int, int] | None
) -> None:
    assert percentiles(values) == expected


def _context() -> ReportContext:
    return ReportContext(
        model="qwen2.5:3b",
        ollama_version="0.34.4",
        model_digest="abcdef012345",
        runs=_RUNS,
        seed=57,
    )


def _probe(
    pattern: ArrivalPattern = ArrivalPattern.INCREMENTAL,
    *,
    constrained: bool = True,
    complete: int = 3,
) -> StructuredProbeResult:
    arrivals = {
        ArrivalPattern.INCREMENTAL: summarize_arrivals([0, 100, 200, 300, 400], 410),
        ArrivalPattern.BURST: summarize_arrivals([0, 1, 1, 2, 2], 12),
        ArrivalPattern.INCONCLUSIVE: summarize_arrivals([0, 100], 110),
    }[pattern]
    runs = [StructuredRun(RunStatus.COMPLETE, arrivals)] * complete
    runs.append(StructuredRun(RunStatus.PROVIDER_ERROR, None))
    return StructuredProbeResult(tuple(runs), constrained)


@pytest.mark.unit
def test_the_report_states_facts_rules_and_every_section() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 2),
        *_case(StreamVariant.FULL_REPEAT, "a", 2),
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
        _bad("a", shape=FailureShape.TAG_WRAPPED, position=1),
    ]

    report = render_diagnosis_report(observations, _context(), _probe(), _probe(constrained=False))

    for expected in (
        "qwen2.5:3b",
        "abcdef012345",
        "0.34.4",
        "server defaults",
        "seed: 57",
        "the noise of repeating one condition",
        "## 1. Fallback by variant and source",
        "## 2. Interventions against `full`",
        "exploratory",
        "confirm with another seed",
        "Noise (pp)",
        "mean absolute difference",
        "## 3. Failure shapes",
        "## 4. Turns under `full`",
        "## 5. Timing (ms)",
        "## 6. Execution order",
        "## 7. Prompt size",
        "## 8. Stream arrival probe",
        "### Schema-constrained",
        "### Plain-text control",
        "Verdict: incremental",
        "provider_error",
        "compatible with incremental generation",
    ):
        assert expected in report


@pytest.mark.unit
def test_the_headline_rate_is_the_baseline_not_the_whole_experiment() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 0),
        *_case(StreamVariant.PUBLIC_WITH_CONTEXT, "p", 5),
    ]

    report = render_diagnosis_report(observations, _context(), None)

    assert "baseline (`full`) fallback rate: context 0.00 %" in report
    assert "fallback rate over graded" not in report


@pytest.mark.unit
def test_a_shape_that_only_an_intervention_causes_is_not_the_dominant_shape() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 1),
        *[_bad("p", StreamVariant.PUBLIC_WITH_CONTEXT, FailureShape.TAG_WRAPPED)] * 5,
    ]

    report = render_diagnosis_report(observations, _context(), None)
    full_section = report.split("## 3. Failure shapes")[1].split("## 4.")[0]

    assert "Dominant shape in `full` (context): `no_tag`" in full_section
    assert full_section.count("tag_wrapped") == 1  # only in the apart table of its variant


@pytest.mark.unit
def test_the_case_summary_never_claims_every_run_when_some_were_errors() -> None:
    observations = [_bad("a"), *[_err("a")] * 4]

    report = render_diagnosis_report(observations, _context(), None)

    assert "in every expected run: 0" in report
    assert "incomplete turns: 1" in report


@pytest.mark.unit
def test_the_report_without_a_probe_or_observations_still_renders() -> None:
    report = render_diagnosis_report([], _context(), None)

    assert "Not run." in report
    assert "n/a" in report


@pytest.mark.unit
def test_a_report_without_the_control_probe_says_so() -> None:
    report = render_diagnosis_report([], _context(), _probe(), None)

    assert "Plain-text control: not run." in report


@pytest.mark.unit
@pytest.mark.parametrize(
    "constrained, plain, fragment",
    [
        (ArrivalPattern.INCREMENTAL, None, "compatible with incremental generation"),
        (
            ArrivalPattern.INCREMENTAL,
            ArrivalPattern.BURST,
            "compatible with incremental generation",
        ),
        (ArrivalPattern.BURST, ArrivalPattern.INCREMENTAL, "differs from the plain-text control"),
        (ArrivalPattern.BURST, ArrivalPattern.BURST, "cannot tell generation from buffering"),
        (ArrivalPattern.BURST, ArrivalPattern.INCONCLUSIVE, "stays unproven"),
        (ArrivalPattern.BURST, None, "stays unproven"),
        (ArrivalPattern.INCONCLUSIVE, ArrivalPattern.INCREMENTAL, "No conclusion"),
        (ArrivalPattern.INCONCLUSIVE, None, "No conclusion"),
    ],
)
def test_a_burst_is_never_read_as_proof_that_ollama_withholds_the_reply(
    constrained: ArrivalPattern, plain: ArrivalPattern | None, fragment: str
) -> None:
    control = None if plain is None else _probe(plain, constrained=False)

    reading = probe_reading(_probe(constrained), control)

    assert fragment in reading
    assert "header holds" not in reading
    if constrained is ArrivalPattern.INCONCLUSIVE:
        assert "not evidence that the" in reading


@pytest.mark.unit
def test_the_report_states_what_a_client_side_probe_can_and_cannot_see() -> None:
    report = render_diagnosis_report([], _context(), _probe(ArrivalPattern.BURST), None)

    assert "as this client received them" in report
    assert "a burst never proves" in report
    assert "stays unproven" in report
    assert "header holds" not in report


@pytest.mark.unit
def test_a_spread_out_arrival_is_compatible_with_incremental_generation_not_proof_of_it() -> None:
    """The client sees arrivals, not when Ollama finished generating."""
    reading = probe_reading(_probe(ArrivalPattern.INCREMENTAL), None)

    assert "cannot see when generation ended" in reading
    assert "evidence against" in reading
    assert "is wrong" not in reading
    assert "did not withhold" not in reading
```

- [ ] **Step 2: Run it to see it fail.**
  `uv run pytest tests/unit/test_stream_diagnosis_report.py -q -p no:cacheprovider`.
  Expected: `ModuleNotFoundError: No module named 'scripts.stream_diagnosis_report'`.

- [ ] **Step 3: Write the aggregation module** (the constants are R-2, R-3 and R-5 of
  the *Rules*; change none of them after the run starts. A comparison pairs only the
  turns where `full`, the variant and the `full_repeat` control have every expected run
  graded, and measures its noise on exactly those turns)

`scripts/stream_diagnosis_stats.py`:

```python
"""Counts-only aggregation of the streaming diagnosis (Plan 0057).

Every rule that turns a number into a reading is a constant below, fixed before the
measurement is run. Nothing here reads, prints or stores model output.

The baseline is the ``full`` variant: the rate and the dominant failure shape describe
production's own prompt. Every other variant is an intervention and is read apart,
against ``full`` on the very turns it ran, with its denominators in view.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.eval_stream_protocol import StreamOutcome
from scripts.stream_diagnosis_variants import StreamVariant

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from scripts.eval_stream_diagnosis import Observation

PERCENT = 100
SIGNAL_THRESHOLD_PP = 15.0
DRIFT_THRESHOLD_PP = 15.0
DOMINANT_SHAPE_SHARE = 0.5
_BUCKETS = 4
_P50 = 50
_P95 = 95

# Variants that add something to the baseline; every other variant removes or moves it.
_ADDITIVE = frozenset({StreamVariant.PUBLIC_WITH_CONTEXT})
READING_SIGNAL = "exploratory signal"
READING_NO_SIGNAL = "no signal"
READING_INCOMPLETE = "incomplete"
READING_CONTROL = "control"


@dataclass(frozen=True)
class GroupSummary:
    """Outcome counts of one group of observations."""

    valid: int
    invalid_protocol: int
    empty_stream: int
    errors: int
    undue_accept: int
    inconsistent: int

    @property
    def graded(self) -> int:
        """Observations that count toward the rate (provider errors excluded)."""
        return self.valid + self.invalid_protocol + self.empty_stream

    @property
    def fallbacks(self) -> int:
        """Graded replies that would drop to the fallback phrase."""
        return self.invalid_protocol + self.empty_stream

    @property
    def fallback_rate(self) -> float | None:
        """Share of graded replies that would drop to the fallback phrase."""
        if not self.graded:
            return None
        return self.fallbacks / self.graded


def summarize(observations: Iterable[Observation]) -> GroupSummary:
    """Count outcomes, undue accepts and fragmentation-dependent replies."""
    items = list(observations)
    return GroupSummary(
        valid=sum(o.outcome is StreamOutcome.VALID for o in items),
        invalid_protocol=sum(o.outcome is StreamOutcome.INVALID_PROTOCOL for o in items),
        empty_stream=sum(o.outcome is StreamOutcome.EMPTY_STREAM for o in items),
        errors=sum(o.outcome is StreamOutcome.ERROR for o in items),
        undue_accept=sum(o.undue_accept for o in items),
        inconsistent=sum(o.fragmentation_consistent is False for o in items),
    )


def _rate(observations: Iterable[Observation]) -> float | None:
    return summarize(observations).fallback_rate


def baseline_observations(observations: Iterable[Observation]) -> list[Observation]:
    """Return only the ``full`` observations: production's own prompt."""
    return [obs for obs in observations if obs.variant is StreamVariant.FULL]


def group_by_variant_and_source(
    observations: Sequence[Observation],
) -> dict[tuple[StreamVariant, str], list[Observation]]:
    """Group observations by variant (enum order) then source."""
    groups: dict[tuple[StreamVariant, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        groups[(obs.variant, obs.source)].append(obs)
    return dict(
        sorted(groups.items(), key=lambda item: (list(StreamVariant).index(item[0][0]), item[0][1]))
    )


def shape_counts(observations: Iterable[Observation]) -> dict[str, int]:
    """Count the failure shapes of the replies that fell back, most frequent first."""
    counts: dict[str, int] = defaultdict(int)
    for obs in observations:
        if obs.fell_back and obs.shape is not None:
            counts[obs.shape.value] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def dominant_shape(counts: dict[str, int]) -> str | None:
    """Return the shape holding at least half of the fallbacks, if there is one."""
    total = sum(counts.values())
    for shape, count in counts.items():
        if total and count / total >= DOMINANT_SHAPE_SHARE:
            return shape
    return None


@dataclass(frozen=True)
class CaseCounts:
    """What happened to one turn under one variant, against the runs that were expected."""

    fallbacks: int
    errors: int
    graded: int
    expected: int

    @property
    def complete(self) -> bool:
        """Whether every expected run produced a gradable reply (none missing, none failed)."""
        return self.graded == self.expected

    @property
    def fell_every_run(self) -> bool:
        """Whether every expected run was graded and fell back."""
        return self.fallbacks == self.expected


def per_case_counts(
    observations: Iterable[Observation], variant: StreamVariant, runs: int
) -> dict[str, CaseCounts]:
    """Return the counts of every turn of one variant, sorted by label.

    Args:
        observations: Every observation of the run.
        variant: The variant to read.
        runs: The repetitions that were expected per turn; a missing or failed one keeps
            the turn from being ``complete``.
    """
    by_label: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        if obs.variant is variant:
            by_label[obs.label].append(obs)
    result = {}
    for label, items in sorted(by_label.items()):
        summary = summarize(items)
        result[label] = CaseCounts(summary.fallbacks, summary.errors, summary.graded, runs)
    return result


@dataclass(frozen=True)
class Comparison:
    """One variant against ``full`` on the turns where every needed side is complete."""

    variant: StreamVariant
    paired_cases: int
    excluded_cases: int
    baseline_fallbacks: int
    baseline_graded: int
    variant_fallbacks: int
    variant_graded: int
    noise_pp: float | None

    @property
    def baseline_rate(self) -> float | None:
        """The ``full`` rate on the paired turns."""
        return self.baseline_fallbacks / self.baseline_graded if self.baseline_graded else None

    @property
    def variant_rate(self) -> float | None:
        """The variant's rate on the paired turns."""
        return self.variant_fallbacks / self.variant_graded if self.variant_graded else None

    @property
    def change_pp(self) -> float | None:
        """Points the intervention moved the rate in the direction that would be a cause.

        Removing or moving a factor: ``full`` minus the variant. Adding one: the variant
        minus ``full``. ``None`` when there is no complete pair.
        """
        if self.baseline_rate is None or self.variant_rate is None:
            return None
        if self.variant in _ADDITIVE:
            return (self.variant_rate - self.baseline_rate) * PERCENT
        return (self.baseline_rate - self.variant_rate) * PERCENT

    @property
    def reading(self) -> str:
        """An exploratory reading, never a cause.

        A signal needs a change of at least 15 points that also exceeds the noise measured
        on the very same turns. A comparison without a complete control on its turns is
        ``incomplete``: it can never be a signal.
        """
        if self.variant is StreamVariant.FULL_REPEAT:
            return READING_CONTROL
        change = self.change_pp
        if change is None or self.noise_pp is None:
            return READING_INCOMPLETE
        if change >= SIGNAL_THRESHOLD_PP and change > self.noise_pp:
            return READING_SIGNAL
        return READING_NO_SIGNAL


def _turn_rate(counts: CaseCounts) -> float:
    return counts.fallbacks / counts.graded


def compare_to_full(
    observations: Sequence[Observation], variant: StreamVariant, runs: int
) -> Comparison:
    """Compare ``variant`` with ``full`` on the turns where every needed side is complete.

    A turn needs all ``runs`` graded on ``full``, on the variant and, for an
    intervention, on the ``full_repeat`` control. A turn missing any of them is excluded,
    never compared on a different sample.

    The noise is how much repeating ``full`` alone moved each paired turn, averaged as an
    absolute difference turn by turn (opposite swings on two turns never cancel). It is
    measured on exactly the turns the comparison uses.
    """
    full = per_case_counts(observations, StreamVariant.FULL, runs)
    ran = per_case_counts(observations, variant, runs)
    control = per_case_counts(observations, StreamVariant.FULL_REPEAT, runs)
    is_control = variant is StreamVariant.FULL_REPEAT
    paired = [
        label
        for label, counts in ran.items()
        if counts.complete
        and label in full
        and full[label].complete
        and (is_control or (label in control and control[label].complete))
    ]
    noise = None
    if paired and not is_control:
        noise = (
            sum(abs(_turn_rate(full[label]) - _turn_rate(control[label])) for label in paired)
            / len(paired)
            * PERCENT
        )
    return Comparison(
        variant=variant,
        paired_cases=len(paired),
        excluded_cases=len(ran) - len(paired),
        baseline_fallbacks=sum(full[label].fallbacks for label in paired),
        baseline_graded=sum(full[label].graded for label in paired),
        variant_fallbacks=sum(ran[label].fallbacks for label in paired),
        variant_graded=sum(ran[label].graded for label in paired),
        noise_pp=noise,
    )


def comparisons(observations: Sequence[Observation], runs: int) -> list[Comparison]:
    """Compare every variant that ran with ``full``, the noise control first."""
    present = {obs.variant for obs in observations}
    return [
        compare_to_full(observations, variant, runs)
        for variant in StreamVariant
        if variant is not StreamVariant.FULL and variant in present
    ]


def drift_rates(observations: Sequence[Observation]) -> list[float | None]:
    """Return the fallback rate in each quarter of the execution order."""
    if not observations:
        return []
    total = max(o.position for o in observations) + 1
    buckets: list[list[Observation]] = [[] for _ in range(_BUCKETS)]
    for obs in observations:
        buckets[min(_BUCKETS - 1, obs.position * _BUCKETS // total)].append(obs)
    return [_rate(bucket) for bucket in buckets]


def drift_flagged(rates: Sequence[float | None]) -> bool:
    """Whether the highest and lowest quarter differ by at least 15 percentage points."""
    known = [rate for rate in rates if rate is not None]
    return bool(known) and (max(known) - min(known)) * PERCENT >= DRIFT_THRESHOLD_PP


def _nearest_rank(ordered: Sequence[int], percent: int) -> int:
    """The value at rank ``ceil(n * percent / 100)`` of an ascending list (integer math)."""
    rank = -(-len(ordered) * percent // PERCENT)
    return ordered[max(rank, 1) - 1]


def percentiles(values: Sequence[int]) -> tuple[int, int] | None:
    """Return ``(p50, p95)`` by the nearest-rank method, or ``None`` for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return _nearest_rank(ordered, _P50), _nearest_rank(ordered, _P95)
```

- [ ] **Step 4: Write the report module**

`scripts/stream_diagnosis_report.py`:

```python
"""Markdown report of the streaming diagnosis (Plan 0057): counts and rates only.

Nothing here reads, prints or stores model output; the rules behind each reading live
in ``stream_diagnosis_stats`` and ``stream_diagnosis_probes``. The headline and the
failure shapes describe the baseline (``full``); every other variant is read apart.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.eval_stream_protocol import StreamOutcome
from scripts.stream_diagnosis_probes import ArrivalPattern, RunStatus
from scripts.stream_diagnosis_stats import (
    DRIFT_THRESHOLD_PP,
    PERCENT,
    SIGNAL_THRESHOLD_PP,
    baseline_observations,
    comparisons,
    dominant_shape,
    drift_flagged,
    drift_rates,
    group_by_variant_and_source,
    per_case_counts,
    percentiles,
    shape_counts,
    summarize,
)
from scripts.stream_diagnosis_variants import VARIANT_DESCRIPTIONS, StreamVariant

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from scripts.eval_stream_diagnosis import Observation
    from scripts.stream_diagnosis_probes import StructuredProbeResult

_SOURCES = ("context", "public")


@dataclass(frozen=True)
class ReportContext:
    """What the run was made against and with."""

    model: str
    ollama_version: str
    model_digest: str
    runs: int
    seed: int


def _percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * PERCENT:.2f} %"


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return [*lines, ""]


def _fraction(fallbacks: int, graded: int) -> str:
    rate = fallbacks / graded if graded else None
    return f"{fallbacks}/{graded} ({_percent(rate)})"


def _legend_section() -> list[str]:
    rows = [(variant.value, VARIANT_DESCRIPTIONS[variant]) for variant in StreamVariant]
    return ["## Variants", "", *_table(("Variant", "What it changes"), rows)]


def _variant_section(observations: Sequence[Observation]) -> list[str]:
    rows = []
    for (variant, source), items in group_by_variant_and_source(observations).items():
        s = summarize(items)
        rows.append(
            (
                variant.value,
                source,
                s.valid,
                s.invalid_protocol,
                s.empty_stream,
                s.errors,
                _percent(s.fallback_rate),
                s.undue_accept,
                s.inconsistent,
            )
        )
    header = (
        "Variant",
        "Source",
        "Valid",
        "Invalid",
        "Empty",
        "Errors",
        "Fallback rate",
        "Undue accept",
        "Split-dependent",
    )
    return ["## 1. Fallback by variant and source", "", *_table(header, rows)]


def _comparison_section(observations: Sequence[Observation], runs: int) -> list[str]:
    rows = []
    for c in comparisons(observations, runs):
        change = "n/a" if c.change_pp is None else f"{c.change_pp:+.1f}"
        noise = "n/a" if c.noise_pp is None else f"{c.noise_pp:.1f}"
        rows.append(
            (
                c.variant.value,
                c.paired_cases,
                c.excluded_cases,
                _fraction(c.baseline_fallbacks, c.baseline_graded),
                _fraction(c.variant_fallbacks, c.variant_graded),
                change,
                noise,
                c.reading,
            )
        )
    rule = (
        f"Each row compares one intervention with `full` on the turns where `full`, the "
        f"variant and the `full_repeat` control all have the {runs} expected runs graded; a "
        f"turn missing any of them is excluded, never compared on a different sample, and a "
        f"row with no complete control is `incomplete`, never a signal. The noise of a row "
        f"is the mean absolute difference, turn by turn, between `full` and `full_repeat` "
        f"on that row's own turns (opposite swings never cancel). A signal is a change of "
        f"at least {SIGNAL_THRESHOLD_PP:.0f} points that also exceeds that noise. It is an "
        f"exploratory signal, not a cause: confirm with another seed before attributing one."
    )
    note = (
        "`question_only` runs only on turns that have a person or a history; elsewhere it "
        "sends what `no_context` sends and is not repeated."
    )
    header = (
        "Variant",
        "Paired",
        "Excluded",
        "`full`",
        "Variant",
        "Change (pp)",
        "Noise (pp)",
        "Reading",
    )
    return [
        "## 2. Interventions against `full` (exploratory)",
        "",
        rule,
        "",
        *_table(header, rows),
        note,
        "",
    ]


def _shape_section(observations: Sequence[Observation]) -> list[str]:
    lines = ["## 3. Failure shapes", ""]
    baseline = baseline_observations(observations)
    for source in _SOURCES:
        counts = shape_counts(o for o in baseline if o.source == source)
        total = sum(counts.values())
        lines.extend(
            _table(
                (f"Shape in `full` ({source})", "Count", "Share"),
                [(shape, n, _percent(n / total)) for shape, n in counts.items()],
            )
        )
        dominant = dominant_shape(counts)
        if not counts:
            lines.extend([f"No fallbacks in `full` ({source}).", ""])
        elif dominant:
            lines.extend([f"Dominant shape in `full` ({source}): `{dominant}`.", ""])
        else:
            lines.extend([f"No shape holds half of the fallbacks in `full` ({source}).", ""])
    rows = []
    for (variant, source), items in group_by_variant_and_source(observations).items():
        if variant is StreamVariant.FULL:
            continue
        rows.extend((variant.value, source, shape, n) for shape, n in shape_counts(items).items())
    lines.extend(["Shapes of each intervention, apart (never merged into the baseline):", ""])
    return [*lines, *_table(("Variant", "Source", "Shape", "Count"), rows)]


def _case_section(observations: Sequence[Observation], runs: int) -> list[str]:
    cases = per_case_counts(observations, StreamVariant.FULL, runs)
    some = sum(1 for c in cases.values() if c.fallbacks)
    always = sum(1 for c in cases.values() if c.fell_every_run)
    incomplete = sum(1 for c in cases.values() if not c.complete)
    rows = [(label, c.fallbacks, c.errors, c.graded, c.expected) for label, c in cases.items()]
    summary = (
        f"Turns with at least one fallback: {some} of {len(cases)}; that fell back in every "
        f"expected run: {always}; incomplete turns: {incomplete}."
    )
    header = ("Turn", "Fallbacks", "Provider errors", "Graded", "Expected")
    return ["## 4. Turns under `full`", "", *_table(header, rows), summary, ""]


def _timing_cells(group: Sequence[Observation]) -> list[str]:
    cells = []
    for pick in (
        lambda o: o.first_delta_ms,
        lambda o: o.speech_start_ms,
        lambda o: o.end_ms,
    ):
        found = percentiles([v for v in (pick(o) for o in group) if v is not None])
        cells.append("n/a" if found is None else f"{found[0]} / {found[1]}")
    return cells


def _timing_section(observations: Sequence[Observation]) -> list[str]:
    rows = []
    by_variant: dict[StreamVariant, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_variant[obs.variant].append(obs)
    for variant in StreamVariant:
        items = by_variant.get(variant, [])
        for name, group in (
            ("valid", [o for o in items if o.outcome is StreamOutcome.VALID]),
            ("fallback", [o for o in items if o.fell_back]),
        ):
            if group:
                rows.append([variant.value, name, len(group), *_timing_cells(group)])
    header = ("Variant", "Outcome", "n", "First delta", "Speech start", "End")
    note = (
        "p50 / p95 by the nearest-rank method. Speech start is when production would hand "
        "its first sentence, or the fallback, to TTS (TTS time excluded)."
    )
    return ["## 5. Timing (ms)", "", *_table(header, rows), note, ""]


def _drift_section(observations: Sequence[Observation]) -> list[str]:
    rates = drift_rates(observations)
    rows = [(f"Q{i}", _percent(rate)) for i, rate in enumerate(rates, start=1)]
    verdict = (
        f"Quarters differ by {DRIFT_THRESHOLD_PP:.0f} points or more: repeat with another seed."
        if drift_flagged(rates)
        else "No order effect above the rule."
    )
    note = "Quarters of the shuffled execution order, all variants together: it describes the experiment, not the baseline."
    return [
        "## 6. Execution order",
        "",
        note,
        "",
        *_table(("Quarter", "Fallback rate"), rows),
        verdict,
        "",
    ]


def _prompt_section(observations: Sequence[Observation]) -> list[str]:
    by_variant: dict[StreamVariant, list[int]] = defaultdict(list)
    for obs in observations:
        by_variant[obs.variant].append(obs.prompt_chars)
    rows = [
        (
            v.value,
            min(by_variant[v]),
            round(sum(by_variant[v]) / len(by_variant[v])),
            max(by_variant[v]),
        )
        for v in StreamVariant
        if v in by_variant
    ]
    return [
        "## 7. Prompt size (characters sent)",
        "",
        *_table(("Variant", "Min", "Mean", "Max"), rows),
    ]


def probe_reading(constrained: StructuredProbeResult, plain: StructuredProbeResult | None) -> str:
    """Read the two probes together, never claiming more than a client can see.

    A burst at the client is what a withheld reply, fast generation and buffering all
    look like; only a spread-out arrival of the schema-constrained reply is evidence
    (against the claim, being compatible with incremental generation), and a contrast
    with the plain-text control is a hint, not a proof.
    """
    verdict = constrained.verdict
    if verdict is ArrivalPattern.INCREMENTAL:
        return (
            "The schema-constrained reply reached this client spread over time, which is "
            "compatible with incremental generation: streaming with a JSON schema is a "
            "candidate protocol and this is evidence against the `llm_streaming.py` claim "
            "that Ollama withholds it, though a client cannot see when generation ended."
        )
    if verdict is ArrivalPattern.INCONCLUSIVE:
        return (
            "No conclusion: the schema-constrained runs show no clear pattern, or too few "
            "were complete. This is not evidence that the `llm_streaming.py` header is right."
        )
    control = None if plain is None else plain.verdict
    if control is ArrivalPattern.INCREMENTAL:
        return (
            "The schema-constrained reply reached this client as a burst while the plain-text "
            "control arrived spread over time. That differs from the plain-text control and is "
            "consistent with Ollama withholding schema output, but a client cannot prove the "
            "cause: the "
            "`llm_streaming.py` claim stays unproven."
        )
    if control is ArrivalPattern.BURST:
        return (
            "Both the schema-constrained reply and the plain-text control reached this client "
            "as bursts: this probe cannot tell generation from buffering here, so the "
            "`llm_streaming.py` claim stays unproven."
        )
    return (
        "The schema-constrained reply reached this client as a burst, and without a "
        "plain-text control that reads clearly this cannot show that Ollama withholds it "
        "(fast generation and buffering look the same): the `llm_streaming.py` claim stays "
        "unproven."
    )


def _probe_table(probe: StructuredProbeResult) -> list[str]:
    rows = []
    for i, run in enumerate(probe.runs, start=1):
        a = run.arrivals
        rows.append(
            (
                i,
                run.status.value,
                "n/a" if a is None else a.chunks,
                "n/a" if a is None else f"{a.paced_gaps}/{a.gaps}",
                "n/a" if a is None else a.pattern.value,
            )
        )
    counts = (
        f"Complete runs: {probe.count(RunStatus.COMPLETE)} of {len(probe.runs)}; "
        f"provider errors: {probe.count(RunStatus.PROVIDER_ERROR)}; "
        f"incomplete: {probe.count(RunStatus.INCOMPLETE)}; "
        f"off schema: {probe.count(RunStatus.OFF_SCHEMA)}. "
        f"Verdict: {probe.verdict.value}."
    )
    header = ("Run", "Status", "Chunks", "Paced gaps / gaps", "Pattern")
    return [*_table(header, rows), counts, ""]


def _probe_section(
    constrained: StructuredProbeResult | None, plain: StructuredProbeResult | None
) -> list[str]:
    if constrained is None:
        return ["## 8. Stream arrival probe", "", "Not run.", ""]
    note = (
        "The probe sees the chunks as this client received them. It cannot tell a reply "
        "that Ollama withheld from fast generation, from buffering or from the client's own "
        "reading, so a burst never proves the `llm_streaming.py` header; only a "
        "spread-out arrival of the schema-constrained reply is evidence against it."
    )
    lines = [
        "## 8. Stream arrival probe",
        "",
        note,
        "",
        "### Schema-constrained",
        "",
        *_probe_table(constrained),
    ]
    if plain is None:
        lines.extend(["Plain-text control: not run.", ""])
    else:
        lines.extend(["### Plain-text control", "", *_probe_table(plain)])
    return [*lines, f"Reading: {probe_reading(constrained, plain)}", ""]


def _head(observations: Sequence[Observation], context: ReportContext) -> list[str]:
    total = summarize(observations)
    baseline = baseline_observations(observations)
    by_source = ", ".join(
        f"{source} {_percent(summarize(o for o in baseline if o.source == source).fallback_rate)}"
        for source in _SOURCES
    )
    return [
        "# Streaming protocol diagnosis (Plan 0057)",
        "",
        f"- model: {context.model} (digest `{context.model_digest}`)",
        f"- ollama version: {context.ollama_version}",
        "- generation options: server defaults (production passes none)",
        f"- runs per turn and variant: {context.runs}; shuffle seed: {context.seed}",
        f"- observations (all variants): {len(observations)} "
        f"(graded {total.graded}, provider errors {total.errors})",
        f"- baseline (`full`) fallback rate: {by_source}",
        f"- replies spoken that the whole text rejects (all variants): {total.undue_accept}",
        "",
    ]


def render_diagnosis_report(
    observations: Sequence[Observation],
    context: ReportContext,
    probe: StructuredProbeResult | None,
    plain_control: StructuredProbeResult | None = None,
) -> str:
    """Render the diagnosis as Markdown: counts and rates only, never model output.

    Args:
        observations: Every observation of the run, in any order.
        context: The facts of the run (model, Ollama, runs per variant, seed).
        probe: The schema-constrained probe result, or ``None`` when it was skipped.
        plain_control: The plain-text control probe, or ``None`` when it was skipped.

    Returns:
        The Markdown report. The headline and the failure shapes describe ``full``;
        interventions appear apart.
    """
    sections = [
        _head(observations, context),
        _legend_section(),
        _variant_section(observations),
        _comparison_section(observations, context.runs),
        _shape_section(observations),
        _case_section(observations, context.runs),
        _timing_section(observations),
        _drift_section(observations),
        _prompt_section(observations),
        _probe_section(probe, plain_control),
    ]
    return "\n".join(line for section in sections for line in section)
```

- [ ] **Step 5: Run, lint, commit.**
  `uv run pytest tests/unit/test_stream_diagnosis_report.py -q -p no:cacheprovider`
  (38 pass), then `ruff check` and `ruff format --check` over the three paths.
  Commit — `feat(scripts): aggregate and render the stream diagnosis`.

---

## Task 7: `just diagnose-stream`

**Files:**
- Create: `scripts/diagnose_stream_protocol.py`
- Modify: `scripts/eval_chat.py` (one extracted helper), `justfile`
- Test: `tests/unit/test_diagnose_stream_protocol.py`

**Interfaces:**
- Consumes: everything above, plus `scripts.eval_chat` (`_GOLDEN_PATH`,
  `_REPORT_DIRECTORY`, `load_suite`, `select_cases`, `write_report`) and
  `scripts.longitudinal_eval_metadata.sanitize_url`.
- Produces: `golden_stream_turns(cases) -> list[StreamTurn]` (in `eval_chat`),
  `CliOptions`, `parse_cli_args`, `run_cli(options, *, client_factory) -> int`
  (`0` ok, `1` provider error, `2` Ollama not answering, nothing written); it runs the
  schema-constrained probe and then the plain-text control, and still writes the report
  of every stream measured whatever a probe reply looks like.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_diagnose_stream_protocol.py`:

```python
"""The ``just diagnose-stream`` command (Plan 0057, Task 6)."""

from collections import Counter
from collections.abc import AsyncGenerator, AsyncIterator, Callable
import contextlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import NamedTuple
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from scripts import diagnose_stream_protocol as cli
from scripts.diagnose_stream_protocol import CliOptions, parse_cli_args, run_cli
from scripts.eval_chat import golden_stream_turns, load_suite
from scripts.eval_stream_diagnosis import Observation, run_diagnosis
from scripts.eval_stream_protocol import StreamOutcome, public_turns
from scripts.stream_diagnosis_probes import (
    OllamaFacts,
    RunStatus,
    StructuredProbeResult,
    StructuredRun,
    summarize_arrivals,
)
from scripts.stream_diagnosis_report import ReportContext, render_diagnosis_report
from scripts.stream_diagnosis_variants import DiagnosisUnit, StreamVariant, build_units
from scripts.stream_failure_shapes import FailureShape


@contextlib.asynccontextmanager
async def _factory() -> AsyncGenerator[httpx.AsyncClient]:
    yield Mock(spec=httpx.AsyncClient)


def _observation(
    outcome: StreamOutcome, variant: StreamVariant = StreamVariant.FULL
) -> Observation:
    return Observation(
        variant=variant,
        source="public",
        label="public_1",
        run=1,
        position=0,
        outcome=outcome,
        shape=None if outcome is StreamOutcome.ERROR else FailureShape.VALID,
        whole_text_outcome=None if outcome is StreamOutcome.ERROR else StreamOutcome.VALID,
        fragmentation_consistent=None if outcome is StreamOutcome.ERROR else True,
        prompt_chars=10,
        reply_chars=5,
        delta_count=1,
        first_delta_ms=1,
        speech_start_ms=1,
        end_ms=2,
    )


def _probe_result(*extra: RunStatus, constrained: bool = True) -> StructuredProbeResult:
    paced = summarize_arrivals([0, 100, 200, 300, 400], 410)
    runs = [StructuredRun(RunStatus.COMPLETE, paced)] * 3
    extras = (StructuredRun(status, None) for status in extra)
    return StructuredProbeResult((*runs, *extras), constrained)


class _Patched(NamedTuple):
    run: AsyncMock
    probe: AsyncMock | None


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reachable: bool = True,
    outcome: StreamOutcome = StreamOutcome.VALID,
    probe_extra: tuple[RunStatus, ...] = (),
    control_extra: tuple[RunStatus, ...] = (),
    patch_probe: bool = True,
) -> _Patched:
    facts = OllamaFacts(reachable=reachable, version="0.34.4", model="qwen2.5:3b", digest="abc")
    monkeypatch.setattr(cli, "fetch_ollama_facts", AsyncMock(return_value=facts))
    run = AsyncMock(return_value=[_observation(outcome)])
    monkeypatch.setattr(cli, "run_diagnosis", run)
    if not patch_probe:
        return _Patched(run, None)

    def probe_result(
        _client: object, *, runs: int, constrained: bool = True
    ) -> StructuredProbeResult:
        extra = probe_extra if constrained else control_extra
        return _probe_result(*extra, constrained=constrained)

    probe = AsyncMock(side_effect=probe_result)
    monkeypatch.setattr(cli, "probe_structured_stream", probe)
    return _Patched(run, probe)


@pytest.mark.unit
def test_the_defaults_match_the_plan() -> None:
    options = parse_cli_args([])

    assert (options.runs, options.seed, options.variants, options.structured_runs) == (
        5,
        57,
        None,
        5,
    )


@pytest.mark.unit
def test_variants_are_parsed_as_words_without_quotes() -> None:
    options = parse_cli_args(["--variants", "no_context", "question_only", "--runs", "3"])

    assert options.variants == [StreamVariant.NO_CONTEXT, StreamVariant.QUESTION_ONLY]
    assert options.runs == 3


@pytest.mark.unit
@pytest.mark.parametrize("argv", [["--runs", "0"], ["--runs", "11"], ["--structured-runs", "11"]])
def test_out_of_range_runs_are_rejected(argv: list[str]) -> None:
    with pytest.raises(ValueError, match=r"less than or equal|greater than or equal"):
        parse_cli_args(argv)


@pytest.mark.unit
def test_an_unknown_variant_is_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["--variants", "nope"])


@pytest.mark.unit
async def test_a_complete_run_writes_the_report_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _patch(monkeypatch).run
    output = tmp_path / "diagnosis.md"

    code = await run_cli(CliOptions(output=output, runs=2, seed=9), client_factory=_factory)

    assert code == 0
    text = output.read_text(encoding="utf-8")
    assert "# Streaming protocol diagnosis (Plan 0057)" in text
    assert "qwen2.5:3b" in text
    assert "seed: 9" in text
    assert run.await_args is not None
    assert run.await_args.kwargs["runs"] == 2
    assert run.await_args.kwargs["seed"] == 9
    units = run.await_args.args[0]
    assert {u.variant for u in units} == set(StreamVariant)


@pytest.mark.unit
async def test_the_closing_log_line_reports_the_baseline_rate_not_the_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch(monkeypatch)
    monkeypatch.setattr(
        cli,
        "run_diagnosis",
        AsyncMock(
            return_value=[
                _observation(StreamOutcome.VALID),
                _observation(StreamOutcome.INVALID_PROTOCOL, variant=StreamVariant.NO_CONTEXT),
            ]
        ),
    )

    with caplog.at_level("INFO", logger=cli.logger.name):
        await run_cli(CliOptions(output=tmp_path / "d.md"), client_factory=_factory)

    assert "baseline_fallback_rate=0.0" in caplog.text


@pytest.mark.unit
async def test_the_variant_filter_reaches_the_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _patch(monkeypatch).run
    options = CliOptions(output=tmp_path / "d.md", variants=[StreamVariant.NO_CONTEXT])

    await run_cli(options, client_factory=_factory)

    assert run.await_args is not None
    assert {u.variant for u in run.await_args.args[0]} == {StreamVariant.NO_CONTEXT}


@pytest.mark.unit
async def test_a_provider_error_exits_one_but_still_writes_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, outcome=StreamOutcome.ERROR)
    output = tmp_path / "d.md"

    assert await run_cli(CliOptions(output=output), client_factory=_factory) == 1
    assert output.exists()


@pytest.mark.unit
@pytest.mark.parametrize("status", [RunStatus.PROVIDER_ERROR, RunStatus.INCOMPLETE])
async def test_a_failed_probe_run_also_exits_one(
    status: RunStatus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, probe_extra=(status,))

    assert await run_cli(CliOptions(output=tmp_path / "d.md"), client_factory=_factory) == 1


@pytest.mark.unit
async def test_an_off_schema_probe_run_is_a_finding_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, probe_extra=(RunStatus.OFF_SCHEMA,))
    output = tmp_path / "d.md"

    assert await run_cli(CliOptions(output=output), client_factory=_factory) == 0
    assert "off_schema" in output.read_text(encoding="utf-8")


@pytest.mark.unit
async def test_the_plain_text_control_runs_after_the_schema_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _patch(monkeypatch).probe
    output = tmp_path / "d.md"

    await run_cli(CliOptions(output=output, structured_runs=4), client_factory=_factory)

    assert probe is not None
    assert [call.kwargs for call in probe.await_args_list] == [
        {"runs": 4, "constrained": True},
        {"runs": 4, "constrained": False},
    ]
    assert "### Plain-text control" in output.read_text(encoding="utf-8")


@pytest.mark.unit
async def test_a_failed_control_run_also_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, control_extra=(RunStatus.PROVIDER_ERROR,))

    assert await run_cli(CliOptions(output=tmp_path / "d.md"), client_factory=_factory) == 1


@pytest.mark.unit
@pytest.mark.parametrize("emotion", ["[]", "{}", "null", "7", "true"])
async def test_a_real_off_schema_reply_never_costs_the_report(
    emotion: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probe runs last: a bad reply must cost one status, not the measured streams."""
    _patch(monkeypatch, patch_probe=False)
    reply = '{"response": "Hola", "emotion": ' + emotion + "}"
    lines = "".join(
        json.dumps({"message": {"content": reply[i : i + 6]}}) + "\n"
        for i in range(0, len(reply), 6)
    )
    lines += json.dumps({"done": True}) + "\n"

    @contextlib.asynccontextmanager
    async def factory() -> AsyncGenerator[httpx.AsyncClient]:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, content=lines.encode())
        )
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    output = tmp_path / "d.md"

    code = await run_cli(CliOptions(output=output, structured_runs=3), client_factory=factory)

    text = output.read_text(encoding="utf-8")
    assert code == 0
    assert "off_schema" in text
    assert "## 8. Stream arrival probe" in text


@pytest.mark.unit
async def test_skipping_the_probe_runs_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch)
    probe = AsyncMock()
    monkeypatch.setattr(cli, "probe_structured_stream", probe)
    output = tmp_path / "d.md"

    code = await run_cli(CliOptions(output=output, structured_runs=0), client_factory=_factory)

    assert code == 0
    probe.assert_not_awaited()
    assert "Not run." in output.read_text(encoding="utf-8")


@pytest.mark.unit
async def test_an_unreachable_ollama_exits_two_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _patch(monkeypatch, reachable=False).run
    output = tmp_path / "d.md"

    assert await run_cli(CliOptions(output=output), client_factory=_factory) == 2
    assert not output.exists()
    run.assert_not_awaited()


@pytest.mark.unit
def test_the_golden_turns_are_shared_with_the_stream_evaluator() -> None:
    suite = load_suite(Path("tests") / "evals" / "golden_chat_faithfulness.yaml")

    turns = golden_stream_turns(suite.cases)

    assert [t.label for t in turns] == [c.id for c in suite.cases]
    assert {t.source for t in turns} == {"context"}


@pytest.mark.unit
def test_the_script_runs_when_executed_directly(tmp_path: Path) -> None:
    """``python scripts/diagnose_stream_protocol.py`` has ``scripts/`` on sys.path, not the root."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "diagnose_stream_protocol.py"
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}

    completed = subprocess.run(  # noqa: S603 — fixed interpreter and our own script
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--variants" in completed.stdout


@pytest.mark.unit
def test_justfile_exposes_diagnose_stream_and_forwards_arguments() -> None:
    justfile = Path("justfile").read_text(encoding="utf-8")

    assert "diagnose-stream *ARGS:" in justfile
    assert "python scripts/diagnose_stream_protocol.py {{ARGS}}" in justfile


def _real_units() -> list[DiagnosisUnit]:
    suite = load_suite(Path("tests") / "evals" / "golden_chat_faithfulness.yaml")
    return build_units(golden_stream_turns(suite.cases), public_turns())


@pytest.mark.unit
def test_the_real_suite_expands_to_the_units_the_plan_promises() -> None:
    units = _real_units()

    counts = Counter(unit.variant for unit in units)

    assert len(units) == 100  # 500 streams at 5 runs
    assert counts == {
        StreamVariant.FULL: 24,
        StreamVariant.FULL_REPEAT: 24,
        StreamVariant.CONTRACT_FIRST: 24,
        StreamVariant.NO_CONTEXT: 12,
        StreamVariant.QUESTION_ONLY: 2,
        StreamVariant.NO_PERSON: 1,
        StreamVariant.NO_HISTORY: 1,
        StreamVariant.PUBLIC_WITH_CONTEXT: 12,
    }


@pytest.mark.unit
async def test_the_whole_pipeline_runs_on_the_real_suite_with_a_fake_model() -> None:
    replies = itertools.cycle(["EMOTION:joy\nHola. Bien.", "sin etiqueta", "EMOTION:joy\n{x}"])

    def generate_for(_variant: StreamVariant) -> Callable[..., AsyncIterator[str]]:
        async def generate(
            _client: httpx.AsyncClient, _text: str, **_kwargs: object
        ) -> AsyncIterator[str]:
            yield next(replies)

        return generate

    units = _real_units()
    observations = await run_diagnosis(
        units, client=Mock(spec=httpx.AsyncClient), runs=2, seed=1, generate_for=generate_for
    )
    context = ReportContext(model="m", ollama_version="v", model_digest="d", runs=2, seed=1)
    report = render_diagnosis_report(observations, context, _probe_result())

    assert len(observations) == len(units) * 2
    assert sorted(o.position for o in observations) == list(range(len(units) * 2))
    for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 8."):
        assert section in report
```

- [ ] **Step 2: Run it to see it fail.**
  `uv run pytest tests/unit/test_diagnose_stream_protocol.py -q -p no:cacheprovider`.
  Expected: `ModuleNotFoundError: No module named 'scripts.diagnose_stream_protocol'`.

- [ ] **Step 3: Extract the shared helper** from `eval_chat._run_stream_mode`, so both
  stream tools measure the very same golden turns (DRY):

```diff
-async def _run_stream_mode(
-    options: CliOptions, cases: list[GoldenCase], factory: ClientFactory
-) -> int:
-    """Measure the streaming protocol on the golden context turns plus public turns."""
-    turns = [
+def golden_stream_turns(cases: Sequence[GoldenCase]) -> list[StreamTurn]:
+    """Turn golden cases into the ``context`` streaming turns both stream tools measure.
+
+    Args:
+        cases: Validated golden cases.
+
+    Returns:
+        One ``StreamTurn`` per case, carrying its memory context, history and active person.
+    """
+    return [
         StreamTurn(
             case.id,
             "context",
@@
         for case in cases
     ]
+
+
+async def _run_stream_mode(
+    options: CliOptions, cases: list[GoldenCase], factory: ClientFactory
+) -> int:
+    """Measure the streaming protocol on the golden context turns plus public turns."""
     async with factory() as client:
         result = await measure_stream_protocol(
-            [*turns, *public_turns()], client=client, runs=options.runs
+            [*golden_stream_turns(cases), *public_turns()], client=client, runs=options.runs
         )
```

- [ ] **Step 4: Add the recipe** to `justfile`, after `eval-chat`:

```diff
 eval-chat *ARGS:
     uv run --env-file .env python scripts/eval_chat.py {{ARGS}}

+# Diagnostico del respaldo del streaming (Plan 0057): variantes por factor, formas de fallo y tiempos; requiere Ollama real y el servidor detenido
+diagnose-stream *ARGS:
+    uv run --env-file .env python scripts/diagnose_stream_protocol.py {{ARGS}}
+
 # Baseline reproducible de memoria longitudinal contra Ollama real + DB temporal (Plan 0046)
```

- [ ] **Step 5: Write the command**

`scripts/diagnose_stream_protocol.py`:

```python
"""Diagnose why the streaming protocol falls back (Plan 0057): ``just diagnose-stream``.

Runs the golden and public turns under several variants against the real local Ollama,
in a seeded shuffled order, then writes a counts-only report. Pipec runs it; nothing in
the report is model text.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution (``python scripts/diagnose_stream_protocol.py``) puts ``scripts/`` on
# ``sys.path[0]``, not the repo root; see ``scripts/eval_chat.py``. Must run before any
# ``from scripts.…`` import below.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
import asyncio
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, NoReturn

import httpx
from pydantic import BaseModel, Field
from server.settings import settings

from scripts.eval_chat import (
    _GOLDEN_PATH,
    _REPORT_DIRECTORY,
    golden_stream_turns,
    load_suite,
    select_cases,
    write_report,
)
from scripts.eval_stream_diagnosis import run_diagnosis
from scripts.eval_stream_protocol import public_turns
from scripts.longitudinal_eval_metadata import sanitize_url
from scripts.stream_diagnosis_probes import fetch_ollama_facts, probe_structured_stream
from scripts.stream_diagnosis_report import ReportContext, render_diagnosis_report
from scripts.stream_diagnosis_stats import baseline_observations, summarize
from scripts.stream_diagnosis_variants import StreamVariant, build_units

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from contextlib import AbstractAsyncContextManager

    type ClientFactory = Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]]

logger = logging.getLogger(__name__)

_MIN_RUNS = 1
_MAX_RUNS = 10
_DEFAULT_SEED = 57
EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_PREFLIGHT = 2


class CliOptions(BaseModel):
    """Validated command-line options for the diagnosis."""

    runs: int = Field(default=5, ge=_MIN_RUNS, le=_MAX_RUNS)
    seed: int = _DEFAULT_SEED
    variants: list[StreamVariant] | None = None
    output: Path | None = None
    structured_runs: int = Field(default=5, ge=0, le=_MAX_RUNS)


def parse_cli_args(argv: Sequence[str] | None = None) -> CliOptions:
    """Parse and validate command-line arguments.

    Args:
        argv: Optional arguments excluding the executable name.

    Returns:
        Typed, validated CLI options.
    """
    parser = argparse.ArgumentParser(description="Diagnose the streaming protocol fallback")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=_DEFAULT_SEED)
    parser.add_argument("--variants", nargs="+", choices=[v.value for v in StreamVariant])
    parser.add_argument("--output")
    parser.add_argument("--structured-runs", type=int, default=5)
    namespace = parser.parse_args(argv)
    output = Path(namespace.output).expanduser().resolve() if namespace.output else None
    return CliOptions(
        runs=namespace.runs,
        seed=namespace.seed,
        variants=[StreamVariant(v) for v in namespace.variants] if namespace.variants else None,
        output=output,
        structured_runs=namespace.structured_runs,
    )


def _default_client_factory() -> AbstractAsyncContextManager[httpx.AsyncClient]:
    """Build the single Ollama HTTP client owned by one CLI invocation."""
    return httpx.AsyncClient(timeout=settings.ollama_timeout_s)


async def run_cli(options: CliOptions, *, client_factory: ClientFactory | None = None) -> int:
    """Run the diagnosis against the local Ollama and write its Markdown report.

    Args:
        options: Validated command-line options.
        client_factory: Optional async context-manager factory for the run-owned HTTP
            client; defaults to a real ``httpx.AsyncClient``.

    Returns:
        ``0`` on success, ``1`` if any provider call failed, ``2`` if Ollama did not
        answer (nothing is written then).
    """
    suite = load_suite(_GOLDEN_PATH)
    golden = golden_stream_turns(select_cases(suite, None))
    units = build_units(golden, public_turns(), options.variants)
    factory = client_factory or _default_client_factory
    async with factory() as client:
        facts = await fetch_ollama_facts(client)
        if not facts.reachable:
            logger.error("Ollama is not answering at %s", sanitize_url(settings.ollama_url))
            return EXIT_PREFLIGHT
        logger.info(
            "Diagnosis: %d units x %d runs = %d streams (seed %d)",
            len(units),
            options.runs,
            len(units) * options.runs,
            options.seed,
        )
        observations = await run_diagnosis(
            units, client=client, runs=options.runs, seed=options.seed
        )
        probe = control = None
        if options.structured_runs:
            probe = await probe_structured_stream(
                client, runs=options.structured_runs, constrained=True
            )
            control = await probe_structured_stream(
                client, runs=options.structured_runs, constrained=False
            )
    context = ReportContext(
        model=facts.model,
        ollama_version=facts.version,
        model_digest=facts.digest,
        runs=options.runs,
        seed=options.seed,
    )
    stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    output = options.output or _REPORT_DIRECTORY / f"{stamp}-stream-diagnosis.md"
    write_report(output, render_diagnosis_report(observations, context, probe, control))
    baseline = summarize(baseline_observations(observations))
    logger.info(
        "Diagnosis complete: baseline_fallback_rate=%s report=%s", baseline.fallback_rate, output
    )
    probe_errors = sum(result.errors for result in (probe, control) if result)
    errors = summarize(observations).errors + probe_errors
    return EXIT_PROVIDER_ERROR if errors else EXIT_OK


def main() -> NoReturn:
    """Run the command-line diagnosis and exit with its status."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    raise SystemExit(asyncio.run(run_cli(parse_cli_args())))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run everything, lint, commit.**
  `uv run pytest tests/unit/test_diagnose_stream_protocol.py tests/unit/test_eval_chat.py -q -p no:cacheprovider`
  (the existing `eval_chat` tests prove the extraction changed nothing), then
  `ruff check` and `ruff format --check` over the explicit paths of every file of
  Tasks 1 to 7, then `just gate` (rehearsed: 2038 tests). Commit —
  `feat(scripts): add just diagnose-stream`.

---

## Task 8: Run it, record it, apply the rules

**Files:** Create `docs/evals/0057-stream-protocol-diagnosis.md` and the raw reports
under `docs/evals/`; modify `docs/evals/README.md`, this plan (execution record).
No production code.

Pipec runs these on the development laptop with Ollama up and the server and robot
**stopped** (the same non-dedicated machine as Plan 0056 measured on; say so in the
record). The executor records the printed lines and the report numbers, never a reply.

- [ ] **Step 1: Smoke run (about 4 minutes).**
  `just diagnose-stream --variants full full_repeat --runs 1 --structured-runs 3 --output docs/evals/0057-stream-diagnosis-smoke.md`.
  It must exit `0` and print `Diagnosis complete`. Open the report: the variants legend and sections 1 to 8, the
  Ollama version and the model digest filled in (not `unknown`), no provider error. A `1`
  or a `2` is fixed or reported before the real run.
- [ ] **Step 2: The run (about one hour and a half).**
  `just diagnose-stream --runs 5 --output docs/evals/0057-stream-diagnosis-run1.md`.
  500 streams plus 5 schema-probe runs and 5 plain-text control runs. A provider error exits `1` after writing the
  report: record it and repeat only what failed (`--variants`). A turn with a failed run
  is excluded from every comparison, never compared on another sample.
- [ ] **Step 3: Apply R-1 to R-7** to the report and write each reading in the record
  with the measured number, the rule and the outcome. R-5 firing, or any R-3
  *exploratory signal*, is **not** a conclusion yet: run once more with another seed,
  restricted to what must be confirmed (for a signal on `no_context`:
  `just diagnose-stream --variants full full_repeat no_context --seed 58 --structured-runs 0 --output docs/evals/0057-stream-diagnosis-run2.md`)
  and record both runs. Only a signal that appears again is written as *confirmed*, and
  even then as an input to the repair plan, not as its cause. An *inconclusive* R-6 is
  recorded as no conclusion: repeat the probe (`--variants full --runs 1 --structured-runs 10`),
  and if it stays inconclusive say so. A *burst* is recorded as **unproven**, never as
  "the header holds": say which way the plain-text control read.
- [ ] **Step 4: Optional comparison.** If Pipec wants to know whether a bigger model
  behaves differently, the same command runs with `OLLAMA_MODEL=<other model>` in the
  environment (the report records the model and digest). It is a choice of Pipec's,
  not a requirement of this plan.
- [ ] **Step 5: Record.** `docs/evals/0057-stream-protocol-diagnosis.md` holds: date,
  the commit SHA, a hardware line, the Ollama version and the model digest from the
  report, one table per rule (command, counts, rule, reading), the dominant shape of
  `full` per source and its candidate (from the *Rules* table), the interventions table
  with its paired turns, denominators and per-row noise, and for each signal whether it
  was **confirmed** by another seed or stays **exploratory**; and an honest
  *Limitations* paragraph: the generator, not the full voice path; one model; a
  synthetic set; 500 streams give a wide interval; the golden turns are 12 cases
  repeated, not independent conversations; `no_person` and `no_history` rest on one
  turn each; the rules are agreed in advance, not proof. Numbers only: no reply, no
  household name.
- [ ] **Step 6: Commit** — `docs(evals): record the streaming diagnosis`.

---

## Task 9: Documentation truth

**Files:** the docs listed under *Permitted files*. No production code.

- [ ] **Step 1: Correct the 0056 record.** In
  `docs/evals/0056-voice-pipeline-measurements.md`, the *Limitations* sentence "60
  golden cases repeated five times" is wrong: it is **12 golden cases repeated five
  times (60 observations)**. Fix it, and add one dated sentence to section 1 saying
  the rates are of a synthetic evaluation of the generator, not production telemetry,
  and that the context split mixes four factors, linking the 0057 record.
- [ ] **Step 2: Roadmap.** Replace the *Streaming-protocol fallback repair* row's
  trigger text with the 0057 readings (the dominant shape, the contributing factors,
  whether a schema streams) and the repair plan's inputs. The **first task of that
  repair** is the fragmentation defect (D-5): say so. The row stays `Unplanned`; the
  next free plan number becomes 0058.
- [ ] **Step 3: 0049 O-04.** Add one sentence to the O-04 note pointing at the 0057
  record.
- [ ] **Step 4: `current-state.md`.** In the *Voice-pipeline reliability (Plan 0056)* row
  replace "so a repair plan is opened" by what is now known, state that the 29.17 %
  is a synthetic evaluation, state the confirmed fragmentation defect (production
  validates the body start once; pinned by `test_stream_fragmentation.py`), and name
  `just diagnose-stream`. Preserve the other rows.
- [ ] **Step 5: Operator manual and evals index.** Add `just diagnose-stream` to
  `docs/runbooks/operator-manual.md` (what it proves: why replies fall back, for the
  generator and this model; what it does not: the real voice path) and a row to
  `docs/evals/README.md`.
- [ ] **Step 6: Architecture diagram.** `current-state.md` changed, so (Pipec's standing
  preference) refresh the Archify diagram: update
  `docs/architecture/diagrams/current-state.json` only if a node's text changes, then
  `validate` → `deliver` to regenerate the `.html`; if no node changes, still run
  `validate` and record "diagram unchanged".
- [ ] **Step 7: Board.** `docs/plans/README.md` and `docs/plans/open/README.md` move
  0057 to closed with its result, `NOW` is empty again, next free number 0058. Move
  this file to `docs/plans/completed/` in the closure PR.
- [ ] **Step 8: Verify and commit.** Python blocks in these docs are checked by CI's
  `ruff format --check` (the local hooks skip `.md`): run
  `uv run ruff format --check .` and `uv run ruff check .`. Check every relative link
  in the touched docs with this scratch script (save it outside the repository, for
  example in your scratchpad; it is not committed):

```python
"""Check that every relative Markdown link in the given files resolves (Plan 0057, Task 9)."""

from pathlib import Path
import re
import sys

_LINK = re.compile(r"\]\(([^)\s]+)\)")
_EXTERNAL = ("http://", "https://", "mailto:", "#")


def broken_links(path: Path) -> list[str]:
    """Return the relative link targets in ``path`` that do not exist on disk."""
    missing = []
    for target in _LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(_EXTERNAL):
            continue
        if not (path.parent / target.split("#", 1)[0]).exists():
            missing.append(target)
    return missing


if __name__ == "__main__":
    failures = {name: broken_links(Path(name)) for name in sys.argv[1:]}
    for name, targets in failures.items():
        for target in targets:
            print(f"{name}: broken link {target}")  # noqa: T201
    raise SystemExit(1 if any(failures.values()) else 0)
```

  Run `uv run python <path>/check_links.py <touched .md files>` (it exits `1` and names
  a broken link), then `uv run python scripts/check_reserved_terms.py`,
  `git diff --check`, and commit —
  `docs: align roadmap and evals with plan 0057`.

---

## Non-goals

Each exclusion has an owner so that nothing is left as text only:

- **Repairing the prefix validation** (the fragmentation defect). Owner: the first task
  of the repair plan (roadmap row *Streaming-protocol fallback repair*); this plan
  pins it with `test_stream_fragmentation.py` and measures it live (R-1).
- **A tolerant tag grammar, retry once, rescuing plain text as `neutral`, removing the
  emotion from the LLM, a schema-constrained stream or another model.** Owner: the
  repair plan, chosen from the readings. Rescuing text changes rule 4 of *Protocol rules
  this plan relies on* and needs that decision stated explicitly and recorded in an ADR.
- **Moving the contract in production's prompt.** Owner: the repair plan. Here
  `contract_first` is only measured, through a script-local generator.
- **The classic parser's malformed-JSON decision** (Plan 0056 D-7). Owner: its own
  decision; R-6 may inform it.
- **The real end-to-end rate** (microphone → server → audio). Owner: PC-5 acceptance or
  a telemetry plan; this plan measures the generator.
- **Production telemetry for the fallback.** Owner: not in the current queue.
- **Any change under `server/src`.** Owner: the repair plan.

## Verification

Run before claiming done, in this order:

```powershell
uv lock --check
just lint
just typecheck
just test
just audit
just check
uv run ruff format --check .
uv build --all-packages
git diff --check
git diff --stat main -- server
```

`git diff --stat main -- server` must print nothing: D-1.

Plus `ruff check` and `ruff format --check` over the **explicit paths** of every file of
Tasks 1 to 7 (`just lint` does not look at `scripts/`; the pre-commit hook does), and
the exact deterministic CI coverage command:

```powershell
uv run pytest -m "not slow and not hardware and not eval" `
  --cov=server/src --cov=robot/src --cov-report=term --cov-fail-under=80
```

## Completion criteria

- `classify_failure_shape` returns a member of a closed enum, never any text; every
  member is exercised and `VALID` agrees with the whole-text protocol (Task 1).
- The defect that the verdict depends on the split is pinned by a test that names the
  repair plan as the one that flips it; the equivalence test against the real consumer
  still passes with the wider fragmentation family (Task 2).
- Variants omit what would send the same inputs as another, borrow a golden context in
  rotation for a public question, give every turn, public ones included, its own noise
  control, run in a seeded interleaved order, and `prompt_chars` equals what is really
  sent; the real suite expands to 100 units (Task 3 and Task 7).
- An `Observation` holds no text, counts an undue accept, keeps a provider error apart
  and measures when production would start speaking or fall back (Task 4).
- The Ollama version and model digest are read; the structured-stream probe separates
  complete, provider-error, incomplete and off-schema runs, never crashes on a reply
  whose `emotion` is not text, reads the spacing between chunks (a long first wait is not
  "withheld", a stored burst is not "incremental"), returns *inconclusive* without three
  complete runs and a majority, and has a plain-text control (Task 5).
- The report states the facts, the variants and the rules; its headline, shapes and
  concentration describe `full`; interventions are read apart with paired turns,
  denominators, the noise of their own turns and an *exploratory* reading, and a row
  without a complete control is *incomplete*; a burst is read as unproven, against the
  plain-text control; "every run" requires every expected run; percentiles are
  nearest-rank (Task 6).
- `just diagnose-stream` runs under direct execution, runs the plain-text control after
  the schema probe, exits `0`, `1` or `2` as documented (an off-schema probe run is a
  finding, not an error), still writes the report when a probe reply is off-schema and
  writes nothing when Ollama is down (Task 7).
- The measurement is recorded with R-1 to R-7 applied, every signal either confirmed
  with another seed or called exploratory, and the repair plan's inputs named; or a
  provider failure is recorded honestly (Task 8).
- The 0056 record, the roadmap, 0049 O-04, `current-state.md` and the board match the
  evidence; every gate above passes; `git diff --stat main -- server` is empty
  (Task 9).

## Real runtime acceptance

Task 8 is the acceptance: Pipec's own run of the command, recorded in the evals
record. **No live voice-turn acceptance applies:** no production code, request,
response, streaming event or audio path changes (confirm it with Pipec explicitly
rather than skipping it silently, as Plans 0040 and 0042 did).

## Rollback

Revert the squash-merged PR as one unit. No schema migration, wire change or new
dependency; `server/src` is untouched, so the product behaves exactly as before. The
recorded evidence under `docs/evals/` is history and is not rewritten.

## Execution record

Executed 2026-10-06 on `feat/0057-stream-protocol-diagnosis`, from `main` at `c062282`.

- **Promotion:** `a5091c2` (Ready/NOW, D-1 to D-7 confirmed by Pipec as written).
- **Task 0:** base `just gate` on `main`: **1858 passed** (not the 1807 the plan quotes; Plan 0051
  added 51). Symbols the plan imports exist as described. Docs inventory: 27 mentions of the
  29.17 % / 56.67 % / "golden cases repeated" / "streaming-protocol fallback" text in 11 files, for
  Task 9.
- **Tasks 1 to 7:** `754ecdb`, `e1cc96f`, `880d432`, `dba88e8`, `bdcd983`, `244d6f8`, `0bf77d5`,
  one commit each, every new test observed RED for its stated reason (a missing module, or
  `AttributeError: ... 'sentences_seen'` for the counter) before the implementation. After Task 7,
  `just gate`: **2089 passed** (1858 + 231, as rehearsed), `ruff check` and `ruff format --check`
  over every touched `scripts/` and test path, `mypy server/src robot/src` clean,
  `git diff --stat main -- server` empty.
- **Intermittent failure, recorded and not attributed:** the first gate after Task 7 reported one
  crashed xdist worker in `tests/unit/test_robot_app.py::test_thinking_success_goes_to_speaking`
  (1 failed, 2088 passed). The file passes alone (34 of 34) and the next full gate passed. It touches
  none of this plan's files. (The rehearsal saw a different intermittent, in
  `tests/slow/test_speaker_embedding_real_model.py`, which did not reappear.)
- **Task 8:** run by Pipec on his non-dedicated laptop; smoke (48 streams, 0 errors, Ollama 0.34.4,
  model digest `357c53fb659c` filled), run 1 (seed 57, 500 streams, 0 errors) and run 2 (seed 58,
  320 streams, 0 errors). Readings and statuses in
  [`docs/evals/0057-stream-protocol-diagnosis.md`](../../evals/0057-stream-protocol-diagnosis.md).
  R-5 fired in run 2 and stays unresolved; `no_context` was confirmed, `no_person` was not.
- **Task 9:** the 0056 record corrected ("12 golden cases repeated five times, 60 observations")
  and annotated; roadmap rows, the delivery map, `current-state.md` (a new row), the operator
  manual, the evals index and the 0049 O-04 note aligned with the record; the board shows the
  plan closed, `NOW` empty and 0058 as the next free number; this file moved to `completed/`.
  Architecture diagram: `archify validate` and `deliver` (showcase) pass and no node text mentions
  this subject; the delivered HTML is byte-identical to the committed one, so it is unchanged. Docs checks: relative links, `check_reserved_terms.py`,
  `ruff format --check .`, `ruff check .` and `git diff --check` clean.
- **Independent review (two read-only sonnet agents, 2026-10-06):** 0 Critical. The code review
  found one Important (a threshold met exactly, such as 42/60 against 33/60, was missed by float
  error in R-3 and R-5; none of the recorded rows sits at a limit) and minor points; all were fixed
  test-first in `b0d957b` (exact threshold comparison, a worse-than-baseline intervention labelled
  `opposite direction`, a tie between two shapes read as mixed, a failing stream close logged and
  ignored, a bad option exiting `2` with a log line, justifications for three modules over the size
  guideline). Not changed on purpose: an interrupt or an unexpected error in the middle of a run
  still loses the observations (the same as `eval-chat --mode stream`; the report is written once, at
  the end), and tests read repository files relative to the working directory like the existing
  eval tests. The evidence review confirmed every number of the record against the raw reports and
  found five Important wording problems (a factor ranking the data does not support, the missing
  counter-evidence of `public_with_context`, a loose R-7 summary, an inconsistent sign in the summary
  table, an inexact per-turn limitation) and thirteen minor ones; all were corrected in the record and
  in the documents that repeat it.
- **Final verification after the fixes:** `uv lock --check`, `just lint`, `just typecheck` (mypy and
  pyright, 0 errors), `just check`, `just audit`, `uv build --all-packages`, the exact CI coverage
  command (2079 passed in the CI selection, 91.99 % coverage) and `git diff --stat main -- server` (empty);
  `just gate`: **2096 passed** (the 2089 of Task 7 plus 7 tests for the review fixes).
- **Live acceptance (Pipec, 2026-10-07):** the plan states that no live voice-turn acceptance applies
  (no production code, request, response, streaming event or audio path changes) and asks for an
  explicit confirmation rather than a silent skip. Pipec chose to run one anyway and stated that the
  session counts as the acceptance. One streaming session with the robot and server started by
  Pipec on this branch (`ROBOT_STREAMING`, face authentication, speaker authentication and the
  owner-PIN prompt on): 5 turns, no fallback phrase. Three turns were deterministic (identity,
  own-children list, protected household data) with the actor identified from the face
  (`face_only`, owner); two were free conversation through the model, both `outcome=ok`. The speaker
  verdict was `unknown` on every identity turn because no voiceprint is enrolled (0 profiles stored,
  2 consent grants), so voice was not validated in this session and no `face_voice` fusion was
  seen; that is a state of the local data, not a finding of this plan. Outcomes only: no
  transcript, no name.

## Closure

One PR from `feat/0057-stream-protocol-diagnosis`, based on `main` after the Task 0
revalidation. On merge: move this file to `completed/`, update the board, the
roadmap row, `current-state.md` and 0049 O-04, and record the PR number and squash SHA
in a small documentation PR (as for Plans 0050, 0055 and 0056).
