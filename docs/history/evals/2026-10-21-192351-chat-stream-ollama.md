# Streaming protocol measurement

- model: qwen2.5:3b
- runs per turn: 10
- graded observations: 360
- fallback rate (invalid protocol + empty stream, over graded): 0.00 %
- replies not in Spanish (word-list heuristic, replies it could judge): 0 of 326

| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate | Not in Spanish |
|---|---:|---:|---:|---:|---:|---:|
| all | 360 | 0 | 0 | 0 | 0.00 % | 0 of 326 |
| context | 120 | 0 | 0 | 0 | 0.00 % | 0 of 99 |
| history | 120 | 0 | 0 | 0 | 0.00 % | 0 of 109 |
| public | 120 | 0 | 0 | 0 | 0.00 % | 0 of 118 |
