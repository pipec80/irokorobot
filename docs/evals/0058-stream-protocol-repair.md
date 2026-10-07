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
