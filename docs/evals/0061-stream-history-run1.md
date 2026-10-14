# Streaming protocol measurement

- model: qwen2.5:3b
- runs per turn: 5
- graded observations: 180
- fallback rate (invalid protocol + empty stream, over graded): 0.00 %
- replies not in Spanish (word-list heuristic, replies it could judge): 1 of 147

| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate | Not in Spanish |
|---|---:|---:|---:|---:|---:|---:|
| all | 180 | 0 | 0 | 0 | 0.00 % | 1 of 147 |
| context | 60 | 0 | 0 | 0 | 0.00 % | 0 of 42 |
| history | 60 | 0 | 0 | 0 | 0.00 % | 0 of 50 |
| public | 60 | 0 | 0 | 0 | 0.00 % | 1 of 55 |
