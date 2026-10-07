# Streaming protocol diagnosis (Plan 0057)

- model: qwen2.5:3b (digest `357c53fb659c`)
- ollama version: 0.34.4
- generation options: server defaults (production passes none)
- runs per turn and variant: 5; shuffle seed: 58
- observations (all variants): 320 (graded 320, provider errors 0)
- baseline (`full`) fallback rate: context 43.33 %, public 3.33 %
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
| full | context | 34 | 26 | 0 | 0 | 43.33 % | 0 | 0 |
| full | public | 58 | 2 | 0 | 0 | 3.33 % | 0 | 0 |
| full_repeat | context | 29 | 31 | 0 | 0 | 51.67 % | 0 | 0 |
| full_repeat | public | 58 | 2 | 0 | 0 | 3.33 % | 0 | 0 |
| no_context | context | 50 | 10 | 0 | 0 | 16.67 % | 0 | 0 |
| no_person | context | 1 | 4 | 0 | 0 | 80.00 % | 0 | 0 |
| no_history | context | 4 | 1 | 0 | 0 | 20.00 % | 0 | 0 |
| question_only | context | 9 | 1 | 0 | 0 | 10.00 % | 0 | 0 |

## 2. Interventions against `full` (exploratory)

Each row compares one intervention with `full` on the turns where `full`, the variant and the `full_repeat` control all have the 5 expected runs graded; a turn missing any of them is excluded, never compared on a different sample, and a row with no complete control is `incomplete`, never a signal. The noise of a row is the mean absolute difference, turn by turn, between `full` and `full_repeat` on that row's own turns (opposite swings never cancel). A signal is a change of at least 15 points that also exceeds that noise. It is an exploratory signal, not a cause: confirm with another seed before attributing one.

| Variant | Paired | Excluded | `full` | Variant | Change (pp) | Noise (pp) | Reading |
|---|---|---|---|---|---|---|---|
| full_repeat | 24 | 0 | 28/120 (23.33 %) | 33/120 (27.50 %) | -4.2 | n/a | control |
| no_context | 12 | 0 | 26/60 (43.33 %) | 10/60 (16.67 %) | +26.7 | 15.0 | exploratory signal |
| no_person | 1 | 0 | 3/5 (60.00 %) | 4/5 (80.00 %) | -20.0 | 20.0 | no signal |
| no_history | 1 | 0 | 4/5 (80.00 %) | 1/5 (20.00 %) | +60.0 | 0.0 | exploratory signal |
| question_only | 2 | 0 | 7/10 (70.00 %) | 1/10 (10.00 %) | +60.0 | 10.0 | exploratory signal |

`question_only` runs only on turns that have a person or a history; elsewhere it sends what `no_context` sends and is not repeated.

## 3. Failure shapes

| Shape in `full` (context) | Count | Share |
|---|---|---|
| tag_same_line | 22 | 84.62 % |
| no_tag | 3 | 11.54 % |
| text_before_tag | 1 | 3.85 % |

Dominant shape in `full` (context): `tag_same_line`.

| Shape in `full` (public) | Count | Share |
|---|---|---|
| tag_same_line | 2 | 100.00 % |

Dominant shape in `full` (public): `tag_same_line`.

Shapes of each intervention, apart (never merged into the baseline):

| Variant | Source | Shape | Count |
|---|---|---|---|
| full_repeat | context | tag_same_line | 28 |
| full_repeat | context | no_tag | 2 |
| full_repeat | context | text_before_tag | 1 |
| full_repeat | public | tag_same_line | 2 |
| no_context | context | tag_same_line | 5 |
| no_context | context | no_tag | 3 |
| no_context | context | text_before_tag | 2 |
| no_person | context | tag_same_line | 4 |
| no_history | context | tag_same_line | 1 |
| question_only | context | tag_same_line | 1 |

## 4. Turns under `full`

| Turn | Fallbacks | Provider errors | Graded | Expected |
|---|---|---|---|---|
| absent_address | 2 | 0 | 5 | 5 |
| absent_pet | 3 | 0 | 5 | 5 |
| corrected_age_active_fact | 5 | 0 | 5 | 5 |
| corrected_species_active_fact | 1 | 0 | 5 | 5 |
| identified_person_second_person | 3 | 0 | 5 | 5 |
| multiple_active_facts | 5 | 0 | 5 | 5 |
| old_history_vs_active_fact | 4 | 0 | 5 | 5 |
| persisted_context_after_restart | 1 | 0 | 5 | 5 |
| public_1 | 0 | 0 | 5 | 5 |
| public_10 | 0 | 0 | 5 | 5 |
| public_11 | 0 | 0 | 5 | 5 |
| public_12 | 0 | 0 | 5 | 5 |
| public_2 | 0 | 0 | 5 | 5 |
| public_3 | 0 | 0 | 5 | 5 |
| public_4 | 1 | 0 | 5 | 5 |
| public_5 | 0 | 0 | 5 | 5 |
| public_6 | 0 | 0 | 5 | 5 |
| public_7 | 0 | 0 | 5 | 5 |
| public_8 | 0 | 0 | 5 | 5 |
| public_9 | 1 | 0 | 5 | 5 |
| resolved_face_enrollment | 1 | 0 | 5 | 5 |
| resolved_face_recognition | 1 | 0 | 5 | 5 |
| semantic_distractor_ignored | 0 | 0 | 5 | 5 |
| two_children_names | 0 | 0 | 5 | 5 |

Turns with at least one fallback: 12 of 24; that fell back in every expected run: 2; incomplete turns: 0.

## 5. Timing (ms)

| Variant | Outcome | n | First delta | Speech start | End |
|---|---|---|---|---|---|
| full | valid | 92 | 1076 / 1517 | 2848 / 5885 | 4161 / 11830 |
| full | fallback | 28 | 1220 / 1623 | 3978 / 7915 | 3978 / 7915 |
| full_repeat | valid | 87 | 1092 / 1425 | 2919 / 5664 | 4457 / 7740 |
| full_repeat | fallback | 33 | 1230 / 1554 | 3894 / 8234 | 3894 / 8234 |
| no_context | valid | 50 | 1115 / 2136 | 3554 / 7158 | 5141 / 9620 |
| no_context | fallback | 10 | 1099 / 1323 | 3253 / 6136 | 3253 / 6136 |
| no_person | valid | 1 | 926 / 926 | 2035 / 2035 | 3626 / 3626 |
| no_person | fallback | 4 | 1071 / 1141 | 2491 / 4267 | 2491 / 4267 |
| no_history | valid | 4 | 1067 / 1193 | 2080 / 3168 | 2210 / 3385 |
| no_history | fallback | 1 | 1177 / 1177 | 5235 / 5235 | 5235 / 5235 |
| question_only | valid | 9 | 983 / 1079 | 2891 / 5657 | 4847 / 6148 |
| question_only | fallback | 1 | 1055 / 1055 | 10212 / 10212 | 10212 / 10212 |

p50 / p95 by the nearest-rank method. Speech start is when production would hand its first sentence, or the fallback, to TTS (TTS time excluded).

## 6. Execution order

Quarters of the shuffled execution order, all variants together: it describes the experiment, not the baseline.

| Quarter | Fallback rate |
|---|---|
| Q1 | 23.75 % |
| Q2 | 21.25 % |
| Q3 | 11.25 % |
| Q4 | 40.00 % |

Quarters differ by 15 points or more: repeat with another seed.

## 7. Prompt size (characters sent)

| Variant | Min | Mean | Max |
|---|---|---|---|
| full | 2822 | 2884 | 3173 |
| full_repeat | 2822 | 2884 | 3173 |
| no_context | 2819 | 2863 | 3100 |
| no_person | 2890 | 2890 | 2890 |
| no_history | 2895 | 2895 | 2895 |
| question_only | 2817 | 2826 | 2835 |

## 8. Stream arrival probe

Not run.
