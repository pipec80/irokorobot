# Streaming protocol measurement

- model: qwen2.5:3b
- runs per turn: 5
- graded observations: 120
- fallback rate (invalid protocol + empty stream, over graded): 29.17 %

| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate |
|---|---:|---:|---:|---:|---:|
| all | 85 | 35 | 0 | 0 | 29.17 % |
| context | 26 | 34 | 0 | 0 | 56.67 % |
| public | 59 | 1 | 0 | 0 | 1.67 % |
