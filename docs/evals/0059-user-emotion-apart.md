# The user's emotion decided apart (Plan 0059)

> **Status:** Measured 2026-10-08. Numbers only: no reply, no transcript and no household name
> appear here. The gate and the reading rules were fixed in
> [Plan 0059](../plans/completed/0059-user-emotion-apart.md#rules-fixed-before-the-run) **before**
> the runs and were not changed afterwards.

## Conditions

| Item | Value |
|---|---|
| Date | 2026-10-08 |
| Commit | `228b146` (the final code of the plan; `git log` of the branch `feat/0059-user-emotion-apart`) |
| Machine | non-dedicated development laptop; Ollama running, server and robot stopped; **nothing else ran during the two final runs** (no tests, no agents) |
| Model | `qwen2.5:3b`, digest `357c53fb659c` |
| Ollama | 0.34.4 |
| Generation options | server defaults (production passes none) |
| Who ran it | Pipec, locally, one run after the other; the executor recorded only the printed numbers |
| Seeds | 57 and 59 (a seed fixes only the shuffled execution order; Ollama's sampling is not seeded) |
| Instrument | `just diagnose-stream --variants full full_repeat --structured-runs 0`: the **generator** (`generate_response_stream`) over the golden and public turns, not the full microphone → server → audio path |

Raw reports: [seed 57](0059-user-emotion-seed57.md), [seed 59](0059-user-emotion-seed59.md), and
[a first run of seed 57 on `9739ea7`](0059-user-emotion-seed57-preliminary-9739ea7.md), made before
the independent audit's fixes (kept as a record; it overlapped the auditors' test runs, so its
timings are not valid). Each final run is 48 units × 5 runs = 240 streams, all graded, 0 provider
errors.

## Fallback rate of `full`

| Source | Plan 0057 (before) | Plan 0058 (tolerant grammar) | Seed 57 | Seed 59 |
|---|---:|---:|---:|---:|
| context (12 turns × 5 runs = 60) | 43 to 52 % (seed 59 baseline: 58.33 %) | 35.00 % (21 of 60, seed 57) | **0 of 60** | **0 of 60** |
| public (12 turns × 5 runs = 60) | 1.7 to 3.3 % | 0.00 % | **0 of 60** | **0 of 60** |

`full_repeat` (noise control): 0 of 60 in both sources of both seeds. 0 undue accepts, 0
split-dependent replies, 0 turns with a fallback (of 24), no order effect (every quarter 0.00 %).

## Gate (D-5), by the rules fixed before the run

| Gate | Seed 57 | Seed 59 | Met |
|---|---|---|---|
| `full`, context: at most 3 fallbacks of 60 (5.00 %) | 0 of 60 | 0 of 60 | yes |
| `full`, public: at most 3 fallbacks of 60 | 0 of 60 | 0 of 60 | yes |
| 0 undue accepts | 0 | 0 | yes |
| 0 split-dependent replies | 0 | 0 | yes |
| Noise band (exactly 4 of 60) | not needed | not needed | n/a |

**The gate is met in both seeds.** Reported, not gated: no stream of `full` or `full_repeat`
started with a tag anyway (it would have been a fallback), so the share of "tag anyway" replies is
0 of 480 in this instrument.

## Time to first speech (reported, not gated)

Valid replies, p50 / p95 in ms. Every reply is valid now, so the comparison with Plan 0058
(where only the replies that had survived the tag grammar counted) is indicative, not exact.

| Run | First delta | Speech start | End |
|---|---:|---:|---:|
| Plan 0058, seed 57 (replies that passed) | 1167 / 1626 | 2739 / 7131 | 3916 / 11746 |
| Seed 57, final code | 942 / 1515 | 2012 / 4192 | 3355 / 8410 |
| Seed 59, final code | 1125 / 1909 | 3301 / 6933 | 5894 / 12031 |

The two seeds differ by more than the change does (speech start p50 2012 against 3301 ms on the
same code), so this measurement shows that the first speech did not get slower and it does **not**
prove a speed-up; the machine is not dedicated. The preliminary run of seed 57, which overlapped
the auditors' test runs, gave 5176 ms: load alone moves the figure that much.

## What this measurement does not say

- It runs the generator over 24 invented turns with one model (`qwen2.5:3b`); it is not the rate
  of a spoken turn on the real path (STT, controller, TTS, robot).
- The prompt now asks for plain text and a reply that *starts* with a tag still falls back
  (D-6). None did in 480 streams, but another model or another prompt could change that; the
  `tag_anyway` figure must be read again after any prompt or model change.
- The user's emotion is decided by a precision-first rule table: most turns are `neutral`. The
  tone-adaptation window therefore changes less often than a model that labelled freely would
  (see ADR 0018, *Consequences*). The classifier was measured on a labelled set of invented
  sentences (see the plan), not on real speech.
- The real path is covered only by the acceptance below.

## Real-hardware acceptance (Pipec, 2026-10-08)

Development laptop, microphone, Piper, Ollama `qwen2.5:3b`, `ROBOT_STREAMING=true`, server and robot started by
Pipec; commit `228b146`. Outcomes only.

| Case | Result |
|---|---|
| 1. Small talk, no fallback phrase | Pass: 13 turns over two sessions, every one `outcome=ok`, no `protocol_fallback` |
| 2. A turn that carries memory | Not exercisable: every turn logs `Turn memory: skipped (no verified identity)`; production puts no history or memory in the prompt before CM-2 |
| 3. The emotion event | Pass: exactly one `emotion` before the first audio each time; `neutral` in 11 turns, `joy` in one, `sadness` for a sentence in which the user said they were a little sad |
| 4. No tag or label spoken aloud | Pass for the three turns whose text was logged (`LOG_CONVERSATION_TEXT=true`); the first ten turns were not logged as text and nothing odd was reported |
| 5. The robot behaves as before | Pass: emotion then audio, sentence by sentence |

**Finding, open:** in one turn the model answered in French although the transcript was Spanish. The
benchmark does not measure the language of a reply and no streaming contract tells the model to answer in
Spanish, so it is not known whether it predates this plan. It is recorded as open work in the plan's
*Closure*; it was not fixed here because it would change the prompt that was measured.
