# Plan 0090 — hardware acceptance (Task 9)

> **Status:** Recorded 2026-11-26, Pipec at the laptop. Outcomes, times and counts only: no read
> text and no value of a real paper. **8 of 8 passed.**

## Setup

- The development laptop (Windows 11, 15.7 GiB of RAM, MX450 2 GiB). Server and robot started by
  Pipec (`just run-server`, `just run-robot`) on the branch `feat/0090-read-and-explain-a-paper`
  at `6c50266`, the **streaming** route (production's).
- Switches: `MEMORY_ENABLED`, `DOCUMENTS_ENABLED`, `VISION_ENABLED`,
  `FACE_AUTHENTICATION_ENABLED`, `ROBOT_FACE_AUTH_ENABLED`, `ROBOT_STREAMING` on;
  `READING_ENGINE=rapidocr`. Whisper `medium` on the GPU; the OCR on the CPU.
- The paper: Plan 0089's invented bill, printed («Boleta qqluzqq», a total and a due date).
- The robot was restarted before the steps below, so its camera asked for 1280x720
  (ADR 0041 decision 2). The frame's size is not logged; the same request gave 1280x720 with
  `scripts/camera_preview.py --hd` on the same webcam.
- A backup of the database was taken before the session.

## Steps

| # | Said (face) | Expected | Outcome | Total turn |
|---|---|---|---|---:|
| 1 | «Iroko, lee esto» (visible) | read aloud, then the offer | pass: read exactly | 18.5 s (first reading: the OCR models load) |
| — | «Sí, guárdalo» right after | kept | pass | 6.0 s |
| — | «¿Cuánto tengo que pagar?» 4 min later | today's turn: the paper ended after 180 s of silence | pass: the generic model answered, no amount invented | — |
| 2 | «Iroko, lee esto» (visible) | read aloud, then the offer | pass: read exactly | 6.3 s |
| 3 | «¿Cuánto tengo que pagar?» | «Según el papel: Total a pagar: …» | pass | 4.1 s |
| 4 | «¿Para cuándo es?» | «Según el papel: Vence: …» | pass | 4.1 s |
| 5 | «¿Es grave?» | the fixed refusal to interpret | pass | 4.2 s |
| 6 | «Sí, guárdalo» right after | kept | pass | 20.2 s (the embedding model loaded to index the note) |
| 7 | «Iroko, lee esto» (face covered by the paper) | read aloud | pass | 5.4 s |
| 8 | «¿Cuánto tengo que pagar?» (still covered) | «Solo puedo leértelo; para responder sobre el papel necesito reconocerte.» | pass | 3.7 s |

## The server's log (`logs/server.log`, the session's lines)

- **No line holds the paper:** zero hits for the canary title, the amount, the due date or the
  bill's other words.
- The OCR read each frame in **1.1 to 1.3 s** (`vision.ocr_read`: 4 lines, 75 characters).
- Every paper question was decided with no language model: `need=paper_question`,
  `source=deterministic`, `llm_ms=0`.
- The face identified Pipec on every turn with the face in view (`face_only`, the voice
  `unknown` on these short clips, as known); the covered turns had `no_evidence`.
- Free RAM at the turns' start: 1.0 to 1.8 GB.

## Findings

- **Piper reads «$» as «dólar».** «Total a pagar: $12.345» is spoken «dólar doce mil trescientos…»;
  in Chile the sign is pesos. Pipec's decision (2026-11-26): not in this plan. He widened it the
  same day to one rule per household locale (the currency's name by country, the separators,
  dates, times and units), its own ADR and plan: the roadmap's cross-cutting row *Figures spoken
  by Piper, by the household's country*.
- The first reading after a start pays the OCR's model load (about 10 s more), and the first keep
  pays the embedding model's load.
