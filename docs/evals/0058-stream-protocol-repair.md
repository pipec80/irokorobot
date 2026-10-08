# Streaming-protocol repair (Plan 0058)

> **Status:** In progress. Numbers only: no reply, no transcript and no household name appear
> here. The gate and the reading rules are fixed in
> [Plan 0058](../plans/open/0058-stream-protocol-repair.md#rules-fixed-before-the-run) **before**
> the runs and are not changed afterwards.

## Conditions

| Item | Value |
|---|---|
| Date | 2026-10-07 |
| Commit | `eaabbe1` (`main`; the branch of this baseline holds documents only, so the code is that of `main`) |
| Machine | non-dedicated development laptop (Docker and development tools running alongside); Ollama running, server and robot stopped |
| Model | `qwen2.5:3b`, digest `357c53fb659c` |
| Ollama | 0.34.4 |
| Generation options | server defaults (production passes none) |
| Who ran it | Pipec, locally; the executor recorded only the printed numbers |
| Seed | 59 (fixes only the shuffled execution order; Ollama's sampling is not seeded) |
| Instrument | `just diagnose-stream`: the **generator** (`generate_response_stream`) over the golden and public turns, not the full microphone → server → audio path |

Raw report: [run 3](0057-stream-diagnosis-run3.md) (seed 59, 5 runs, 6 variants, 320 streams,
0 provider errors).

## Baseline, seed 59 (Task 0, unchanged code)

### Fallback rate of `full`

| Source | Valid | Invalid | Fallback rate | Plan 0057 (seeds 57, 58) |
|---|---:|---:|---:|---|
| context (12 turns, 60 streams) | 25 | 35 | **58.33 %** | 43 to 52 % |
| public (12 turns, 60 streams) | 60 | 0 | **0.00 %** | 1.7 to 3.3 % |

`full_repeat` (noise control): context 61.67 % (37 of 60), public 1.67 % (1 of 60). 0 undue
accepts and 0 split-dependent replies in 320 streams.

The premise of the plan reproduces: the context baseline is above 5 % (it is above the 43 to 52 %
range of Plan 0057), so there is something to repair.

### Dominant shape in `full` (context)

| Shape | Count | Share |
|---|---:|---:|
| `tag_same_line` | 31 | 88.57 % |
| `no_tag` | 3 | 8.57 % |
| `text_before_tag` | 1 | 2.86 % |

Dominant: `tag_same_line`. Public: no fallbacks.

### Turns under `full`

12 of 24 turns had at least one fallback (all 12 are context turns); 3 turns fell back in every
run (`identified_person_second_person`, `multiple_active_facts`, `old_history_vs_active_fact`).

### R-5 — execution-order effect

| Quarter | Fallback rate |
|---|---:|
| Q1 | 22.50 % |
| Q2 | 37.50 % |
| Q3 | 22.50 % |
| Q4 | 28.75 % |

Spread: **15.0 points** (37.50 − 22.50). By the rule fixed in the plan (15 points or more), the
order effect is read as **real**: Plan 0057's R-3 confirmations need re-reading with that in mind.
It informs the record; it gates nothing.

## After the repair, seed 57 (Task 6, first seed)

> **Result: the gate is NOT met.** By the rule fixed in the plan, the plan stops here: seed 59 was
> not run (the gate needs both seeds, and one failed outright), ADR 0017 stays `Proposed`, the code
> branch is not merged and Task 7 is not done.

### Conditions

Same as the table above, except: date 2026-10-07, commit `d3d4c23` (the end of Task 5; the later
`41be4dc` only edits the plan's execution log), seed 57, `--variants full full_repeat`, 5 runs,
48 units x 5 runs = 240 streams, 0 provider errors. Raw report:
[seed 57](0058-stream-repair-seed57.md).

### Fallback rate of `full` against the baselines

| Source | Plan 0057, seed 57 (before) | Task 0, seed 59 (before) | After, seed 57 | Fallbacks |
|---|---:|---:|---:|---|
| context (60 streams) | 51.67 % | 58.33 % | **35.00 %** | 21 of 60 |
| public (60 streams) | 1.67 % | 0.00 % | **0.00 %** | 0 of 60 |

`full_repeat` (noise control): context 30.00 % (18 of 60), public 3.33 % (2 of 60). Over all 24
turns the control agrees with `full` (+0.8 points). 0 undue accepts and 0 split-dependent replies
in 240 streams. The execution-order spread is under the rule (quarters 18.33, 21.67, 11.67 and
16.67 %).

### Tolerated and remaining shapes in `full` (context)

| Reading | Shape (strict 0057) | Count |
|---|---|---:|
| Tolerated (spoken) | `tag_same_line` | 12 |
| Tolerated (spoken) | `no_tag` | 1 |
| Still a fallback | `tag_same_line` | 20 |
| Still a fallback | `text_before_tag` | 1 |

No tolerated `other_label` reply. Of the 32 context replies that carried a tag sharing its line
with the text, 12 are now spoken and 20 still fall back: the repair speaks the known-emotion ones,
and the remaining ones are those the protocol refuses on purpose (a word after the tag that is not
a known emotion, or glued to punctuation). Public turns: nothing tolerated, nothing fell back.

Turns under `full`: 7 of 24 have at least one fallback (before, seed 59: 12 of 24), 1 fell back in
every run (`multiple_active_facts`, 5 of 5), and 3 more have 3 or 4 of 5 fallbacks.

### Gate

| Gate (rules fixed before the run) | Value | Met |
|---|---|---|
| `full`, context, seed 57: at most 3 fallbacks of 60 (5.00 %) | 21 of 60 (35.00 %) | no |
| `full`, public, seed 57: at most 3 fallbacks of 60 | 0 of 60 | yes |
| Undue accepts | 0 | yes |
| Split-dependent replies | 0 | yes |
| Noise band (exactly 4 of 60) | 21 of 60: 5 or more fails outright, no repeat | n/a |
| Seed 59 | not run | n/a |

The repair works in the direction intended (context 51.67 % to 35.00 % in seed 57, and the
tolerated replies are spoken, none of them a label) but it is far from 5 %. The tag sharing its line
still accounts for nearly every remaining fallback. What the next plan decides (not this one): what to
do with a same-line tag whose next word is not an emotion (the ADR refuses it on purpose so that a
mutilated sentence is never spoken), or the alternatives the ADR keeps open.
