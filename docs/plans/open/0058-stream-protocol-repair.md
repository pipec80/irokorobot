# 0058 — Streaming reply protocol repair

> **Status:** `Ready` — written 2026-10-07 after Plan 0057 closed and after a read-only audit
> of the streaming path (below), independently reviewed the same day (approved with fixes; every
> fix applied), and **promoted by Pipec on 2026-10-07**, who fixed decisions D-1 to D-4 in the
> planning session and confirmed D-5 to D-8 exactly as written below. It is the `NOW` item. The
> protocol it implements is [ADR 0017](../../adr/0017-streaming-reply-protocol.md), `Proposed` until
> Task 6 passes.
>
> **Queue position (Pipec, 2026-10-05):** after CM-1 (Plan 0051, closed) and the diagnosis
> (Plan 0057, closed); a hard gate of CM-2, the first slice that puts memory or history in the
> prompt. Nothing in CM-1 depends on it.

> **For agentic workers:** REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. Execute only while this is the explicitly
> authorized `NOW` item, in a new session. **Pipec's rules win over the skills:** one plain
> branch from `main` (`git checkout -b`), never a git worktree (treat any "create a worktree"
> instruction as "create the branch"), no subagents unless Pipec asks, and this plan lives under
> `docs/plans/`, not `docs/superpowers/plans/`. Implement exactly the tasks below, in order, one
> commit per task. If evidence contradicts the plan, stop and report the conflict instead of
> redesigning. Pipec runs every local process (Ollama, the measurements, the server and robot);
> you record what they print, outcomes only.

**Goal:** Make `/transcribe/stream` speak the replies the model already writes well. Today a
reply is thrown away when its `EMOTION:` tag shares a line with the text or is missing, and the
robot says its fixed "still waking up" phrase instead (43 to 52 % of turns that carry memory
context in Plan 0057's measurement). After this plan those replies are spoken, a tag is never
spoken, a forbidden start split across tokens is caught, and the measured fallback rate of the
baseline is at or below 5 %.

**Architecture:** The parser changes, the prompt and the wire do not. `streaming_protocol.py`
decides how a reply starts as soon as the text allows it (own-line tag, same-line tag with a
known emotion, or no tag, which is rescued as plain text with the emotion `neutral`), refuses a
tag that can never be valid at once, and waits on undecided prefixes. `streaming_render.py`
keeps the single judgement of the end of the stream (`classify_stream_end`) that both production
and the evaluator under `scripts/` use, and never releases a sentence that carries a tag. The
diagnosis instrument keeps naming shapes with Plan 0057's strict reading and counts the replies
production now speaks anyway as *tolerated*.

**Tech Stack:** Python 3.12, httpx, pydantic, pytest (+ xdist). No new dependency, setting or
environment variable.

**Spec:** [ADR 0017](../../adr/0017-streaming-reply-protocol.md) (the protocol, in full, with
valid and invalid examples), the roadmap row
[*Streaming-protocol fallback repair*](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio),
and the [Plan 0057 record](../../evals/0057-stream-protocol-diagnosis.md) for the measured
shapes. The rules this plan relies on are stated below from the code and its tests, which
outrank a plan under the repository's own order, and from
[`current-state.md`](../../architecture/current-state.md); no historical plan is a source of this
plan.

**Rehearsal (2026-10-07).** Every diff and file below was applied, in task order, onto a scratch
copy of `main` (`747bca6`) outside the repository, and the copy was discarded. Each task was
written test-first and its RED was observed for the stated reason before its code. With all five
code tasks applied:

- **Streaming-related tests** (the 15 files of the streaming protocol, evaluator and diagnosis, plus
  the streaming integration files): 354 passing before, 484 after. RED observed per task: 24 failing
  items, then 16, 19, 4 and 1; GREEN 374, 405, 477, 481 and 484.
- **CI selection** (`-m "not slow and not hardware and not eval"`): 2081 tests before, 2211 after
  (+130, net of the tests deleted or merged). 2210 passed; one failed only because
  `test_eval_chat_runs_under_direct_execution_like_the_justfile_recipe` spawns a subprocess that
  imports the installed `server` of the real checkout instead of the scratch copy (the same artifact
  as one `test_diagnose_stream_protocol.py` test, deselected in the copy). Both run in the real tree
  under the full `uv run pytest` of *Verification*.
- **Static checks:** `ruff check` and `ruff format --check` over the explicit paths of every touched
  file, `mypy server/src robot/src` (102 files) and `pyright` were clean.
- **Independent review** (a fresh reviewer, 2026-10-07): it applied every diff of the plan with `patch`
  onto `git archive 747bca6` (no fuzz, byte-identical to the rehearsal), reproduced the RED counts,
  killed 29 mutants of the rehearsed code and fuzzed 4000 random replies and splits against the
  wire rules. It approved with fixes; the fixes are in this plan (a tag mention hidden in markup, the
  gate stated in counts, the tag-only scope of F-8, the outcome name, the tests of the rejected
  batch) and the rehearsal above was repeated after them.

Not rehearsed: the live path against a real Ollama, Task 0, Task 6 and Task 7 (they need Pipec's
local processes). The scratch copy had no `.git` of the repository, so commit titles and the
`just gate` run are checked during execution. Treat the diffs as rehearsed code, not as a
substitute for the RED/GREEN record each task requires.

## Global Constraints

- Audio contract everywhere: WAV · 16 000 Hz · mono · int16. This plan touches no audio; nothing
  here may start touching it.
- No real household data, voice or name in any tracked file, test, prompt, doc or commit message;
  every example below is invented (`scripts/check_reserved_terms.py` guards this).
- Ollama stays the only LLM runtime; no cloud provider (ADR-0004).
- The API contract does not change: no field, event, status code or route is added or removed, the
  generated OpenAPI is byte-identical, and the robot is not touched (ADR-0012: server and robot
  change together; nothing changes on either side of the wire).
- No `print()` in `server/src` or `robot/src`; type hints on every signature; Google docstrings on
  public APIs; `ruff` clean over the **explicit paths** of every `scripts/` file touched (`just lint`
  skips `scripts/` but the pre-commit hook does not); `mypy server/src robot/src` clean.
- A log line, an exception message, an `Observation` or a report never carries any part of a model
  reply: only closed enums, counts, flags, lengths and milliseconds.
- Every new test is observed RED for the stated reason before its implementation.
- A commit title is at most 72 characters (commitizen rejects longer ones silently): check
  `git log -1` after every commit.
- `.env.example` does not change (no new variable).
- Python code blocks in Markdown are checked by CI's `ruff format --check`: run
  `uv run ruff format --check` and `uv run ruff check .` before pushing a docs change.

## Review Focus

Inputs the spec implies that are most likely to bite, each pinned by a test in its owning task:

1. A forbidden prefix split across deltas (`EMO` + `TION:`, or the first two backticks of a fence)
   must be judged as the whole text is, under every split, and never spoken (Task 1).
2. A rejected sentence must not promote the emotion: the robot needs exactly one `emotion` event
   before the first `audio`, so the fallback must still be able to send it (Task 2).
3. A tag is never spoken at any position, in a sentence or in the unfinished tail; what was already
   spoken stays and the fallback follows (Tasks 2 and 3).
4. A known emotion on the same line as the text is spoken; an unknown word there (`EMOTION: Hola,
   ¿cómo estás?`) must fall back, never speak the mutilated sentence (Task 3).
5. JSON or a code fence with no tag is not rescued, and an undecided prefix at the end of the stream
   (`EMOTION:joy` with nothing after it) is still a fallback (Task 3).
6. A rescued reply is recorded as a normal turn and logged as `rescued_no_tag`; a fallback is never
   recorded (Task 3).
7. The diagnosis shapes must not move when the protocol learns to tolerate one, or the before/after
   comparison would compare different things (Tasks 3 and 4).

## Why this plan exists

[Plan 0057](../completed/0057-stream-protocol-diagnosis.md) measured on `qwen2.5:3b` (820 streams
over two seeds, the generator only; [record](../../evals/0057-stream-protocol-diagnosis.md)) that
the baseline falls back in 43 to 52 % of context turns and 1.7 to 3.3 % of public turns, and that
the dominant shape is a tag that shares its line with the text (`tag_same_line`, 85 to 97 % of the
context fallbacks). It chose no repair (its D-6 left every option open) and left the defect of a
forbidden prefix split across tokens as this plan's first task. The queue makes the repair a hard
gate of CM-2.

### Audit of the streaming path (2026-10-07, read-only)

The code and tests of the path were read again against `main` (`747bca6`) before writing this plan
(queue rule 4: re-audit only this plan's assumptions). Findings, and where this plan closes each
(the standing policy is to fix every finding):

| # | Severity | Where | Finding | Closed in |
|---|---|---|---|---|
| F-1 | High | `streaming_protocol.py` regex `^EMOTION:\s*(\w+)\s*\n` | The tag must end its line. `EMOTION:joy ¡Hola!...` never matches, so the whole reply is buffered until the model stops, then thrown away. Explains `tag_same_line` and the long fallback p95. | Task 3 |
| F-2 | High | `streaming_render._consume_body` | The body start is validated once with the first non-blank fragment. A split `EMOTION:` or fence is spoken and never looked at again. Pinned by `test_stream_fragmentation.py`. | Task 1 |
| F-3 | Medium | `parse_streaming_emotion` | With no match and `final=False` it waits forever, even when the text can no longer be a tag (`no_tag`). Every invalid reply costs the whole generation. | Task 3 |
| F-4 | Medium | `llm_streaming.py` header | Claims Ollama withholds structured output until the end. Plan 0057 measured the opposite (5 of 5 incremental). Its D-1 forbade editing it there. | Task 5 |
| F-5 | Low | `llm_streaming.py` | A "temporary" re-export with a `noqa: F401` citing a task long closed; only two test files still read it. | Task 3 |
| F-6 | Low | `_finalize_model_output` | Calls `parse_streaming_emotion(buffer, final=True)` and drops the result; the call can only raise, so the logic reads as if it could match. | Task 2 |
| F-7 | Low | `streaming.py` and `streaming_render._done_event` | `llm_ms` computed in two places. | Task 5 |
| F-8 | Medium | `_consume_body` | Only the start of the body is validated: a second tag in the middle of the reply is spoken. (JSON or a code fence in the middle is not guarded either: it stays a known limit, see *Non-goals*.) | Task 2 (tags only) |

Not changed, on purpose: `llm_streaming._build_messages` duplicates a four-line helper of `llm.py`
(its own comment says why, and widening `llm.py`'s public API for one call site is worse).

## Task overview

| Task | What | Closes |
|---:|---|---|
| 0 | Baseline run of Plan 0057's third seed on the unchanged code (Pipec); reads R-5. | R-5 of Plan 0057 |
| 1 | A body start that is still a prefix of `EMOTION:` or of a code fence waits (production and the evaluator). | F-2 |
| 2 | A tag is never spoken; one shared judgement of the end of the stream; the streaming loop catches the protocol error only. | F-6, F-8 |
| 3 | The start grammar of ADR 0017: same-line tag, leading whitespace, rescue, early refusal; rescued turns are recorded and logged; the diagnosis shapes keep the strict reading; the temporary re-export goes. | F-1, F-3, F-5 |
| 4 | The diagnosis instrument counts and reports *tolerated* replies. | Instrument |
| 5 | The stale header, one `llm_ms` helper. | F-4, F-7 |
| 6 | Measurement of the repair against the gate (Pipec). | Gate |
| 7 | Documentation truth: ADR accepted, state, roadmap, queue, diagram, plan closed. | Docs |

## Protocol rules this plan relies on

[ADR 0017](../../adr/0017-streaming-reply-protocol.md) is the source; the rules are restated here
so the plan can be read alone. Decision numbers refer to the ADR.

1. A reply starts with `EMOTION:<emotion>` on its own line, with the same tag followed by the text
   on the same line (the word must be a known emotion), or with no tag (rescued, emotion
   `neutral`). Leading whitespace and the letter case of `EMOTION:` are ignored (decision 1).
2. A tag that can never become valid is refused at once: an unknown word on the same line, a word
   glued to punctuation, a wrapped word, no word at all (decision 2).
3. A buffer that is still a proper prefix of `EMOTION:` (`E`, `EMO`), or a body that is still a
   proper prefix of `EMOTION:` or of a code fence, waits and speaks nothing. At the end of the
   stream an undecided start is a violation; an undecided body prefix is ordinary text (decision 3).
4. A body that starts with `{`, `[`, a code fence or `EMOTION:` is refused (decision 4).
5. No sentence and no unfinished tail that mentions `EMOTION` followed by a colon is spoken, in any
   letter case, with up to three symbols between them (`**EMOTION**:`) and either colon width;
   `demotion:` does not count
   (decision 5).
6. The fallback is one fixed phrase, with no retry. Exactly one `emotion` event precedes the first
   `audio`; `done` only follows audio (decision 6, ADR 0012).
7. A rescued reply is a normal turn: spoken, recorded with emotion `neutral`, logged as
   `rescued_no_tag` (decision 7).

## Decisions

| ID | Decision | Source |
|---|---|---|
| D-1 | The repair is the tolerant grammar **plus** the rescue of a reply with no tag as plain text (neutral). It changes the old rule "plain text without the tag is a fallback", so it is recorded in ADR 0017. | Pipec, 2026-10-07 |
| D-2 | Gate: the fallback rate of `full` is at or below **5 %** in context turns and in public turns, in seeds 57 and 59, with 0 undue accepts and 0 split-dependent replies (rules fixed below). | Pipec, 2026-10-07 |
| D-3 | R-5 (execution-order effect) is closed here: Task 0 runs seed 59 on the unchanged code and reads it with Plan 0057's 15-point rule. | Pipec, 2026-10-07 |
| D-4 | The contract text in the prompt is not touched, so the measured change is attributed to the parser. | Pipec, 2026-10-07 |
| D-5 | A rescued turn is recorded as a normal turn (emotion `neutral`) and logged as `rescued_no_tag`; a fallback is never recorded. | Pipec, 2026-10-07 (proposed in the draft, confirmed as written) |
| D-6 | A tag is never spoken, at any position, in any mode; what was spoken stays and the fallback follows (logged as `protocol_fallback`). | Pipec, 2026-10-07 (proposed in the draft, confirmed as written) |
| D-7 | The wire, the robot, the schemas, the settings and the dependencies do not change. | Pipec, 2026-10-07 (proposed in the draft, confirmed as written) |
| D-8 | The diagnosis keeps naming shapes with Plan 0057's strict grammar (frozen in `stream_failure_shapes.py`) and reports the replies production now speaks anyway as *tolerated*. | Pipec, 2026-10-07 (proposed in the draft, confirmed as written) |

## Rules fixed before the run

These are constants of the reading, fixed **before** Task 6 and not changed after it.

- **Gate (D-2).** For each of seeds 57 and 59 (`--runs 5`, `--variants full full_repeat`, generator
  only): the fallback rate of `full` is at or below **5.00 %** in context turns **and** in public
  turns; the report shows 0 undue accepts and 0 split-dependent replies; no provider error is read
  as a pass (the instrument already keeps them out of the rate).
- **In counts.** Each cell is 12 turns × 5 runs = 60 streams, so the gate means **at most 3
  fallbacks of 60**. One golden turn that falls back in all 5 runs is 5 of 60 (8.33 %) and fails the
  gate by itself: the gate really says that no golden turn may fail persistently (Plan 0057 saw two
  such turns in each seed). The report's section 4 prints the number of turns with at least one
  fallback and of turns that fell back in every run; both are recorded.
- **Noise band.** Exactly 4 fallbacks of 60 (6.67 %) in a seed may be repeated once with `--runs 10`
  (120 streams, at most 6 fallbacks to pass) and the repeat decides that seed; 5 or more of 60 fails
  the gate outright, and a pass is final. The public half is not discriminating (the baseline is
  already 1.7 to 3.3 %): it only guards against a regression.
- **Controls and a read, not gates.** `full_repeat` is the noise control and is reported. The
  counts of *tolerated* replies by strict-0057 shape are reported too, and **Pipec reads them before
  Task 7**: the gate counts only fallbacks, so a repair that speaks junk would never fail it.
  Tolerated `other_label` replies (a label such as `Emoción: joy` read aloud) are the ones to look
  at; a share that Pipec finds too high stops the plan the same way a failed gate does.
- **R-5 (Task 0).** The fallback rate by quarter of the shuffled order, all variants together. A
  spread of **15 points or more** means the order effect is real and Plan 0057's R-3 confirmations
  need re-reading; a smaller spread means run 2 most likely mixed variants unevenly per quarter. It
  informs the record; it gates nothing.
- **If the gate fails:** stop and report the numbers. Do not redesign, do not merge, leave ADR 0017
  `Proposed`. A new plan decides what comes next.

## Required reading

Read these, and nothing from `project-history/`:

- `AGENTS.md`, `CLAUDE.md` and `.claude/rules/` (`python-style.md`, `tests.md`,
  `scripts-powershell.md`, `software-principles.md`).
- [ADR 0017](../../adr/0017-streaming-reply-protocol.md) and
  [ADR 0012](../../adr/0012-line-delimited-stream-terminal-events.md).
- `server/src/server/streaming_protocol.py`, `streaming_render.py`, `streaming.py`,
  `llm_streaming.py`, `sentences.py`.
- `robot/src/robot/stream_validation.py` (read-only: the one-emotion-before-audio rule).
- `scripts/eval_stream_protocol.py`, `stream_failure_shapes.py`, `stream_fragmentation.py`,
  `eval_stream_diagnosis.py`, `stream_diagnosis_stats.py`, `stream_diagnosis_report.py`.
- The [Plan 0057 record](../../evals/0057-stream-protocol-diagnosis.md).

## Permitted files

- `server/src/server/streaming_protocol.py`, `streaming_render.py`, `streaming.py`,
  `llm_streaming.py`.
- `scripts/eval_stream_protocol.py`, `stream_failure_shapes.py`, `eval_stream_diagnosis.py`,
  `stream_diagnosis_stats.py`, `stream_diagnosis_report.py`.
- Tests: `tests/unit/test_streaming_protocol.py`, `test_streaming_render_decisions.py` (new),
  `test_llm_streaming.py`, `test_eval_stream_protocol.py`, `test_stream_fragmentation.py`,
  `test_stream_failure_shapes.py`, `test_eval_stream_diagnosis.py`,
  `test_stream_diagnosis_report.py`, and `tests/integration/test_transcribe_stream.py`,
  `test_transcribe_stream_resilience.py`.
- Docs: this plan, [ADR 0017](../../adr/0017-streaming-reply-protocol.md), `docs/adr/README.md`,
  `docs/evals/0058-stream-protocol-repair.md` (new), `docs/evals/0057-stream-diagnosis-run3.md`
  (new, written by the command of Task 0), `docs/evals/0058-stream-repair-seed57.md` and
  `docs/evals/0058-stream-repair-seed59.md` (new, written by the commands of Task 6),
  `docs/architecture/current-state.md` and its diagram
  under `docs/architecture/diagrams/`, `docs/roadmap/cognitive-roadmap.md`,
  `docs/plans/README.md`, `docs/plans/open/README.md`, `docs/plans/completed/README.md`.

Anything else is a conflict to report.

## Task 0: Baseline run on the unchanged code (Pipec)

**Files:** `docs/evals/0057-stream-diagnosis-run3.md` (written by the command),
`docs/evals/0058-stream-protocol-repair.md` (new, written by you).

Pipec runs it, locally, with Ollama running and the server and robot **stopped** (about 30 minutes
on the development laptop; the branch holds documents only, so this is the code of `main`):

```powershell
just diagnose-stream --variants full full_repeat no_context no_person no_history question_only --seed 59 --structured-runs 0 --output docs/evals/0057-stream-diagnosis-run3.md
```

- [ ] **Step 1:** Pipec runs the command and hands over the report path.
- [ ] **Step 2:** Create `docs/evals/0058-stream-protocol-repair.md` with the same *Conditions* table
  as the [Plan 0057 record](../../evals/0057-stream-protocol-diagnosis.md#conditions) (date, commit,
  machine, model digest, Ollama version, who ran it, seed 59, instrument) and a section
  **Baseline, seed 59** holding: the fallback rate of `full` per source, the dominant shape, and the
  R-5 reading by the rule above (quarter rates and spread in points). Numbers only: no reply, no
  transcript, no name.
- [ ] **Step 3:** If the baseline of `full` in context turns is already at or below 5 %, stop and
  report: the premise of the plan (a context fallback near 43 to 52 %) did not reproduce and there is
  nothing left to repair.
- [ ] **Step 4:** Commit.

```powershell
git add docs/evals/0057-stream-diagnosis-run3.md docs/evals/0058-stream-protocol-repair.md
git commit -m "docs: baseline of the streaming fallback, seed 59 (plan 0058)"
```

## Task 1: A body start that is still a prefix of a forbidden start waits

Closes F-2. A body that begins `E`, `EM`, ... `EMOTION` or one or two backticks may still become a
second tag or a code fence, so it must neither be spoken nor judged yet.

**Files:**
- Modify: `server/src/server/streaming_protocol.py`, `server/src/server/streaming_render.py`
- Test: `tests/unit/test_streaming_protocol.py`, `tests/unit/test_stream_fragmentation.py`,
  `tests/unit/test_eval_stream_protocol.py`, `tests/unit/test_eval_stream_diagnosis.py`

**Interfaces:**
- Produces: `streaming_protocol.is_body_start_undecided(body: str) -> bool`.
- `streaming_render._consume_body` keeps its signature `(buffer, state) -> (buffer, sentences)`.

- [ ] **Step 1: Write the failing tests.** The fragmentation test stops pinning the defect and pins
  its repair; two other tests that pinned the defect now pin the repair.

`tests/unit/test_stream_fragmentation.py`:

```diff
@@ -13,6 +13,8 @@ _FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown c

 # Replies production judges the same way however the tokens split.
 _CONSISTENT = [
+    "EMOTION:joy\nEMOTION:anger\nhola",
+    f"EMOTION:joy\n{_FENCE}json\n{{}}\n{_FENCE}",
     "EMOTION:joy\nHola, ¿cómo estás?",
     "EMOTION:joy\n",
     "EMOTION:joy",
@@ -22,11 +24,9 @@ _CONSISTENT = [
     "",
 ]

-# Replies whose verdict depends on the split TODAY: production validates the start of the
-# body once, with the first fragment, so a prefix that is still undecidable ("E", "`")
-# is accepted and the rest is never checked. Plan 0057 pins this defect; the repair plan
-# flips these into ``_CONSISTENT``.
-_INCONSISTENT_TODAY = [
+# Replies whose body starts with a prefix that is still undecidable ("E", "`"): production
+# waits for the rest instead of speaking it (Plan 0058, ADR 0017 decision 3).
+_SPLIT_PREFIX_REPLIES = [
     "EMOTION:joy\nEMOTION:anger\nhola",
     f"EMOTION:joy\n{_FENCE}json\n{{}}\n{_FENCE}",
 ]
@@ -54,9 +54,9 @@ def test_a_reply_judged_the_same_under_every_split_is_consistent(reply: str) ->


 @pytest.mark.unit
-@pytest.mark.parametrize("reply", _INCONSISTENT_TODAY)
-def test_the_known_fragmentation_defect_is_pinned_until_the_repair_plan(reply: str) -> None:
-    """Whole, the reply is rejected; split inside its first body token, it is spoken."""
+@pytest.mark.parametrize("reply", _SPLIT_PREFIX_REPLIES)
+def test_a_split_forbidden_prefix_is_rejected_under_every_split(reply: str) -> None:
+    """The 0057 defect: split inside its first body token, the reply used to be spoken."""
     assert classify_deltas([reply]) is StreamOutcome.INVALID_PROTOCOL
-    assert fragmentation_outcomes(reply) == {StreamOutcome.VALID, StreamOutcome.INVALID_PROTOCOL}
-    assert not is_fragmentation_consistent(reply)
+    assert fragmentation_outcomes(reply) == {StreamOutcome.INVALID_PROTOCOL}
+    assert is_fragmentation_consistent(reply)
```


`tests/unit/test_eval_stream_protocol.py`:

```diff
@@ -68,12 +68,14 @@ def test_classify_deltas_reports_the_production_outcome(


 @pytest.mark.unit
-def test_the_outcome_depends_on_how_the_reply_is_fragmented_exactly_as_in_production() -> None:
-    """Production stops validating once the body start is accepted ("EMO" is not a tag)."""
+def test_a_forbidden_prefix_split_across_deltas_is_judged_like_the_whole_text() -> None:
+    """The prefix EMO may still become a second tag, so the evaluator waits for the rest."""
     reply = "EMOTION:joy\nEMOTION:anger\nhola"

     assert classify_deltas([reply]) is StreamOutcome.INVALID_PROTOCOL
-    assert classify_deltas(["EMOTION:joy\nEMO", "TION:anger\nhola"]) is StreamOutcome.VALID
+    assert (
+        classify_deltas(["EMOTION:joy\nEMO", "TION:anger\nhola"]) is StreamOutcome.INVALID_PROTOCOL
+    )


 async def _production_result(
@@ -98,6 +100,18 @@ async def _production_result(
     return state.recordable is False, match.group(1) if match else None


+@pytest.mark.unit
+async def test_production_never_speaks_a_forbidden_prefix_split_across_deltas(
+    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
+) -> None:
+    fell_back, reason = await _production_result(
+        ["EMOTION:joy\nEMO", "TION:anger\nhola"], monkeypatch, caplog
+    )
+
+    assert fell_back
+    assert reason == "invalid_protocol"
+
+
 @pytest.mark.unit
 @pytest.mark.parametrize("reply", _REPLIES)
 async def test_the_evaluator_agrees_with_production_for_every_fragmentation(
```


`tests/unit/test_eval_stream_diagnosis.py`:

```diff
@@ -98,14 +98,14 @@ async def test_a_valid_reply_starts_speaking_at_its_first_closed_sentence() -> N


 @pytest.mark.unit
-async def test_a_prefix_split_across_deltas_is_an_undue_accept() -> None:
-    """Production speaks what the whole text would reject: the 0057 fragmentation defect."""
+async def test_a_prefix_split_across_deltas_is_no_longer_an_undue_accept() -> None:
+    """The 0057 fragmentation defect, repaired: production waits for the rest of "EMO"."""
     obs = await _observe(_FakeStream("EMOTION:joy\nEMO", "TION:anger\nhola"))

-    assert obs.outcome is StreamOutcome.VALID
+    assert obs.outcome is StreamOutcome.INVALID_PROTOCOL
     assert obs.whole_text_outcome is StreamOutcome.INVALID_PROTOCOL
-    assert obs.fragmentation_consistent is False
-    assert obs.undue_accept
+    assert obs.fragmentation_consistent is True
+    assert not obs.undue_accept


 @pytest.mark.unit
```


`tests/unit/test_streaming_protocol.py`:

```diff
@@ -17,7 +17,7 @@ from __future__ import annotations
 import pytest
 from server.exceptions import LLMError

-from server import llm_streaming
+from server import llm_streaming, streaming_protocol


 @pytest.mark.unit
@@ -106,10 +106,24 @@ def test_full_hybrid_example_rejected_before_speech() -> None:
 @pytest.mark.unit
 def test_llm_streaming_reexports_protocol_functions() -> None:
     """llm_streaming.py must still resolve both names for existing call sites."""
-    from server import streaming_protocol  # noqa: PLC0415 — keeps collection RED-safe
-
     assert llm_streaming.parse_streaming_emotion is streaming_protocol.parse_streaming_emotion
     assert (
         llm_streaming.validate_streaming_body_start
         is streaming_protocol.validate_streaming_body_start
     )
+
+
+@pytest.mark.unit
+@pytest.mark.parametrize("body", ["E", "EM", "emotion", "  EMOTION", "`", "``"])
+def test_a_body_that_could_still_become_a_forbidden_start_is_undecided(body: str) -> None:
+    """A prefix of ``EMOTION:`` or of a code fence cannot be judged yet: wait for more."""
+    assert streaming_protocol.is_body_start_undecided(body)
+
+
+@pytest.mark.unit
+@pytest.mark.parametrize(
+    "body", ["", "   ", "Hola", "Es", "{", "[", "EMOTION:", "emotion:joy", "`x", "`" * 3, "Eso."]
+)
+def test_a_body_that_is_decided_is_not_undecided(body: str) -> None:
+    """Decided means allowed (plain text) or already forbidden (``validate`` rejects it)."""
+    assert not streaming_protocol.is_body_start_undecided(body)
```


- [ ] **Step 2: Run them and see them fail for the stated reason.**

```powershell
uv run pytest tests/unit/test_streaming_protocol.py tests/unit/test_stream_fragmentation.py tests/unit/test_eval_stream_protocol.py tests/unit/test_eval_stream_diagnosis.py -q
```

Expected: FAILED. The new `is_body_start_undecided` tests fail with `AttributeError: module
'server.streaming_protocol' has no attribute 'is_body_start_undecided'`; the fragmentation,
evaluator and diagnosis tests fail because the outcome is `VALID` where `INVALID_PROTOCOL` is
expected (the defect).

- [ ] **Step 3: Implement.**

`server/src/server/streaming_protocol.py`:

```diff
@@ -20,7 +20,10 @@ _EMOTION_TAG_RE = re.compile(r"^EMOTION:\s*(\w+)\s*\n", re.IGNORECASE)
 # output here (it may contain arbitrary, unbounded model text).
 _INVALID_PROTOCOL_MESSAGE = "Invalid streaming response protocol"

-_INVALID_BODY_PREFIXES = ("{", "[", "```")
+_FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
+_TAG = "EMOTION:"
+_INVALID_BODY_PREFIXES = ("{", "[", _FENCE)
+_UNDECIDED_BODY_PREFIXES = (_TAG, _FENCE)


 def parse_streaming_emotion(
@@ -59,6 +62,25 @@ def parse_streaming_emotion(
     return emotion, buffer[match.end() :]


+def is_body_start_undecided(body: str) -> bool:
+    """Whether the body so far is a proper prefix of a forbidden start (tag or fence).
+
+    A body that begins ``E`` or a single backtick may still become ``EMOTION:`` or a
+    code fence once the next token arrives, so it can be neither spoken nor judged yet.
+
+    Args:
+        body: The text after the preamble, as received so far.
+
+    Returns:
+        True while more text is needed to know whether the body start is allowed.
+    """
+    stripped = body.lstrip()
+    return bool(stripped) and any(
+        len(stripped) < len(prefix) and prefix.startswith(stripped.upper())
+        for prefix in _UNDECIDED_BODY_PREFIXES
+    )
+
+
 def validate_streaming_body_start(body: str) -> None:
     """Reject structured metadata or a repeated protocol tag before speech.

@@ -75,5 +97,5 @@ def validate_streaming_body_start(body: str) -> None:
             ``{``, ``[``, a code fence, or another ``EMOTION:`` tag.
     """
     stripped = body.lstrip()
-    if stripped.startswith(_INVALID_BODY_PREFIXES) or stripped.upper().startswith("EMOTION:"):
+    if stripped.startswith(_INVALID_BODY_PREFIXES) or stripped.upper().startswith(_TAG):
         raise LLMError(_INVALID_PROTOCOL_MESSAGE)
```


`server/src/server/streaming_render.py`:

```diff
@@ -24,7 +24,11 @@ from server.schemas_streaming import (
 )
 from server.sentences import split_first_sentence
 from server.settings import settings
-from server.streaming_protocol import parse_streaming_emotion, validate_streaming_body_start
+from server.streaming_protocol import (
+    is_body_start_undecided,
+    parse_streaming_emotion,
+    validate_streaming_body_start,
+)

 logger = logging.getLogger(__name__)

@@ -155,16 +159,19 @@ def _consume_body(buffer: str, state: StreamState) -> tuple[str, list[str]]:
     """Split complete sentences off the body, promoting emotion once valid.

     Promotes ``pending_emotion`` to emitted ``emotion`` the first time
-    non-whitespace content passes ``validate_streaming_body_start``.
+    non-whitespace content passes ``validate_streaming_body_start``. While the
+    body is still a prefix of a forbidden start (``E``, a lone backtick) nothing is
+    promoted or spoken: the next delta decides it.

     Raises:
         LLMError: If the body content is structurally invalid.
     """
-    if state.emotion is None:
-        stripped = buffer.lstrip()
-        if stripped:
-            validate_streaming_body_start(stripped)
-            state.emotion = state.pending_emotion
+    has_content = bool(buffer.strip())
+    if state.emotion is None and has_content:
+        if is_body_start_undecided(buffer):
+            return buffer, []
+        validate_streaming_body_start(buffer)
+        state.emotion = state.pending_emotion
     sentences: list[str] = []
     while (split := split_first_sentence(buffer)) is not None:
         sentence, buffer = split
```


- [ ] **Step 4: Run the tests again and the wider streaming set.**

```powershell
uv run pytest tests/unit tests/integration -q -k "stream"
uv run ruff check server/src/server/streaming_protocol.py server/src/server/streaming_render.py tests/unit/test_streaming_protocol.py tests/unit/test_stream_fragmentation.py tests/unit/test_eval_stream_protocol.py tests/unit/test_eval_stream_diagnosis.py
uv run ruff format --check server/src/server/streaming_protocol.py server/src/server/streaming_render.py tests/unit/test_streaming_protocol.py tests/unit/test_stream_fragmentation.py tests/unit/test_eval_stream_protocol.py tests/unit/test_eval_stream_diagnosis.py
```

Expected: all pass, ruff clean.

- [ ] **Step 5: Commit.**

```powershell
git add server/src/server/streaming_protocol.py server/src/server/streaming_render.py tests/unit/test_streaming_protocol.py tests/unit/test_stream_fragmentation.py tests/unit/test_eval_stream_protocol.py tests/unit/test_eval_stream_diagnosis.py
git commit -m "fix(server): wait on an undecided stream body start (plan 0058)"
```

## Task 2: A tag is never spoken; one judgement of the end of the stream

Closes F-6 and F-8. Introduces `StreamProtocolError` (a subclass of `LLMError`, so every caller that
catches `LLMError` keeps working) and the single end-of-stream judgement that production and the
evaluator share, so they cannot drift apart.

**Files:**
- Modify: `server/src/server/streaming_protocol.py`, `streaming_render.py`, `streaming.py`,
  `scripts/eval_stream_protocol.py`
- Create: `tests/unit/test_streaming_render_decisions.py`
- Test: `tests/unit/test_streaming_protocol.py`, `tests/unit/test_eval_stream_protocol.py`,
  `tests/integration/test_transcribe_stream.py`

**Interfaces:**
- Consumes: `is_body_start_undecided` (Task 1).
- Produces: `streaming_protocol.StreamProtocolError(LLMError)`,
  `streaming_protocol.reject_embedded_tag(text: str) -> None`,
  `streaming_render.classify_stream_end(buffer: str, state: StreamState) -> StreamFallbackReason | None`.
  `validate_streaming_body_start` and `parse_streaming_emotion(final=True)` now raise
  `StreamProtocolError`.

- [ ] **Step 1: Write the failing tests.** One new test file for the decisions that need no TTS,
  protocol tests, two integration cases (a tag after the first sentence, in a late sentence and in
  the unfinished tail), and two more replies in the evaluator's equivalence table.

`tests/unit/test_streaming_render_decisions.py` (whole file):

```python
"""Decisions of ``streaming_render`` that need no TTS (Plan 0058)."""

import pytest
from server.streaming_protocol import StreamProtocolError
from server.streaming_render import (
    StreamFallbackReason,
    StreamState,
    _consume_body,
    classify_stream_end,
)


def _state(*, pending: str | None = "joy", emotion: str | None = None) -> StreamState:
    state = StreamState(request_start=0.0)
    state.pending_emotion = pending
    state.emotion = emotion
    return state


@pytest.mark.unit
def test_a_sentence_that_carries_a_tag_is_never_released() -> None:
    state = _state()

    with pytest.raises(StreamProtocolError):
        _consume_body("Hola. Luego EMOTION:anger. Adiós.", state)

    assert state.emotion is None  # a rejected batch must not promote the emotion event


@pytest.mark.unit
def test_plain_sentences_are_released_and_promote_the_emotion() -> None:
    state = _state()

    buffer, sentences = _consume_body("Hola. ¿Qué tal? Y", state)

    assert sentences == ["Hola.", "¿Qué tal?"]
    assert buffer == "Y"
    assert state.emotion == "joy"


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer, pending, emotion, expected",
    [
        ("", None, None, StreamFallbackReason.EMPTY_STREAM),
        ("  \n", None, None, StreamFallbackReason.EMPTY_STREAM),
        ("EMOTION:joy", None, None, StreamFallbackReason.INVALID_PROTOCOL),
        ("", "joy", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("   ", "joy", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("{", "joy", None, StreamFallbackReason.INVALID_PROTOCOL),
        ("Adiós EMOTION:joy", "joy", "joy", StreamFallbackReason.INVALID_PROTOCOL),
        ("Hola", "joy", None, None),
        ("E", "joy", None, None),
        ("Adiós", "joy", "joy", None),
        ("", "joy", "joy", None),
    ],
)
def test_the_end_of_the_stream_is_judged_in_one_place(
    buffer: str, pending: str | None, emotion: str | None, expected: StreamFallbackReason | None
) -> None:
    assert classify_stream_end(buffer, _state(pending=pending, emotion=emotion)) is expected
```


`tests/unit/test_streaming_protocol.py`:

```diff
@@ -127,3 +127,46 @@ def test_a_body_that_could_still_become_a_forbidden_start_is_undecided(body: str
 def test_a_body_that_is_decided_is_not_undecided(body: str) -> None:
     """Decided means allowed (plain text) or already forbidden (``validate`` rejects it)."""
     assert not streaming_protocol.is_body_start_undecided(body)
+
+
+@pytest.mark.unit
+def test_a_protocol_error_is_an_llm_error_and_the_body_validator_raises_it() -> None:
+    """Callers that catch ``LLMError`` keep working; the streaming loop catches the subclass."""
+    assert issubclass(streaming_protocol.StreamProtocolError, LLMError)
+    with pytest.raises(streaming_protocol.StreamProtocolError):
+        streaming_protocol.validate_streaming_body_start('{"response": "hola"}')
+
+
+@pytest.mark.unit
+@pytest.mark.parametrize(
+    "text",
+    [
+        "Hola. EMOTION:joy",
+        "**EMOTION:** joy",
+        "**EMOTION**: joy",
+        "EMOTION\uff1a joy",
+        "EMOTION : joy",
+        "emotion: joy",
+        "Claro, emotion:joy otra vez.",
+    ],
+)
+def test_reject_embedded_tag_refuses_a_tag_anywhere(text: str) -> None:
+    with pytest.raises(streaming_protocol.StreamProtocolError) as exc_info:
+        streaming_protocol.reject_embedded_tag(text)
+
+    assert text not in str(exc_info.value)
+
+
+@pytest.mark.unit
+@pytest.mark.parametrize(
+    "text",
+    [
+        "La emoción es alegría.",
+        "Emotion es una palabra.",
+        "Una demotion: palabra rara.",
+        "¿Qué emoción sientes?",
+        "",
+    ],
+)
+def test_reject_embedded_tag_allows_plain_speech(text: str) -> None:
+    streaming_protocol.reject_embedded_tag(text)
```


`tests/unit/test_eval_stream_protocol.py`:

```diff
@@ -43,6 +43,8 @@ _REPLIES = [
     "EMOTION:joy\nEMOTION:anger\nhola",
     "EMOTION:unknownemotion\nHola",
     "emotion: joy\nHola",
+    "EMOTION:joy\nHola. EMOTION:anger\nAdiós.",
+    "EMOTION:joy\nHola. **EMOTION:** joy",
 ]


```


`tests/integration/test_transcribe_stream.py`:

```diff
@@ -586,6 +586,55 @@ def test_stream_structured_body_uses_audible_protocol_fallback(
     record.assert_not_called()


+@pytest.mark.integration
+@pytest.mark.parametrize(
+    "deltas",
+    [
+        ["EMOTION:joy\nHola. ", "EMOTION:anger\nAdiós."],
+        ["EMOTION:joy\nHola. Adiós EMOTION:anger"],
+    ],
+)
+def test_stream_a_tag_after_the_first_sentence_keeps_the_audio_and_adds_the_fallback(
+    client: TestClient,
+    silence_wav_bytes: bytes,
+    monkeypatch: pytest.MonkeyPatch,
+    deltas: list[str],
+) -> None:
+    """A tag is never spoken; what already played stays and the fallback follows (ADR 0017)."""
+    record = Mock()
+    synthesize = AsyncMock(return_value=("QQ==", 10))
+    monkeypatch.setattr(streaming, "record_text_turn", record)
+    monkeypatch.setattr(tts, "synthesize", synthesize)
+    events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, deltas)
+    assert [event["type"] for event in events] == [
+        "text_heard",
+        "emotion",
+        "audio",
+        "audio",
+        "done",
+    ]
+    assert events[1]["value"] == "joy"
+    spoken = [call.args[0] for call in synthesize.await_args_list]
+    assert spoken == ["Hola.", settings.llm_fallback_phrase]
+    record.assert_not_called()
+
+
+@pytest.mark.integration
+def test_stream_a_rejected_batch_still_sends_exactly_one_emotion_before_the_audio(
+    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """The robot raises on audio before emotion: a rejected batch must not swallow the event."""
+    monkeypatch.setattr(streaming, "record_text_turn", Mock())
+    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 10)))
+    events = _post_stream_with_deltas(
+        client, monkeypatch, silence_wav_bytes, ["EMOTION:joy\nHola. EMOTION:anger\nAdiós."]
+    )
+    kinds = [event["type"] for event in events]
+    assert kinds.count("emotion") == 1
+    assert kinds.index("emotion") < kinds.index("audio")
+    assert kinds[-1] == "done"
+
+
 @pytest.mark.integration
 def test_stream_truncated_emotion_uses_audible_protocol_fallback(
     client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
```


- [ ] **Step 2: Run them and see them fail for the stated reason.**

```powershell
uv run pytest tests/unit/test_streaming_protocol.py tests/unit/test_streaming_render_decisions.py tests/integration/test_transcribe_stream.py -q
```

Expected: FAILED. `test_streaming_render_decisions.py` errors with `ImportError: cannot import name
'StreamProtocolError' from 'server.streaming_protocol'`; the protocol tests fail with
`AttributeError` for `StreamProtocolError` and `reject_embedded_tag`; the integration case with the
second tag in a later delta fails because the sentence that carries the tag is spoken.

- [ ] **Step 3: Implement.** The preamble regex of `streaming_protocol.py` is left for Task 3.

`server/src/server/streaming_protocol.py`:

```diff
@@ -20,10 +20,16 @@ _EMOTION_TAG_RE = re.compile(r"^EMOTION:\s*(\w+)\s*\n", re.IGNORECASE)
 # output here (it may contain arbitrary, unbounded model text).
 _INVALID_PROTOCOL_MESSAGE = "Invalid streaming response protocol"

+
+class StreamProtocolError(LLMError):
+    """The model's streamed output broke the protocol (never carries model text)."""
+
+
 _FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
 _TAG = "EMOTION:"
 _INVALID_BODY_PREFIXES = ("{", "[", _FENCE)
 _UNDECIDED_BODY_PREFIXES = (_TAG, _FENCE)
+_TAG_MENTION_RE = re.compile(r"\bemotion\W{0,3}[:\uff1a]", re.IGNORECASE)


 def parse_streaming_emotion(
@@ -48,13 +54,13 @@ def parse_streaming_emotion(
         ``final=False``).

     Raises:
-        LLMError: If ``final`` is True and the buffer never produced a
+        StreamProtocolError: If ``final`` is True and the buffer never produced a
             complete, valid protocol line.
     """
     match = _EMOTION_TAG_RE.match(buffer)
     if match is None:
         if final:
-            raise LLMError(_INVALID_PROTOCOL_MESSAGE)
+            raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
         return None
     emotion = match.group(1).lower()
     if emotion not in VALID_EMOTIONS:
@@ -93,9 +99,24 @@ def validate_streaming_body_start(body: str) -> None:
         body: The response text remaining after the emotion preamble.

     Raises:
-        LLMError: If ``body`` (ignoring leading whitespace) starts with
+        StreamProtocolError: If ``body`` (ignoring leading whitespace) starts with
             ``{``, ``[``, a code fence, or another ``EMOTION:`` tag.
     """
     stripped = body.lstrip()
     if stripped.startswith(_INVALID_BODY_PREFIXES) or stripped.upper().startswith(_TAG):
-        raise LLMError(_INVALID_PROTOCOL_MESSAGE)
+        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
+
+
+def reject_embedded_tag(text: str) -> None:
+    """Reject speech that contains a protocol tag anywhere (ADR 0017, decision 5).
+
+    Args:
+        text: One sentence, or the final unfinished tail, about to be spoken.
+
+    Raises:
+        StreamProtocolError: If ``text`` mentions ``EMOTION`` followed by a colon, in any
+            letter case, with up to three symbols between them (``**EMOTION**:``) and
+            either colon width.
+    """
+    if _TAG_MENTION_RE.search(text):
+        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
```


`server/src/server/streaming_render.py`:

```diff
@@ -14,7 +14,6 @@ import logging

 from server import llm, tts
 from server.conversation_log import log_spoken
-from server.exceptions import LLMError
 from server.pipeline import _elapsed_ms
 from server.schemas_streaming import (
     StreamAudioEvent,
@@ -25,8 +24,10 @@ from server.schemas_streaming import (
 from server.sentences import split_first_sentence
 from server.settings import settings
 from server.streaming_protocol import (
+    StreamProtocolError,
     is_body_start_undecided,
     parse_streaming_emotion,
+    reject_embedded_tag,
     validate_streaming_body_start,
 )

@@ -161,21 +162,25 @@ def _consume_body(buffer: str, state: StreamState) -> tuple[str, list[str]]:
     Promotes ``pending_emotion`` to emitted ``emotion`` the first time
     non-whitespace content passes ``validate_streaming_body_start``. While the
     body is still a prefix of a forbidden start (``E``, a lone backtick) nothing is
-    promoted or spoken: the next delta decides it.
+    promoted or spoken: the next delta decides it. No sentence that carries a
+    protocol tag is released, and a rejected batch promotes nothing, so the
+    fallback can still send the one ``emotion`` event the robot requires.

     Raises:
-        LLMError: If the body content is structurally invalid.
+        StreamProtocolError: If the body content is structurally invalid.
     """
     has_content = bool(buffer.strip())
     if state.emotion is None and has_content:
         if is_body_start_undecided(buffer):
             return buffer, []
         validate_streaming_body_start(buffer)
-        state.emotion = state.pending_emotion
     sentences: list[str] = []
     while (split := split_first_sentence(buffer)) is not None:
         sentence, buffer = split
+        reject_embedded_tag(sentence)
         sentences.append(sentence)
+    if state.emotion is None and has_content:
+        state.emotion = state.pending_emotion
     return buffer, sentences


@@ -186,30 +191,42 @@ def _preamble_fallback_reason(buffer: str) -> StreamFallbackReason:
     return StreamFallbackReason.EMPTY_STREAM


+def classify_stream_end(buffer: str, state: StreamState) -> StreamFallbackReason | None:
+    """Decide whether what is left when the stream ends can be spoken.
+
+    The single judgement shared by production and by the evaluator under ``scripts/``.
+
+    Args:
+        buffer: Text received but not yet spoken.
+        state: The turn's state at the end of the stream.
+
+    Returns:
+        ``None`` when the end can be spoken, otherwise the reason it cannot.
+    """
+    if state.pending_emotion is None and state.emotion is None:
+        return _preamble_fallback_reason(buffer)
+    tail = buffer.strip()
+    if state.emotion is None and not tail:
+        return StreamFallbackReason.INVALID_PROTOCOL
+    try:
+        if state.emotion is None:
+            validate_streaming_body_start(tail)
+        reject_embedded_tag(tail)
+    except StreamProtocolError:
+        return StreamFallbackReason.INVALID_PROTOCOL
+    return None
+
+
 async def _finalize_model_output(buffer: str, state: StreamState) -> AsyncIterator[str]:
     """Validate stream EOF; emit the final sentence or a safe fallback."""
-    if state.pending_emotion is None and state.emotion is None:
-        try:
-            parse_streaming_emotion(buffer, final=True)
-        except LLMError:
-            state.outcome = StreamOutcome.PROTOCOL_FALLBACK
-            reason = _preamble_fallback_reason(buffer)
-            async for line in emit_fallback(state, reason=reason):
-                yield line
-            return
+    reason = classify_stream_end(buffer, state)
+    if reason is not None:
+        state.outcome = StreamOutcome.PROTOCOL_FALLBACK
+        async for line in emit_fallback(state, reason=reason):
+            yield line
+        return
     tail = buffer.strip()
     if state.emotion is None:
-        valid_body = bool(tail)
-        if valid_body:
-            try:
-                validate_streaming_body_start(tail)
-            except LLMError:
-                valid_body = False
-        if not valid_body:
-            state.outcome = StreamOutcome.PROTOCOL_FALLBACK
-            async for line in emit_fallback(state, reason=StreamFallbackReason.INVALID_PROTOCOL):
-                yield line
-            return
         if state.pending_emotion is None:
             raise RuntimeError("pending_emotion must be set before promoting to emotion")
         state.emotion = state.pending_emotion
```


`server/src/server/streaming.py`:

```diff
@@ -32,6 +32,7 @@ from server.schemas_streaming import (
     StreamEmotionEvent,
     StreamTextHeardEvent,
 )
+from server.streaming_protocol import StreamProtocolError
 from server.streaming_render import (
     StreamErrorCode,
     StreamFallbackReason,
@@ -90,7 +91,7 @@ async def _consume_llm_stream(
         emotion_before = state.emotion
         try:
             buffer, sentences = _consume_body(buffer, state)
-        except LLMError:
+        except StreamProtocolError:
             state.outcome = StreamOutcome.PROTOCOL_FALLBACK
             async for line in emit_fallback(state, reason=StreamFallbackReason.INVALID_PROTOCOL):
                 yield line
```


`scripts/eval_stream_protocol.py`:

```diff
@@ -16,9 +16,14 @@ import enum
 import logging
 from typing import TYPE_CHECKING

-from server.exceptions import LLMError
-from server.streaming_protocol import parse_streaming_emotion, validate_streaming_body_start
-from server.streaming_render import StreamState, _consume_body, _consume_preamble
+from server.streaming_protocol import StreamProtocolError
+from server.streaming_render import (
+    StreamFallbackReason,
+    StreamState,
+    _consume_body,
+    _consume_preamble,
+    classify_stream_end,
+)

 from server import llm_streaming

@@ -61,21 +66,13 @@ class StreamOutcome(enum.StrEnum):


 def _classify_end_of_stream(buffer: str, state: StreamState) -> StreamOutcome:
-    """Mirror `streaming_render._finalize_model_output`'s decisions, without any TTS."""
-    if state.pending_emotion is None and state.emotion is None:
-        try:
-            parse_streaming_emotion(buffer, final=True)
-        except LLMError:
-            return StreamOutcome.INVALID_PROTOCOL if buffer.strip() else StreamOutcome.EMPTY_STREAM
-    if state.emotion is None:
-        tail = buffer.strip()
-        if not tail:
-            return StreamOutcome.INVALID_PROTOCOL
-        try:
-            validate_streaming_body_start(tail)
-        except LLMError:
-            return StreamOutcome.INVALID_PROTOCOL
-    return StreamOutcome.VALID
+    """Map production's end-of-stream judgement (`classify_stream_end`) to an outcome."""
+    reason = classify_stream_end(buffer, state)
+    if reason is None:
+        return StreamOutcome.VALID
+    if reason is StreamFallbackReason.EMPTY_STREAM:
+        return StreamOutcome.EMPTY_STREAM
+    return StreamOutcome.INVALID_PROTOCOL


 class _StreamClassifier:
@@ -99,7 +96,7 @@ class _StreamClassifier:
                 return None
         try:
             self._buffer, sentences = _consume_body(self._buffer, self._state)
-        except LLMError:
+        except StreamProtocolError:
             return StreamOutcome.INVALID_PROTOCOL
         self.sentences_seen += len(sentences)
         return None
```


- [ ] **Step 4: Run the streaming set and lint.**

```powershell
uv run pytest tests/unit tests/integration -q -k "stream"
uv run mypy --config-file=pyproject.toml server/src robot/src
uv run ruff check server/src/server/streaming_protocol.py server/src/server/streaming_render.py server/src/server/streaming.py scripts/eval_stream_protocol.py tests/unit/test_streaming_render_decisions.py tests/unit/test_streaming_protocol.py tests/unit/test_eval_stream_protocol.py tests/integration/test_transcribe_stream.py
uv run ruff format --check server/src/server/streaming_protocol.py server/src/server/streaming_render.py server/src/server/streaming.py scripts/eval_stream_protocol.py tests/unit/test_streaming_render_decisions.py tests/unit/test_streaming_protocol.py tests/unit/test_eval_stream_protocol.py tests/integration/test_transcribe_stream.py
```

Expected: all pass, mypy and ruff clean.

- [ ] **Step 5: Commit.**

```powershell
git add server/src/server/streaming_protocol.py server/src/server/streaming_render.py server/src/server/streaming.py scripts/eval_stream_protocol.py tests/unit/test_streaming_render_decisions.py tests/unit/test_streaming_protocol.py tests/unit/test_eval_stream_protocol.py tests/integration/test_transcribe_stream.py
git commit -m "fix(server): never speak a protocol tag (plan 0058)"
```

## Task 3: The start grammar of ADR 0017

Closes F-1, F-3 and F-5. `parse_streaming_emotion` returns a `Preamble` (emotion, remainder,
rescued) instead of a tuple, decides as soon as the text allows it, and may now raise mid-stream, so
the streaming loop and the evaluator treat the preamble inside the same `try` as the body. A rescued
reply sets the outcome `RESCUED`, which is recorded like `OK`. The diagnosis keeps naming shapes with
the strict grammar of Plan 0057.

**Files:**
- Modify: `server/src/server/streaming_protocol.py` (whole file), `streaming_render.py`,
  `streaming.py`, `llm_streaming.py`, `scripts/eval_stream_protocol.py`,
  `scripts/stream_failure_shapes.py`
- Test: `tests/unit/test_streaming_protocol.py` (rewritten), `test_llm_streaming.py`,
  `test_stream_failure_shapes.py`, `test_eval_stream_protocol.py`, `test_stream_fragmentation.py`,
  `test_eval_stream_diagnosis.py`, `tests/integration/test_transcribe_stream.py`,
  `test_transcribe_stream_resilience.py`

**Interfaces:**
- Consumes: `StreamProtocolError`, `reject_embedded_tag`, `is_body_start_undecided` (Tasks 1 and 2).
- Produces: `streaming_protocol.Preamble(emotion: str, remainder: str, rescued: bool = False)`;
  `parse_streaming_emotion(buffer: str, *, final: bool = False) -> Preamble | None`;
  `StreamOutcome.RESCUED = "rescued_no_tag"`.

- [ ] **Step 1: Write the failing tests.** The protocol test file is rewritten: it carries the tables
  of ADR 0017 (own-line, same-line, rescued, refused, undecided) and the earlier body tests. The
  three parse tests of `test_llm_streaming.py` move there, so they are deleted. A test that said a
  reply with no tag is a fallback now says it is spoken; the TTS-failure and `done`-after-audio
  tests that used plain text as their "invalid" input use JSON with no tag instead.

`tests/unit/test_streaming_protocol.py` (whole file):

```python
"""Unit tests for server.streaming_protocol: the streaming wire format (ADR 0017).

``parse_streaming_emotion`` decides how a reply starts as soon as the text allows it;
``validate_streaming_body_start``, ``is_body_start_undecided`` and ``reject_embedded_tag``
decide what may be spoken. None of them may leak model text into an exception message.
"""

from __future__ import annotations

import pytest
from server.exceptions import LLMError
from server.streaming_protocol import (
    Preamble,
    StreamProtocolError,
    is_body_start_undecided,
    parse_streaming_emotion,
    reject_embedded_tag,
    validate_streaming_body_start,
)

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

# Buffers that may still become a valid start: wait for the next delta.
_UNDECIDED = [
    "",
    "   ",
    "E",
    "EMO",
    "emotion",
    "EMOTION:",
    "EMOTION:jo",
    "EMOTION:joy",
    "EMOTION:joy  ",
    "EMOTION: joy",
]

# Buffers whose tag can never become valid: refuse as soon as that is known.
_REJECTED = [
    "EMOTION: Hola, ¿cómo estás?",
    "EMOTION: Hola cómo estás",
    "EMOTION:joy. Hola",
    "EMOTION:joy,Hola",
    "EMOTION:<joy>\nHola",
    "EMOTION: [joy]\nHola",
    "EMOTION: -\nHola",
]


@pytest.mark.unit
@pytest.mark.parametrize("buffer", _UNDECIDED)
def test_an_undecided_start_waits_for_more_text(buffer: str) -> None:
    assert parse_streaming_emotion(buffer) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer, expected",
    [
        ("EMOTION:joy\n", Preamble("joy", "")),
        ("EMOTION:joy\nhola", Preamble("joy", "hola")),
        ("EMOTION: joy \nhola", Preamble("joy", "hola")),
        ("emotion: sadness\nLo siento.", Preamble("sadness", "Lo siento.")),
        ("EMOTION:cosmic\nhola", Preamble("neutral", "hola")),
        ("EMOTION:\njoy\nhola", Preamble("joy", "hola")),
        ("\n EMOTION:anger\nCalma.", Preamble("anger", "Calma.")),
        ("EMOTION:joy\r\nhola", Preamble("joy", "hola")),
    ],
)
def test_a_tag_on_its_own_line_is_parsed(buffer: str, expected: Preamble) -> None:
    assert parse_streaming_emotion(buffer) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer, expected",
    [
        ("EMOTION:joy ¡Hola! ¿Qué tal?", Preamble("joy", "¡Hola! ¿Qué tal?")),
        ("emotion: sadness Lo siento mucho.", Preamble("sadness", "Lo siento mucho.")),
        ("EMOTION:joy\tHola", Preamble("joy", "Hola")),
        ("EMOTION:joy H", Preamble("joy", "H")),
        ('EMOTION: joy {"response":"hola"}', Preamble("joy", '{"response":"hola"}')),
    ],
)
def test_a_known_emotion_on_the_same_line_as_the_text_is_parsed(
    buffer: str, expected: Preamble
) -> None:
    assert parse_streaming_emotion(buffer) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "buffer",
    [
        "Hola sin etiqueta",
        "  Eso es genial.",
        "Emoción pura.",
        "Claro. EMOTION:joy\nHola",
        '{"response": "x"}',
    ],
)
def test_text_without_a_leading_tag_is_rescued_as_neutral(buffer: str) -> None:
    preamble = parse_streaming_emotion(buffer)

    assert preamble == Preamble("neutral", buffer.lstrip(), rescued=True)


@pytest.mark.unit
@pytest.mark.parametrize("buffer", _REJECTED)
def test_a_tag_that_can_never_be_valid_is_refused_at_once(buffer: str) -> None:
    with pytest.raises(StreamProtocolError) as exc_info:
        parse_streaming_emotion(buffer)

    assert buffer not in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.parametrize("buffer", _UNDECIDED)
def test_an_undecided_start_at_the_end_of_the_stream_is_a_violation(buffer: str) -> None:
    with pytest.raises(StreamProtocolError) as exc_info:
        parse_streaming_emotion(buffer, final=True)

    message = str(exc_info.value)
    assert message  # bounded, non-empty
    if buffer.strip():
        assert buffer not in message


@pytest.mark.unit
def test_a_decided_start_is_the_same_at_the_end_of_the_stream() -> None:
    assert parse_streaming_emotion("EMOTION:joy\nhola", final=True) == Preamble("joy", "hola")
    assert parse_streaming_emotion("Hola", final=True) == Preamble("neutral", "Hola", rescued=True)


@pytest.mark.unit
def test_a_tag_and_a_json_body_on_one_line_is_parsed_then_refused_by_the_body_check() -> None:
    preamble = parse_streaming_emotion('EMOTION: joy {"response":"hola"}')

    assert preamble is not None
    assert preamble.emotion == "joy"
    with pytest.raises(StreamProtocolError):
        validate_streaming_body_start(preamble.remainder)


@pytest.mark.unit
def test_validate_body_rejects_structured_json() -> None:
    """Hybrid output mixing the JSON contract into the streaming body is invalid."""
    hybrid_bodies = [
        '{"response": "hola", "emotion": "joy"}',
        '{"response":"hola"}',
        '["hola", "chau"]',
        f'{_FENCE}json\n{{"response": "hola"}}\n{_FENCE}',
        '  {"response": "hola"}',  # leading whitespace before the brace
    ]
    for body in hybrid_bodies:
        with pytest.raises(StreamProtocolError) as exc_info:
            validate_streaming_body_start(body)
        assert body not in str(exc_info.value)


@pytest.mark.unit
def test_validate_body_rejects_repeated_protocol() -> None:
    """A second EMOTION: tag inside the body means the model repeated the preamble."""
    repeated_bodies = [
        "EMOTION:joy\nhola de nuevo",
        "emotion:joy\nhola",
        "  EMOTION:sadness\nhola",
    ]
    for body in repeated_bodies:
        with pytest.raises(StreamProtocolError) as exc_info:
            validate_streaming_body_start(body)
        assert body not in str(exc_info.value)

    # A normal plain-text body must pass without raising.
    validate_streaming_body_start("hola, como estas?")


@pytest.mark.unit
def test_a_protocol_error_is_an_llm_error() -> None:
    """Callers that catch ``LLMError`` keep working; the streaming loop catches the subclass."""
    assert issubclass(StreamProtocolError, LLMError)


@pytest.mark.unit
@pytest.mark.parametrize("body", ["E", "EM", "emotion", "  EMOTION", "`", "``"])
def test_a_body_that_could_still_become_a_forbidden_start_is_undecided(body: str) -> None:
    """A prefix of ``EMOTION:`` or of a code fence cannot be judged yet: wait for more."""
    assert is_body_start_undecided(body)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body", ["", "   ", "Hola", "Es", "{", "[", "EMOTION:", "emotion:joy", "`x", _FENCE, "Eso."]
)
def test_a_body_that_is_decided_is_not_undecided(body: str) -> None:
    """Decided means allowed (plain text) or already forbidden (``validate`` rejects it)."""
    assert not is_body_start_undecided(body)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "Hola. EMOTION:joy",
        "**EMOTION:** joy",
        "**EMOTION**: joy",
        "EMOTION\uff1a joy",
        "EMOTION : joy",
        "emotion: joy",
        "Claro, emotion:joy otra vez.",
    ],
)
def test_reject_embedded_tag_refuses_a_tag_anywhere(text: str) -> None:
    with pytest.raises(StreamProtocolError) as exc_info:
        reject_embedded_tag(text)

    assert text not in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "La emoción es alegría.",
        "Emotion es una palabra.",
        "Una demotion: palabra rara.",
        "¿Qué emoción sientes?",
        "",
    ],
)
def test_reject_embedded_tag_allows_plain_speech(text: str) -> None:
    reject_embedded_tag(text)
```


`tests/unit/test_llm_streaming.py`:

```diff
@@ -127,18 +127,3 @@ def test_streaming_system_prompt_appends_exactly_one_contract() -> None:
     assert prompt.count("EMOTION:") == 1
     assert '"response"' not in prompt
     assert '"emotion"' not in prompt
-
-
-@pytest.mark.unit
-def test_parse_streaming_emotion_valid_tag() -> None:
-    assert llm_streaming.parse_streaming_emotion("EMOTION:joy\nhola") == ("joy", "hola")
-
-
-@pytest.mark.unit
-def test_parse_streaming_emotion_unknown_tag_defaults_neutral() -> None:
-    assert llm_streaming.parse_streaming_emotion("EMOTION:cosmic\nhola") == ("neutral", "hola")
-
-
-@pytest.mark.unit
-def test_parse_streaming_emotion_no_tag_returns_none() -> None:
-    assert llm_streaming.parse_streaming_emotion("hola sin tag") is None
```


`tests/unit/test_stream_failure_shapes.py`:

```diff
@@ -49,13 +49,37 @@ def test_every_shape_is_named_exactly(text: str, shape: FailureShape) -> None:
     assert classify_failure_shape(text) is shape


+# Shapes of replies the protocol of ADR 0017 now speaks although the strict 0057 grammar
+# named them failures: a tag sharing its line, text before any tag, a leading blank, a label.
+_TOLERATED = {
+    FailureShape.NO_TAG,
+    FailureShape.OTHER_LABEL,
+    FailureShape.LEADING_WHITESPACE,
+    FailureShape.TAG_SAME_LINE,
+}
+
+
+def _whole_text_outcome(text: str) -> StreamOutcome:
+    return classify_deltas([text] if text else [])
+
+
 @pytest.mark.unit
 @pytest.mark.parametrize("text, shape", _CASES)
-def test_valid_shape_agrees_with_the_whole_text_protocol(text: str, shape: FailureShape) -> None:
-    """The shape table and the protocol never disagree about speakable text."""
-    whole = classify_deltas([text] if text else [])
+def test_a_strictly_valid_shape_is_always_speakable(text: str, shape: FailureShape) -> None:
+    """The strict reading never accepts what production refuses (production may accept more)."""
+    if shape is FailureShape.VALID:
+        assert _whole_text_outcome(text) is StreamOutcome.VALID
+
+
+@pytest.mark.unit
+def test_the_shapes_production_now_tolerates_are_exactly_these() -> None:
+    tolerated = {
+        shape
+        for text, shape in _CASES
+        if shape is not FailureShape.VALID and _whole_text_outcome(text) is StreamOutcome.VALID
+    }

-    assert (shape is FailureShape.VALID) == (whole is StreamOutcome.VALID)
+    assert tolerated == _TOLERATED


 @pytest.mark.unit
```


`tests/unit/test_eval_stream_protocol.py`:

```diff
@@ -45,6 +45,14 @@ _REPLIES = [
     "emotion: joy\nHola",
     "EMOTION:joy\nHola. EMOTION:anger\nAdiós.",
     "EMOTION:joy\nHola. **EMOTION:** joy",
+    "EMOTION:joy ¡Hola! ¿Qué tal?",
+    "EMOTION: Hola, ¿cómo estás?",
+    "EMOTION:joy. Hola",
+    "\nEMOTION:anger\nCalma.",
+    "Emoción pura. Gracias.",
+    "Claro. EMOTION:joy\nHola",
+    "**EMOTION**: joy\nHola. Qué tal.",
+    '{"response": "x"}',
 ]


@@ -55,7 +63,12 @@ _REPLIES = [
         (["EMOTION:joy\nHola, ¿cómo estás?"], StreamOutcome.VALID),
         (["EMOTION:joy\n"], StreamOutcome.INVALID_PROTOCOL),
         (["EMOTION:joy\n   "], StreamOutcome.INVALID_PROTOCOL),
-        (["Hola sin etiqueta"], StreamOutcome.INVALID_PROTOCOL),
+        (["Hola sin etiqueta"], StreamOutcome.VALID),
+        (["EMOTION:joy ¡Hola!"], StreamOutcome.VALID),
+        (["\nEMOTION:joy\nHola"], StreamOutcome.VALID),
+        (["EMOTION: Hola, ¿cómo estás?"], StreamOutcome.INVALID_PROTOCOL),
+        (['{"response": "x"}'], StreamOutcome.INVALID_PROTOCOL),
+        (["Claro. EMOTION:joy\nHola"], StreamOutcome.INVALID_PROTOCOL),
         (['EMOTION:joy\n{"response": "x"}'], StreamOutcome.INVALID_PROTOCOL),
         (["EMOTION:joy\nEMOTION:anger\nhola"], StreamOutcome.INVALID_PROTOCOL),
         (["EMOTION:joy"], StreamOutcome.INVALID_PROTOCOL),
@@ -180,6 +193,7 @@ async def _evaluator_after_a_provider_error(fragments: list[str]) -> str:
     [
         (["EMOTION:joy\n{"], "invalid_protocol"),
         (["EMOTION:joy\n", "[1]"], "invalid_protocol"),
+        (["EMOTION: Hola, ¿cómo"], "invalid_protocol"),
         (["EMOTION:joy\nHola"], "provider_error"),
         (["EMOTION:joy\n"], "provider_error"),
         (["Hola sin etiqueta"], "provider_error"),
@@ -258,13 +272,13 @@ async def test_measure_counts_each_outcome_and_keeps_errors_out_of_the_rate() ->
     )

     assert (result.valid, result.invalid_protocol, result.empty_stream, result.errors) == (
-        1,
         2,
         1,
         1,
+        1,
     )
     assert result.graded == 4
-    assert result.fallback_rate == pytest.approx(3 / 4)
+    assert result.fallback_rate == pytest.approx(2 / 4)


 @pytest.mark.unit
@@ -274,7 +288,7 @@ async def test_measure_splits_the_counts_by_turn_source() -> None:
         client=_client(),
         runs=2,
         generate=_generator(
-            ["EMOTION:joy\nHola", "EMOTION:joy\nHola", "sin etiqueta", "sin etiqueta"]
+            ["EMOTION:joy\nHola", "EMOTION:joy\nHola", '{"response": "x"}', '{"response": "x"}']
         ),
     )

```


`tests/unit/test_stream_fragmentation.py`:

```diff
@@ -46,6 +46,22 @@ def test_the_family_includes_word_and_punctuation_tokens() -> None:
     assert ["EMOTION", ":", "joy", "\n", "Hola"] in reply_fragmentations("EMOTION:joy\nHola")


+# Replies the protocol of ADR 0017 speaks although the 0057 grammar refused them.
+_TOLERATED = [
+    "EMOTION:joy ¡Hola! ¿Qué tal?",
+    "emotion: sadness Lo siento mucho.",
+    "\nEMOTION:anger\nCalma.",
+    "Hola sin etiqueta",
+    "Emoción pura. Gracias.",
+]
+
+
+@pytest.mark.unit
+@pytest.mark.parametrize("reply", _TOLERATED)
+def test_a_tolerated_reply_is_accepted_under_every_split(reply: str) -> None:
+    assert fragmentation_outcomes(reply) == {StreamOutcome.VALID}
+
+
 @pytest.mark.unit
 @pytest.mark.parametrize("reply", _CONSISTENT)
 def test_a_reply_judged_the_same_under_every_split_is_consistent(reply: str) -> None:
```


`tests/unit/test_eval_stream_diagnosis.py`:

```diff
@@ -123,15 +123,27 @@ async def test_an_invalid_body_start_decides_at_once_and_closes_the_stream() ->


 @pytest.mark.unit
-async def test_a_reply_without_the_tag_waits_for_the_end_of_the_stream() -> None:
+async def test_a_reply_without_the_tag_is_spoken_from_its_first_closed_sentence() -> None:
     obs = await _observe(_FakeStream("Hola ", "sin etiqueta."))

-    assert obs.outcome is StreamOutcome.INVALID_PROTOCOL
+    assert obs.outcome is StreamOutcome.VALID
     assert obs.shape is FailureShape.NO_TAG
-    assert obs.speech_start_ms == obs.end_ms == 30
+    assert not obs.fell_back
+    assert obs.speech_start_ms == 20  # the second delta closes the first sentence
+    assert obs.end_ms == 30
     assert obs.first_delta_ms == 10


+@pytest.mark.unit
+async def test_json_without_a_tag_waits_for_nothing_and_falls_back() -> None:
+    obs = await _observe(_FakeStream('{"response": "x"}'))
+
+    assert obs.outcome is StreamOutcome.INVALID_PROTOCOL
+    assert obs.shape is FailureShape.JSON_START
+    assert obs.fell_back
+    assert obs.speech_start_ms == obs.first_delta_ms == 10
+
+
 @pytest.mark.unit
 async def test_an_empty_stream_is_an_empty_observation() -> None:
     obs = await _observe(_FakeStream())
@@ -169,7 +181,7 @@ async def test_an_observation_never_holds_the_reply_text() -> None:

 @pytest.mark.unit
 async def test_the_diagnosis_runs_every_unit_and_keeps_provider_errors_apart() -> None:
-    replies: list[str | Exception] = ["EMOTION:joy\nHola.", LLMError("boom"), "sin etiqueta"]
+    replies: list[str | Exception] = ["EMOTION:joy\nHola.", LLMError("boom"), '{"response": "x"}']
     queue = iter(replies)

     def generate_for(_variant: StreamVariant) -> StreamGenerator:
```


`tests/integration/test_transcribe_stream.py`:

```diff
@@ -635,6 +635,114 @@ def test_stream_a_rejected_batch_still_sends_exactly_one_emotion_before_the_audi
     assert kinds[-1] == "done"


+@pytest.mark.integration
+@pytest.mark.parametrize(
+    "deltas, emotion, spoken",
+    [
+        (
+            ["EMOTION:joy ¡Qué ", "emocionante! Cuéntame."],
+            "joy",
+            ["¡Qué emocionante!", "Cuéntame."],
+        ),
+        (["\nEMOTION:anger\nCalma."], "anger", ["Calma."]),
+        (["Hola. ", "¿Cómo estás?"], "neutral", ["Hola.", "¿Cómo estás?"]),
+    ],
+)
+def test_stream_tolerated_replies_are_spoken_and_recorded(
+    client: TestClient,
+    silence_wav_bytes: bytes,
+    monkeypatch: pytest.MonkeyPatch,
+    deltas: list[str],
+    emotion: str,
+    spoken: list[str],
+) -> None:
+    """A tag sharing its line, a leading blank and a reply with no tag are all spoken."""
+    record = Mock()
+    synthesize = AsyncMock(return_value=("QQ==", 10))
+    monkeypatch.setattr(streaming, "record_text_turn", record)
+    monkeypatch.setattr(tts, "synthesize", synthesize)
+    events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, deltas)
+    assert [event["type"] for event in events] == [
+        "text_heard",
+        "emotion",
+        *["audio"] * len(spoken),
+        "done",
+    ]
+    assert events[1]["value"] == emotion
+    assert [call.args[0] for call in synthesize.await_args_list] == spoken
+    record.assert_called_once()
+    assert record.call_args.args[2] == " ".join(spoken)
+    assert record.call_args.args[3] == emotion
+
+
+@pytest.mark.integration
+def test_stream_a_reply_without_a_tag_logs_the_rescued_outcome(
+    client: TestClient,
+    silence_wav_bytes: bytes,
+    monkeypatch: pytest.MonkeyPatch,
+    caplog: pytest.LogCaptureFixture,
+) -> None:
+    caplog.set_level(logging.INFO, logger="server.streaming_render")
+
+    _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, ["Hola. ¿Cómo estás?"])
+
+    messages = [record.getMessage() for record in caplog.records]
+    assert any("Stream done: outcome=rescued_no_tag" in message for message in messages)
+
+
+@pytest.mark.integration
+@pytest.mark.parametrize(
+    "deltas",
+    [
+        ["EMOTION: Hola, ¿cómo estás?"],
+        ["EMOTION:joy. Hola"],
+        ["EMOTION:<joy>\nHola"],
+        ['{"response": "hola"}'],
+        ["**EMOTION**: joy\nHola. Qué tal."],
+        ["EMOTION\uff1ajoy\nHola. Qué tal."],
+    ],
+)
+def test_stream_a_tag_that_can_never_be_valid_uses_audible_protocol_fallback(
+    client: TestClient,
+    silence_wav_bytes: bytes,
+    monkeypatch: pytest.MonkeyPatch,
+    deltas: list[str],
+) -> None:
+    record = Mock()
+    synthesize = AsyncMock(return_value=("QQ==", 10))
+    monkeypatch.setattr(streaming, "record_text_turn", record)
+    monkeypatch.setattr(tts, "synthesize", synthesize)
+    events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, deltas)
+    _assert_audible_protocol_fallback(events)
+    synthesize.assert_awaited_once_with(settings.llm_fallback_phrase)
+    record.assert_not_called()
+
+
+@pytest.mark.integration
+def test_stream_a_tag_after_untagged_speech_keeps_the_audio_and_adds_the_fallback(
+    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """Known limit (ADR 0017): the sentence before a late tag has already been spoken."""
+    record = Mock()
+    synthesize = AsyncMock(return_value=("QQ==", 10))
+    monkeypatch.setattr(streaming, "record_text_turn", record)
+    monkeypatch.setattr(tts, "synthesize", synthesize)
+    events = _post_stream_with_deltas(
+        client, monkeypatch, silence_wav_bytes, ["Claro. EMOTION:joy\nHola"]
+    )
+    assert [event["type"] for event in events] == [
+        "text_heard",
+        "emotion",
+        "audio",
+        "audio",
+        "done",
+    ]
+    assert events[1]["value"] == "neutral"
+    spoken = [call.args[0] for call in synthesize.await_args_list]
+    assert spoken == ["Claro.", settings.llm_fallback_phrase]
+    record.assert_not_called()
+
+
 @pytest.mark.integration
 def test_stream_truncated_emotion_uses_audible_protocol_fallback(
     client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
@@ -691,7 +799,8 @@ def test_every_done_has_prior_contract_valid_audio(
         ["EMOTION:ale"],
         [],
         ["EMOTION:joy\n   "],
-        ["Hola sin protocolo."],
+        ['{"response": "hola"}'],
+        ["EMOTION: Hola, ¿cómo estás?"],
     ]
     for deltas in invalid_delta_cases:
         events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, deltas)
@@ -773,7 +882,7 @@ async def test_stream_protocol_fallback_tts_failure_has_no_done(
     )

     async def plain_text(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
-        yield "Hola sin protocolo."
+        yield '{"response": "hola"}'

     monkeypatch.setattr(llm_streaming, "generate_response_stream", plain_text)
     monkeypatch.setattr(tts, "synthesize", AsyncMock(side_effect=TTSError("piper down")))
@@ -805,7 +914,7 @@ async def test_stream_tts_failure_logs_tts_error_outcome(
     )

     async def plain_text(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
-        yield "Hola sin protocolo."
+        yield '{"response": "hola"}'

     monkeypatch.setattr(llm_streaming, "generate_response_stream", plain_text)
     monkeypatch.setattr(tts, "synthesize", AsyncMock(side_effect=TTSError("piper down")))
```


`tests/integration/test_transcribe_stream_resilience.py`:

```diff
@@ -73,15 +73,15 @@ def test_stream_empty_audio_returns_422(client: TestClient) -> None:


 @pytest.mark.integration
-def test_stream_plain_text_uses_audible_protocol_fallback(
+def test_stream_json_without_a_tag_uses_audible_protocol_fallback(
     client: TestClient,
     silence_wav_bytes: bytes,
     monkeypatch: pytest.MonkeyPatch,
 ) -> None:
-    """Plain text with no EMOTION tag at all is invalid output — spoken as fallback."""
+    """Structured output with no EMOTION tag is invalid output — spoken as fallback."""

     async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
-        for delta in ("Hola. ", "¿Cómo estás?"):
+        for delta in ('{"response": ', '"Hola.", "emotion": "joy"}'):
             yield delta

     monkeypatch.setattr(llm_streaming, "generate_response_stream", fake_stream)
```


- [ ] **Step 2: Run them and see them fail for the stated reason.**

```powershell
uv run pytest tests/unit/test_streaming_protocol.py tests/unit/test_stream_failure_shapes.py tests/unit/test_eval_stream_protocol.py tests/unit/test_stream_fragmentation.py tests/unit/test_eval_stream_diagnosis.py tests/integration/test_transcribe_stream.py -q
```

Expected: FAILED. `test_streaming_protocol.py` errors with `ImportError: cannot import name
'Preamble' from 'server.streaming_protocol'`; the tolerated-reply cases fail because the reply is
refused (`INVALID_PROTOCOL` where `VALID` is expected, or the fallback phrase where the reply is
expected); the rescued-outcome log test fails because no line says `rescued_no_tag`; the
tolerated-shapes test fails because the set is empty.

- [ ] **Step 3: Implement.** First the whole of `streaming_protocol.py`:

`server/src/server/streaming_protocol.py` (whole file):

```python
"""Pure parsing/validation for the streaming EMOTION-tag output protocol (ADR 0017).

llm_streaming.py owns prompt assembly and the Ollama transport; this module
owns only the wire-format rules for what a valid streamed response looks
like. Kept dependency-free of I/O and logging on purpose: the orchestration
loop in streaming.py calls these functions to decide whether a candidate
response is speakable at all, so they must be safe to unit test in isolation
and must never leak raw model output into an exception message (that text
may contain anything the model produced).
"""

from dataclasses import dataclass
import re

from server.exceptions import LLMError
from server.llm import FALLBACK_EMOTION, VALID_EMOTIONS

_TAG = "EMOTION:"
_FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
_INVALID_BODY_PREFIXES = ("{", "[", _FENCE)
_UNDECIDED_BODY_PREFIXES = (_TAG, _FENCE)
_INLINE_SPACE = " \t\r"
_WORD_AFTER_TAG_RE = re.compile(r"\s*(\w+)")
# A tag mention in speech: **EMOTION**: and a fullwidth colon count; demotion: does not.
_TAG_MENTION_RE = re.compile(r"\bemotion\W{0,3}[:\uff1a]", re.IGNORECASE)

# Bounded, content-free message — never interpolate the raw candidate/model
# output here (it may contain arbitrary, unbounded model text).
_INVALID_PROTOCOL_MESSAGE = "Invalid streaming response protocol"


class StreamProtocolError(LLMError):
    """The model's streamed output broke the protocol (never carries model text)."""


@dataclass(frozen=True)
class Preamble:
    """The decided start of a streamed reply.

    Attributes:
        emotion: A member of ``VALID_EMOTIONS``: ``neutral`` when the model named an
            unknown one or sent no tag at all.
        remainder: The text after the tag, or the whole reply when it was rescued.
        rescued: True when the reply carried no tag and is spoken as plain text.
    """

    emotion: str
    remainder: str
    rescued: bool = False


def _is_proper_prefix(text: str, target: str) -> bool:
    """Whether ``text`` could still grow into ``target`` (ignoring letter case)."""
    return len(text) < len(target) and target.startswith(text.upper())


def _decide(text: str) -> Preamble | None:
    """Decide the preamble of ``text`` (already left-stripped) or ask for more input.

    Raises:
        StreamProtocolError: If the tag is present but can never become valid.
    """
    if not text or _is_proper_prefix(text, _TAG):
        return None
    if not text.upper().startswith(_TAG):
        return Preamble(FALLBACK_EMOTION, text, rescued=True)
    after_tag = text[len(_TAG) :]
    word = _WORD_AFTER_TAG_RE.match(after_tag)
    if word is None:
        if after_tag.strip():
            raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
        return None  # only whitespace after the colon so far: the word has not started
    rest = after_tag[word.end() :]
    line_rest = rest.lstrip(_INLINE_SPACE)
    if not line_rest:
        return None  # the word may still grow, or the newline may still come
    emotion = word.group(1).lower()
    if line_rest[0] == "\n":
        return Preamble(emotion if emotion in VALID_EMOTIONS else FALLBACK_EMOTION, line_rest[1:])
    if rest[0] not in _INLINE_SPACE or emotion not in VALID_EMOTIONS:
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
    return Preamble(emotion, line_rest)


def parse_streaming_emotion(buffer: str, *, final: bool = False) -> Preamble | None:
    """Decide how a streamed reply starts, as soon as the text allows it.

    A reply may open with ``EMOTION:<emotion>`` on its own line, with the same tag
    followed by the text on the same line (only for a known emotion), or with no tag at
    all (rescued as plain text with the ``neutral`` emotion). Leading whitespace is
    ignored. A tag that can never become valid is refused at once.

    Args:
        buffer: Text accumulated so far from generate_response_stream.
        final: Whether the stream has ended and no more text will arrive. When True,
            a buffer that is still undecided is a protocol violation rather than
            "keep waiting".

    Returns:
        A ``Preamble`` once the start is decided, or ``None`` while more input may
        still decide it (only possible when ``final=False``).

    Raises:
        StreamProtocolError: If the start can never be valid, or ``final`` is True and
            the buffer is still undecided.
    """
    preamble = _decide(buffer.lstrip())
    if preamble is None and final:
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
    return preamble


def is_body_start_undecided(body: str) -> bool:
    """Whether the body so far is a proper prefix of a forbidden start (tag or fence).

    A body that begins ``E`` or a single backtick may still become ``EMOTION:`` or a
    code fence once the next token arrives, so it can be neither spoken nor judged yet.

    Args:
        body: The text after the preamble, as received so far.

    Returns:
        True while more text is needed to know whether the body start is allowed.
    """
    stripped = body.lstrip()
    return bool(stripped) and any(
        _is_proper_prefix(stripped, prefix) for prefix in _UNDECIDED_BODY_PREFIXES
    )


def validate_streaming_body_start(body: str) -> None:
    """Reject structured metadata or a repeated protocol tag before speech.

    Called once the emotion preamble has been stripped, before the
    remainder is treated as speakable text. Guards against hybrid model
    output that mixes the classic JSON contract or repeats the streaming
    tag instead of answering in plain text.

    Args:
        body: The response text remaining after the emotion preamble.

    Raises:
        StreamProtocolError: If ``body`` (ignoring leading whitespace) starts with
            ``{``, ``[``, a code fence, or another ``EMOTION:`` tag.
    """
    stripped = body.lstrip()
    if stripped.startswith(_INVALID_BODY_PREFIXES) or stripped.upper().startswith(_TAG):
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)


def reject_embedded_tag(text: str) -> None:
    """Reject speech that contains a protocol tag anywhere (ADR 0017, decision 5).

    Args:
        text: One sentence, or the final unfinished tail, about to be spoken.

    Raises:
        StreamProtocolError: If ``text`` mentions ``EMOTION`` followed by a colon, in any
            letter case, with up to three symbols between them (``**EMOTION**:``) and
            either colon width.
    """
    if _TAG_MENTION_RE.search(text):
        raise StreamProtocolError(_INVALID_PROTOCOL_MESSAGE)
```


Then the other production and instrument files:

`server/src/server/streaming_render.py`:

```diff
@@ -38,6 +38,7 @@ class StreamOutcome(StrEnum):
     """How one streamed turn ended — drives the final `done` log line."""

     OK = "ok"
+    RESCUED = "rescued_no_tag"
     PROTOCOL_FALLBACK = "protocol_fallback"
     LLM_FALLBACK = "llm_fallback"
     PARTIAL_FALLBACK = "partial_fallback"
@@ -142,18 +143,26 @@ async def emit_fallback(state: StreamState, *, reason: StreamFallbackReason) ->


 def _consume_preamble(buffer: str, state: StreamState) -> tuple[str, bool]:
-    """Consume the EMOTION preamble line once it is fully buffered.
+    """Consume the start of the reply once ``parse_streaming_emotion`` has decided it.
+
+    A reply with no tag is rescued: its whole text is the body, the emotion is
+    ``neutral`` and the turn is logged as ``rescued_no_tag`` (it is still recorded).

     Returns:
-        ``(remaining_buffer, True)`` once the preamble line was consumed
-        (stored in ``state.pending_emotion``), or ``(buffer, False)`` while
-        more input may still complete it.
+        ``(remaining_buffer, True)`` once the start was decided (stored in
+        ``state.pending_emotion``), or ``(buffer, False)`` while more input may
+        still decide it.
+
+    Raises:
+        StreamProtocolError: If the tag can never become valid.
     """
     parsed = parse_streaming_emotion(buffer)
     if parsed is None:
         return buffer, False
-    state.pending_emotion, remainder = parsed
-    return remainder, True
+    state.pending_emotion = parsed.emotion
+    if parsed.rescued:
+        state.outcome = StreamOutcome.RESCUED
+    return parsed.remainder, True


 def _consume_body(buffer: str, state: StreamState) -> tuple[str, list[str]]:
```


`server/src/server/streaming.py`:

```diff
@@ -55,6 +55,9 @@ from server.text_turn import (

 logger = logging.getLogger(__name__)

+# Outcomes whose reply was spoken whole and is persisted as a normal turn.
+_RECORDED_OUTCOMES = frozenset({StreamOutcome.OK, StreamOutcome.RESCUED})
+

 async def _text_deltas(client: httpx.AsyncClient, inputs: PreparedTextTurn) -> AsyncIterator[str]:
     """Yield "EMOTION:xxx\\n"-tagged text deltas from local Ollama, token by token."""
@@ -84,12 +87,12 @@ async def _consume_llm_stream(
     buffer = ""
     async for delta in _text_deltas(client, inputs):
         buffer += delta
-        if state.pending_emotion is None and state.emotion is None:
-            buffer, consumed = _consume_preamble(buffer, state)
-            if not consumed:
-                continue
         emotion_before = state.emotion
         try:
+            if state.pending_emotion is None and state.emotion is None:
+                buffer, consumed = _consume_preamble(buffer, state)
+                if not consumed:
+                    continue
             buffer, sentences = _consume_body(buffer, state)
         except StreamProtocolError:
             state.outcome = StreamOutcome.PROTOCOL_FALLBACK
@@ -111,7 +114,7 @@ def _record_success(
     scheduler: ConsolidationScheduler,
 ) -> None:
     """Persist a turn — only ever called for a fully successful stream."""
-    if state.outcome is not StreamOutcome.OK or not state.recordable or not state.response_parts:
+    if state.outcome not in _RECORDED_OUTCOMES or not state.recordable or not state.response_parts:
         return
     record_text_turn(
         prepared.message,
```


`server/src/server/llm_streaming.py`:

```diff
@@ -32,14 +32,6 @@ from server.onboarding import OnboardingSlot
 from server.schemas import ConversationTurn, MemoryContext
 from server.settings import settings

-# Re-exported temporarily so existing call sites/tests can keep resolving
-# the streaming protocol from this module. Task 3 moves the orchestration
-# call-sites in streaming.py to import from streaming_protocol directly.
-from server.streaming_protocol import (  # noqa: F401
-    parse_streaming_emotion,
-    validate_streaming_body_start,
-)
-
 # Sole owner of the streaming /transcribe/stream output contract.
 # build_system_prompt is format-neutral (identity/behavior only) — this is
 # the ONLY place the streaming EMOTION-tag contract is appended, so the
```


`scripts/eval_stream_protocol.py`:

```diff
@@ -2,9 +2,8 @@

 Runs real turns through the production streaming generator and consumes the deltas the
 way `server.streaming._consume_llm_stream` does: incrementally, with the production
-helpers, so a reply fragmented differently is classified differently exactly as it
-would be live (production stops validating once the body start is accepted). A test
-pins the equivalence against the real consumer for several fragmentations. It measures
+helpers, so a reply is judged exactly as it would be live. A test pins the equivalence
+against the real consumer for several fragmentations. It measures
 how often a reply would drop to the fallback phrase (0049 O-04); it never prints or
 stores model output.
 """
@@ -90,11 +89,11 @@ class _StreamClassifier:
             The decided outcome, or ``None`` while production would keep consuming.
         """
         self._buffer += delta
-        if self._state.pending_emotion is None and self._state.emotion is None:
-            self._buffer, consumed = _consume_preamble(self._buffer, self._state)
-            if not consumed:
-                return None
         try:
+            if self._state.pending_emotion is None and self._state.emotion is None:
+                self._buffer, consumed = _consume_preamble(self._buffer, self._state)
+                if not consumed:
+                    return None
             self._buffer, sentences = _consume_body(self._buffer, self._state)
         except StreamProtocolError:
             return StreamOutcome.INVALID_PROTOCOL
```


`scripts/stream_failure_shapes.py`:

```diff
@@ -9,14 +9,15 @@ from __future__ import annotations
 import enum
 import re

-from server.streaming_protocol import parse_streaming_emotion
-
 _TAG_PREFIX = "EMOTION:"
 _WRAPPERS = "<[({\"'«*_`"
 _JSON_STARTS = ("{", "[")
 _FENCE = "`" * 3  # built, not written: this module is quoted inside Markdown fences
 _LABEL_RE = re.compile(r"^\W*(?:emoci[oó]n|emotion|mood|sentimiento|estado)\b", re.IGNORECASE)
 _WORD_RE = re.compile(r"\w+")
+# Plan 0057's strict grammar, frozen on purpose: a shape names what the MODEL wrote, so it
+# must not change when the protocol learns to tolerate one (Plan 0058, ADR 0017).
+_STRICT_TAG_RE = re.compile(r"^EMOTION:\s*\w+\s*\n", re.IGNORECASE)


 class FailureShape(enum.StrEnum):
@@ -41,6 +42,12 @@ class FailureShape(enum.StrEnum):
     OTHER = "other"


+def _strict_body(text: str) -> str | None:
+    """Return what follows a strictly well-formed ``EMOTION:<x>`` line, or ``None``."""
+    match = _STRICT_TAG_RE.match(text)
+    return None if match is None else text[match.end() :]
+
+
 def _body_shape(body: str) -> FailureShape:
     """Classify what follows a well-formed ``EMOTION:<x>`` line."""
     stripped = body.lstrip()
@@ -75,7 +82,7 @@ def _malformed_tag_shape(text: str) -> FailureShape:

 def _tag_prefixed_shape(text: str, stripped: str) -> FailureShape:
     """Classify a reply whose first non-blank text is ``EMOTION:`` but is not a valid line."""
-    if stripped != text and parse_streaming_emotion(stripped) is not None:
+    if stripped != text and _strict_body(stripped) is not None:
         return FailureShape.LEADING_WHITESPACE
     return _malformed_tag_shape(stripped)

@@ -103,11 +110,12 @@ def classify_failure_shape(text: str) -> FailureShape:
         text: The reply as received (may be partial when production stopped reading).

     Returns:
-        A ``FailureShape``. ``VALID`` means the text, taken whole, passes the protocol.
+        A ``FailureShape``. ``VALID`` means the text, taken whole, passes the strict
+        0057 grammar; production may speak more (ADR 0017), never less.
     """
     if not text.strip():
         return FailureShape.EMPTY
-    parsed = parse_streaming_emotion(text)
-    if parsed is not None:
-        return _body_shape(parsed[1])
+    body = _strict_body(text)
+    if body is not None:
+        return _body_shape(body)
     return _unparsed_shape(text)
```


- [ ] **Step 4: Run the streaming set, the type check and lint.**

```powershell
uv run pytest tests/unit tests/integration -q -k "stream"
uv run mypy --config-file=pyproject.toml server/src robot/src
uv run pyright
uv run ruff check server/src/server/streaming_protocol.py server/src/server/streaming_render.py server/src/server/streaming.py server/src/server/llm_streaming.py scripts/eval_stream_protocol.py scripts/stream_failure_shapes.py tests/unit tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py
uv run ruff format --check server/src/server/streaming_protocol.py server/src/server/streaming_render.py server/src/server/streaming.py server/src/server/llm_streaming.py scripts/eval_stream_protocol.py scripts/stream_failure_shapes.py tests/unit tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py
```

Expected: all pass; mypy, pyright and ruff clean. The generated OpenAPI is unchanged (`tests/integration/test_api_contract.py`
passes).

- [ ] **Step 5: Commit.**

```powershell
git add server/src/server/streaming_protocol.py server/src/server/streaming_render.py server/src/server/streaming.py server/src/server/llm_streaming.py scripts/eval_stream_protocol.py scripts/stream_failure_shapes.py tests/unit tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py
git commit -m "feat(server): tolerant streaming reply start (plan 0058)"
```

## Task 4: The diagnosis counts tolerated replies

Without this, the next `just diagnose-stream` would report a fallback rate that fell and no reason
why. A *tolerated* reply is one production speaks although the strict 0057 shape names a failure.

**Files:**
- Modify: `scripts/eval_stream_diagnosis.py`, `stream_diagnosis_stats.py`,
  `stream_diagnosis_report.py`
- Test: `tests/unit/test_stream_diagnosis_report.py`, `tests/unit/test_eval_stream_diagnosis.py`

**Interfaces:**
- Consumes: `Observation.shape` (strict reading, Task 3).
- Produces: `Observation.tolerated: bool` (property), `GroupSummary.tolerated: int`,
  `stream_diagnosis_stats.tolerated_shape_counts(observations) -> dict[str, int]`; a *Tolerated*
  column in section 1 and a *Tolerated in `full`* table per source in section 3 of the report.

- [ ] **Step 1: Write the failing tests.**

`tests/unit/test_stream_diagnosis_report.py`:

```diff
@@ -27,6 +27,7 @@ from scripts.stream_diagnosis_stats import (
     percentiles,
     shape_counts,
     summarize,
+    tolerated_shape_counts,
 )
 from scripts.stream_diagnosis_variants import StreamVariant
 from scripts.stream_failure_shapes import FailureShape
@@ -620,3 +621,44 @@ def test_two_shapes_at_exactly_half_are_mixed_not_a_dominant_one() -> None:
     assert dominant_shape({"no_tag": 2, "tag_same_line": 2}) is None
     assert dominant_shape({"tag_same_line": 3, "no_tag": 1}) == "tag_same_line"
     assert dominant_shape({"tag_same_line": 1}) == "tag_same_line"
+
+
+@pytest.mark.unit
+def test_a_valid_reply_with_a_failure_shape_is_tolerated_not_a_fallback() -> None:
+    tolerated = _obs(shape=FailureShape.TAG_SAME_LINE)
+
+    assert tolerated.tolerated
+    assert not tolerated.fell_back
+    assert not _ok().tolerated
+    assert not _bad().tolerated
+    assert not _err().tolerated
+
+
+@pytest.mark.unit
+def test_tolerated_shapes_are_counted_apart_from_fallback_shapes() -> None:
+    observations = [
+        _obs(shape=FailureShape.TAG_SAME_LINE),
+        _obs(shape=FailureShape.TAG_SAME_LINE),
+        _obs(shape=FailureShape.NO_TAG),
+        _bad(shape=FailureShape.TAG_WRAPPED),
+        _ok(),
+    ]
+
+    assert tolerated_shape_counts(observations) == {"tag_same_line": 2, "no_tag": 1}
+    assert shape_counts(observations) == {"tag_wrapped": 1}
+    assert summarize(observations).tolerated == 3
+
+
+@pytest.mark.unit
+def test_the_report_lists_the_tolerated_shapes_of_the_baseline() -> None:
+    observations = [
+        *_case(StreamVariant.FULL, "a", 1),
+        _obs(shape=FailureShape.TAG_SAME_LINE, position=2),
+    ]
+
+    report = render_diagnosis_report(observations, _context(), None)
+    section = report.split("## 3. Failure shapes")[1].split("## 4.")[0]
+
+    assert "Tolerated in `full` (context)" in section
+    assert "| tag_same_line | 1 |" in section
+    assert "Tolerated" in report.split("## 1. Fallback by variant and source")[1].split("## 2.")[0]
```


`tests/unit/test_eval_stream_diagnosis.py`:

```diff
@@ -95,6 +95,7 @@ async def test_a_valid_reply_starts_speaking_at_its_first_closed_sentence() -> N
     assert obs.reply_chars == len("EMOTION:joy\nHola. ¿Cómo estás?")
     assert not obs.fell_back
     assert not obs.undue_accept
+    assert not obs.tolerated


 @pytest.mark.unit
@@ -128,12 +129,23 @@ async def test_a_reply_without_the_tag_is_spoken_from_its_first_closed_sentence(

     assert obs.outcome is StreamOutcome.VALID
     assert obs.shape is FailureShape.NO_TAG
+    assert obs.tolerated
     assert not obs.fell_back
     assert obs.speech_start_ms == 20  # the second delta closes the first sentence
     assert obs.end_ms == 30
     assert obs.first_delta_ms == 10


+@pytest.mark.unit
+async def test_a_tag_sharing_its_line_is_tolerated_and_keeps_its_strict_shape() -> None:
+    obs = await _observe(_FakeStream("EMOTION:joy ¡Hola! ", "¿Qué tal?"))
+
+    assert obs.outcome is StreamOutcome.VALID
+    assert obs.shape is FailureShape.TAG_SAME_LINE
+    assert obs.tolerated
+    assert not obs.undue_accept
+
+
 @pytest.mark.unit
 async def test_json_without_a_tag_waits_for_nothing_and_falls_back() -> None:
     obs = await _observe(_FakeStream('{"response": "x"}'))
```


- [ ] **Step 2: Run them and see them fail for the stated reason.**

```powershell
uv run pytest tests/unit/test_stream_diagnosis_report.py tests/unit/test_eval_stream_diagnosis.py -q
```

Expected: FAILED: the report tests error with `ImportError: cannot import name
'tolerated_shape_counts'`; the diagnosis tests fail with `AttributeError: 'Observation' object has
no attribute 'tolerated'`.

- [ ] **Step 3: Implement.**

`scripts/eval_stream_diagnosis.py`:

```diff
@@ -64,6 +64,15 @@ class Observation:
         """Whether production would have spoken the fallback phrase."""
         return self.outcome in (StreamOutcome.INVALID_PROTOCOL, StreamOutcome.EMPTY_STREAM)

+    @property
+    def tolerated(self) -> bool:
+        """Production spoke a reply whose shape the strict 0057 grammar named a failure."""
+        return (
+            self.outcome is StreamOutcome.VALID
+            and self.shape is not None
+            and self.shape is not FailureShape.VALID
+        )
+
     @property
     def undue_accept(self) -> bool:
         """Production spoke a reply that the whole text would have rejected."""
```


`scripts/stream_diagnosis_stats.py`:

```diff
@@ -21,7 +21,7 @@ from scripts.eval_stream_protocol import StreamOutcome
 from scripts.stream_diagnosis_variants import StreamVariant

 if TYPE_CHECKING:
-    from collections.abc import Iterable, Sequence
+    from collections.abc import Callable, Iterable, Sequence

     from scripts.eval_stream_diagnosis import Observation

@@ -53,6 +53,7 @@ class GroupSummary:
     errors: int
     undue_accept: int
     inconsistent: int
+    tolerated: int

     @property
     def graded(self) -> int:
@@ -82,6 +83,7 @@ def summarize(observations: Iterable[Observation]) -> GroupSummary:
         errors=sum(o.outcome is StreamOutcome.ERROR for o in items),
         undue_accept=sum(o.undue_accept for o in items),
         inconsistent=sum(o.fragmentation_consistent is False for o in items),
+        tolerated=sum(o.tolerated for o in items),
     )


@@ -106,15 +108,27 @@ def group_by_variant_and_source(
     )


-def shape_counts(observations: Iterable[Observation]) -> dict[str, int]:
-    """Count the failure shapes of the replies that fell back, most frequent first."""
+def _count_shapes(
+    observations: Iterable[Observation], keep: Callable[[Observation], bool]
+) -> dict[str, int]:
+    """Count the shapes of the observations ``keep`` accepts, most frequent first."""
     counts: dict[str, int] = defaultdict(int)
     for obs in observations:
-        if obs.fell_back and obs.shape is not None:
+        if keep(obs) and obs.shape is not None:
             counts[obs.shape.value] += 1
     return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


+def shape_counts(observations: Iterable[Observation]) -> dict[str, int]:
+    """Count the failure shapes of the replies that fell back, most frequent first."""
+    return _count_shapes(observations, lambda obs: obs.fell_back)
+
+
+def tolerated_shape_counts(observations: Iterable[Observation]) -> dict[str, int]:
+    """Count the strict-0057 shapes of the replies production spoke anyway (ADR 0017)."""
+    return _count_shapes(observations, lambda obs: obs.tolerated)
+
+
 def dominant_shape(counts: dict[str, int]) -> str | None:
     """Return the shape holding at least half of the fallbacks, if exactly one does.

```


`scripts/stream_diagnosis_report.py`:

```diff
@@ -30,6 +30,7 @@ from scripts.stream_diagnosis_stats import (
     percentiles,
     shape_counts,
     summarize,
+    tolerated_shape_counts,
 )
 from scripts.stream_diagnosis_variants import VARIANT_DESCRIPTIONS, StreamVariant

@@ -86,6 +87,7 @@ def _variant_section(observations: Sequence[Observation]) -> list[str]:
                 s.empty_stream,
                 s.errors,
                 _percent(s.fallback_rate),
+                s.tolerated,
                 s.undue_accept,
                 s.inconsistent,
             )
@@ -98,6 +100,7 @@ def _variant_section(observations: Sequence[Observation]) -> list[str]:
         "Empty",
         "Errors",
         "Fallback rate",
+        "Tolerated",
         "Undue accept",
         "Split-dependent",
     )
@@ -175,6 +178,9 @@ def _shape_section(observations: Sequence[Observation]) -> list[str]:
             lines.extend([f"Dominant shape in `full` ({source}): `{dominant}`.", ""])
         else:
             lines.extend([f"No shape holds half of the fallbacks in `full` ({source}).", ""])
+        tolerated = tolerated_shape_counts(o for o in baseline if o.source == source)
+        header = (f"Tolerated in `full` ({source}), by strict-0057 shape", "Count")
+        lines.extend(_table(header, tolerated.items()))
     rows = []
     for (variant, source), items in group_by_variant_and_source(observations).items():
         if variant is StreamVariant.FULL:
```


- [ ] **Step 4: Run, lint, and check the whole command still runs.**

```powershell
uv run pytest tests/unit/test_stream_diagnosis_report.py tests/unit/test_eval_stream_diagnosis.py tests/unit/test_diagnose_stream_protocol.py -q
uv run ruff check scripts/eval_stream_diagnosis.py scripts/stream_diagnosis_stats.py scripts/stream_diagnosis_report.py tests/unit/test_stream_diagnosis_report.py tests/unit/test_eval_stream_diagnosis.py
uv run ruff format --check scripts/eval_stream_diagnosis.py scripts/stream_diagnosis_stats.py scripts/stream_diagnosis_report.py tests/unit/test_stream_diagnosis_report.py tests/unit/test_eval_stream_diagnosis.py
```

Expected: all pass, ruff clean.

- [ ] **Step 5: Commit.**

```powershell
git add scripts/eval_stream_diagnosis.py scripts/stream_diagnosis_stats.py scripts/stream_diagnosis_report.py tests/unit/test_stream_diagnosis_report.py tests/unit/test_eval_stream_diagnosis.py
git commit -m "feat(scripts): count tolerated streaming replies (plan 0058)"
```

## Task 5: The stale header, one `llm_ms`

Closes F-4 and F-7. The first has no behaviour to test (it is a docstring); the second is a
behaviour-preserving extraction whose new helper gets a test first and whose callers are covered by
the existing done-event tests.

**Files:**
- Modify: `server/src/server/llm_streaming.py`, `streaming_render.py`, `streaming.py`
- Test: `tests/unit/test_streaming_render_decisions.py`

**Interfaces:**
- Produces: `streaming_render.llm_elapsed_ms(total_ms: int, stt_ms: int, tts_ms: int) -> int`.

- [ ] **Step 1: Write the failing test.**

`tests/unit/test_streaming_render_decisions.py`:

```diff
@@ -7,6 +7,7 @@ from server.streaming_render import (
     StreamState,
     _consume_body,
     classify_stream_end,
+    llm_elapsed_ms,
 )


@@ -59,3 +60,13 @@ def test_the_end_of_the_stream_is_judged_in_one_place(
     buffer: str, pending: str | None, emotion: str | None, expected: StreamFallbackReason | None
 ) -> None:
     assert classify_stream_end(buffer, _state(pending=pending, emotion=emotion)) is expected
+
+
+@pytest.mark.unit
+@pytest.mark.parametrize(
+    "total_ms, stt_ms, tts_ms, expected", [(100, 30, 20, 50), (100, 0, 0, 100), (10, 30, 20, 0)]
+)
+def test_the_llm_time_is_what_is_left_after_stt_and_tts_and_never_negative(
+    total_ms: int, stt_ms: int, tts_ms: int, expected: int
+) -> None:
+    assert llm_elapsed_ms(total_ms, stt_ms, tts_ms) == expected
```


- [ ] **Step 2: Run it and see it fail.**

```powershell
uv run pytest tests/unit/test_streaming_render_decisions.py -q
```

Expected: FAILED with `ImportError: cannot import name 'llm_elapsed_ms' from 'server.streaming_render'`.

- [ ] **Step 3: Implement.**

`server/src/server/streaming_render.py`:

```diff
@@ -244,6 +244,11 @@ async def _finalize_model_output(buffer: str, state: StreamState) -> AsyncIterat
         yield await synthesize_sentence(tail, state)


+def llm_elapsed_ms(total_ms: int, stt_ms: int, tts_ms: int) -> int:
+    """Return the time not spent in STT or TTS, never negative (rounding can overshoot)."""
+    return max(0, total_ms - stt_ms - tts_ms)
+
+
 def _log_stream_metrics(state: StreamState, total_ms: int) -> None:
     """Log the bounded operational metrics line shared by every stream outcome."""
     logger.info(
@@ -280,7 +285,7 @@ def _done_event(
     if state.audio_chunks < 1:
         raise RuntimeError("Refusing to emit done before any audio chunk was spoken")
     total_ms = _elapsed_ms(request_start)
-    llm_ms = max(0, total_ms - stt_ms - state.tts_ms_total)
+    llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total)
     _log_stream_metrics(state, total_ms)
     done = StreamDoneEvent(
         stt_ms=stt_ms,
```


`server/src/server/streaming.py`:

```diff
@@ -45,6 +45,7 @@ from server.streaming_render import (
     _log_stream_metrics,
     emit_fallback,
     error_event,
+    llm_elapsed_ms,
     synthesize_sentence,
 )
 from server.text_turn import (
@@ -229,7 +230,7 @@ async def stream_pipeline(
     _record_success(prepared, state, schedule_consolidation)

     total_ms = _elapsed_ms(request_start)
-    llm_ms = max(0, total_ms - stt_ms - state.tts_ms_total)
+    llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total)
     _log_pipeline_timing("stream.legacy_text_turn", stt_ms, llm_ms, state.tts_ms_total, total_ms)
     yield _done_event(stt_ms, request_start, state)

```


`server/src/server/llm_streaming.py`:

```diff
@@ -3,16 +3,18 @@
 llm.generate_response() returns a finished (text, emotion) tuple — there is
 no seam to emit per-sentence audio while the model is still generating. The
 JSON schema it forces via Ollama structured outputs ({"response", "emotion"})
-is not streameable either: Ollama withholds structured output until the full
-object is ready, defeating the point of streaming.
-
-This module trades the JSON contract for a streaming-friendly one: the model
-is asked to prefix its plain-text answer with "EMOTION:<emotion>\\n" on its
-own first line, then answer normally. generate_response_stream() yields raw
-text deltas as they arrive; parse_streaming_emotion() extracts the emotion
-tag once the caller has buffered up to the first newline. Kept as a separate
-module (not added to llm.py) so llm.py stays under the file size limit and
-the non-streaming contract used by POST /transcribe is untouched.
+is read whole, once the reply is complete. (Plan 0057 measured that such a
+reply does reach the client spread over time, so Ollama is not known to
+withhold it; this header no longer claims it does.)
+
+This module uses a plain-text contract instead (ADR 0017): the model is asked
+to prefix its answer with "EMOTION:<emotion>" and then answer normally.
+generate_response_stream() yields raw text deltas as they arrive;
+streaming_protocol.parse_streaming_emotion() decides how the reply starts once
+enough has been buffered, and tolerates a tag that shares its line with the
+text or no tag at all. Kept as a separate module (not added to llm.py) so
+llm.py stays under the file size limit and the non-streaming contract used by
+POST /transcribe is untouched.

 Streaming is local-only: it uses the configured Ollama model and yields its
 token deltas to the sentence-streaming pipeline.
@@ -156,8 +158,8 @@ async def generate_response_stream(

     Yields:
         Raw text deltas as Ollama generates them. The first delta(s) carry
-        the ``EMOTION:xxx\\n`` tag inline — use ``parse_streaming_emotion``
-        once enough has been buffered to see the first newline.
+        the ``EMOTION:xxx`` tag inline — decide how the reply starts with
+        ``streaming_protocol.parse_streaming_emotion`` on the buffered text.

     Raises:
         ValueError: If text is empty.
```


- [ ] **Step 4: Run the streaming set and lint.**

```powershell
uv run pytest tests/unit tests/integration -q -k "stream"
uv run ruff check server/src/server/llm_streaming.py server/src/server/streaming_render.py server/src/server/streaming.py tests/unit/test_streaming_render_decisions.py
uv run ruff format --check server/src/server/llm_streaming.py server/src/server/streaming_render.py server/src/server/streaming.py tests/unit/test_streaming_render_decisions.py
```

Expected: all pass, ruff clean.

- [ ] **Step 5: Commit.**

```powershell
git add server/src/server/llm_streaming.py server/src/server/streaming_render.py server/src/server/streaming.py tests/unit/test_streaming_render_decisions.py
git commit -m "refactor(server): one llm_ms and an honest streaming header (plan 0058)"
```

## Task 6: Measurement of the repair (Pipec)

**Files:** `docs/evals/0058-stream-protocol-repair.md`, two raw reports under `docs/evals/`.

Pipec runs these on the branch with Ollama running and the server and robot stopped (about 20
minutes each on the development laptop; 48 units × 5 runs = 240 streams per seed):

```powershell
just diagnose-stream --variants full full_repeat --seed 57 --structured-runs 0 --output docs/evals/0058-stream-repair-seed57.md
just diagnose-stream --variants full full_repeat --seed 59 --structured-runs 0 --output docs/evals/0058-stream-repair-seed59.md
```

- [ ] **Step 1:** Pipec runs both commands and hands over the report paths.
- [ ] **Step 2:** Add a section **After the repair** to `docs/evals/0058-stream-protocol-repair.md`,
  with the same *Conditions* table plus the commit, and for each seed: the fallback rate of `full`
  per source against the baseline of Plan 0057 (43 to 52 % and 1.7 to 3.3 %) and of Task 0; the
  `full_repeat` control; the *Tolerated* counts by shape; undue accepts and split-dependent counts;
  the turns with at least one fallback and the turns that fell back in every run. Read the shape
  `tag_same_line` twice: under the fallbacks it is a tag followed by a word that is not an emotion;
  under *Tolerated* it is a known emotion that is now spoken. Read the gate **by the rules fixed
  above**, in a table (gate, value, met or not). Numbers only.
- [ ] **Step 3:** If a seed lands in the noise band, Pipec repeats **that seed** once with `--runs 10`
  and the repeat decides it; record both.
- [ ] **Step 4:** If any gate is not met, or Pipec stops the plan after reading the tolerated counts,
  stop here: commit the evidence, report, and do not continue to Task 7. The evidence is kept by a
  docs-only branch from `main` that carries just these documents and its own PR; the code branch is
  not merged. Otherwise commit.

```powershell
git add docs/evals/0058-stream-repair-seed57.md docs/evals/0058-stream-repair-seed59.md docs/evals/0058-stream-protocol-repair.md
git commit -m "docs: measure the streaming reply repair (plan 0058)"
```

## Task 7: Documentation truth

Only after the gate of Task 6 is met.

**Files:** `docs/adr/0017-streaming-reply-protocol.md`, `docs/adr/README.md`,
`docs/architecture/current-state.md` and its diagram, `docs/roadmap/cognitive-roadmap.md`,
`docs/plans/README.md`, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, this plan.

- [ ] **Step 1:** ADR 0017: `Status: Accepted (<date>, Pipec)`; fix the table row in
  `docs/adr/README.md`.
- [ ] **Step 2:** `docs/architecture/current-state.md`: the streaming section states the grammar of
  ADR 0017 and the measured rates after the repair, with their limits (one model, the generator and
  not the voice path). Regenerate the architecture diagram with the Archify skill
  (`validate` then `deliver`) so it does not lag the document; the skill is local and git-ignored, so
  this step runs on Pipec's machine.
- [ ] **Step 3:** `docs/roadmap/cognitive-roadmap.md`: the *Streaming-protocol fallback repair* row
  becomes closed with Plan 0058, and CM-2's dependency on it is met; the "What is really missing"
  entry loses the repair.
- [ ] **Step 4:** Move this plan to `docs/plans/completed/`, list it in the board and in both indexes
  as `CLOSED`, leave `NOW` empty and set the next free number (0059).
- [ ] **Step 5:** `uv run ruff format --check` and `uv run ruff check .` (CI formats the Python
  blocks inside the Markdown), `uv run python scripts/check_reserved_terms.py`, `just gate`.
- [ ] **Step 6:** Commit, push, open the PR, squash-merge only with Pipec's confirmation.

```powershell
git commit -m "docs: close plan 0058 and accept ADR 0017"
```

## Non-goals

Each has an owner or is out of the queue:

- The contract text in the prompt, a retry, another model, a schema-constrained stream, removing
  the emotion from the model (all alternatives of ADR 0017, kept open there).
- Rescuing JSON or a code fence with no tag (the classic route owns JSON).
- Speaking or marking a rescued reply differently (no new event, field or emotion; ADR 0017).
- Production telemetry for the fallback or the rescue rate (not in the current queue; the log line
  `rescued_no_tag` is the only trace).
- The real end-to-end rate of a spoken turn (the measurement is the generator only; PC-5 acceptance
  or a telemetry plan owns it).
- Any robot, schema, OpenAPI, setting or dependency change.
- Interrupting the robot while it speaks (barge-in). The loop stays half-duplex; the gap is a row of the
  roadmap's cross-cutting table, unplanned, and this plan neither blocks nor changes it.
- Guarding JSON or a code fence in the **middle** of a reply (ADR 0017 decision 4 is about how a body
  *starts*); and a label that does not use the English keyword (`Emoción: joy`), which is still
  spoken. Both are known limits recorded in the ADR.
- A rescued count in `eval-chat --mode stream`: with the rescue its fallback rate drifts towards 0 % if
  the model stops tagging; the *Tolerated* column of `just diagnose-stream` is the instrument that
  shows it, and the `rescued_no_tag` log line the only trace in production.
- Keeping the emotion tag in the assistant turns of the stored history. The history sent to the model
  holds untagged replies while the prompt demands a tag, which may push a small model to omit it
  (turns with history fell back 43 to 52 % against 1.7 to 3.3 % without, but removing only the memory
  block already cut it to 17 %, so this is a hypothesis, not a finding). It is a variant for a later
  measurement and, like the prompt, outside this plan (D-4).
- Re-grading the Plan 0057 reports (they hold no reply text, so they cannot be re-read with another
  grammar; the comparison is by running the instrument again).

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

plus `uv run ruff check` and `uv run ruff format --check` over the explicit paths of every `scripts/`
file touched (they are excluded from `just lint`).

## Completion criteria

1. Tasks 1 to 5 each in one commit, each test observed RED for the stated reason before its code.
2. `just gate` green; the test count and coverage recorded against the baseline of `main`.
3. The generated OpenAPI is byte-identical and the robot untouched.
4. Task 6's gate met in both seeds by the rules fixed above, recorded in
   `docs/evals/0058-stream-protocol-repair.md`.
5. ADR 0017 `Accepted`; `current-state.md`, its diagram, the roadmap, both plan indexes and the board
   agree.
6. Pipec's acceptance on real hardware (below) recorded, or each unrun case named.

## Real runtime acceptance

Pipec starts the server and the robot himself (`just run-server`, `just run-robot`, streaming on) and
runs, in one session:

1. **Small talk, five turns,** including a greeting and a question about the weather: no fallback
   phrase is spoken.
2. **A turn that carries memory:** state a fact, then ask about it two turns later: the answer is
   spoken, not the fallback.
3. **The server console:** the turns end `outcome=ok` or `outcome=rescued_no_tag`; note how many of
   each, and whether any is `protocol_fallback`.
4. **No tag or label is spoken aloud** in any turn.
5. **The robot** plays emotion and audio as before (nothing changed on its side).

Record outcomes only: which cases ran, which did not, and the counts of case 3.

## Rollback

Each task is one commit; revert them in reverse order. Nothing under `server/src` merges unless
Task 6 met its gate. The wire, the schema, the robot and the settings are untouched, so no data or
client migration exists. If the gate fails, the code branch is not merged, ADR 0017 stays `Proposed`,
and the measurement evidence is preserved by a docs-only PR (Task 6, step 4).

## Execution record

Branch `feat/0058-stream-protocol-repair`, from `main` at `eaabbe1`. One plain branch, no worktree,
no subagent; the final review was a self-review by the executor.

| Task | Commit | RED observed (reason) | GREEN |
|---:|---|---|---|
| 0 | `90bf4ec` | n/a (Pipec's run; baseline context 58.33 %, public 0.00 %, R-5 spread 15.0 points) | n/a |
| 1 | `026323f` | 24 failing: `AttributeError` for `is_body_start_undecided`, and `VALID` where `INVALID_PROTOCOL` expected | 465 (stream selection) |
| 2 | `d166da4` | 15 failing + 1 collection `ImportError` (`StreamProtocolError`, `classify_stream_end`); the second-tag-in-a-later-delta case failed because the sentence was spoken | 496 |
| 3 | `ae587a0` | 18 failing + 1 collection `ImportError` (`Preamble`): refused tolerated replies, no `rescued_no_tag` log, empty tolerated-shape set | 568, mypy and pyright clean, `test_api_contract` 9 passed |
| 4 | `9eb72ed` | collection `ImportError` (`tolerated_shape_counts`), 3 `AttributeError` (`tolerated`) | 85 |
| 5 | `d3d4c23` | collection `ImportError` (`llm_elapsed_ms`) | 575 (stream selection) |

`just gate` after Task 5: 2229 passed, ruff, mypy, pyright and `check_reserved_terms` clean, audit
clean. `robot/` and `docs/adr/` untouched; the generated OpenAPI is unchanged (contract test green).
Tasks 6 and 7 are pending (Pipec's measurement, then the documentation).

## Closure

*(Filled in when the plan closes: PR number and merge commit, date, and what remains open.)*
