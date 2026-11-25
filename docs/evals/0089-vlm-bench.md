# Plan 0089 — the vision model under load (Task 4 record)

> **Status:** Recorded 2026-11-25, Pipec at the laptop. Numbers and outcomes only: no description,
> no read text, no photograph enters this file. The photographs and the raw JSON lines stay in the
> ignored `.superpowers/sdd/0089/` and are deleted at the plan's close.

## Setup

- **Machine:** the development laptop, Windows 11, 15.7 GiB of RAM, an NVIDIA MX450 with 2 GiB.
- **Ollama:** 0.40.18, no `OLLAMA_*` variable set. Models: `qwen3-vl:2b-instruct` (vision),
  `qwen2.5:3b` (conversation), `qwen3:4b-instruct-2507-q4_K_M` (consolidation),
  `granite-embedding:278m`.
- **Load:** the server up as on a normal day (`just run-server`, the production `.env`): Whisper
  `medium`, Piper, `buffalo_l` and the speaker model loaded; the robot off.
- **Tool:** `scripts/vlm_bench.py`, calling the product's own `describe_image` and `read_text`.
  One JSON line per call: latency, Ollama's own metrics (`vision.metrics`), free RAM and VRAM
  before and after, the 3B model's next latency (the probe), the failure cause and closed
  quality checks (no judge model).
- **Photographs:** taken once with the robot's capture path (`robot.camera_capture`,
  device 0, which gives **640x480**), in the room's ordinary light: the printed canary card, the
  same card on a phone screen, a ball, an invented bill, the canary list handwritten with a
  marker (neat and hurried) and with a standard ballpoint pen, a twelve-face puzzle and a smart
  band. The household had no QR code, cup, key or pen at hand.
- **Safety stop:** under 1 GB free, or one call over 120 s, ends the cell. Nothing was retried.

## Run 1 — Whisper on the GPU (11:24 to 12:15, 31 calls)

| cell | mode | capability | calls | median ms | max ms | median load ms | min free MB | quality ok | failures |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| today | cold | reading | 3 | 116509 | 121085 | - | 2528 | 2/3 | 1 |
| today | cold | scene | 1 | 120036 | 120036 | - | 2571 | 0/1 | 1 |
| today | warm | reading | 2 | 120131 | 120139 | - | 2493 | 0/2 | 2 |
| side512 | cold | reading | 1 | 120166 | 120166 | - | 2575 | 0/1 | 1 |
| side512 | warm | reading | 1 | 120250 | 120250 | - | 3445 | 0/1 | 1 |
| ctx4096 | cold | reading | 1 | 120173 | 120173 | - | 2660 | 0/1 | 1 |
| ctx4096 | warm | reading | 2 | 105946 | 113134 | - | 2413 | 2/2 | 0 |
| ctx4096 | warm | scene | 1 | 94252 | 94252 | - | 2502 | 1/1 | 0 |
| ctx2048 | cold | reading | 2 | 80903 | 90638 | - | 2744 | 2/2 | 0 |
| ctx2048 | cold | scene | 1 | 82584 | 82584 | - | 2738 | 1/1 | 0 |
| ctx2048 | warm | reading | 2 | 105601 | 116573 | - | 2616 | 2/2 | 0 |
| ctx2048 | warm | scene | 1 | 120034 | 120034 | - | 2726 | 0/1 | 1 |
| caps | warm | reading | 2 | 116433 | 120037 | - | 2597 | 1/2 | 1 |
| keepalive | warm | reading | 1 | 120162 | 120162 | - | 2820 | 0/1 | 1 |

Ollama's metrics are missing from run 1: the bench lost them (a plain script logs at WARNING and
`vision.metrics` is INFO). Fixed before run 2 (commits `d78194f`, `7d635ca`). In run 1, "warm" was
never warm: the 3B probe after each call evicted the vision model.

## Run 2 — Whisper on the CPU (12:46 to 13:16, 19 calls)

`WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`; GPU in use 0 to 235 MiB during the run.
`--no-probe` keeps the vision model truly warm.

| cell | mode | capability | calls | median ms | max ms | median load ms | min free MB | quality ok | failures |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| today | cold | reading | 3 | 107000 | 120249 | 18314 | 1024 | 2/3 | 1 |
| today | cold | scene | 1 | 120041 | 120041 | - | 2111 | 0/1 | 1 |
| today | warm | reading | 3 | 120039 | 120216 | 20 | 1852 | 1/3 | 2 |
| ctx2048 | cold | reading | 1 | 120098 | 120098 | - | 1771 | 0/1 | 1 |
| ctx2048 | warm | reading | 2 | 89656 | 107251 | 8393 | 1061 | 2/2 | 0 |
| ctx2048 | warm | scene | 1 | 97367 | 97367 | 40 | 1641 | 1/1 | 0 |
| side384 | warm | reading | 2 | 96622 | 103656 | 25 | 1573 | 2/2 | 0 |
| side384 | warm | scene | 1 | 120080 | 120080 | - | 2288 | 0/1 | 1 |

## Where the time goes (run 2, Ollama's own metrics)

| Part of one call | Measured |
|---|---|
| Loading the vision model (cold only) | 17 to 19 s |
| **Prompt evaluation: ~1099 tokens, almost all the image** | **69 to 109 s** (~13 tokens/s, CPU) |
| Writing the answer (14 to 97 tokens) | 2 to 16 s |

- The frame's size changes nothing: a 640x480 frame and the same frame shrunk to 384 px both give
  **1099 prompt tokens**. The model or Ollama brings every image to a fixed size, so
  `VLM_IMAGE_MAX_SIDE` buys neither time nor memory with this model.
- Warm saves only the load (~18 s); the image's evaluation is the cost.
- Free memory fell to **1024 MB** in run 2 (Whisper's model then lives in RAM), at the safety
  stop's edge.

## Why the GPU does not help (Ollama's log, both runs)

- Ollama sees `gpu memory available="1.1 GiB" free="1.5 GiB" minimum="457.0 MiB"` in **both** runs,
  with Whisper on the GPU and without it. The vision model is predicted at **1.9 GiB**, so Ollama
  logs `disabling multimodal projector offload reason=limited-vram` and runs it on the CPU.
- Only one model is loaded at a time: every switch between the vision model, the 3B and the 4B
  logs `predicted to exceed available memory, evicting` and costs a load of 10 to 30 s.
- Ollama also logs `unable to refresh free memory, using old values` (its GPU discovery times
  out), so its view of free VRAM can be stale.
- Conclusion: on a 2 GiB GPU, Ollama's 457 MiB floor leaves no room for this 2B vision model,
  whether or not Whisper is there.

## What the current model reads

| Photograph | Check | Outcome |
|---|---|---|
| Printed canary card | `canary_ok` | Read exactly whenever the call finished (9 of 9) |
| The card on a phone screen | `canary_ok` | Read exactly whenever the call finished (7 of 7) |
| Ball | `object_named` | Named whenever the call finished (3 of 3) |
| Invented bill | `bill_ok` | Not measured: the call timed out (1 of 1) |
| Handwriting: marker neat, marker hurried, ballpoint | `canary_ok` | Not reached: each cell stopped at an earlier timeout |
| Twelve-face puzzle, smart band | `object_named` | Not reached |
| QR code and barcode | `code_named` | Not photographed (none at hand) |

## Pipec's choice (2026-11-25)

No setting of D-12 changes the outcome on this laptop: the frame's size does not change the
tokens, keep-alive and warm save only the load, and the context window stays within noise. The
five `VLM_*` settings **stay unset** (today's behaviour), pinned by
`test_the_vision_model_settings_are_neutral_by_default`. No warm-up at start (a warm call still
takes 70 to 110 s). Ollama's own switches (flash attention, the KV cache type, the loaded-model
limit) were **not measured**: they cannot make a 1.9 GiB model fit 1.1 GiB, so the operator
manual records no recommendation for them.

## Triggers this record meets

- *Another vision model or a quantization of it* (Plan 0089, *Deferred*): the tuned model fails
  the safety stop with every setting of the matrix.
- *Reading and explaining a paper* (Plan 0090): reading through this vision model costs 90 to 120 s
  per frame here, so a dedicated OCR, measured on the CPU, is the first option to weigh (ADR 0034
  rejected one "now"; Plan 0090 decides it with its own ADR).
- The home-server budget (PC-5, block D): the vision model needs a GPU with more than 2 GiB, or a
  lighter model, before scene description is usable in conversation.
