# Streaming protocol diagnosis (Plan 0057)

- model: qwen2.5:3b (digest `357c53fb659c`)
- ollama version: 0.34.4
- generation options: server defaults (production passes none)
- runs per turn and variant: 5; shuffle seed: 59
- observations (all variants): 320 (graded 320, provider errors 0)
- baseline (`full`) fallback rate: context 58.33 %, public 0.00 %
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
| full | context | 25 | 35 | 0 | 0 | 58.33 % | 0 | 0 |
| full | public | 60 | 0 | 0 | 0 | 0.00 % | 0 | 0 |
| full_repeat | context | 23 | 37 | 0 | 0 | 61.67 % | 0 | 0 |
| full_repeat | public | 59 | 1 | 0 | 0 | 1.67 % | 0 | 0 |
| no_context | context | 50 | 10 | 0 | 0 | 16.67 % | 0 | 0 |
| no_person | context | 1 | 4 | 0 | 0 | 80.00 % | 0 | 0 |
| no_history | context | 4 | 1 | 0 | 0 | 20.00 % | 0 | 0 |
| question_only | context | 9 | 1 | 0 | 0 | 10.00 % | 0 | 0 |

## 2. Interventions against `full` (exploratory)

Each row compares one intervention with `full` on the turns where `full`, the variant and the `full_repeat` control all have the 5 expected runs graded; a turn missing any of them is excluded, never compared on a different sample, and a row with no complete control is `incomplete`, never a signal. The noise of a row is the mean absolute difference, turn by turn, between `full` and `full_repeat` on that row's own turns (opposite swings never cancel). A signal is a change of at least 15 points that also exceeds that noise. It is an exploratory signal, not a cause: confirm with another seed before attributing one.

| Variant | Paired | Excluded | `full` | Variant | Change (pp) | Noise (pp) | Reading |
|---|---|---|---|---|---|---|---|
| full_repeat | 24 | 0 | 35/120 (29.17 %) | 38/120 (31.67 %) | -2.5 | n/a | control |
| no_context | 12 | 0 | 35/60 (58.33 %) | 10/60 (16.67 %) | +41.7 | 16.7 | exploratory signal |
| no_person | 1 | 0 | 5/5 (100.00 %) | 4/5 (80.00 %) | +20.0 | 20.0 | no signal |
| no_history | 1 | 0 | 5/5 (100.00 %) | 1/5 (20.00 %) | +80.0 | 0.0 | exploratory signal |
| question_only | 2 | 0 | 10/10 (100.00 %) | 1/10 (10.00 %) | +90.0 | 10.0 | exploratory signal |

`question_only` runs only on turns that have a person or a history; elsewhere it sends what `no_context` sends and is not repeated.

## 3. Failure shapes

| Shape in `full` (context) | Count | Share |
|---|---|---|
| tag_same_line | 31 | 88.57 % |
| no_tag | 3 | 8.57 % |
| text_before_tag | 1 | 2.86 % |

Dominant shape in `full` (context): `tag_same_line`.

| Shape in `full` (public) | Count | Share |
|---|---|---|

No fallbacks in `full` (public).

Shapes of each intervention, apart (never merged into the baseline):

| Variant | Source | Shape | Count |
|---|---|---|---|
| full_repeat | context | tag_same_line | 33 |
| full_repeat | context | no_tag | 3 |
| full_repeat | context | text_before_tag | 1 |
| full_repeat | public | tag_same_line | 1 |
| no_context | context | no_tag | 5 |
| no_context | context | tag_same_line | 5 |
| no_person | context | tag_same_line | 4 |
| no_history | context | tag_same_line | 1 |
| question_only | context | tag_same_line | 1 |

## 4. Turns under `full`

| Turn | Fallbacks | Provider errors | Graded | Expected |
|---|---|---|---|---|
| absent_address | 3 | 0 | 5 | 5 |
| absent_pet | 3 | 0 | 5 | 5 |
| corrected_age_active_fact | 1 | 0 | 5 | 5 |
| corrected_species_active_fact | 4 | 0 | 5 | 5 |
| identified_person_second_person | 5 | 0 | 5 | 5 |
| multiple_active_facts | 5 | 0 | 5 | 5 |
| old_history_vs_active_fact | 5 | 0 | 5 | 5 |
| persisted_context_after_restart | 1 | 0 | 5 | 5 |
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
| resolved_face_enrollment | 2 | 0 | 5 | 5 |
| resolved_face_recognition | 3 | 0 | 5 | 5 |
| semantic_distractor_ignored | 1 | 0 | 5 | 5 |
| two_children_names | 2 | 0 | 5 | 5 |

Turns with at least one fallback: 12 of 24; that fell back in every expected run: 3; incomplete turns: 0.

## 5. Timing (ms)

| Variant | Outcome | n | First delta | Speech start | End |
|---|---|---|---|---|---|
| full | valid | 85 | 1195 / 1870 | 3671 / 9469 | 5294 / 11374 |
| full | fallback | 35 | 1278 / 1687 | 4315 / 7607 | 4315 / 7607 |
| full_repeat | valid | 82 | 1191 / 1953 | 3959 / 9331 | 5291 / 13204 |
| full_repeat | fallback | 38 | 1248 / 1633 | 4223 / 9039 | 4223 / 9039 |
| no_context | valid | 50 | 1201 / 2452 | 3670 / 9265 | 5755 / 11981 |
| no_context | fallback | 10 | 1121 / 2404 | 3303 / 6719 | 3303 / 6719 |
| no_person | valid | 1 | 1165 / 1165 | 2165 / 2165 | 4275 / 4275 |
| no_person | fallback | 4 | 1233 / 1292 | 4195 / 6922 | 4195 / 6922 |
| no_history | valid | 4 | 1163 / 1198 | 2161 / 3564 | 3218 / 3849 |
| no_history | fallback | 1 | 1252 / 1252 | 4252 / 4252 | 4252 / 4252 |
| question_only | valid | 9 | 1205 / 1778 | 5622 / 10277 | 6789 / 14255 |
| question_only | fallback | 1 | 794 / 794 | 5025 / 5025 | 5025 / 5025 |

p50 / p95 by the nearest-rank method. Speech start is when production would hand its first sentence, or the fallback, to TTS (TTS time excluded).

## 6. Execution order

Quarters of the shuffled execution order, all variants together: it describes the experiment, not the baseline.

| Quarter | Fallback rate |
|---|---|
| Q1 | 22.50 % |
| Q2 | 37.50 % |
| Q3 | 22.50 % |
| Q4 | 28.75 % |

Quarters differ by 15 points or more: repeat with another seed.

## 7. Prompt size (characters sent)

| Variant | Min | Mean | Max |
|---|---|---|---|
| full | 2825 | 2887 | 3176 |
| full_repeat | 2825 | 2887 | 3176 |
| no_context | 2822 | 2866 | 3103 |
| no_person | 2893 | 2893 | 2893 |
| no_history | 2898 | 2898 | 2898 |
| question_only | 2820 | 2829 | 2838 |

## 8. Stream arrival probe

Not run.
