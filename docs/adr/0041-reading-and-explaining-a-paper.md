# 0041 — Reading and explaining a paper: a dedicated OCR, the paper's own slot, quoted answers

- **Status:** **Proposed** (2026-11-26). Accepted when
  [Plan 0090](../plans/open/0090-reading-and-explaining-a-paper.md) closes on real hardware.
  Pipec's decisions of 2026-11-25 and 2026-11-26 (the plan's *Pipec's decisions*) and the OCR
  probe ([record](../evals/0090-ocr-probe.md)) are its source.
- **Date:** 2026-11-26
- **Builds on:** [ADR 0034](0034-documents-and-reading-through-the-camera.md) (decision 5, «Iroko,
  lee esto», and its deviations 3, 5, 9 and 11), [ADR 0020](0020-authorized-actor-in-the-conversation.md)
  (the short-term session and its 180 s of silence), [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md)
  (the closed «sí, guárdalo» and its 60 s offer window), [ADR 0004](0004-local-first-cognitive-policy.md)
  (Ollama is the model runtime).
- **Amends:** ADR 0034 decision 5 (the read text now waits and answers questions) and its
  rejected alternative «a dedicated OCR engine now» (the measurement exists); ADR 0021's 60 s
  window, for a reading only (decision 6).
- **Delivers:** row 9a of the
  [path to the finish line](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory).

## Context

1. **Reading through the vision model is too slow on the laptop.** Plan 0089's bench measured
   70 to 120 s per frame for `qwen3-vl:2b-instruct`: ~1100 image tokens evaluated on the CPU,
   because the 1.9 GiB model never fits the 2 GiB GPU beside Ollama's floor. It reads printed text
   exactly, when it finishes.
2. **A dedicated OCR reads print in about a second.** The isolated probe (Plan 0090 Task 1, server
   and Ollama off) read the invented bill exactly in 0.8 to 1.1 s with RapidOCR 3.10.0 and its
   default PP-OCRv6 small models, on the installed ONNX Runtime; the models load once in about 8 s
   with no measurable drop of free RAM. Handwriting in block capitals is read partly (2 of 5 canary
   words in blue ballpoint, 1 of 5 in graphite; a contrast step added one word each but misread a
   digit of a real bill's total, so it was dropped).
3. **The frame was the limit for a real paper.** The robot asks the webcam for no size and gets
   640x480; a utility bill's figures are then a few pixels high. At 1280x720, the image contract's
   maximum, the probe read a real bill's due date and total exactly (outcomes only).
4. **What Pipec wants (option B, 2026-11-24).** The robot reads the paper, then answers questions
   about it only from what it read, saying so, or says the answer is not there; the text lives only
   in the short term; a stranger hears no answer; a medical letter is never interpreted; it is kept
   only after «sí, guárdalo».
5. **A model must not word the answer.** On ADR 0034's bench the local 3B obeyed an order planted
   in a document in 12 of 24 answers (ADR 0034 deviation 9).

## Decision

### 1. The reader is RapidOCR, reading the frame as taken, behind the reading seam

`READING_ENGINE` names the one reader: `vlm` (today's) or `rapidocr`. RapidOCR runs in the
server's process on the CPU, through the bounded executor, with its default models (PP-OCRv6
small, which covers Spanish), on the frame as taken: no contrast step. A failure says
the existing «No pude leerlo…»; it never falls back to the vision model. The vision model stays
for «¿qué ves?». Licences: RapidOCR's code is Apache-2.0 and its models derive from PaddleOCR's
(Apache-2.0); no AGPL, GPL or non-commercial term. Ollama stays the only runtime of language and
vision models (ADR 0004); the OCR is a small ONNX model like the face model.

### 2. The robot asks the camera for 1280x720

Within the image contract (JPEG, at most 1280x720): the robot requests that size and keeps what the
camera gives (a camera that cannot is unchanged). The face check reads the same frame; its result
and the frame's size are checked on hardware.

### 3. The paper waits in its own slot, under the short-term session's rules

The whole read text (at most 4,000 characters; 400 are spoken) waits in an in-process slot bound
to the person identified on the reading turn. Another identified person, 180 s of silence, a new
reading or a restart ends it; an unknown or ambiguous turn neither reads nor extends it. It never
enters the continuity slot, the generic prompt, the conversation record, the diary, a recall unit,
an export or a log. A reading with nobody identified keeps no text, only that it happened.

### 4. Questions about the paper are a closed cue, and the answer quotes

While a paper waits, a closed list («¿cuánto tengo que pagar?», «¿para cuándo es?», «¿qué dice la
carta…?», …) is answered from the paper by quotation, no model: «Según el papel: …», raised by a
closed amount or date extractor, with every order and every secret left out (ADR 0034's filters),
or «Eso no aparece en lo que leí.». Every other turn is unchanged.

### 5. Two fixed phrases

- Nobody identified: «Solo puedo leértelo; para responder sobre el papel necesito reconocerte.».
- A question that asks to interpret («¿es grave?», «¿qué significa?», …): «Eso no lo puedo
  interpretar. Te puedo leer lo que dice; para entenderlo, pregúntale a tu médico.», for every
  paper.

### 6. «Sí, guárdalo» while the paper lives

The offer is spoken after the reading only; the closed verb keeps the paper's whole text while its
slot lives, from the same person, even after questions. Elsewhere ADR 0021's 60 s window stands.

## Consequences

- **Positive:** a printed paper is read in about a second on the laptop, and asked about safely;
  the reading works the same on a later board with no GPU.
- **Negative:** one runtime dependency more (`rapidocr` and its OpenCV headless build) and an 8 s
  model load once; handwriting is partial; larger frames travel on every turn that carries one.
- **Left out, with their triggers** (Plan 0090, *Deferred*): other OCR engines, the vision model
  against the OCR on the same frames, the reader's contention with the other models (PC-5), a
  doctor's handwritten prescription, QR and barcodes, a model that words the answer (P4.1).

## Alternatives considered

- **Keep the vision model:** right on print, 70 to 120 s per frame here. Rejected by Pipec.
- **RapidOCR with a contrast step:** one handwritten word more per note, but one digit of a real
  bill's total misread. Rejected by Pipec.
- **The paper in the continuity slot:** the generic prompt would read it. Rejected.
- **The 3B words the answer:** it obeys planted orders. Rejected.
- **Every turn of the window goes to the paper:** it steals the conversation. Rejected.
