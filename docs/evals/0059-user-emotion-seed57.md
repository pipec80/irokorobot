# Streaming protocol diagnosis (Plan 0057)

- model: qwen2.5:3b (digest `357c53fb659c`)
- ollama version: 0.34.4
- generation options: server defaults (production passes none)
- runs per turn and variant: 5; shuffle seed: 57
- observations (all variants): 240 (graded 240, provider errors 0)
- baseline (`full`) fallback rate: context 0.00 %, public 0.00 %
- replies spoken that the whole text rejects (all variants): 0

## Variants

| Variant | What it changes |
|---|---|
| full | the turn exactly as `just eval-chat --mode stream` sends it (the baseline) |
| full_repeat | `full` again, interleaved: the noise of repeating one condition |
| no_context | the memory block removed; person and history kept |
| no_person | the active person removed; memory and history kept |
| no_history | the history removed; memory and person kept |
| question_only | memory, person and history all removed (several factors at once) |
| contract_first | the output contract moved to the start of the system prompt |
| public_with_context | a public question with a golden memory block borrowed in rotation |

## 1. Fallback by variant and source

| Variant | Source | Valid | Invalid | Empty | Errors | Fallback rate | Undue accept | Split-dependent |
|---|---|---|---|---|---|---|---|---|
| full | context | 60 | 0 | 0 | 0 | 0.00 % | 0 | 0 |
| full | public | 60 | 0 | 0 | 0 | 0.00 % | 0 | 0 |
| full_repeat | context | 60 | 0 | 0 | 0 | 0.00 % | 0 | 0 |
| full_repeat | public | 60 | 0 | 0 | 0 | 0.00 % | 0 | 0 |

## 2. Interventions against `full` (exploratory)

Each row compares one intervention with `full` on the turns where `full`, the variant and the `full_repeat` control all have the 5 expected runs graded; a turn missing any of them is excluded, never compared on a different sample, and a row with no complete control is `incomplete`, never a signal. The noise of a row is the mean absolute difference, turn by turn, between `full` and `full_repeat` on that row's own turns (opposite swings never cancel). A signal is a change of at least 15 points that also exceeds that noise. It is an exploratory signal, not a cause: confirm with another seed before attributing one.

| Variant | Paired | Excluded | `full` | Variant | Change (pp) | Noise (pp) | Reading |
|---|---|---|---|---|---|---|---|
| full_repeat | 24 | 0 | 0/120 (0.00 %) | 0/120 (0.00 %) | +0.0 | n/a | control |

`question_only` runs only on turns that have a person or a history; elsewhere it sends what `no_context` sends and is not repeated.

## 3. Failure shapes

| Shape in `full` (context) | Count | Share |
|---|---|---|

No fallbacks in `full` (context).

| Shape in `full` (public) | Count | Share |
|---|---|---|

No fallbacks in `full` (public).

Shapes of each intervention, apart (never merged into the baseline):

| Variant | Source | Shape | Count |
|---|---|---|---|

## 4. Turns under `full`

| Turn | Fallbacks | Provider errors | Graded | Expected |
|---|---|---|---|---|
| absent_address | 0 | 0 | 5 | 5 |
| absent_pet | 0 | 0 | 5 | 5 |
| corrected_age_active_fact | 0 | 0 | 5 | 5 |
| corrected_species_active_fact | 0 | 0 | 5 | 5 |
| identified_person_second_person | 0 | 0 | 5 | 5 |
| multiple_active_facts | 0 | 0 | 5 | 5 |
| old_history_vs_active_fact | 0 | 0 | 5 | 5 |
| persisted_context_after_restart | 0 | 0 | 5 | 5 |
| public_1 | 0 | 0 | 5 | 5 |
| public_10 | 0 | 0 | 5 | 5 |
| public_11 | 0 | 0 | 5 | 5 |
| public_12 | 0 | 0 | 5 | 5 |
| public_2 | 0 | 0 | 5 | 5 |
| public_3 | 0 | 0 | 5 | 5 |
| public_4 | 0 | 0 | 5 | 5 |
| public_5 | 0 | 0 | 5 | 5 |
| public_6 | 0 | 0 | 5 | 5 |
| public_7 | 0 | 0 | 5 | 5 |
| public_8 | 0 | 0 | 5 | 5 |
| public_9 | 0 | 0 | 5 | 5 |
| resolved_face_enrollment | 0 | 0 | 5 | 5 |
| resolved_face_recognition | 0 | 0 | 5 | 5 |
| semantic_distractor_ignored | 0 | 0 | 5 | 5 |
| two_children_names | 0 | 0 | 5 | 5 |

Turns with at least one fallback: 0 of 24; that fell back in every expected run: 0; incomplete turns: 0.

## 5. Timing (ms)

| Variant | Outcome | n | First delta | Speech start | End |
|---|---|---|---|---|---|
| full | valid | 120 | 942 / 1515 | 2012 / 4192 | 3355 / 8410 |
| full_repeat | valid | 120 | 948 / 1431 | 1931 / 4111 | 3362 / 7326 |

p50 / p95 by the nearest-rank method. Speech start is when production would hand its first sentence, or the fallback, to TTS (TTS time excluded).

## 6. Execution order

Quarters of the shuffled execution order, all variants together: it describes the experiment, not the baseline.

| Quarter | Fallback rate |
|---|---|
| Q1 | 0.00 % |
| Q2 | 0.00 % |
| Q3 | 0.00 % |
| Q4 | 0.00 % |

No order effect above the rule.

## 7. Prompt size (characters sent)

| Variant | Min | Mean | Max |
|---|---|---|---|
| full | 2734 | 2796 | 3085 |
| full_repeat | 2734 | 2796 | 3085 |

## 8. Stream arrival probe

Not run.
