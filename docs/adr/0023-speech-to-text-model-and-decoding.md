# 0023 — Speech-to-text: the model, the decoding and the turn closing, measured on the owner's voice

- **Status:** Accepted (2026-10-21). Pipec accepted the measurements and every decision below on
  2026-10-21 («acepto todo para ir cerrando»), and chose the `medium` GPU profile for the runtime.
- **Date:** 2026-10-21
- **Builds on:** [ADR 0004](0004-local-first-cognitive-policy.md) (nothing in the speech-to-text path leaves
  the machine),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md) (the gate that reads Whisper's
  transcript)
- **Amends:** nothing. It replaces the unmeasured configuration of the speech-to-text with a measured one.
- **Implemented by:** [Plan 0069](../plans/completed/0069-stt-owner-voice-audit.md); the figures are in
  [the evaluation record](../evals/0069-stt-owner-voice.md).

## Context

There is no keyboard: every turn starts with what Whisper heard, and an error there breaks the grammar,
the memory and the reply that follow. The speech-to-text had only been measured with synthetic speech
(Plan 0056, WER 0.15–0.20); the hardware sessions of 2026-10-19 and 2026-10-20 showed human-voice errors
(a near-homophone pair, short answers, a split turn) and 4–14 s per transcription. Plan 0069 measured it
with Pipec's own voice through the robot's capture chain: a reading script, a private corpus recorded as
continuous raw takes, a deterministic bench that runs the production decode function, and a text arm
that separates «Whisper misheard» from «the rest misread».

What the measurements showed (held-out half, `small` on the CPU as it was): 15.4 % of the words wrong and
25.7 % on the short answers («sí», «no», «autorizo»); under load from Ollama a median 8.7 s per clip
(worst 90 s). The model was the only link whose change separated from noise.

## Decisions

1. **The recommended profile is `medium`, CUDA, `int8_float16`.** On the held-out half it has 6.8 % WER
   (against 15.4 %), 2.9 % on the short answers (against 25.7 %), no wrong number and no lost first word,
   at a median 2.99 s and p90 4.0 s per clip with Ollama busy, and 1.25 GB of VRAM. `small` on the GPU
   (same accuracy as today, 1.4 s median under load) is the fast alternative. **The code's default stays
   `small`, `int8`, CPU**: the GPU needs the optional `cuda` extra of `server` and not every host has
   CUDA (the homelab server, CI). A GPU host sets `WHISPER_MODEL`, `WHISPER_DEVICE` and
   `WHISPER_COMPUTE_TYPE` in its `.env`; the operator manual says how.
2. **Whisper's retry temperature is fixed at 0** (`WHISPER_TEMPERATURES`, default `[0.0]`). The random
   retries produced the 14–48 s tails on short spontaneous clips and made the text unrepeatable; fixed at
   0 the slowest clip fell from 24 s to 9.8 s at the same WER. The other decoding values keep the
   library's (beam 5, best-of 5, thresholds); `condition_on_previous_text=False`, `patience` and
   `num_workers` stay fixed in code with their reasons.
3. **The robot closes a turn after 1200 ms of silence and uploads a 300 ms tail** (`VAD_SILENCE_MS`,
   `VAD_UPLOAD_TAIL_MS`; reply mode keeps 1600 ms). Pipec's spontaneous speech has 93 pauses inside a
   sentence, median 0.70 s: at 800 ms it split into 48 clips, at 1200 ms into 29. A turn ends 0.4 s
   later; the shorter tail keeps the clip, and the transcription time, short. A pause longer than the
   closing silence still splits the turn, and that is the price of any silence-based end of turn; keeping
   2–3 s pauses in one turn needs an end-of-turn strategy, a later decision.
4. **The vocabulary prompt, the hotwords and Whisper's own silence filter stay as they were.** With one
   session their differences were within noise (−1.0, −0.5 and −0.5 points, intervals wide). The robot's
   Silero detector closed turns correctly through synthetic steady noise up to −25 dBFS; it was not
   tested with speech-like noise.
5. **The «No te entendí bien. ¿Me lo repites?» reply exists and is off by default**
   (`WHISPER_UNCLEAR_LOGPROB`). Whisper's mean log-probability separates a murmur from speech in the live
   runs (−0.98 against −0.5 or better on 30 turns) but not on the 48 long spontaneous clips, so the plan's
   rule (at most 5 % of correct clips rejected, at least half of the errors caught) is not met. Pipec
   runs `-0.9` to try it. Every clip logs one `stt.confidence` line, without text, to calibrate it later.
6. **A transcript that names `amara.org` is discarded as silence**, like a prompt echo. It is the credit
   Whisper writes on audio without speech; the robot answered it as if it had been said.
7. **The taste gate keeps refusing a text with «?» or «¿»** (ADR 0021, decision 4). Measured both ways on
   the A pairs: 0 of 17 statements were written with a question mark; 3 of 10 questions were written
   without one, so a word rule could turn a question into a taste. Intonation stays out of scope.
8. **Capture:** speaking at 15, 30 or 60 cm made no measurable difference with the laptop's array, and the
   Windows enhancements are left as they are. WASAPI is not adopted. PortAudio's blocking read on WASAPI
   dropped about half of the buffers without a flag, so any WASAPI capture must read through the stream
   callback.
9. **The GPU is declared as an optional `cuda` extra** (`nvidia-cublas-cu12`). On Windows the loader
   registers each wheel's folder with `os.add_dll_directory` **and** prepends it to `PATH`, because
   CTranslate2 loads cuBLAS with a plain `LoadLibrary`; the registration alone loaded the model and
   failed on the first real clip. The `deptry` check ignores the wheel (it is never imported).
10. **The latency budget** is a median of 3.0 s and a p90 of 5.0 s per clip with Ollama busy; the measured
    figures are in the record. `medium` sits at the edge of it.

## What triggers a new measurement

The Raspberry Pi's microphone (distance, gain and enhancements do not carry from the laptop), the homelab
server (a faster CPU or a larger GPU may allow `large-v3-turbo`, which measured 5.0 % on the dev half at
3.5 s per clip), a new user to enrol, a change of Whisper model or of `faster-whisper`/CTranslate2, and
real use that fills the `stt.confidence` log with enough errors to set the unclear threshold on evidence.

## Consequences

- The robot's turn is 0.4 s longer to close and the transcription is about 3 times faster under load; the
  total from the end of speech to the transcript is about the same as before at 3.5 s, with half the errors
  (and with `small` on the GPU 1.7 s faster).
- A host with a GPU gains a 1.25 GB resident model that competes for VRAM with Ollama's partial offload;
  `small` on the GPU leaves more room.
- The instruments (reading script, corpus recorder, bench, threshold calibration) stay in `scripts/` and
  are the base of a voice calibration when a new user is enrolled; that product feature is not built here.
- The evidence is one speaker, one session per condition and one microphone in a quiet room, with wide
  intervals; the record lists what was not measured.
