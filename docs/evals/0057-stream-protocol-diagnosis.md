# Streaming-protocol diagnosis (Plan 0057, Task 8)

> **Status:** Historical measurement, recorded 2026-10-06. Numbers only: no reply,
> no transcript and no household name appear here. The reading rules (R-1 to R-7)
> were written in [Plan 0057](../plans/completed/0057-stream-protocol-diagnosis.md#rules-fixed-before-the-run)
> **before** the runs and were not changed afterwards. Every intervention reading is
> *exploratory*: it is an input to a repair plan, not a cause.

## Conditions

| Item | Value |
|---|---|
| Date | 2026-10-06 |
| Commit | both runs were made with the code at `0bf77d5` (the end of Task 7). The later commit `b0d957b` fixed the review findings (a threshold met exactly was missed by float error, an intervention that made things worse is now labelled `opposite direction`, a tie between two shapes is read as mixed, a failing stream close no longer ends a run); none of them changes a number recorded here, and `server/` is untouched |
| Machine | non-dedicated development laptop (Docker and development tools running alongside); Ollama running, server and robot stopped |
| Model | `qwen2.5:3b`, digest `357c53fb659c` |
| Ollama | 0.34.4 |
| Generation options | server defaults (production passes none) |
| Who ran it | Pipec, locally; the executor recorded only the printed numbers |
| Seed | fixes only the shuffled execution order; Ollama's sampling is not seeded, so a run cannot be reproduced bit for bit |
| Instrument | `just diagnose-stream`: the **generator** (`generate_response_stream`) over the golden and public turns, not the full microphone → server → audio path |

Raw reports: [smoke](0057-stream-diagnosis-smoke.md) (1 run per turn, instrument
check only), [run 1](0057-stream-diagnosis-run1.md) (seed 57, 5 runs, 500 streams,
0 provider errors) and [run 2](0057-stream-diagnosis-run2.md) (seed 58, confirmation).

## Run 1 — seed 57, `just diagnose-stream --runs 5`

100 units × 5 runs = 500 streams, all graded.

| Variant | Source | Valid | Invalid | Fallback rate |
|---|---|---:|---:|---:|
| `full` (baseline) | context (12 turns, 60) | 29 | 31 | **51.67 %** |
| `full` (baseline) | public (12 turns, 60) | 59 | 1 | **1.67 %** |
| `full_repeat` (noise control) | context | 29 | 31 | 51.67 % |
| `full_repeat` | public | 58 | 2 | 3.33 % |

### R-1 — the fragmentation defect on live traffic

0 undue accepts and 0 split-dependent replies in 500. **Not observed on real model
output with this model and prompt.** Rule R-1 sends the defect to the repair plan
whatever the number, and the unit test `test_stream_fragmentation.py` keeps pinning it:
this measurement neither confirms nor retires it.

### R-2 — dominant failure shape in `full`

| Source | Fallbacks | Shapes | Reading |
|---|---:|---|---|
| context | 31 | `tag_same_line` 30 (96.77 %), `no_tag` 1 | **dominant: `tag_same_line`** |
| public | 1 | `tag_same_line` 1 | one fallback only: not read |

(The raw report prints "dominant" for a single fallback; this record does not read it.)

`tag_same_line` is a reply whose `EMOTION:<x>` tag shares its line with the text. The
candidate the plan's table points to is a tolerant tag grammar (specified with valid and
invalid examples). It is a pointer for the repair plan, not a decision (D-6).

### R-3 — interventions against `full` (exploratory)

Compared on the turns where `full`, the variant and `full_repeat` have every run graded.
Noise: mean absolute difference per turn between `full` and `full_repeat` on those turns.

| Variant | Paired turns | `full` | Variant | Change (pp) | Noise (pp) | Reading |
|---|---:|---:|---:|---:|---:|---|
| `no_context` | 12 | 31/60 | 10/60 | +35.0 | 16.7 | exploratory signal |
| `question_only` | 2 | 9/10 | 0/10 | +90.0 | 10.0 | exploratory signal (2 turns) |
| `no_person` | 1 | 4/5 | 3/5 | +20.0 | 0.0 | hint only (1 turn) |
| `no_history` | 1 | 5/5 | 3/5 | +40.0 | 20.0 | hint only (1 turn) |
| `public_with_context` | 12 | 1/60 | 6/60 | +8.3 | 1.7 | no signal (below 15 pp) |
| `contract_first` | 24 | 32/120 | 120/120 | −73.3 | 9.2 | opposite direction (it made things worse; the raw report, made before that label existed, prints `no signal`) |

`contract_first` fell back in all 120 runs, every one `no_tag`, in context and public
turns alike. The unit test of Task 3 pins that its prompt carries the same content as
production's with only the contract moved, so this is not an instrument artefact; the
mechanism is not measured here, and one seed is all there is. It is the largest effect of the
whole experiment and it points away from moving the contract to the start of the prompt.

The raw reports label every row with a signal "exploratory signal"; this record reads
`no_person` and `no_history` as hints because each rests on one turn (the R-3 rule says to).

### R-4 — concentration in `full`

9 of 24 turns had at least one fallback (8 of the 12 context turns, 1 public turn);
**2 turns fell back in every one of their 5 runs**; 0 incomplete turns. The failures are
spread over most context turns, not concentrated in two or three.

### R-5 — execution order

Fallback rate by quarter of the shuffled order, all variants together: 41.6 %, 42.4 %,
44.0 %, 37.6 %. The spread is 6.4 points, under the 15-point rule: the rule did not fire in this
run (run 2 below fired it). Each quarter mixes variants with very different rates (for example
`contract_first` is a quarter of the streams at 100 %), so an order effect is neither shown nor
excluded.

### R-6 — do the chunks of a schema-constrained reply arrive spread over time

| Probe | Complete runs | Paced gaps | Verdict |
|---|---:|---|---|
| schema-constrained (`format`) | 5 of 5 | every gap 20 ms or more in each run (97 to 125 chunks) | **incremental** |
| plain-text control | 5 of 5 | every gap 20 ms or more in each run (98 to 111 chunks) | incremental |

The schema-constrained reply reached this client spread over time, which is compatible
with incremental generation and is evidence against the `llm_streaming.py` header's claim
that Ollama withholds schema-constrained output until the end, **for this Ollama version
and model**. A client cannot see when generation ended, so this is not a proof of how
Ollama works internally. The probe uses one fixed synthetic question with a minimal system
prompt (not production's prompts) and 5 runs.

### R-7 — cost of a fallback (`full`, time at which production would hand its first sentence, or the fallback, to TTS; TTS excluded)

| Outcome | n | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|
| valid reply, first sentence | 88 | 4157 | 8452 |
| fallback | 32 | 4315 | 15049 |

No threshold. The median fallback is not faster than a good reply: 4315 against 4157 ms in run 1
and 3978 against 2848 ms in run 2 (the `full_repeat` control: 4323 against 3269 and 3894 against
2919), and the p95 is longer in both runs. It ends in the fixed phrase.

## Run 2 — seed 58, confirmation of the R-3 signals

`just diagnose-stream --variants full full_repeat no_context no_person no_history question_only --seed 58 --structured-runs 0`:
64 units × 5 runs = 320 streams, all graded, 0 provider errors. The two probes were
not repeated (R-6 was clear in run 1).

| Variant | Source | Valid | Invalid | Fallback rate |
|---|---|---:|---:|---:|
| `full` | context | 34 | 26 | 43.33 % |
| `full` | public | 58 | 2 | 3.33 % |
| `full_repeat` | context | 29 | 31 | 51.67 % |
| `full_repeat` | public | 58 | 2 | 3.33 % |

| Variant | Paired turns | `full` | Variant | Change (pp) | Noise (pp) | Reading | Run 1 |
|---|---:|---:|---:|---:|---:|---|---|
| `no_context` | 12 | 26/60 | 10/60 | +26.7 | 15.0 | exploratory signal | signal (+35.0) |
| `question_only` | 2 | 7/10 | 1/10 | +60.0 | 10.0 | exploratory signal | signal (+90.0) |
| `no_history` | 1 | 4/5 | 1/5 | +60.0 | 0.0 | exploratory signal (1 turn) | signal (+40.0) |
| `no_person` | 1 | 3/5 | 4/5 | −20.0 | 20.0 | no signal | signal (+20.0) |

- **R-1:** 0 undue accepts and 0 split-dependent replies again (820 streams over both runs).
- **R-2:** `tag_same_line` is again the dominant shape in `full` with context: 22 of 26
  fallbacks (84.62 %), then `no_tag` 3 and `text_before_tag` 1. In public turns `tag_same_line`
  accounts for both of the 2 fallbacks.
- **R-4:** 12 of 24 turns had at least one fallback (10 of the 12 context turns); 2 turns fell
  back in every run, and they are not the same two as in run 1 (one is shared:
  `corrected_age_active_fact`); 0 incomplete turns.
- **R-5 fired in this run:** the quarters of the execution order were 23.75 %, 21.25 %, 11.25 %
  and 40.00 %, a spread of 28.8 points (run 1: 6.4). The plan allows one repeat with seed 58 and
  this run was it, so it is recorded and neither run decides alone. The report cannot say why:
  each quarter holds 80 streams of mixed variants (fallback rates by variant run from 10 % to
  80 % in this run), so a
  different mix per quarter moves the rate on its own, and the counts-only report does not
  separate that from a real order effect. **Unresolved.** R-1 and R-6 do not depend on the order
  and R-2 held in both seeds, but the R-3 confirmations come from the run that tripped the rule,
  so they carry that caveat.
- **R-7 (`full`):** valid first sentence p50 / p95 2848 / 5885 ms (n 92); fallback 3978 / 7915 ms
  (n 28), against 4157 / 8452 and 4315 / 15049 in run 1.

## Readings after both runs

Sign convention of the "Change (pp)" columns, as in the raw reports: positive means the intervention
**lowered** the fallback rate (`full` minus the variant); for `public_with_context`, which adds a
factor, positive means the rate **rose**.

| Rule | Reading | Status |
|---|---|---|
| R-1 | no reply in 820 was judged differently under any token split (0 undue accepts, 0 split-dependent); the shapes that could trigger the defect (a second tag or a code fence after the tag) did not occur | not observed live; it stays a correctness defect pinned by test and enters the repair plan as its first task |
| R-2 | `tag_same_line` dominant in `full` with context in both seeds (96.77 % and 84.62 % of fallbacks) | consistent across two seeds; candidate: tolerant tag grammar |
| R-3 `no_context` | removing the memory block lowered the fallback rate on the same 12 turns by +35.0 then +26.7 points, above the noise of those turns (16.7, 15.0) | **confirmed** by a second seed (the run that tripped R-5), as an input to the repair plan, not as a cause |
| R-3 `question_only` | +90.0 then +60.0 points on 2 turns | repeated on 2 turns; the variant removes three factors at once, so it does not isolate any |
| R-3 `no_history` | +40.0 then +60.0 points on 1 turn | repeated, but 1 turn: a hint |
| R-3 `no_person` | +20.0 then −20.0 | **not confirmed**; no reading |
| R-3 `public_with_context` | +8.3 points (the rate rose from 1.7 % to 10.0 %), below 15 | no signal (run 1 only); see the paragraph below |
| R-3 `contract_first` | −73.3 points (the rate rose to 100 %), run 1 only | opposite direction; one seed |
| R-4 | failures spread over most context turns in both runs | consistent in breadth; which turns fail the most changes between seeds |
| R-5 | the rule did not fire in run 1 (6.4 points); it fired in run 2 (28.8 points) | unresolved; see run 2 |
| R-6 | incremental, 5 of 5, with the plain-text control also incremental | evidence against the header's claim for this Ollama, model and probe prompt; not proof of Ollama's internals |
| R-7 | the median fallback is not faster than a good reply (4.3 and 4.0 s against 4.2 and 2.8 s in `full`, runs 1 and 2) and the p95 is longer in both | recorded |

What this means for the repair plan, and what it does not. In this set, removing the memory block
lowered the fallback rate on the same 12 turns (confirmed by a second seed, exploratory), `no_history`
points the same way on one turn, `no_person` was not confirmed, and the factors are **not ranked**:
the per-factor denominators are too small and `question_only` removes three at once. The failure is
mostly a tag that shares its line with the text. This does **not** say the memory content causes it:
adding the same blocks to public questions raised the rate only from 1.7 % to 10.0 %, far below the
51.67 % of the golden turns, which points at the question itself or at an interaction, and the block
also changes the prompt's content and length. Moving the contract to the start of the prompt made the
tag disappear in 120 of 120 runs (one seed). The repairs the plan lists (a tolerant tag grammar, a
retry, rescuing plain text, another model, a schema-constrained stream) are still to be chosen and
tested by the repair plan (D-6), which also owns correcting the stale header of `llm_streaming.py`
(it claims Ollama withholds structured output; D-1 forbids editing it here).

## Limitations

- The generator, not the full voice path: nothing here is the real rate of a spoken turn.
- One model (`qwen2.5:3b`), one Ollama version, one synthetic set.
- The golden turns are 12 cases repeated five times, not 60 independent conversations;
  500 streams give a wide interval. Per-turn results range from 0 to 5 of 5 and change partly
  between seeds (for example `resolved_face_enrollment` 4 of 5 then 1 of 5); only some turns repeat
  (`corrected_age_active_fact` fell back 5 and 5 times).
- `no_person` and `no_history` each rest on one turn, and `question_only` on two:
  one fallback moves them by 20 points at least. Read them as hints.
- The rules were agreed in advance and are not proof; a repair plan must still choose
  and test its own change.
- The machine is not dedicated, so the timings describe this laptop, and the duration of the
  runs was not recorded.
- The R-6 probe uses one synthetic question with a minimal system prompt, not production's prompts.
