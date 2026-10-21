# Plan 0069 — speech-to-text on the owner's real voice: measurements

Counts, rates and tallies only. The reading script is invented and tracked
(`tests/evals/stt_reading_script.yaml`), so its items are named by id. No sentence of the spontaneous
session and no household name appears here; the private corpus lives outside git and is deleted at
the close of the plan.

## Machine and method

- Dell laptop: i7-11390H (4 cores, 8 threads), 15.7 GB of RAM, Intel Iris Xe and an NVIDIA MX450 with
  2 GB (driver 610.60), Windows 11. Faster-Whisper 1.2.1 on CTranslate2 4.8.2; the GPU runs use the
  cuBLAS 12 wheels (`nvidia-cublas-cu12` 12.9.2.10), cuDNN was not needed.
- The speaker is Pipec, at 60 cm from the laptop's own microphone array (Windows defaults, the robot's
  MME 16 kHz stream), in a quiet room: floor about −60 dBFS, signal-to-noise 39–46 dB.
- Corpus: a pilot (24 block items, session `s0`), one main session `s1` (layers A to E once each, 60
  takes), the condition block at 15 and 30 cm (24 takes each) and a 5-minute spontaneous session `s4`
  (48 clips, annotated by confirming a `P0` draft, so `P0`'s errors there are a floor). The scope was
  trimmed on 2026-10-21 (the plan's header says what was dropped).
- Items are split into a dev half (selects) and a test half (decides) by item, seed 69. Differences are
  `candidate − P0`, paired by item, 95 % block bootstrap; negative favours the candidate.
- The accuracy runs were made with the laptop in everyday use (the timings of those runs are not
  quoted). The timed runs (idle and under load) had the charger connected, Windows' best-performance
  power mode, Chrome closed and the GPU free.

## Capture levels (D-6, Task 10)

Targets: peak −12 to −3 dBFS, speech −30 to −20 dBFS, no clipped samples, floor at least 30 dB under
the speech.

| Take | Peak | Speech | Floor | SNR |
|---|---|---|---|---|
| 60 cm, MME | −6.9 | −21.0 | −60.1 | 39.1 dB |
| 30 cm, MME | −3.5 | −20.1 | −63.9 | 43.7 dB |
| 15 cm, MME | −3.5 | −18.7 | −64.3 | 45.6 dB |
| 60 cm, MME, Windows enhancements off | −29.3 | −46.2 | −72.1 | 25.9 dB |
| 60 cm, WASAPI | −5.1 | −20.0 | −61.2 | 41.2 dB |

Switching the enhancements off lowered the voice by about 24 dB, so the vendor's processing applies a
large gain. Two defects of the new tool were found and fixed on the way: the first WASAPI takes were
garbled because PortAudio's blocking read on WASAPI silently dropped about half of the buffers (9 s of
audio took 19 s with no overflow flag; reading through the stream callback fixed it), and the capture
judged levels on the raw take (with its 3 s countdown) instead of on the clips.

## The pilot gate (D-6)

24 block items once at `c60`, run through `P0` and `T0` twice.

| Check | Result |
|---|---|
| Every take gave one clip, or the count is explained | 23 of 24; the other was read twice (the countdown was read aloud) |
| No take lost its first word to the capture | Every clip starts 0.28–0.40 s before the voice; the one first-word miss is Whisper joining «sí po» |
| `T0` gives the same text twice on every clip | 25 of 25 (so did `P0` on those clips) |
| No clipped samples | 0 |

`P0` on the pilot: WER 21.4 %, exact 13 of 24 (the 24 block items, the hardest mix).

## Stage 1 — dev half (D-8)

47 read takes, 199 reference words; `P0` repeated twice, the rest once.

| Configuration | WER | Difference | Median s per clip |
|---|---|---|---|
| `P0` — `small`, int8, CPU, random retries (production before the plan) | 12.6 % | — | 3.04 |
| `PR-vocab` (vocabulary prompt) | 11.6 % | −1.0 [−3.9, +1.6] | 2.90 |
| `HW` (hotwords) | 12.1 % | −0.5 [−3.4, +2.6] | 2.97 |
| `V-off` (Whisper's silence filter off) | 12.1 % | −0.5 [−5.0, +4.8] | 3.46 |
| `PR-none` | 13.6 % | +1.0 [−4.3, +7.5] | 2.79 |
| `G-small` (`small`, int8_float16, CUDA) | 10.6 % | −2.0 [−7.7, +2.4] | 0.88 |
| `G-medium` (`medium`, int8_float16, CUDA) | 7.0 % | −6.5 [−11.9, −1.7] | 2.39 |
| `G-turbo` (`large-v3-turbo`, int8_float16, CUDA) | 5.0 % | −7.5 [−13.9, −2.1] | 3.52 |

Only the model separates from noise. The first draft of `PR-vocab` held the sentence of two script
items and its first score (13 %) was void; the prompt now holds single words only and a test enforces it.

## Stage 2 — test half (D-9)

The test half includes the 24 pilot takes at 60 cm and the 15 and 30 cm block takes of its items as well as the
main-session takes, while stage 1's dev half was recorded before the block and holds 60 cm takes only, so the
dev `P0` (12.6 %) and the test `P0` (15.4 %) are not comparable with each other; each is compared with its own
candidates.

57 read takes, 221 reference words, once each. `C1` = `G-small` with a 1200 ms closing silence and a
300 ms upload tail. `C2` = `medium`, CUDA int8_float16, retry temperature fixed at 0, same segmentation.
`C2` was fixed after `C1` and the test half was already seen for `C1`: a second look, disclosed in the
plan.

| | `P0` | `C1` | `C2` |
|---|---|---|---|
| WER | 15.4 % | 15.8 % | **6.8 %** |
| Difference against `P0` | — | +0.5 [−2.6, +3.0] | **−8.6 [−15.2, −1.8]** (MAPSSWE p 0.011; a paired z on clips that ignores item clustering, so the bootstrap interval is the figure to trust) |
| Exact takes | 36 of 57 | 36 of 57 | 47 of 57 |
| Wrong takes, difference | — | +0.0 [−5.1, +5.0] | −19.3 [−34.9, −7.5] |
| Critical-term takes, difference | — | 0 [0, 0] | −7.0 [−22.2, 0.0] |
| Layer B (short answers) WER | 25.7 % | 28.6 % | **2.9 %** (1 of 35 words; Wilson about 0.5–15 %, against 9 of 35, about 14–42 %) |
| Minimal pairs right | 10 of 14 | 11 of 14 | 13 of 14 |
| Wrong numbers / first word lost | 4 / 2 | 4 / 2 | 0 / 0 |
| Empty transcripts | 0 | 0 | 0 |

Text arm (does the text give the intended need, taste and answer, and does the transcript give the same):
layer B `ok` 14 of 15 for `P0` and `C1`, 15 of 15 for `C2`; layer D 13, 13 and 14 `ok`; layers A, C, E and
H all `ok` in the three; the `rest` column is 0 everywhere, so the readers after the speech-to-text
behave as written on the script.

D-9 verdict: `C1` and `C2` both pass (a) accuracy, (b) critical terms and layer B, (c) the latency budget
(below), (d) the noise probe and (e) empty rate on B. Both are recorded; Pipec chose `C2`.

## Speed (D-9 c, D-19)

Dev half, 128 clips (80 read, 48 spontaneous), once. Median / p90 / worst case in seconds per clip.

| | Idle | Ollama busy (`eval-chat --mode stream --runs 10`) | Peak RAM | Peak VRAM |
|---|---|---|---|---|
| `P0` (CPU) | 2.65 / 2.99 / 21.0 | **8.67 / 15.26 / 90.4** | 1029 MB | — |
| `C1` (`small` GPU) | 0.88 / 1.19 / 8.9 | 1.38 / 1.93 / 15.6 | 820 MB | 735 MB (1042 MB with Ollama) |
| `C2` (`medium` GPU) | 2.54 / 3.23 / 14.3 | 2.99 / 4.01 / 19.2 | 1867 MB | 1247 MB (1810 MB with Ollama) |

The budget (median ≤ 3.0 s, p90 ≤ 5.0 s) is missed by `P0` under load and met by both GPU profiles; `C2`
sits at its edge (read clips only: 2.88 / 3.37). The CPU profile loses to Ollama because both use the
same processor. D-15's 200 MB of free VRAM holds (about 240 MB with Ollama and `medium`).
Live acceptance (below) confirms: median 2.6 s, p90 4.1 s with Ollama and the memory extraction running.

## Decoding determinism and the latency tail

Random retries (Whisper's temperature fallback) were used on three of the 48 spontaneous clips (random
sampling, so not repeatable) and produced the slowest ones (24 s for a 3 s clip with `P0`, 14 s with `G-small`, 48 s with
`G-medium`). With the temperature fixed at 0 the slowest spontaneous clip fell from 24.2 s to 9.8 s, no
retry happened and the WER was 10.6 % against 10.3 % (a one-word difference). Fixed at 0 is the new
default (`WHISPER_TEMPERATURES`).

## Spontaneous session `s4` (48 clips, 435 reference words)

- WER: `P0` 10.3 % (draft-anchored, a floor), `G-small` 11.7 %, `T0` 10.6 %; exact clips 34, 31 and 33 of
  48. Edits for `P0`: 39 substituted, 3 deleted, 3 inserted. The «eh» filler appeared 5 times and was
  dropped 3 times; no other filler of the usual list appeared.
- Clips with an error by length: under 2 s 6 of 15, 2–5 s 2 of 17, over 5 s 6 of 16.
- Confidence (`P0`): log-probability under −0.7 on 12 clips, 6 wrong; under −0.9 on 6 clips, 3 wrong.
- Whisper's own silence filter removed a median 10 % of a clip (p90 27 %, one clip entirely).
- Pauses inside the speech: 93, median 0.70 s, p90 2.53 s, longest 16.6 s. Clips by closing silence:
  800 ms 48, 1200 ms 29, 1600 ms 20. Read takes split in two or more (of 132): 8, 7 and 6.

## Capture conditions (D-16)

`G-small`, the 24 block items paired by item: WER at 60 cm 18.0 %, at 30 cm 18.4 % (+0.4 [−13.4, +13.5]),
at 15 cm 19.4 % (+1.4 [−6.8, +9.1]); critical-term takes 2, 2 and 0. No distance separates from noise on
this microphone. The enhancements-off and WASAPI conditions were dropped by the trim (their hardware does
not carry to the Raspberry Pi); their level measurements are above.

## The robot's voice activity detector under noise (synthetic, VAD only)

The 24 pilot takes with synthetic noise added in the file and cut by the robot's own segmentation (close 800
ms). Clips per take, one / none / two or more: as recorded 23 / 0 / 1; white noise at −50, −40, −30 and
−25 dBFS RMS 22 / 0 / 2, 23 / 0 / 1, 23 / 0 / 1, 23 / 0 / 1; a low-passed fan hum at the same levels 23 / 0 / 1
each. Not measured: noise with speech in it (a television), and Whisper's accuracy under noise.

## Hallucination on noise (D-9 d) and on murmurs

`just probe-stt noise --clips 100` (synthetic noise): 100 empty, 0 echo, 0 other, with the `C1` settings
and with the `C2` settings. On Pipec's own murmurs (live acceptance), Whisper once invented a sentence
(confidence −0.98) and once wrote its known subtitle credit (confidence −0.33, no-speech probability
0.45, its silence filter kept 0.9 s of 2.0 s); the robot answered both. The credit is now discarded as
silence.

## The «no te entendí» reply (D-11)

Built, logged (`stt.confidence`) and off by default. The plan's rule (at most 5 % of correct clips rejected,
at least half of the errors caught, at least 30 errors on the test half) is not met: no threshold separates
the errors on the spontaneous clips, and the test half holds fewer than 30 wrong clips. In the live runs,
31 turns had a median confidence of −0.36 and one murmured clip fell under −0.6 (the other murmured clip, the
subtitle credit, scored −0.33, as high as real speech), so `-0.9` flags one of the two murmurs and none of
the 30 real turns, while on the 48 spontaneous clips (`small`'s, draft-anchored; there is no `medium` data on
long clips) it flags 6 (3 correct, about 9 % of the correct ones). Pipec set `WHISPER_UNCLEAR_LOGPROB=-0.9` in the runtime `.env` to try it; the code default
stays off.

## Whisper's marks and the taste gate (D-12)

Statement takes of layer A written with «?» or «¿»: 0 of 17 with `medium`, 0 of 13 with `small` (rule of three: a 95 % upper bound of about 18 % and 23 %; the plan's *Why* records one such statement in the 2026-10-19 session, so the risk is small, not nil). Question
takes written without them: 3 of 10 and 4 of 6. The direction that would cost a taste did not occur, so
the gate stays as it is (Task 13 not done, Pipec agreed) and the intonation work remains out of scope (D-1).

## Live acceptance (Task 17)

Server and robot started by Pipec with the adopted profile, 60 cm, Ollama up. Numbers from the server log
(it never holds text): 31 turns, 0 `ERROR` lines, 0 responses 422 or 500; the speech-to-text took a median
2.6 s and p90 4.1 s (the language model took a median 19 s, up to 57 s: Ollama on the CPU with the memory
extraction in the background, the roadmap's PC-5 row). The memory dialogue worked: offer, answer
«autorizo» and `Candidate answer: promoted`; a short refusal got the short-clip retry; the model's claim of
having saved something was replaced once.

## Decisions each rule produced

| Rule | Outcome |
|---|---|
| D-8 / D-9 | `C1` and `C2` pass; `C2` chosen as the recommended GPU profile (`medium`, CUDA, int8_float16, temperature 0, 1200 ms closing silence, 300 ms tail). The code default keeps the CPU profile because the `cuda` extra is optional |
| D-10 | Prompt and hotwords unchanged (no difference separable from noise) |
| D-11 | Off by default; Pipec runs `-0.9` |
| D-12 | Gate kept |
| D-13 | `WHISPER_HALLUCINATION_SILENCE_THRESHOLD` removed (word timestamps stay off) |
| D-15 | GPU adopted as an optional `cuda` extra of `server`; the loader registers the wheels' DLL folders and prepends them to `PATH` |
| D-16 | Distance and enhancements: no change; WASAPI not adopted |
| D-17 | Closing silence 1200 ms and a 300 ms upload tail |
| D-19 | Measured under load; `C2` at the edge of the budget, `C1` with margin |
| D-20 | Not done (optional) |

## Not covered, and what would trigger a new measurement

One speaker, one session per condition, one microphone in a quiet room, intervals wide. Not measured: the
Raspberry Pi's microphone, noise with speech, Whisper's accuracy under noise, the dropped layers (Chilean
markers such as «po», sentences with pauses, full phonetic coverage), intonation and other voices. The
script is derived from linguistic material and has not been validated by an expert. A new measurement
follows any of: the Pi's microphone, the homelab server, more VRAM (the `turbo` model measured 5.0 % on the
dev half at 3.5 s per clip), a new user to enrol, or a change of Whisper model or library version.
