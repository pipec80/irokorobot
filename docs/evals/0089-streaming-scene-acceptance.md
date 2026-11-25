# Plan 0089 — acceptance, closed by decision (Task 11)

> **Status:** Closed 2026-11-25 by Pipec's decision, **without a hardware sitting** (as Plan 0084
> was closed on 2026-11-16). Outcomes only.

## Why there was no sitting

Pipec decided it on 2026-11-25, after the bench ([record](0089-vlm-bench.md)):

- **Quality is known.** Every time the vision model answered on the bench, the answer was right:
  the printed canary card read exactly 9 of 9 times, the phone screen 7 of 7, the ball named
  3 of 3.
- **The latency is known and explained.** On the development laptop every frame costs 70 to 120 s
  (~1100 image tokens evaluated on the processor), because the 2 GiB GPU minus Ollama's 457 MiB
  floor cannot hold the 1.9 GiB vision model, with or without Whisper on it. A sitting would only
  repeat 100-second waits under memory pressure, with no new evidence, and could not tell a
  defect from the laptop's limit.
- **What is new is covered by automated tests** (CI selection 8936 passed after the review fixes;
  the cue phrase on its neighbour suites):
  - the scene over streaming from the turn's frame, the cue phrase spoken before the camera
    looks, the fixed phrases without a frame, with a switch off, with a rejected frame and on a
    failed vision call (`tests/integration/test_stream_scene.py`);
  - the record and the opt-in spoken log keeping the marker, never the description, and no frame
    byte in the database or a log;
  - the robot starting in streaming with server vision on, with no `/health` call
    (`tests/unit/test_robot_app.py`);
  - the camera phrases and their traps (`test_document_cues.py`, `test_intent_resolution.py`);
  - the trace of one turn and Ollama's failure logs, with their privacy canaries
    (`test_turn_trace*.py`, `test_llm_transport.py`, `test_vision_log_privacy.py`).

## What was not run on hardware

The Task 11 script (parts A, B and C) was not run. Not proven on the real microphone, camera and
speaker:

- the cue phrase heard through the robot before a slow description;
- the trace joined from the robot's log to the server's on a real turn (A7);
- «le esto» as the speech-to-text really writes it (B4);
- the classic route's scene after this plan (C3; the classic route did not change).

These are observed in normal use and are re-run when the server moves to hardware with a larger
GPU (the home-server budget, PC-5), where the vision model can run on the GPU.

## Close

- The five `VLM_*` settings stay unset; Ollama's own switches are not recommended (not measured).
- `VISION_ENABLED` stays the owner's choice: on, «¿qué ves?» and «lee esto» work on both routes and
  take 70 to 120 s on this laptop.
- Next: Plan 0090 (reading and explaining a paper) weighs a dedicated OCR with these numbers.
