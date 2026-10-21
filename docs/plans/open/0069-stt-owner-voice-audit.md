# 0069 — Speech-to-text on the owner's real voice: capture, corpus, a deterministic bench and changes backed by evidence

> **Status:** `Ready` and `NOW` — written and **promoted by Pipec on 2026-10-20**, with decisions
> D-1 to D-20 as written (the thresholds of D-9 and D-11 included) and Pipec's standing rule kept as is:
> every finding met while executing is fixed. Two outside reviews Pipec brought the same day were
> folded in before the promotion (the pilot gate, the near reference, critical-term errors, the
> pause test, dev/test selection, a coherent confidence figure, D-12 left to Pipec). This plan goes
> **before** the pending hardware tasks of Plan 0068 (Tasks 6 to 8), which is `PAUSED`, not closed.
> Pipec authorized an isolated GPU virtual environment in the scratchpad (D-15) and prepares the
> laptop for every timed run (charger, the Windows maximum-performance power plan, Chrome closed,
> server stopped). **Not rehearsed.**
>
> **Scope trimmed by Pipec on 2026-10-21, after the pilot** (the plan allows it once an effect is
> obvious; the pilot showed the misses on short answers, the «helado»/«de lado» pair and numbers).
> The goal is a small `small`-sized model that works well on a shared 2 GB laptop and enrols one
> user, not a statistical study. **Kept:** the pilot (as the block's `c60` cell), one session `s1`
> with layers A to E once each (`capture --layers ABCDE --once`, 60 takes), the block at `c15` and
> `c30` (the distance that matters for the Pi's microphone), a 5-minute spontaneous session `s4`,
> and a bench limited to the large levers (model, prompt and hotwords, silence filter, the unclear
> threshold of D-11). **Dropped:** session `s2`, the conditions `c60-noenh`, `c60-wasapi`,
> `c60-noise` and `c60-fast` (their hardware does not carry to the Pi), layers F, G and H, and the
> other bench configurations. With one session and a lighter bench the intervals are wide: D-9
> still decides adoption, but a difference it cannot separate from noise is reported as such, never
> adopted. Task 14 (`cuda` extra) and Task 15 (WASAPI on the robot) stay out unless the evidence
> asks for them.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`. Pipec's
> rules win: one plain branch from `main`, never a git worktree; subagents only with model `sonnet`,
> after reading `.claude/` in full, on disjoint files and without committing. An agent never opens
> the microphone, never records, imitates or plays back a voice, and never reads the private corpus
> aloud; Pipec runs every capture and every playback. Synthetic audio is allowed. Create and edit
> files with the Write and Edit tools (the Bash of this environment drops backslashes and non-ASCII
> characters in heredocs). Run the suite with `MEMORY_ENABLED=false`. Every finding met while
> executing is fixed (Pipec's standing policy).

**Goal:** Measure, for the first time, how well the speech-to-text understands Pipec's real voice
through the robot's real capture chain; find which link causes the errors (microphone and capture,
the robot's segmentation, Whisper's own silence filter, the model, its decoding, the prompt); change
only what the evidence supports; and make the robot say «No te entendí bien. ¿Me lo repites?» instead
of acting on a transcript Whisper doubted.

**Why:** There is no keyboard: every turn starts with what Whisper heard, and an error there breaks
the grammar, the memory and the reply that follow. The speech-to-text was measured only with
synthetic Piper speech ([Plan 0056 measurements](../../evals/0056-voice-pipeline-measurements.md):
mean WER 0.15–0.20 with `small`); never with a human voice. Hardware sessions on 2026-10-19 and
2026-10-20 heard «helado» as «de lado», «guardes» as «guartes», «sabores» as «sabore», added a «Que»
at the start of a taste, wrote a stated taste as a question, and split one turn in two at a 2–3 s
pause. The face check got a battery of photographs in several lights (Plan 0030); the input of the
whole pipeline deserves at least that.

**Architecture:** Three layers, in order. (1) **Instruments**, under `scripts/`, that change no
runtime behavior: a capture auditor (the rewritten `mic_test.py`), a corpus tool that records one
continuous raw take per item and derives from it, offline, the exact clip the robot would upload, a
deterministic bench that runs the production decode function under named configurations, and a text
arm that separates «Whisper misheard» from «the rest misread». (2) **Seams with today's defaults**:
the Whisper call goes through one options structure whose code defaults are today's values (the bench
varies it; only what the evidence moves becomes a setting, in Task 12); the per-clip confidence is computed and logged; an «unclear speech» reply exists behind a threshold that
defaults to off; the robot gets a segmentation policy and an upload tail whose default reproduces
today's clip byte for byte. (3) **Decisions from evidence**: each candidate change has an adoption
rule written here before anything is measured; only adopted changes move defaults; the model choice
is recorded in ADR 0023. The server stays a generic audio API and the robot a generic audio client
(ADR-0002): the robot change is capture only, and the server never learns which device recorded.

**Tech Stack:** Python 3.12, faster-whisper 1.2.1 (CTranslate2 4.8.2), sounddevice 0.5.6 (PortAudio
MME and WASAPI), Silero VAD (robot), `soxr` (already a `server` dependency), FastAPI, pytest. A new
runtime dependency appears only if D-15 adopts the GPU.

**Spec:** Pipec's request of 2026-10-20 (summarized in *Why* and in D-1), [ADR-0002](../../adr/0002-server-robot-separation.md),
[ADR-0004](../../adr/0004-local-first-cognitive-policy.md) (no cloud STT), [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md)
(the preference gate and the answer grammar that consume the transcript), the *Evidence base* below,
and `.claude/rules/` (not tracked; read them from the working copy).

## Evidence base (checked 2026-10-20; nothing here depends on local notes)

**Facts from the code and the machine.**

- Whisper today (`server/src/server/settings.py`, `stt.py`): `small`, `int8`, CPU, beam 5, language
  `es` forced, `initial_prompt` «Conversación con un robot doméstico llamado Iroko.», no static
  hotwords (memory names and, in reply mode, `SHORT_REPLY_HOTWORDS`), `vad_filter=True` hard-coded
  with `VadOptions(min_silence_duration_ms=500)` (other fields at the library defaults: threshold
  0.5, `speech_pad_ms` 400, `min_speech_duration_ms` 0), `condition_on_previous_text=False`
  hard-coded. Everything else is a faster-whisper default: temperatures `[0.0, 0.2, 0.4, 0.6, 0.8,
  1.0]`, `best_of` 5, `compression_ratio_threshold` 2.4, `log_prob_threshold` −1.0,
  `no_speech_threshold` 0.6. Each segment's `avg_logprob`, `no_speech_prob`, `compression_ratio`
  and `temperature` reach only a DEBUG log; `transcribe` returns the text alone.
- **Dead setting (finding):** `WHISPER_HALLUCINATION_SILENCE_THRESHOLD=2.0` acts only inside
  faster-whisper's `if options.word_timestamps:` branch (`transcribe.py` around line 1294 in 1.2.1),
  and `word_timestamps` is off. D-13 decides it.
- **Whisper's punctuation decides intent (finding):** `memory/preference_gate.match_preference`
  refuses any transcript that contains «?» or «¿» (`NOT_A_TASTE`). A stated taste that Whisper
  writes as a question («¿Me gustan las películas de ciencia ficción?», seen 2026-10-20) can never
  become a candidate. D-12 decides it. `user_emotion` also reads «?», but there a mark only silences
  an emotion (it fails toward neutral); it is left as is.
- **The French turn (closed by evidence):** every Whisper language line in `logs/server.2026-10-19.log`
  (68 clips) and `logs/server.log` of 2026-10-20 (32 clips) says `es (100%)` — the language is forced.
  The French turns of Plans 0059 and 0063 were the model's replies, not transcripts.
- The robot (`robot/src/robot/audio_capture.py`) opens the default input with
  `sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=512)` and no `device=`;
  Silero closes the utterance after `VAD_SILENCE_MS=800` of silence, keeps `VAD_PREROLL_MS=400`
  before the onset and uploads the whole 800 ms silent tail (reply mode closes at 1600 ms and trims
  back to 800). The default device is «Microphone Array (Intel Smart Sound Technology)» (index 1,
  MME, 44.1 kHz, 4 channels), the array beside the camera; Windows resamples to 16 kHz and the
  vendor's processing (noise suppression, gain control) is on. A «Micrófono (USB Audio Device)» also
  exists that Pipec does not recognize: it is not used. Pipec speaks about 60 cm from the laptop.
- **Two silence filters in series:** Whisper's own filter removed a median of 0.40 s from clips the
  robot had already cut (2026-10-19: 68 clips, maximum 2.2 s; 2026-10-20: 32 clips, maximum 1.3 s),
  and it concatenates speech pieces with no pause between them. On 2026-10-19 28 requests ended in
  «No speech detected» (422).
- **Speed, uncontrolled:** STT took a median of 2.0 s (maximum 31.8 s) per turn on 2026-10-19 and
  6.3 s (maximum 14.6 s) on 2026-10-20, on the shared laptop (i7-11390H, 4 cores / 8 threads,
  15.7 GB RAM, plan «Equilibrado», VS Code, Chrome and Docker open). Whisper always decodes a padded
  30 s window, so the cost per request is almost fixed.
- GPU: NVIDIA MX450, 2 GB, driver 610.60; CTranslate2 4.8.2 sees one CUDA device and supports
  `float16` and `int8_float16` there, but loading a model fails with `cublas64_12.dll is not found`.
  The Hugging Face cache holds only `small` and `tiny`.
- Tools: `scripts/stt_probes.py` (`just probe-stt noise|first-turn`, synthetic only),
  `scripts/mic_test.py` (stale: default model `tiny`, prompt «…Omnibot.», `print`-based),
  `scripts/speaker_calibration*.py` (a recorder with a countdown, a start cue, Silero and clip
  guards). `tests/evals/` holds text-only golden cases; none for speech.

**External evidence.** Tags: **[V]** read in the source; **[F]** seen only in a search fragment;
**[I]** inference.

1. Chilean Spanish: syllable-final /s/ is aspirated or elided and intervocalic /d/ is almost always
   elided in informal speech (one speaker: 97 % of informal /d/) **[V]** —
   [Bolyanatz](https://www.oxy.edu/sites/default/files/assets/Faculty/bolyanatz_2012_s_and_d.pdf);
   «helado» ≈ [e'lao] is acoustically close to «de lado» **[I]**. Chilean yes/no questions rise at
   the end, with weaker cues than Peninsular Spanish **[V]** —
   [Pérez Mora 2024](https://diposit.ub.edu/items/91bb0853-3bea-4274-aeb3-4cf151d37e37/full).
   No usable phonetic statistics were found in RAE/ASALE, CORPES or PRESEEA-Santiago, and no
   verified Chilean sentence list exists for ASR (the audiometric lists are mostly unbalanced,
   [Burdiles-Aguirre 2024](https://www.revistaotorrino-sochiorl.cl/index.php/orl/article/view/492)) **[V]**.
   The Chilean corpus COSCACH combines word reading, minimal pairs, controlled texts and spontaneous
   conversation **[F]** — [Sadowsky](http://sadowsky.cl/research.html); the script below uses the
   same kinds of material, for recognition rather than for phonetics.
2. Model: on Chilean sets `small` is clearly worse than `large-v3` and `large-v3-turbo` (WER 7.99
   vs 4.6 and 2.86 on 4,374 Google samples; 10.34 vs 3.64 and 4.94 on Common Voice) **[V]** —
   [Chilean leaderboard](https://huggingface.co/spaces/idsudd/open_asr_leaderboard_cl/blob/7dfb852bee82c9b602548abb33213449c360e31b/results.csv);
   `medium` is not measured there. A `small` fine-tuned on one Chilean corpus overfits it **[V]**.
   Turbo int8 peaked at 1,545 MB of VRAM on long audio **[V]** —
   [faster-whisper #1030](https://github.com/SYSTRAN/faster-whisper/issues/1030); CTranslate2 ≥ 4.6.3
   makes cuDNN optional **[V]** — [changelog](https://raw.githubusercontent.com/OpenNMT/CTranslate2/master/CHANGELOG.md).
3. Decoding: the temperature fallback samples at random (not reproducible) **[V]** — library code;
   a prompt imitates style and vocabulary, «will not override the audio», and can add words on noise
   **[V]** — [OpenAI prompting guide](https://developers.openai.com/cookbook/examples/whisper_prompting_guide),
   **[F]** [arXiv 2503.06924](https://arxiv.org/pdf/2503.06924). No evidence that a prompt fixes an
   acoustic near-homophone **[I]**. No source says Whisper writes «¿?» from prosody **[I]**: its marks
   are not an intent signal.
4. Capture: Windows' default processing mode may apply echo cancellation, noise suppression, gain
   control and beamforming; «raw» mode must not **[V]** —
   [Microsoft](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/audio-signal-processing-modes);
   a speech developer reports fewer lost words with the enhancements off **[F]** —
   [Microsoft Q&A](https://learn.microsoft.com/answers/a/12277482). MME and DirectSound convert
   formats themselves; WASAPI shared converts only what it is asked to **[V]** —
   [python-sounddevice](https://python-sounddevice.readthedocs.io/en/0.5.3/api/platform-specific-settings.html).
   Clinical voice protocols record at 4–10 cm **[V]**/**[F]** — [PhenX](https://phenxtoolkit.org/protocols/view/201701);
   60 cm is outside every protocol but is the real use.
5. Confidence: `avg_logprob` and `no_speech_prob` are per window and not calibrated; Whisper is
   over-confident in noise **[F]** — [arXiv 2509.07195](https://arxiv.org/pdf/2509.07195).
6. Statistics: utterances from one speaker are correlated, so resample by item, not by utterance
   **[V]** — [Liu and Peng](https://ar5iv.arxiv.org/html/1912.09508). With about 90 % accuracy a
   95 % interval is about ±6 points at n = 100 and ±4 at n = 250 **[I]**.

## Task overview

| # | Task | Owner | Closes |
|---:|---|---|---|
| 0 | Revalidate the baseline | agent | — |
| 1 | Whisper's call goes through one options structure | agent | hard-coded values; the bench uses production code |
| 2 | Per-clip confidence and the «unclear» reply (off) | agent | «si Whisper duda, el robot lo dice» |
| 3 | The robot's segmentation over any source, and an upload tail | agent | replayable segmentation; short tail |
| 4 | The capture auditor (`mic_test.py` rewritten) | agent | device dump, levels, MME vs WASAPI |
| 5 | The reading script and the corpus tool | agent | private corpus, one take → two clips |
| 6 | Metrics and statistics | agent | WER, CER, punctuation, pairs, intervals |
| 7 | The bench | agent | configurations, latency, repeatability, calibration |
| 8 | The text arm | agent | «escuchó mal» vs «interpretó mal» |
| 9 | GPU feasibility | Pipec installs, agent probes | CUDA on the MX450 |
| 10 | Capture sessions | Pipec | the private corpus |
| 11 | Bench runs and the evaluation record | agent (server stopped) | the numbers |
| 12 | Adopted defaults | agent | settings that the evidence moved |
| 13 | The gate stops reading Whisper's marks (conditional) | agent | the lost-taste finding |
| 14 | GPU dependency (conditional) | agent | an optional extra, only if adopted |
| 15 | WASAPI capture on the robot (conditional) | agent | only if adopted |
| 16 | ADR 0023 and documentation truth | agent | the model decision on record |
| 17 | Hardware acceptance and cleanup | Pipec | live turns; corpus deleted |

## Global Constraints

- Local only: no cloud speech-to-text, ever (CLAUDE.md, ADR-0004). Downloading Whisper weights
  (`medium` ≈ 1.5 GB, `large-v3-turbo` ≈ 1.6 GB) into the local Hugging Face cache once is allowed.
- Private corpus: every WAV, transcript, manifest and per-clip result lives under
  `project-history/calibration/stt/` (ignored by git), is never committed, never pasted into a chat,
  never played by an agent, and is deleted at the end after Pipec types `delete`. Tracked records
  carry counts, rates and tallies per **scripted** item (the script is invented and tracked); nothing
  from the spontaneous session except aggregates.
- No real household data (names, pets, birth dates, ages) in anything tracked: the script uses
  invented content and passes `scripts/check_reserved_terms.py`.
- Audio contract: WAV, 16 000 Hz, mono, int16 at every boundary; every function that touches audio
  says so in its docstring. A 48 kHz or 44.1 kHz capture is converted with `soxr` before it becomes a
  WAV.
- Defaults do not move before Task 12: Tasks 1–3 are behavior-preserving (pinned by tests), and the
  API contract of `/transcribe` and `/transcribe/stream` changes only additively (no field removed or
  renamed).
- Every timed run states its machine conditions (charger, power plan, Chrome closed, server stopped,
  Docker state) in its output; Pipec prepares the laptop and stops the server before the agent runs
  Whisper for real.
- `uv pip install` only inside the scratchpad GPU environment of D-15; in the repository, a new
  dependency only through `uv add` and only if Task 14 runs.
- `ruff check` and `ruff format --check` over explicit paths including `scripts/` (the repository
  configuration skips `scripts/` but the pre-commit hook does not); `mypy server/src robot/src`
  clean; `just gate` green before the PR; commit titles of at most 72 characters (count them, then
  check `git log -1`).

## Decisions

1. **D-1 — Scope (Pipec, 2026-10-20).** In: everything between the mouth and the transcript —
   microphone, level and distance, capture format and host API, the robot's segmentation, Whisper's
   silence filter, model, quantization, decoding, prompt and hotwords, GPU, gain normalization,
   pauses and punctuation, the Chilean variety, a read script and a spontaneous session, and a text
   arm. Out, for later plans: intonation (question vs exclamation from pitch), other people's voices
   and impostors, a face-only fallback.
2. **D-2 — Where the corpus lives.** `project-history/calibration/stt/` beside
   `calibration/speaker/`: `takes/` (raw takes), `clips/` (derived robot clips), `manifest.jsonl`
   (one line per take: `take_id`, `item_id` or none, `session`, `condition`, `style`, `mode`
   `read`/`free`, raw path and SHA-256, clip paths and SHA-256, `reference`, `deviated`), `results/`
   (bench output, private), `report.md` (private). Every tool refuses a corpus root outside that
   directory. Deletion: `just stt-corpus cleanup`, only after Pipec types `delete`.
3. **D-3 — One take, two clips (design question a).** The corpus tool opens the default device with
   the robot's exact parameters (16 kHz, mono, int16, blocksize `CHUNK_FRAMES`, no `device=`) and
   lets the stream run and discards its first 0.5 s **before** anything is shown; it keeps samples
   from the start of the countdown, so every take has at least a second of lead-in before the voice.
   The start cue is **visual only** (`>>> HABLA <<<` in the console): no beep enters the take, and
   opening the device never costs an onset (the speaker tool's lost-onset incident, Plan 0047). The
   take is a **continuous raw take** for the item's window. «Raw» means before the robot's VAD, not
   before Windows: the vendor's processing is already in it, and only `c60-noenh` looks past it. The
   clip the robot would upload is derived **offline** by the robot's own code
   (`robot.audio_capture.segment_utterance`, Task 3) reading the raw take chunk by chunk with a fresh
   Silero state, exactly as live (where the robot is listening before the person speaks). Both come
   from the same samples, so any segmentation policy (pre-roll, closing silence, tail) can be replayed
   later without recording again. A test proves the offline path and the live path give the same
   bytes on the same chunks.
4. **D-4 — Reading and spontaneous speech stay apart (design question c).** Read takes have
   `mode=read`, an `item_id`, and the script text as reference unless Pipec answers «n» to «¿Leíste
   exactamente la frase?» and types what was actually said (`deviated=true`). The spontaneous session is one
   continuous raw recording of about 10 minutes, `mode=free`, no item; the robot's segmentation cuts
   it into clips and Pipec types each reference later (`annotate`, which plays each clip back to Pipec,
   accepts «inaudible» and asks «¿La frase seguía en el clip siguiente? [s/N]», which marks a split
   turn). Every table reports read and spontaneous separately; the bench's adoption
   rules use read speech only, and spontaneous speech is the reality check.
5. **D-5 — The script** (draft in Appendix A, tracked as `tests/evals/stt_reading_script.yaml`).
   Eight layers: A tastes (the same words as statement and as question), B confirmations, C
   questions and commands to the robot, D minimal pairs and reductions (careful and relaxed), E
   numbers and times (with accepted written alternatives), F Chilean markers, G pauses, H phonetic
   coverage (own sentences: no verified Chilean list exists, and the word lists of Tato C1 and
   Palacio 1 — the best balanced audiometric lists in Burdiles-Aguirre 2024 — could not be read
   from a verified source; if Pipec finds them, their words can replace H's). Critical items (B and D) ×5, the rest
   ×2, over two sessions on different days: **248 read takes** at the main condition. Pipec reviews
   and edits the script before the first capture; a changed item gets a new id.
6. **D-6 — Conditions.** Main: `c60` — 60 cm, Windows defaults, the robot's MME 16 kHz stream. A
   condition block of 24 items (marked in Appendix A), each once per condition in one session:
   `c60`, `c15` (10–15 cm, the near reference: if Whisper still fails there, the cause is the model
   or the pronunciation, not the distance), `c30` (a realistic closer placement), `c60-noenh`
   (Windows audio enhancements and Voice Clarity off), `c60-wasapi` (WASAPI shared in the device's
   native format, its channels averaged and resampled by `soxr`), `c60-noise` (a fan or a TV at a fixed volume and
   place, noted), `c60-fast` (relaxed, fast speech): 168 takes. Plus the spontaneous session `s4`.
   Order within a condition is shuffled with a seed derived from the session id. **A pilot is a
   go/no-go gate:** the 24 block items once at `c60` (session `s0`), benched with `P0` and `T0` end to
   end. The main sessions start only when (1) every take gave one clip, or the count is explained,
   (2) no take lost its first word to the capture (the raw take still has it), (3) `T0` gives the same
   text twice on every clip, (4) the level verdicts are not `clipped`. A failed check is a tool defect,
   fixed test-first before going on. Its takes count as the block's `c60` cell unless a fix changed the
   capture.
7. **D-7 — Metrics.** Text is normalized the same way on both sides: Unicode NFC, case folding,
   punctuation (including «¿» and «¡») replaced by spaces, spaces collapsed, diacritics **kept**
   («sí» ≠ «si»); an accent-folded figure is reported beside it. An item's reference may list written
   alternatives (E: «las 3 y media») and the best one counts. Per clip: word errors and reference
   length, character errors, exact match, the minimal-pair verdict (the target word present and the
   competitor absent), an empty transcript, the marks present. Per configuration: WER and CER
   (pooled), exact-match rate, minimal-pair accuracy, empty rate, question accuracy on the A pairs
   (a hypothesis with «?» or «¿» counts as a question), per-mark precision, recall and F1 for
   `¿ ? ¡ ! . ,` at utterance level, **critical-term errors** (a «no» gained or lost — a flipped
   negation; a wrong number on layer E; «Iroko» lost), **edge deletions** (the first or the last
   reference word deleted in the alignment — the signature of a silence filter that eats onsets or
   tails), latency (median, p90, maximum, and model load separately), peak memory of the process
   (Windows working set) and, on CUDA, peak VRAM, repeatability (share of clips whose text differs
   between two runs in one process). **A take the robot's segmentation cut in two** is scored twice
   and never as one sentence: *turn integrity* (the take arrived as one clip or not; what the robot
   would have answered is the first clip alone) and *lexical quality* (the transcripts of all its
   clips joined in order against the reference). WER and every rate are **pooled**: the sum of errors
   over the sum of reference words (or of clips), never a mean of per-clip rates. Intervals: a paired
   block bootstrap by script item (2,000 resamples, seed 69, 95 % percentile interval) that resamples
   whole items, recomputes the pooled figure of both configurations on each resample and keeps their
   difference; MAPSSWE at utterance level (paired z on per-clip word errors) beside it. Zero events get
   the rule-of-three bound. Every table states its n.
8. **D-8 — Configurations and stages** (Appendix B). Stage 1, on the **dev** half of the items (a
   seeded split by item, stable across runs): `P0` (production today) and one-factor changes from it,
   plus the segmentation policies replayed with the `P0` decoder. Stage 1 only **selects**: its numbers
   are exploratory and decide nothing by themselves. `C1` = `P0` plus every stage-1 change whose dev
   interval favours it (or, for a speed change, is within ±1 point with a faster median), written into
   the record **before** the test half is run. Stage 2 runs `C1` and `P0` once on the **test** half.
9. **D-9 — Adoption rule (proposal).** `C1` is adopted or rejected **as a whole**, on the test half,
   listing its components. Adopted when (a) the 95 % interval of its pooled WER difference against
   `P0` lies entirely below zero — or, if `C1` holds only speed changes, within ±1 point with a lower
   median latency; (b) it is **not worse on what changes an intention**: the interval of the difference
   in critical-term errors (negation flips, wrong numbers, «Iroko» lost) does not lie entirely above
   zero, and on layer B the share of answers `parse_memory_answer` reads as written does not fall;
   (c) the latency budget holds — **median ≤ 3.0 s and p90 ≤ 5.0 s per clip** on the main set under the
   timed-run conditions; (d) `just probe-stt noise` with `C1`'s settings returns non-echo text on at
   most 5 of 100 clips (Plan 0056 rule); (e) the empty rate does not rise on layer B. If `C1` fails,
   `P0` stays: no component is retried on the test half (that would tune on it). A model that needs
   the GPU to meet (c) is adopted only together with D-15. If `P0` itself misses the budget under the
   timed conditions, the budget becomes «no slower than `P0`» and the record says so. Latency is also
   measured **under load** (D-19): the GPU's case is that Whisper can run on the MX450 while Ollama
   holds the CPU, so a GPU configuration is judged on both the idle and the loaded figures. Capture
   conditions (D-16) are judged apart, on the block, paired by item, with the same interval.
10. **D-10 — The prompt variant is fixed now.** `PR-vocab` = «Conversación en español de Chile con
    Iroko, un robot doméstico: gustos, comidas, la hora y la casa. ¿Lo guardo? Sí. No. Autorizo.»
    (amended 2026-10-21: the first draft held the sentence of items B10 and G02, which inflated its
    own score; a test now fails if the prompt holds any scripted sentence of three words or more.)
    It names no scripted sentence; it exists to test vocabulary and «¿?» style. `PR-none` has
    no prompt. `HW` passes `SHORT_REPLY_HOTWORDS` on every clip.
11. **D-11 — The «unclear» reply (proposal; instrumentation now, rejection only on proof).**
    `avg_logprob` is a mean log-probability per token, not a calibrated probability of being right.
    Per clip, `TranscriptConfidence` keeps one coherent figure, the **token-weighted mean** of the
    segments' `avg_logprob` (the clip's mean per-token log-probability), plus, for diagnosis only,
    the highest `no_speech_prob`, `compression_ratio` and `temperature` and the segment count (robot
    clips are almost always one segment). An INFO record `stt.confidence` logs these numbers, the clip
    and post-VAD seconds and the verdict — never text. With `WHISPER_UNCLEAR_LOGPROB` set and the mean
    below it, a non-empty transcript raises `UnclearSpeechError`, and both voice routes answer
    `UNCLEAR_SPEECH_PHRASE = "No te entendí bien. ¿Me lo repites?"` (tuteo neutro) as a
    deterministic plan: the controller is not called, nothing is written, no grant is spent, the
    stream's `done.expects_short_reply` repeats the request's `short_reply` (an answer heard badly is
    asked for again in reply mode). **Default off**, and it stays off unless all of this holds: Task
    11 sets the threshold on the dev half as the highest value that rejects at most 5 % of fully
    correct clips; on the test half there are **at least 30 clips with a word error** (fewer and the
    catch rate is noise); there it rejects **≤ 5 % of fully correct clips overall and ≤ 5 % on layer B**
    (a robot that keeps asking to repeat «sí» or «acepto» is worse than one that sometimes mishears),
    and catches **≥ 50 % of clips with a word error**, each rate with its 95 % interval; and Pipec
    confirms after reading the numbers. Otherwise the record says why, and the confidence log keeps
    collecting real turns for a later decision.
12. **D-12 — Whisper's marks and the taste gate: measure, then Pipec decides (no automatic change).**
    The finding is real: a statement Whisper writes as a question is never proposed as a taste. But
    «Me gusta el helado» and «¿Me gusta el helado?» have the same words, so without the marks and
    without prosody (out of scope, D-1) no lexical rule can tell them apart; replacing the punctuation
    test with a word rule would trade a lost taste for a question proposed as a taste. Task 11 measures
    both directions on the A pairs: the share of **statement** takes Whisper writes with «?» or «¿»
    (lost tastes) and the share of **question** takes it writes without them (questions the gate would
    take as statements today). The record puts both numbers in front of Pipec with the options —
    keep the gate; or a word rule (refuse interrogative openers and a final tag, accept the rest),
    whose cost is that a first-person yes/no question can become an offer that still needs the
    explicit answer of ADR 0021. Task 13 runs only on Pipec's explicit choice of the second option;
    the real fix, intonation, is a later plan.
13. **D-13 — The dead setting.** Stage 1 runs `WT` (`word_timestamps=True` with the 2.0 s silence
    threshold). If it is not adopted under D-9, Task 12 removes `whisper_hallucination_silence_threshold`
    and its `.env.example` line (settings ignore unknown variables, so an old `.env` keeps working).
14. **D-14 — What stays fixed in code.** `condition_on_previous_text=False` (a clip is one 30 s
    window, so there is no previous text), `patience` (no evidence), `num_workers` (one robot, one
    request at a time) — each with a one-line comment in `stt.py`.
15. **D-15 — GPU.** The agent's harness refused `uv pip install` on 2026-10-20 even after Pipec's
    verbal yes, so **Pipec runs** the two install commands of Task 9 in the scratchpad. CUDA 12 cuBLAS
    first; cuDNN 9 only if loading still fails; `small` first, and `medium` or `large-v3-turbo` on CUDA
    only once `small` runs there. The repository venv never receives them: the bench points CTranslate2
    at the scratch DLL directory (`--cuda-dll-dir`) and keeps the handle `os.add_dll_directory` returns
    for the whole process. VRAM is **sampled during inference** (`nvidia-smi --query-gpu=memory.used
    --format=csv,noheader -lms 100` in a child process while the clips run), not read once afterwards.
    Adopted only under D-9 and with at least 200 MB of VRAM left at the sampled peak while the desktop
    runs; then Task 14 declares
    an optional `cuda` extra of `server` with `uv add --optional cuda`, so the CPU install does not
    change. Otherwise nothing is added and ADR 0023 says why.
16. **D-16 — Capture changes.** If `c60-noenh` beats `c60` under D-9 (paired by item on the block),
    the operator manual tells Pipec to switch the enhancements off (no code). If `c60-wasapi` beats
    `c60`, Task 15 adds WASAPI capture to the robot. WASAPI shared still passes through the Windows
    audio engine and its effects (the tool opens the device's own format, so Windows converts nothing,
    but the signal is not raw), so `c60-wasapi` compares **resamplers** (Windows' MME conversion against `soxr`), and
    `c60-noenh` compares **processing**. If `c30` beats `c60` by a wide margin, the manual states the
    distance; it is a placement fact for the Pi's microphone (electronics track 1).
17. **D-17 — Segmentation.** A pause closes the turn when it is longer than the closing silence,
    whatever that silence is: a 2 s pause splits at 800 ms **and** at 1600 ms. So the question is not
    «which policy keeps a 2–3 s pause» (only a closing silence above 3 s would, adding that much delay
    to every turn) but **how long Pipec's pauses inside a sentence are**. The raw takes answer it: for
    every G take and every spontaneous clip Pipec marks as continued (D-4), the bench measures the
    silent gap between speech bursts in the raw take. Policies replayed offline (Appendix B): closing
    silence 800 / 1200 / 1600 ms × upload tail 800 / 500 / 300 ms, pre-roll 400 / 600 ms. Reported:
    the distribution of in-sentence pauses, the share each closing silence keeps in one clip, the
    delay it adds to every turn (its own length), the split rate, the rate of clips under 1.5 s and
    WER. Today's 800 / 800 / 400 changes only under D-9; the tail and the pre-roll never go under
    300 ms. Keeping 2–3 s pauses in one turn needs an end-of-turn strategy, not a longer silence: a
    finding for a later plan if the pauses measured are that long.
18. **D-18 — ADR 0023.** «Speech-to-text model and decoding for the owner's voice»: the measured
    table, the chosen model, compute type, device and decoding defaults, the latency budget, the GPU
    disposition, the unclear threshold, and what triggers a new measurement (the homelab server, the
    Raspberry Pi's microphone, a new model). `Proposed` in Task 16, `Accepted` when Pipec closes the
    plan.
19. **D-19 — Latency under load.** The logs show STT medians of 2.0 s one day and 6.3 s the next on
    the same machine; the suspected cause, contention with the model's background work, is unproven.
    Task 11 times `P0` (and the best GPU configuration, if any) on the dev half twice: idle, and while
    `just eval-chat --mode stream --runs 20` keeps Ollama generating in another terminal. Both figures go in the
    record; this measures the laptop, and the homelab stays PC-5's.
20. **D-20 — An outside reference, optional (Pipec's choice).** Pipec may read the 24 block items
    into the dictation tool Pipec already uses and save its text output in a private file; the bench
    scores it like any configuration (`--external`). It is a ceiling for «what this room and this
    voice allow», not a candidate: no cloud service enters the runtime path (ADR-0004), and the record
    names the tool and the microphone it used, which may differ from the robot's.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/` (all).
- ADR-0002, ADR-0004, ADR 0021 (decision 9 and its amendments); `docs/architecture/current-state.md`
  (the STT row and the streaming row); [Plan 0056](../completed/0056-voice-pipeline-reliability-and-diagnostics.md)
  (the probes and their rules), [Plan 0067](../completed/0067-reply-listening-mode.md) (reply mode),
  [Plan 0068](0068-short-clip-speaker-measurement.md) (the retry and the short-clip study).
- `server/src/server/{stt,settings,pipeline,exceptions}.py`, `server/src/server/routers/transcribe.py`,
  `server/src/server/streaming.py`, `server/src/server/cognition/response_plan.py`,
  `server/src/server/memory/preference_gate.py`, `server/src/server/cognition/intent_resolution.py`
  (`resolve_information_need`, `parse_memory_answer`), `robot/src/robot/{audio_capture,vad,settings}.py`,
  `scripts/{stt_probes,mic_test,speaker_calibration,speaker_calibration_corpus}.py`, `justfile`,
  `.env.example`, `docs/runbooks/operator-manual.md`.

## Review Focus

1. A clip Whisper doubts while a one-use PIN token is attached: the unclear phrase, the token still
   valid for the next turn, nothing written, the controller never called (Task 2).
2. An unclear answer in reply mode keeps reply mode (`done.expects_short_reply` true); an unclear
   ordinary turn does not switch it on; an empty transcript is still a 422, never the phrase (Task 2).
3. With default settings the Whisper call receives exactly today's arguments, and the robot uploads
   byte-identical clips, in both normal and reply mode (Tasks 1 and 3).
4. A raw take with a 1.2 s pause gives two clips at closing silence 800 ms and one at 1600 ms (a 2 s
   pause gives two at both); a take with no speech gives no clip, never an empty WAV; a take that
   ends mid-word still closes; a split take is scored as turn integrity and lexical quality, never as
   one sentence (Tasks 3, 5 and 7).
5. Private data stays in the corpus root: `mic_test --save` and every corpus or bench command refuse
   another root, the bench report shows only aggregates for `mode=free`, and `git status` never lists
   a file under `project-history/` (Tasks 4, 5 and 7).

---

## Task 0: Revalidate the baseline

- [ ] Status `Ready`; branch `feat/0069-stt-audit` from `main` (`git checkout -b`); `just gate` and
  record the count (3654 at the close of Plan 0068's code); `rg -n "def _whisper_text|vad_filter=True|def capture_utterance|def _trim_trailing_silence|\"?\" in text" server/src robot/src`
  finds what this plan names. If anything differs, stop and report.

## Task 1: Whisper's call goes through one options structure

**Files:** `server/src/server/stt.py`; test `tests/unit/test_stt_decode_options.py` (new); run
`tests/unit/test_stt_echo_guard.py`, `tests/unit/test_stt_hotwords.py`,
`tests/slow/test_stt_transcription.py`.

The experimental parameters live in a structure the bench varies, **not** in new environment
variables: a parameter becomes a setting in Task 12 only if the evidence moves it (or an operator
needs to tune it). Today's existing Whisper settings keep feeding the structure.

**Interfaces — Produces:**
- `@dataclass(frozen=True) class WhisperDecodeOptions` with the fields `language`, `beam_size`,
  `initial_prompt`, `vad_min_silence_ms`, `hallucination_silence_threshold` (from today's settings)
  and, with today's values as **code defaults**, `best_of: int = 5`, `temperatures: tuple[float, ...]
  = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)`, `compression_ratio_threshold: float | None = 2.4`,
  `log_prob_threshold: float | None = -1.0`, `no_speech_threshold: float | None = 0.6`,
  `vad_filter: bool = True`, `vad_threshold: float = 0.5`, `vad_min_speech_ms: int = 0`,
  `vad_speech_pad_ms: int = 400`, `word_timestamps: bool = False`, `input_peak_dbfs: float | None =
  None`. (`cpu_threads` is a model-construction argument: the bench's `BenchConfig` carries it, and
  production keeps CTranslate2's default.)
- `def decode_options(source: Settings) -> WhisperDecodeOptions` (reads only existing settings).
- `@dataclass(frozen=True) class TranscriptConfidence(avg_logprob: float, no_speech_prob: float,
  compression_ratio: float, temperature: float, segments: int)` — `avg_logprob` is the token-weighted
  mean over segments, the other three the highest values (D-11).
- `@dataclass(frozen=True) class Transcript(text: str, confidence: TranscriptConfidence | None,
  clip_s: float, after_vad_s: float)` — `confidence` is `None` when Whisper returned no segment.
- `def run_whisper(model: WhisperModel, audio: bytes, options: WhisperDecodeOptions, hotwords: str |
  None) -> Transcript` — the one place that calls `model.transcribe`; the bench calls it too.
- `def normalize_peak(samples: np.ndarray, target_dbfs: float) -> np.ndarray` — float32 in, float32
  out, all-zero input returned unchanged; used by `run_whisper` only when `input_peak_dbfs` is set
  (then the WAV is decoded to a float32 array at 16 kHz and passed as an array; otherwise the bytes
  go in as today).

- [ ] **Failing tests:** a fake model records the keyword arguments of `transcribe`;
  `stt._transcribe_sync(wav, None)` under `Settings()` passes exactly `language="es"`, `beam_size=5`,
  `best_of=5`, `temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)`, `compression_ratio_threshold=2.4`,
  `log_prob_threshold=-1.0`, `no_speech_threshold=0.6`, the settings prompt, `hotwords=None`,
  `condition_on_previous_text=False`, `word_timestamps=False`,
  `hallucination_silence_threshold=2.0`, `vad_filter=True` and `vad_parameters ==
  VadOptions(min_silence_duration_ms=500)` (equal field by field: threshold 0.5, `speech_pad_ms` 400,
  `min_speech_duration_ms` 0), and an in-memory WAV (not an array). `run_whisper` with two fake
  segments of 10 and 30 tokens and log-probs −0.2 and −1.0 returns the joined text and a confidence
  of −0.8 (token-weighted), the highest no-speech, compression and temperature, and `segments == 2`;
  with none, `confidence is None`. `normalize_peak` brings a −20 dBFS tone to −3.0 ± 0.1 dBFS and
  leaves zeros as zeros; with `input_peak_dbfs=-3.0` the fake model receives a float32 array whose
  peak is −3.0 ± 0.1 dBFS. RED: `run_whisper` does not exist.
- [ ] **Implement:** `_whisper_text` becomes a thin wrapper over `run_whisper(_get_model(), audio,
  decode_options(settings), hotwords).text`; the echo guard is unchanged; D-14's comments.
- [ ] Run the four test files; `uv run ruff check server/src tests/unit/test_stt_decode_options.py`;
  `uv run mypy server/src robot/src`. **Commit** `refactor(server): one options structure for whisper`.

## Task 2: Per-clip confidence and the «unclear» reply (off by default)

**Files:** `server/src/server/stt.py`, `server/src/server/exceptions.py`,
`server/src/server/settings.py`, `.env.example`, `server/src/server/cognition/response_plan.py`,
`server/src/server/routers/transcribe.py`; tests `tests/unit/test_stt_confidence.py` (new),
`tests/integration/test_unclear_speech_routes.py` (new); run `tests/integration/test_transcribe_stream.py`,
`tests/integration/test_transcribe_pipeline.py`, `tests/integration/test_api_contract.py`,
`tests/unit/test_architecture_guards.py`.

**Interfaces.** Consumes `Transcript`, `TranscriptConfidence`, `run_whisper` (Task 1). Produces:
`class UnclearSpeechError(Exception)` with attribute `text: str` and a fixed message that never
contains it (not a subclass of `TranscriptionError` or `ValueError`, so `pipeline._run_stt` lets it
through); `def is_unclear(confidence: TranscriptConfidence | None, threshold: float | None) -> bool`;
setting `whisper_unclear_logprob: float | None = None`; `InformationNeed.UNCLEAR_SPEECH =
"unclear_speech"`; `UNCLEAR_SPEECH_PHRASE`; `def unclear_speech_plan(*, expects_short_reply: bool)
-> ResponsePlan` (deterministic, beside `scene_unavailable_plan`). `stt.transcribe` keeps its
signature and return type (`str`); the about seventy tests that replace it keep working.

- [ ] **Failing tests:** `is_unclear` is false for `None` threshold, for `None` confidence and for a
  log-prob equal to the threshold, true below it. `_transcribe_sync` raises `UnclearSpeechError`
  carrying the text when the threshold is set and the clip is below it; an echo still returns `""`
  first. The `stt.confidence` record has the four numbers, `segments`, `clip_s`, `after_vad_s` and `unclear`,
  and no transcript text (assert a sentinel word is absent). Routes, with `stt.transcribe` replaced
  by a fake that raises `UnclearSpeechError("palabra centinela")`: classic `/transcribe` answers 200
  with `llm_response == UNCLEAR_SPEECH_PHRASE`; the stream's events carry the phrase and
  `done.expects_short_reply` equals the request's `short_reply` (true and false cases); a fake
  `_voice_controller` that fails if called is never called; with an owner unlock token attached the
  next turn can still spend it; nothing is written to the candidate table. An empty transcript is
  still 422. RED: the error and the plan do not exist.
- [ ] **Implement** the confidence log, the gate in `_transcribe_sync`, the error, the plan, and one
  branch in each route around `_run_stt` (classic through the deterministic synthesis path, stream
  through `stream_response_plan`; `text_heard` is the doubtful transcript); the turn log records the
  need.
- [ ] Run the listed files; lint and types. **Commit** `feat(server): say it was unclear when whisper doubts`.

## Task 3: The robot's segmentation over any source, and an upload tail

**Files:** `robot/src/robot/audio_capture.py`, `robot/src/robot/settings.py`, `.env.example`; test
`tests/unit/test_audio_capture.py`.

**Interfaces — Produces:** `CHUNK_FRAMES: Final = 512` (public; `_CHUNK_FRAMES` goes);
`class ChunkSource(Protocol)` with `def read(self, frames: int) -> tuple[np.ndarray, bool]`;
`@dataclass(frozen=True) class SegmentationPolicy(preroll_ms: int, close_silence_ms: int,
upload_tail_ms: int)` with `@classmethod from_settings(cls, close_silence_ms: int | None = None)`;
`async def segment_utterance(source: ChunkSource, vad: VoiceActivityDetector, policy:
SegmentationPolicy, *, max_wait_s: float = 30.0) -> bytes` (WAV 16 kHz mono int16, or `b""`);
setting `vad_upload_tail_ms: int = Field(default=800, ge=300)`. `capture_utterance(max_wait_s, *,
close_silence_ms=None)` keeps its signature: it opens the `sd.InputStream` and delegates.

- [ ] **Failing tests:** with a fake source and a scripted fake VAD, `segment_utterance` under
  `SegmentationPolicy.from_settings()` returns the same bytes as today's `capture_utterance` on the
  same chunks, in normal mode and in reply mode (pin built from today's code before the change); with
  close 800 and tail 300, the clip keeps exactly `round(0.3 / 0.032)` silent chunks after the last
  speech chunk, in both modes; a tail longer than the collected silence cuts nothing;
  `vad_upload_tail_ms=200` fails validation; a source that only returns silence gives `b""` after
  `max_wait_s`. RED: `segment_utterance` and the tail do not exist.
- [ ] **Implement:** `_trim_trailing_silence` cuts to `policy.upload_tail_ms` in both modes (reply mode
  already cut to the normal tail; by default the tail equals `vad_silence_ms`, so nothing changes).
  Document the new variable in `.env.example`.
- [ ] Run the robot tests (`uv run pytest tests/unit/test_audio_capture.py tests/unit/test_robot_app.py -v`);
  lint and types. **Commit** `feat(robot): segment from any source and set the upload tail`.

## Task 4: The capture auditor (`mic_test.py` rewritten)

**Files:** `scripts/mic_test.py` (rewritten), `scripts/stt_audio_levels.py` (new), `justfile`
(`mic-test`); tests `tests/unit/test_stt_audio_levels.py`, `tests/unit/test_mic_test.py` (new).

**Interfaces — Produces** in `stt_audio_levels.py`: `@dataclass(frozen=True) class LevelReport(peak_dbfs:
float | None, speech_rms_dbfs: float | None, floor_dbfs: float | None, snr_db: float | None,
clipped_fraction: float)`; `def level_report(samples: np.ndarray, sample_rate: int = 16_000) ->
LevelReport` (int16 input; 20 ms frames; speech = 90th percentile of frame RMS, floor = 10th
percentile; `None` fields for an all-zero clip); `def level_verdicts(report: LevelReport) ->
dict[str, str]` against the targets peak −12…−3 dBFS, speech RMS −30…−20 dBFS, zero clipped samples,
floor ≥ 30 dB under speech (labels `ok`, `low`, `high`, `clipped`); `def to_contract(samples:
np.ndarray, source_rate: int, channels: int) -> np.ndarray` (mean over channels, `soxr` to 16 kHz,
int16).

- [ ] **Failing tests:** a −6 dBFS sine reports peak −6.0 ± 0.1 and SNR `None`-safe; zeros give
  `None` fields and no warning; a full-scale square wave reports `clipped_fraction` ≥ 0.99; speech
  bursts over a −60 dBFS floor report a floor of −60 ± 1 and an SNR within 1 dB of the constructed
  value; `to_contract` turns 1 s at 48 kHz, two channels, into 16,000 int16 samples and keeps a
  1 kHz tone within 0.5 dB; 44.1 kHz works too. CLI: `devices` lists every input with index, name,
  host API, channels, default rate and the default marker (a fake `sounddevice` in the test), and
  `--save` writes the dump as JSON under the corpus root only; `record --save PATH` with `PATH`
  outside `project-history/calibration/stt/` is refused before any capture; `--prompt` and
  `--hotwords` take `nargs="+"`. RED: the module does not exist.
- [ ] **Implement:** `just mic-test devices [--save]` and `just mic-test record --seconds 6 [--api mme|wasapi]
  [--save NAME] [--transcribe] [--model M] [--beam-size N] [--prompt WORDS...] [--hotwords WORDS...]`.
  `record --api mme` opens the default device exactly like the robot; `--api wasapi` opens the WASAPI
  device of the same name in its native format (its rate, every channel, float32, no `auto_convert`;
  amended 2026-10-20: one channel through `auto_convert` came back garbled and half as long, and so
  did the native format through PortAudio's blocking read, which took 19 s for 9 s of audio with no
  overflow flag; WASAPI is read through the stream callback) and converts with `to_contract`; an
  overflow, or a take that took longer than its audio, is logged; the opened rate is checked and
  printed.
  `--transcribe` uses `server.stt.run_whisper` with `decode_options(settings)` and the overrides
  given. Logging, not `print`, except the final report table (`# noqa: T201` with the reason).
- [ ] Tests; `uv run ruff check scripts/mic_test.py scripts/stt_audio_levels.py tests/unit/test_stt_audio_levels.py tests/unit/test_mic_test.py`.
  **Commit** `feat(scripts): audit microphone capture, levels and host API`.

## Task 5: The reading script and the corpus tool

**Files:** `tests/evals/stt_reading_script.yaml` (new; Appendix A), `scripts/stt_corpus.py` (new),
`scripts/stt_corpus_models.py` (new), `justfile` (`stt-corpus`); test `tests/unit/test_stt_corpus.py`.
Reuse, do not copy: `write_new_file_atomic`, `resolve_corpus_path` and `sha256_of_file` from
`scripts/speaker_calibration_corpus.py`.

**Interfaces.** Consumes `segment_utterance`, `SegmentationPolicy`, `CHUNK_FRAMES` (Task 3),
`level_report`, `to_contract` (Task 4). Produces in `stt_corpus_models.py`: `ScriptItem(id: str, text:
str, also: tuple[str, ...], layer: str, kind: str, pair: str | None, target: str | None,
competitor: str | None, reps: int, window_s: float, block: bool, chat: bool, expect:
dict[str, str])`; `def load_script(path: Path) -> tuple[ScriptItem, ...]`; `Take(...)` with the
fields of D-2; `def append_take(manifest: Path, root: Path, take: Take) -> None`; `def
load_takes(manifest: Path, root: Path) -> list[Take]`; `DEFAULT_STT_CORPUS_ROOT = Path("project-history/calibration/stt")`;
in `stt_corpus.py`: `def segment_take(raw: np.ndarray, policy: SegmentationPolicy) -> list[bytes]`
(feeds the take chunk by chunk to `segment_utterance` with a fresh VAD, followed by silence so the
last utterance closes; repeats on the remainder; returns every clip in order).

- [ ] **Failing tests:** `load_script` on the real YAML: unique ids, known layers, every `pair` has two
  members, every D item has `target` and `competitor`, B and D have `reps` 5, `window_s` ≥ 4, 24 items
  have `block: true`, `check_reserved_terms` passes on the file. `segment_take` with a fake VAD: two
  speech bursts 1.2 s apart give two clips at close 800 ms and one at 1600 ms, and 2 s apart give two
  at both; silence gives `[]`; a
  burst that reaches the end of the take still yields one clip. A take round-trips through the
  manifest with both hashes; a root outside the default is refused; a deviated take keeps the typed
  reference; `cleanup` deletes nothing unless the typed answer is exactly `delete`. The capture path
  is tested with a fake recorder (no microphone): it saves the raw take and the derived clips and
  appends one manifest line per take. RED: nothing exists.
- [ ] **Implement** the CLI: `capture --session S --condition C [--layers A,B] [--block] [--style careful|relaxed]`
  (opens and settles the stream first, shows the text, counts down, shows the visual cue, keeps the
  item's window from the countdown on, shows the level
  verdicts, offers «r» to retake, asks «¿Leíste exactamente la frase? [S/n]»), `free --session S
  --minutes 10`, `annotate --session S` (plays each clip, Pipec types the reference or «inaudible»),
  `validate` (files, hashes, counts per item, condition and session against D-5 and D-6),
  `cleanup`. `--condition c60-wasapi` captures as in Task 4. Fill each item's `expect` (intent need,
  taste yes or no, answer accept, reject or none) from today's `resolve_information_need`,
  `match_preference` and `parse_memory_answer` on the script text, and list them for Pipec's review
  in Task 10; an expectation Pipec marks wrong is a «rest» finding, not a script error.
- [ ] Tests; ruff on explicit paths; `uv run python scripts/check_reserved_terms.py`. **Commit**
  `feat(scripts): reading script and private corpus for the stt study`.

## Task 6: Metrics and statistics

**Files:** `scripts/stt_metrics.py` (new); test `tests/unit/test_stt_metrics.py`.

**Interfaces — Produces:** `def normalize(text: str, *, fold_accents: bool = False) -> str`;
`def word_errors(reference: str, hypothesis: str) -> tuple[int, int]` (edits, reference words);
`def char_errors(reference: str, hypothesis: str) -> tuple[int, int]`; `def best_reference(references:
Sequence[str], hypothesis: str) -> str`; `def marks(text: str) -> frozenset[str]` over `¿ ? ¡ ! . ,`;
`def mark_scores(pairs: Sequence[tuple[str, str]]) -> dict[str, tuple[float, float, float]]`;
`def pair_correct(hypothesis: str, target: str, competitor: str) -> bool`; `@dataclass(frozen=True)
class CriticalErrors(negation_flip: bool, number_wrong: bool, wake_word_lost: bool)` and `def
critical_errors(reference: str, hypothesis: str, *, numbers: bool) -> CriticalErrors` (a flip is a
different count of the word «no»; `numbers` is set for layer E, where any number word or digit group
that differs after `best_reference` counts); `def edge_deletions(reference: str, hypothesis: str) ->
tuple[bool, bool]` (first, last reference word deleted in the word alignment); `def
block_bootstrap_diff(a: Mapping[str, Sequence[tuple[int, int]]], b: Mapping[str, Sequence[tuple[int,
int]]], *, resamples: int = 2000, seed: int = 69) -> tuple[float, float, float]` (difference, low,
high of the **pooled** rate; keys are item ids, values per-clip `(errors, words)` — or `(wrong, 1)`
for a rate per clip — paired; each resample draws whole items and recomputes Σ errors / Σ words for
both sides); `def mapsswe(a: Sequence[int], b: Sequence[int]) ->
tuple[float, float]` (z, two-sided p); `def rule_of_three(n: int) -> float`; `def
calibrate_threshold(dev: Sequence[tuple[float, bool]], test: Sequence[tuple[float, bool]], *,
max_false_reject: float = 0.05) -> CalibrationResult` (`threshold`, test `false_reject`, test
`catch`, n of each).

- [ ] **Failing tests:** `word_errors("Me gusta el helado.", "me gusta de lado") == (2, 4)`;
  `normalize("¿Qué hora es?") == "qué hora es"`; «sí» vs «si» is one error and zero with
  `fold_accents=True`; `best_reference(["son las tres y media", "son las 3 y media"], "son las 3 y
  media")` picks the second; `marks("¿Sí? ¡Ya!") == {"¿", "?", "¡", "!"}`; `pair_correct("dijo de
  lado", "helado", "de lado") is False`; `critical_errors("No quiero que apagues la luz.", "quiero que
  apagues la luz", numbers=False).negation_flip is True`; «Iroko, ¿me escuchas?» heard as «y roco me
  escuchas» loses the wake word; `edge_deletions("sí autorizo que lo guardes", "autorizo que lo")
  == (True, True)`; the bootstrap is reproducible with its seed, its interval
  contains the true difference on a constructed pair and collapses to zero for identical inputs;
  `mapsswe` of identical inputs has z = 0; `rule_of_three(100) == 0.03`; `calibrate_threshold` picks
  the highest threshold whose dev false-reject is ≤ 5 % on a constructed set. RED: no module.
- [ ] Implement (Levenshtein over words and characters; no new dependency). Ruff on explicit paths.
  **Commit** `feat(scripts): stt metrics with paired intervals`.

## Task 7: The bench

**Files:** `scripts/stt_bench.py` (new), `scripts/stt_bench_configs.py` (new), `justfile`
(`stt-bench`); test `tests/unit/test_stt_bench.py`.

**Interfaces.** Consumes `WhisperDecodeOptions`, `decode_options`, `run_whisper` (Task 1),
`segment_take`, `load_script`, `load_takes` (Task 5), the metrics (Task 6). Produces
`@dataclass(frozen=True) class BenchConfig(name: str, model: str, device: str, compute_type: str,
cpu_threads: int, options: WhisperDecodeOptions)`; `def configs(base: WhisperDecodeOptions) ->
dict[str, BenchConfig]` (Appendix B, built with `dataclasses.replace` from `P0`); `def
split_items(item_ids: Sequence[str], seed: int = 69) -> tuple[frozenset[str], frozenset[str]]`.

- [ ] **Failing tests** (fake model, a synthetic three-item manifest under `tmp_path`): `P0` equals
  `decode_options(Settings())` with `small`/`int8`/`cpu`; every other configuration differs from `P0`
  in exactly the fields Appendix B names; the dev/test split is stable for a seed and puts every take
  of an item on one side; `run` loads each (model, device, compute) once, times every clip after a
  warm-up, writes one JSONL line per clip and run with the text, the confidence and the seconds;
  `report` aggregates by D-7 with n per table, compares each configuration with `P0` through
  `block_bootstrap_diff` and `mapsswe`, and prints nothing from `mode=free` but counts and rates (a
  sentinel reference never appears); a configuration whose model fails to load is reported as
  `unavailable` with the error class, not as a crash; `probe` builds a synthetic 3 s clip and reports
  load time and four timings; every run line carries `peak_working_set_mb` (`None` off Windows) and
  the `--conditions` words; `--external FILE --label NAME` scores a filled-in template
  (`item_id<TAB>hypothesis`, one line per block item, written by `external-template`) like a
  configuration, with no latency. RED: no module.
- [ ] **Implement** `just stt-bench run --configs NAME... --half dev|test|all --repeat 2 [--segmentation POLICY]
  [--cuda-dll-dir PATH] --conditions WORDS...`, `segment --policies POLICY...`, `report --runs ID...`,
  `calibrate --run ID`, `probe --model M --device D --compute C [--cuda-dll-dir PATH]`,
  `external-template`. `--cuda-dll-dir` calls `os.add_dll_directory` before loading (Windows only).
  The peak working set comes from `GetProcessMemoryInfo` through `ctypes` (no new dependency). Models other than those cached are
  downloaded once with `local_files_only=False` after printing their size. On `cuda`, `run` and
  `probe` sample VRAM during inference with a child `nvidia-smi --query-gpu=memory.used
  --format=csv,noheader -lms 100` and keep the peak; the `os.add_dll_directory` handle lives for the
  whole process. A take with several clips is scored per D-7 (turn integrity on the first clip,
  lexical quality on all clips joined), and `segment` writes the silent gaps between speech bursts of
  every G take and every spontaneous clip marked as continued (D-17).
- [ ] Tests; ruff on explicit paths. **Commit** `feat(scripts): deterministic stt bench`.

## Task 8: The text arm

**Files:** `scripts/stt_text_arm.py` (new); test `tests/unit/test_stt_text_arm.py`.

**Interfaces.** Consumes the bench's per-clip JSONL and `load_script`. Produces `def attribute(item:
ScriptItem, reference: str, hypothesis: str) -> str` returning `ok`, `stt` (the reference text gives
the expected outcome, the hypothesis does not), `rest` (the reference text itself does not give the
expected outcome) or `both`, judged on the expectation fields the item has (`need` through
`resolve_information_need`, `taste` through `match_preference`, `answer` through
`parse_memory_answer`).

- [ ] **Failing tests:** «Sí, autorizo.» heard as «sí autoriso» → `stt`; «Me gustan las películas de
  ciencia ficción.» heard with «¿…?» → `stt` (today's gate); an item whose reference already fails its
  expectation → `rest`; a correct hypothesis → `ok`. RED: no module.
- [ ] **Implement** and add `just stt-text-arm --run ID` (counts per layer and outcome; scripted item ids
  allowed, never spontaneous text). The manual chat arm is Task 10's last step (Pipec types the
  `chat: true` items in `just chat-test` and counts the replies that understood). Ruff. **Commit**
  `feat(scripts): attribute errors to the stt or to the reader`.

## Task 9: GPU feasibility (Pipec installs, the agent probes)

- [ ] Pipec, in the Claude prompt (the `!` prefix runs it in this session), with the scratchpad path
  the agent gives:
  `! uv venv <scratch>/gpu-venv --python 3.12` then
  `! uv pip install --python <scratch>/gpu-venv/Scripts/python.exe nvidia-cublas-cu12`.
- [ ] Read-only baseline, before and after the install: `nvidia-smi` (driver, free memory with the
  desktop running) and `where.exe cublas64_12.dll`.
- [ ] The agent, after Pipec prepares the laptop (D-9 conditions, server stopped):
  `just stt-bench probe --model small --device cuda --compute int8_float16 --cuda-dll-dir <scratch>/gpu-venv/Lib/site-packages/nvidia/cublas/bin`
  and the same with `float16`, then `large-v3-turbo` and `medium` with `int8_float16`. If a load fails
  on a missing cuDNN library, Pipec adds `nvidia-cudnn-cu12==9.*` to the same environment and the
  probe repeats with both `bin` directories. Record: loads or not, load seconds, the four timings,
  peak VRAM, the driver. The GPU configurations of Appendix B run in Task 11 only if `small` loads.

## Task 10: Capture sessions (Pipec runs everything)

The agent gives the exact commands, one session at a time, and never runs them.

- [ ] **Before the first session:** Pipec reads Appendix A in `tests/evals/stt_reading_script.yaml`,
  edits what Pipec would not say, and reviews the `expect` list from Task 5; dictation off; Chrome
  closed; the server and the robot stopped.
- [ ] **Devices and levels:** `just mic-test devices --save`; then at 15, 30 and 60 cm with MME, and at
  60 cm with enhancements off and with WASAPI: `just mic-test record --seconds 6 --api mme --save lv-c60-mme`
  (and the other four), reading «Me gusta el helado de chocolate» once each. Record the level verdicts
  (numbers only) and which enhancements Windows lists for this microphone.
- [ ] **Pilot** (D-6): `just stt-corpus capture --session s0 --condition c60 --block`, then the agent
  runs `P0` and `T0` over it and checks the four go/no-go conditions of D-6 with Pipec. Any failed
  check is a tool defect, fixed test-first, and the pilot repeats; the main sessions start only on a
  pass. If an effect is already obvious, Pipec may trim the main sessions and the record says so.
- [ ] **Main sessions** (two different days, 60 cm, Windows defaults):
  `just stt-corpus capture --session s1 --condition c60 --style careful` and, for layer D only, a
  second pass `--layers D --style relaxed`; then the same with `--session s2`. About 120 takes per
  session (25–30 minutes).
- [ ] **Condition block** (one day): `just stt-corpus capture --session s3 --condition C --block` for
  each `C` of D-6, in the order Pipec finds practical, noting the fan or TV setting for `c60-noise`.
- [ ] **Spontaneous:** `just stt-corpus free --session s4 --minutes 10` (Pipec talks as if to the
  robot); then `just stt-corpus annotate --session s4`.
- [ ] `just stt-corpus validate` passes. Counts per class and condition only in the chat.
- [ ] **Manual chat arm:** `just chat-test` (interactive) with each `chat: true` item typed as written;
  Pipec counts the replies that understood the request.
- [ ] **Outside reference (optional, D-20):** `just stt-bench external-template`, Pipec dictates the 24
  block items at 60 cm into the usual dictation tool, pastes each result into the template's second
  column and notes the tool and the microphone.

## Task 11: Bench runs and the evaluation record (agent; server stopped)

- [ ] Pipec prepares the laptop (D-9 conditions). Stage 1 on the dev half: every configuration of
  Appendix B available on this machine, `--repeat 2`; then `segment` with every policy of D-17 and a
  `P0` run on each. **Commit `C1`'s composition to the execution record before stage 2** (D-8), then
  stage 2: `C1` and `P0` once on the test half. `calibrate` on the configuration that will be
  adopted. `just stt-text-arm` on `P0` and `C1`. `just probe-stt noise --clips 100` with the
  `C1` settings in a temporary `.env` override (Pipec sets the variables; the agent never reads
  `.env`). Latency under load (D-19): Pipec starts `just eval-chat --mode stream --runs 20` in another
  terminal (Ollama up; restarted if it ends before the timing does), and the agent times `P0` and the best GPU configuration on the dev half with
  `--conditions loaded`. If D-20 was done, `report --external` adds the outside reference.
- [ ] Write `docs/evals/0069-stt-owner-voice.md`: machine conditions, n per table, `P0` per layer and
  condition, every stage-1 difference with its interval, the segmentation table, `C1` vs `P0` on the
  test half, the capture conditions (D-16, with `c15` as the near reference), critical-term errors
  and edge deletions per configuration, latency idle and loaded, memory, repeatability, confidence
  calibration and the D-11 verdict, the D-12 measurement, the text-arm attribution, spontaneous
  aggregates, GPU, the outside reference if any, the decisions each rule produced. No sentence from the spontaneous session, no household name.
- [ ] Pipec reads it and confirms the adoptions. **Commit** `docs: record the stt owner-voice measurements`.

## Task 12: Adopted defaults

**Files:** `server/src/server/settings.py`, `robot/src/robot/settings.py`, `.env.example`; tests
`tests/unit/test_stt_decode_options.py`, `tests/unit/test_audio_capture.py` (default pins);
`docs/runbooks/operator-manual.md`.

- [ ] **Failing tests:** the default pins of Tasks 1–3 change to the adopted values (and only those);
  every `WhisperDecodeOptions` field `C1` changed becomes a setting (`whisper_<field>`, default = the
  adopted value) read by `decode_options`, and so does `cpu_threads` if `C1` changed it; if D-13 removes
  `whisper_hallucination_silence_threshold`, a settings test shows the variable in an environment is
  ignored. RED: the old defaults.
- [ ] Change the defaults and `.env.example`; operator manual: microphone placement and enhancements
  (D-16), the unclear phrase and how to read `stt.confidence`, a model download on first start if the
  model changed. Run `just gate`. **Commit** `feat: adopt the measured stt defaults`.
- [ ] Pipec's `.env` copies `.env.example` (for example `WHISPER_MODEL=small`), so a new default does
  not reach Pipec's runtime by itself: the agent lists every variable to change or delete, and Pipec
  edits that `.env` (the agent never reads it).

## Task 13: The gate stops reading Whisper's marks (only if Pipec chooses it under D-12)

**Files:** `server/src/server/memory/preference_gate.py`, `docs/adr/0021-memory-candidates-and-the-canonical-writer.md`
(amendment line); test `tests/unit/test_preference_gate.py`.

- [ ] **Failing tests:** «¿Me gustan las películas de ciencia ficción?» → the taste is matched;
  «¿Qué helado me gusta?», «¿Cuál me gusta más?», «Me gusta el helado, ¿no?» → `NOT_A_TASTE`; every
  existing gate test still passes. RED: today's punctuation refusal.
- [ ] Implement the word rule of D-12; ADR 0021 gets a dated amendment line naming the cost. **Commit**
  `fix(server): a taste is not refused for whisper's question marks`.
- [ ] If Pipec keeps the gate: the record states both measured shares and Pipec's choice, the gate is
  untouched, and intonation is named as the fix in the roadmap.

## Task 14: GPU dependency (only if D-15 adopts it)

**Files:** `server/pyproject.toml` (through `uv add`), `uv.lock`, `server/src/server/stt.py`,
`server/src/server/settings.py`, `.env.example`; test `tests/unit/test_stt_decode_options.py`.

- [ ] **Failing test:** with `whisper_device="cuda"` on Windows, `_get_model` registers the cuBLAS
  `bin` directory of the installed wheel (found with `importlib.util.find_spec("nvidia.cublas")`)
  through `os.add_dll_directory` before `WhisperModel`; on CPU it does nothing. RED.
- [ ] `cd server && uv add --optional cuda nvidia-cublas-cu12` (plus cuDNN only if Task 9 needed it);
  implement; `.env.example` documents `WHISPER_DEVICE=cuda` with `uv sync --all-packages --all-groups
  --extra cuda`. **Commit** `feat(server): optional cuda extra for whisper`.

## Task 15: WASAPI capture on the robot (only if D-16 adopts it)

**Files:** `robot/src/robot/audio_capture.py`, `robot/src/robot/settings.py`, `robot/pyproject.toml`
(through `uv add soxr`), `uv.lock`, `.env.example`; test `tests/unit/test_audio_capture.py`.

- [ ] **Failing tests:** with `audio_host_api="wasapi"`, the stream opens in the device's native format
  (rate and channels, averaged to mono first) and is read through its callback, never PortAudio's
  blocking read (Task 4); a stateful `soxr.ResampleStream` converts continuously (never block by block from
  scratch) and a re-chunker hands the VAD exactly `CHUNK_FRAMES` int16 samples at 16 kHz, carrying the
  remainder; 1 s of 44.1 kHz and of 48 kHz input yields 16,000 samples in 512-sample chunks with no
  discontinuity at the chunk joins (a 1 kHz tone keeps its level within 0.5 dB); the default `"mme"`
  opens exactly as today. RED.
- [ ] Implement with `soxr` (the converter Task 4 measured). **Commit** `feat(robot): capture through wasapi at the native rate`.

## Task 16: ADR 0023 and documentation truth

- [ ] `docs/adr/0023-speech-to-text-model-and-decoding.md` (`Proposed`, D-18) and the ADR index;
  `docs/architecture/current-state.md` (the STT row: model, decoding, the unclear reply, the upload
  tail); refresh the Archify architecture diagram (`validate` → `deliver`) if the STT row changed;
  `docs/roadmap/cognitive-roadmap.md` (a `—` row «Speech-to-text on the owner's voice» with the
  result, and the cross-cutting row on contention between STT and extraction left to PC-5); the plan
  indexes; this plan's execution record. `ruff format --check .` (the CI also formats Python blocks
  in Markdown), `check_reserved_terms`, links; `just gate`. **Commit** `docs: record plan 0069 and adr 0023`.
  Open the PR; merge with Pipec's go-ahead.

## Task 17: Hardware acceptance and cleanup (Pipec runs everything)

- [ ] With the adopted defaults, `just run-server` and `just run-robot` at 60 cm: 20 scripted items
  from layers A, B, C and E read once (counts: understood, unclear phrase, misheard); two deliberately
  mumbled turns (the unclear phrase is heard if D-11 switched it on); one memory offer answered
  «Sí, autorizo que lo guardes» (promoted or retried, as Plan 0068); `stt.confidence` and
  `pipeline.timing` read from the log as numbers.
- [ ] Pipec accepts the record; `just stt-corpus cleanup` with the typed `delete`; the agent verifies
  the directory is empty except the model cache. ADR 0023 `Accepted`. Plan 0068 returns to `NOW`.
  **Commit** `docs: close plan 0069`.

## Completion criteria

1. The measurements of Task 11 are recorded with n, intervals and machine conditions, read and
   spontaneous apart; every decision D-9 to D-17 has its outcome written.
2. Whisper's call goes through one options structure (adopted values as settings); the per-clip
   confidence is logged; the unclear reply exists
   and is on or off as D-11 decided; the robot's segmentation is replayable and its tail is a setting.
3. Adopted defaults are in place with tests; findings (the dead setting, the gate's marks, the stale
   `mic_test.py`) are fixed or explicitly kept with the measured reason.
4. ADR 0023 is `Accepted`; `just gate` green; Pipec's hardware acceptance recorded; the private corpus
   deleted after Pipec's typed `delete`.

## Not here, and why

- Intonation (question vs exclamation from pitch), other voices and impostors, a face-only fallback:
  Pipec's scope decision (D-1).
- Fine-tuning Whisper on Chilean speech: a fine-tuned `small` overfit its corpus (evidence 2), and one
  speaker is not a training set.
- The STT/extraction contention and the homelab: the roadmap's cross-cutting CPU budget row (PC-5).
- `user_emotion`'s «?» rule: a mark there only silences an emotion; it fails toward neutral.
- Running the bench on OpenSLR 71 (Google's Chilean corpus) as a contrast: the Chilean leaderboard
  already measured those sets (evidence 2); the open question is Pipec's voice through this laptop.
- Barge-in, the speaker check (Plan 0068 Part B), any cloud recognizer.

## Appendix A — the reading script (draft for Pipec's review)

Read at a natural pace unless the style says otherwise. «…» in layer G marks the pause you would make
while thinking, not timed: the bench measures how long it was (D-17). `×n` is the number of main-condition takes over sessions s1 and s2; **(b)** marks the 24
condition-block items; **(c)** marks the 20 items of the manual chat arm.

**A — tastes, statement and question with the same words (×2)**

| id | text | | id | text |
|---|---|---|---|---|
| A01 | Me gusta el helado de chocolate. (b)(c) | | A02 | ¿Me gusta el helado de chocolate? (b)(c) |
| A03 | Me gustan las películas de ciencia ficción. (b)(c) | | A04 | ¿Me gustan las películas de ciencia ficción? (b)(c) |
| A05 | No me gusta el café sin azúcar. | | A06 | ¿No me gusta el café sin azúcar? |
| A07 | Prefiero el té con limón. (c) | | A08 | ¿Prefiero el té con limón? (c) |
| A09 | Me encantan las empanadas de pino. | | A10 | Me gustan los sabores ácidos. (b) |
| A11 | Mi fruta favorita es la frutilla. | | A12 | Me gusta caminar por el cerro en la mañana. |

**B — confirmations (×5)**

B01 Sí. · B02 No. · B03 Acepto. (b) · B04 Autorizo. · B05 Sí, autorizo. (b) · B06 No autorizo. (b) ·
B07 Guárdalo. · B08 Guárdala. (b) · B09 Sí, guárdalo. · B10 Sí, autorizo que lo guardes. (b) ·
B11 No autorizo que lo guardes. · B12 Apruebo.

**C — questions and commands to the robot (×2)**

C01 ¿Qué hora es? (b)(c) · C02 ¿Qué día es hoy? (c) · C03 ¿Cómo te llamas? (c) · C04 Iroko, ¿me
escuchas? (b)(c) · C05 ¿Quién soy? (b)(c) · C06 ¿Cuántos hijos tengo? · C07 ¿Cómo se llaman mis
hijos? (c) · C08 Describe lo que ves. · C09 ¿Qué ves? (c) · C10 Olvida lo que te dije del helado. (b)(c)
· C11 Cuéntame un chiste corto. (c) · C12 Enciende la luz de la sala, por favor. · C13 No quiero que
apagues la luz. (b) · C14 No, todavía no he terminado. · C15 Iroko, espera, todavía estoy hablando.

**D — minimal pairs and reductions (×5: three careful, two relaxed)**

| id | text | target | competitor |
|---|---|---|---|
| D01 | Dijo helado. (b) | helado | de lado |
| D02 | Dijo de lado. (b) | de lado | helado |
| D03 | Me gustan los sabores. (b) | sabores | sabore |
| D04 | Me gusta el sabor. | sabor | sabores |
| D05 | Quiero que lo guardes. (b) | guardes | guarde |
| D06 | Quiero que lo guarde. | guarde | guardes |
| D07 | Las casas grandes. (b) | casas | casa |
| D08 | La casa grande. | casa | casas |
| D09 | Los amigos llegan tarde. | amigos | amigo |
| D10 | El amigo llega tarde. | amigo | amigos |
| D11 | Estoy cansado. | cansado | cansao |
| D12 | El pescado está rico. | pescado | pescao |
| D13 | Ya está mojado. | mojado | mojao |
| D14 | Lo dejé guardado. | guardado | guardao |

**E — numbers and times (×2; written alternatives accepted after normalization)**

E01 Son las tres y media. (b) — «son las 3 y media», «son las 3 30» · E02 Despiértame a las siete
y cuarto. — «a las 7 y cuarto», «a las 7 15» · E03 Quedan quince minutos. — «quedan 15 minutos» ·
E04 Es el piso veintitrés. — «es el piso 23» · E05 Cuesta tres mil quinientos pesos. (b) — «cuesta
3500 pesos», «cuesta 3 500 pesos» · E06 El veintiuno de octubre. — «el 21 de octubre» · E07 El código
es cinco, nueve, cero, siete. — «el código es 5 9 0 7», «el código es 5907»

**F — Chilean markers (×2)**

F01 Ya po, dale. (c) · F02 Sí po, guárdalo. (b) · F03 ¿Cachai lo que te digo? (c) · F04 Está bacán. ·
F05 Voy al tiro. · F06 Oye, ¿y qué más? (c)

**G — pauses (×2, window 12 s)**

G01 Me gusta el helado… sobre todo el de limón. · G02 Sí, autorizo… que lo guardes. · G03 Iroko…
¿qué hora es? (c) · G04 Prefiero el té… pero sin azúcar.

**H — phonetic coverage, own sentences (×2)**

H01 El perro corre rápido por la carretera. (b) · H02 Jugamos ajedrez en junio. · H03 La llave está
debajo de la silla amarilla. · H04 El niño pequeño soñó con una araña. · H05 Compré choclo, porotos
y charqui. (c) · H06 Fuimos a la feria a comprar frutas frescas. · H07 El tren llegó atrasado a la
estación. · H08 Hace mucho frío en el invierno. · H09 Los zapatos azules están en el clóset. ·
H10 Mañana vamos a almorzar temprano. · H11 El bus pasa cada diez minutos por la esquina. · H12 Las
hojas secas cubren el patio. · H13 Mi tío tenía una idea increíble. (vowel sequences) · H14 Quiero
agua fría y un café. · H15 Déjalo de lado, quiero el helado. (the pair inside one sentence)

Totals: 248 main takes (A 24, B 60, C 30, D 70, E 14, F 12, G 8, H 30), 168 condition-block takes
(24 items × 7 conditions, the pilot's 24 included), one spontaneous session of about 10 minutes.
At about 12 s per take the read material is roughly 85 minutes of Pipec's time, spread over four or
five sittings.

## Appendix B — bench configurations (each a single change from `P0`)

| Name | Change from `P0` | Question it answers |
|---|---|---|
| `P0` | — (`small`, `int8`, CPU, beam 5, fallback temperatures, prompt «…Iroko.», Whisper VAD on at 500 ms) | today |
| `T0` | temperatures `(0.0,)` | does random fallback make the variants? |
| `NS-off` | `no_speech_threshold=None` | are short answers dropped as silence? |
| `V-off` | `vad_filter=False` | does the second silence filter cost words? |
| `V-soft` | threshold 0.35, `speech_pad_ms` 500, `min_speech_duration_ms` 150, `min_silence_duration_ms` 2000 | a gentler filter, if one is kept |
| `PR-none` | no prompt | does the prompt help at all? |
| `PR-vocab` | D-10's prompt | vocabulary and «¿?» style |
| `HW` | `SHORT_REPLY_HOTWORDS` on every clip | do the reply hotwords help or hurt? |
| `WT` | `word_timestamps=True` (activates the 2.0 s threshold) | the dead setting (D-13) |
| `B1` | beam 1 | speed |
| `TH8` | `cpu_threads=8` | speed on 4 cores / 8 threads |
| `F32` | compute `float32` | quantization cost |
| `NORM` | input peak normalized to −3 dBFS | gain normalization |
| `M-medium` | model `medium` | a larger model on CPU |
| `M-turbo` | model `large-v3-turbo` | the best Chilean scores, on CPU |
| `G-small` | CUDA `int8_float16` | GPU, if Task 9 loads |
| `G-turbo` | `large-v3-turbo`, CUDA `int8_float16` | GPU, if it fits in 2 GB |

Segmentation policies (D-17), replayed offline with `P0`: `close800-tail800-pre400` (today),
`close800-tail300`, `close800-tail500`, `close1200-tail300`, `close1600-tail300`, `close1200-tail300-pre600`.

## Execution record

Not executed.
