# Operator manual

> **Status:** Canonical. Living day-to-day reference for running, isolating,
> and testing Iroko on the development PC. This is not a dated acceptance
> record — see [`p0-runtime-acceptance.md`](p0-runtime-acceptance.md) for
> that. When this manual and the code disagree, the code wins; update this
> file in the same change that changes behavior.

## 0. Fresh clone — from zero to running

Verified against the actual code and scripts (2026-08-26), not assumed.
`CONTRIBUTING.md`'s "Development setup" only covers `just setup` — treat
this section as the current source of truth for actually running Iroko,
not just contributing code to it.

**Outside the repo, nothing here automates these** — install them yourself
first: `git`, `uv` (≥0.6.0, `pyproject.toml`'s `[tool.uv] required-version`),
`just`, and **Ollama itself** (the application, not just its models). Python
3.12 does not need a separate install — `uv`'s `python-preference = "managed"`
fetches it.

```powershell
just setup                    # deps + pre-commit hooks + secrets baseline + Silero VAD (2.3 MB, bundled — see below)
Copy-Item .env.example .env   # NOT automated anywhere — do this manually
```

Edit the new `.env` — at minimum confirm `PIPER_VOICE` matches the voice
you're about to fetch below.

**Model downloads — verified one by one, each traced to its actual source
in the installed packages, nothing guessed:**

| Model | Auto? | How to get it |
|---|---|---|
| Whisper (STT) | Yes | Cached from HuggingFace on first call, offline after (`stt.py`) — nothing to run. Changing `WHISPER_MODEL` downloads the new model once on the next start (`medium` is about 1.5 GB), so start the server with internet that time |
| InsightFace (face) | Yes | ~300 MB, downloaded on first face detection/enrollment call (`vision/faces.py`) — nothing to run |
| Silero VAD | Bundled into `just setup` (2.3 MB) | Was previously a separate step — `just fetch-vad-model` still works standalone if you skipped `setup` |
| **Piper (TTS voice)** | **No — one command, run once per voice** | `just fetch-piper-voice` — wraps the official `piper.download_voices` module already bundled in the `piper-tts` dependency this project uses; source is `huggingface.co/rhasspy/piper-voices` (verified from the installed package's own code, not guessed). Defaults to `.env`'s `PIPER_VOICE`; pass `--voice <name>` for a different one, `--force` to re-fetch |
| Ollama models (chat/embed/consolidation/vision) | No — opt-in, multi-GB | `just services` only checks and reports `[MISSING]`; run `just pull-models` when you're ready to commit the bandwidth/disk — it pulls exactly the missing ones and is safe to rerun after a partial failure |

```powershell
just fetch-piper-voice        # once per voice — safe to rerun, skips files that already exist
just services                 # starts Ollama, reports which models are still missing
just pull-models              # opt-in — actually downloads the missing ones (can be several GB)
```

Once the server can actually boot and speak, set up the owner:

```powershell
just setup-personal status   # non-interactive: prints owner_count, credential_count, etc — safe to run anytime
just setup-personal          # the interactive wizard (requires run-server/run-robot stopped)
```

The wizard's exact prompt sequence (`personal_setup.py::run_personal_setup_wizard`):
`Owner name:` → `Child names (comma separated, optional):` → `PIN (6-12
digits):` (hidden) → `Confirm PIN:` (hidden) → a summary, then `Type SI to
confirm:` before anything is written. Owner + PIN alone is a complete setup:
a blank children answer creates no children, and only a comma separates two
names (`Ana María, Juan` is two children). The PIN format is checked before
anything is written, so a malformed PIN cancels the wizard with a message and
no entity exists. Re-running with the same PIN is a no-op; a different PIN
rotates the credential.

## 1. Starting the system

```powershell
just services       # Ollama + local models (skip if already running)
just run-server      # the "brain" — loads .env, binds loopback by default
just run-robot        # the "senses" — mic + speaker + webcam, talks to run-server
```

`just run-robot` needs a real microphone/speaker and, with face auth on, a
webcam. For headless iteration without the physical loop, use the tools in
§2 instead of the full robot.

First time only: `just setup` (dependencies + hooks), then
`just setup-personal` (owner, confirmed children, PIN — requires
`run-server`/`run-robot` stopped).

**Seeing what Iroko heard and says (debug, off by default).** The logs carry
only counts and timings — household content is never logged (Plans 0031/0032).
To read the actual texts on your own machine set `LOG_CONVERSATION_TEXT=true` in
`.env` and restart `just run-server` and `just run-robot`: both consoles then
print `Heard:` (the transcript) and `Spoken:` (each sentence sent to the voice,
including deterministic answers such as your own children). It prints to the console only,
never to `logs/server.log`, and startup logs a warning while it is on. Turn it
off when you finish, and do not say a PIN aloud while it is on
([Plan 0052](../plans/completed/0052-opt-in-conversation-text-log.md)).

## 2. QA tools, by what they isolate

Iroko's turn is `mic → STT → LLM → TTS → speaker`, plus an HTTP boundary
between the robot and the server. Each tool below isolates one slice so a
problem can be localized without running the whole loop.

| Tool | Command | Isolates | Needs server? | Needs `.env`? |
|---|---|---|:---:|:---:|
| `mic_test.py` | `just mic-test devices` / `just mic-test record --seconds 6 --api mme` | Capture auditor (Plan 0069): lists the inputs with their host API and native rate; shows the phrase to read (`--phrase` changes it), counts down and cues `>>> HABLA <<<`, then records the window the way the robot opens the microphone (`mme`) or through WASAPI in the device's native format (`wasapi`: every channel averaged, resampled with `soxr`); warns when the stream lost audio; reports peak, speech level, floor, SNR and clipping against the plan's targets; `--transcribe` runs the server's production Whisper options (stop the server first); `--save NAME` keeps the take under `project-history/calibration/stt/mic/` only, and an existing name is refused before recording unless `--replace` | No | Yes |
| `piper_test.py` | `uv run python scripts/piper_test.py --text ...` | Text → Piper TTS → speaker only | No | No |
| `pipeline_test.py` | `just test-pipeline` | Smoke test of the three model seams, `mic → STT → LLM → TTS → speaker` (the mic is optional with `--text`); real model code, but no controller, identity, memory or HTTP | No | Yes (Ollama) |
| `client_test.py` | `just test-client` | Full HTTP round trip through the real running server | Yes | No |
| `chat_test.py` | `just chat-test` | `/chat` text-only: contract, A/B isolation and, with the owner PIN (hidden prompt; Enter skips it), the continuity of the identified owner; interactive mode | Yes | No |
| `memory_test.py` | `just memory-test --session` / `--show-db` | Public voice channel + raw SQLite memory state | Yes (except `--show-db`) | No |
| `vision_demo.py` | `just vision-demo` | Webcam frame → `/vision/describe` (scene only, no identity) | Yes, `VISION_ENABLED=true` | No |
| `faces_demo.py` | `just faces-demo --see` | Webcam/photo → `/vision/respond` scene dialogue (still no biometrics) | Yes | No |
| `face_auth_demo.py` | `just face-auth-demo --enroll` / `--revoke` | The Plan 0029 admin endpoints — enroll/revoke the owner's face | Yes, owner+PIN configured | No |
| `manage_household_roles.py` | `uv run python scripts/manage_household_roles.py bootstrap-owner` | Local role bootstrap, direct DB, no HTTP | No | No |
| `migrate_memory_v4.py` | `uv run python scripts/migrate_memory_v4.py --apply` | Legacy-fact migration into v4, dry-run first | No | No |
| `eval_chat.py` / `eval_consolidation.py` | `just eval-chat` / `just eval-memory` | Response/extraction quality against real Ollama — not `pytest`. `just eval-chat --mode stream` instead measures how often a streamed reply would drop to the fallback phrase (the plain-text contract, Plans 0056 and 0059) and how often a reply is not in Spanish (Plan 0064); it reports counts and rates, never model output | Needs `just services` | Yes |
| `diagnose_stream_protocol.py` | `just diagnose-stream` | Why a streamed reply drops to the fallback phrase (Plan 0057): runs the golden and public turns under variants that each remove or move one factor, in a seeded shuffled order, and reports failure shapes, an ablation read against a noise control, timings and whether a schema-constrained reply arrives spread over time. Counts only, never model output; `--runs`, `--seed`, `--variants`, `--structured-runs`, `--output`. The default 500 streams take on the order of an hour on a non-dedicated laptop (an estimate; the duration of the recorded run was not noted); exit `0`, `1` (a provider error, the report is still written) or `2` (Ollama not answering, nothing written) | Run it with the server stopped | Yes |
| `stt_probes.py` | `just probe-stt noise` / `just probe-stt first-turn` | Whisper on synthetic noise (empty, prompt echo or other text, read before the echo guard) and first-utterance accuracy over fresh processes (Plan 0056); loads the real models, so run it with the server stopped | No | Yes |
| `speaker_calibration.py` | `just speaker-calibration <action>` | Speaker-embedding calibration corpus and analysis (Plan 0047, PC-3A) — capture, embed, analyze, discard, cleanup; local only, never in the runtime | No (mic only for `capture`) | Yes for the recipe |
| `eval_longitudinal_memory.py` | `just eval-longitudinal` | Longitudinal-memory capability probe (multi-session recall, correction, cross-person privacy, deletion, provenance) against real Ollama + a temp DB — not `pytest` | Needs `just services` | Yes |

Rule of thumb: audio sounds wrong → `mic_test.py`/`piper_test.py` first (they
need nothing else running). The answer is wrong but audio is fine →
`pipeline_test.py` (bypasses HTTP and the cognitive controller; it only shows
whether the three models work, not whether the household path does).
Something only breaks through the real server → `client_test.py`/`chat_test.py`.

What the Plan 0056 tools do **not** prove: `probe-stt noise` uses synthetic noise,
not your room, so a clean result does not show the echo guard works on real silence;
`probe-stt first-turn` uses Piper speech and isolates STT from the server's other
start-up work, so it cannot say whether *your* first utterance after a restart is
heard correctly (judge that by speaking it); and `eval-chat --mode stream` measures
the protocol on 120 repeated golden and chit-chat turns, a wide interval, not a
general reliability figure. `diagnose-stream` measures the generator for the configured
model, not the microphone → server → audio path, and its readings are exploratory
signals read against rules fixed in advance (see the
[Plan 0057 record](../evals/0057-stream-protocol-diagnosis.md)), never a cause.

### Speech-to-text profiles — CPU and GPU (Plan 0069)

The server ships with the CPU profile (`small`, `int8`, `cpu`), which needs nothing extra. Measured
on the owner's voice with the laptop's microphone (a 2 GB MX450, Ollama running beside it):

| Profile | Word errors (test half) | Median / p90 per clip, idle | Median / p90 with Ollama busy | VRAM |
|---|---|---|---|---|
| CPU `small` (default) | 15.4 % | 2.7 / 3.0 s | **8.7 / 15.3 s** | — |
| GPU `small` | 15.8 % | 0.9 / 1.2 s | 1.4 / 1.9 s | 0.7 GB |
| GPU `medium` (recommended) | **6.8 %** | 2.5 / 3.2 s | 3.0 / 4.0 s | 1.25 GB (1.8 GB used with Ollama) |

On the short answers («sí», «no», «autorizo»…, 35 reference words on the test half) `medium` misread 1 word
and the other two profiles 9 and 10: a small sample, but the intervals do not overlap. The CPU profile loses to Ollama because both fight for the same processor; the GPU does
not. To switch (the agent never edits your `.env`):

1. `uv sync --all-packages --all-groups --extra cuda` (adds the cuBLAS wheels; the code registers
   their folders itself and puts them on the process's `PATH`, so there is nothing for you to set).
2. In the server's `.env`: `WHISPER_MODEL=medium`, `WHISPER_DEVICE=cuda`,
   `WHISPER_COMPUTE_TYPE=int8_float16`. Use `WHISPER_MODEL=small` for the fast profile. Restart the
   server; the first start downloads the model if it is not cached.
3. To go back, set the three variables to `small`, `cpu`, `int8`. A GPU load that fails reports
   `cublas64_12.dll is not found` when the extra is missing.

Other settings of this plan: `WHISPER_TEMPERATURES` (default `[0.0]`: Whisper no longer re-decodes a
doubtful clip with random sampling, which took 14–48 s on some spontaneous clips and made the text
unrepeatable; the old list is `[0.0,0.2,0.4,0.6,0.8,1.0]`), robot `VAD_SILENCE_MS=1200` (a pause
inside a sentence closes the turn only past 1.2 s) and `VAD_UPLOAD_TAIL_MS=300`.
`WHISPER_HALLUCINATION_SILENCE_THRESHOLD` was removed (it did nothing with word timestamps off); an
old `.env` that still sets it keeps working.

**The «no te entendí» reply is off by default** (`WHISPER_UNCLEAR_LOGPROB` unset; the owner tries
`-0.9` in their own `.env`). Every clip logs one
`stt.confidence` line (no text): `avg_logprob`, `no_speech_prob`, `compression_ratio`,
`temperature`, `segments`, `clip_s`, `after_vad_s` and `unclear`. On 48 spontaneous clips the
doubtful ones were wrong only about half the time and rejecting the 6 lowest would have dropped 3 correct clips, so
no threshold met the plan's rule (at most 5 % of correct clips rejected, at least half of the errors
caught). In the live runs `-0.9` flagged one of the two murmured clips and none of the 30 real turns, but
it asks for a repeat on about one correct long clip in ten. Look at the logged figures after more real
use before making it a default.

**Microphone.** Speaking at 15, 30 or 60 cm from the laptop's array made no measurable difference
(18.0 %, 18.4 % and 19.4 % word errors with GPU `small` on the same 24 phrases); leave the Windows audio
enhancements as they are. Check the level of a new microphone with `just mic-test record`: target
a peak between −12 and −3 dBFS and a floor at least 30 dB under the voice.

### Speaker calibration — `just speaker-calibration` (Plan 0047, PC-3A)

A local, offline study harness — not part of the runtime and not speaker
recognition. Plan 0047 closed 2026-09-25 with a provisional PASS (see
[the plan](../plans/completed/0047-speaker-evidence-calibration-study.md)); the tool
stays for a re-run or for PC-3B calibration. Actions (one per call; PowerShell strips
quotes, so pass words unquoted):

| Action | What it does |
|---|---|
| `model-contract` | The only action allowed on the network: downloads the pinned ECAPA revision (~85 MB) into the gitignored cache and proves it loads offline |
| `capture` | Records one sample with the microphone (phrase shown, 3-2-1 countdown and beep). Needs `--class --subject --session --phrase --condition`. Rejects silent, clipped, too short or too long takes |
| `validate` | Checks the manifest, hashes, the corpus matrix and stray WAV files |
| `embed` | Computes one embedding and latency per sample, with the model id and WAV hash |
| `analyze` | Writes an aggregate-only report (`aggregate-report.md`); refuses to overwrite one |
| `discard` | Permanently deletes one participant's (`--subject`) or one sample's (`--sample`) data, after typing `delete` |
| `cleanup` | Deletes every private artifact after typing `delete`; keeps the model cache unless `--purge-model-cache` |

Privacy rules: the corpus lives only under `project-history/calibration/speaker/`
(gitignored); use letter pseudonyms (`impostor_a`), never names; report counts
and ranges only — no sample ids, file names or per-sample scores in chat or docs;
only consenting adults; an agent never records, imitates or replays a voice.

#### Short-answer study (Plan 0068, Part B)

The same tool measures whether a **short spoken answer** (1 to 2.5 s: «Sí», «Acepto», «Sí,
autorizo») passes the speaker check as often as a long phrase. It changes no threshold, no
enrollment and no runtime code: every variant is judged **at the fixed threshold 0.4834**. Pipec
runs every capture; an agent never records, imitates or replays a voice, and the private corpus is
deleted when the report is accepted (`discard`, then `cleanup` with the typed `delete`).

Four new classes carry the study, each with its own phrases and minimums (counts of samples):

| Class | Who and what | Phrases | Lower bound of a take | Minimum |
|---|---|---|---|---|
| `reference-short` | The owner, one quiet session, `quiet-near` only | `short-01` «Sí», `short-02` «Acepto», `short-03` «Sí, autorizo» | 1.0 s | 6 |
| `genuine-short` | The owner, the same words, at least 2 later sessions, the four conditions | `short-01..03` | 1.0 s | 24 |
| `impostor-short` | At least 3 consenting adults, live, the same words | `short-01..03` | 1.0 s | 18 |
| `replay-short` | Pipec plays a recording of the owner | `short-01..03` | 1.0 s | 6 |

A **long control** is captured too, because the Plan 0047 corpus was deleted: 6 `reference` and 6
`genuine` samples with `phrase-01..03` (lower bound 2.5 s as always). A short sample never fills a
long class minimum, and the reverse. `capture` still rejects silent, clipped and too-short takes.

```powershell
just speaker-calibration capture --class reference-short --subject owner --session short-ref-01 --phrase short-01 --condition quiet-near
just speaker-calibration capture --class genuine-short --subject owner --session short-gen-01 --phrase short-02 --condition quiet-far
just speaker-calibration capture --class impostor-short --subject impostor_a --session short-imp-01 --phrase short-03 --condition quiet-near
just speaker-calibration capture --class replay-short --subject owner --session short-rep-01 --phrase short-01 --condition quiet-near
just speaker-calibration capture --class reference --subject owner --session long-ref-01 --phrase phrase-01 --condition quiet-near
just speaker-calibration capture --class genuine --subject owner --session long-gen-01 --phrase phrase-02 --condition quiet-near
```

A `*-short` class takes only `short-NN` phrases and a long class only `phrase-NN`; the CLI refuses
the other combination. Replay samples use `--subject owner` (the voice being replayed) and the
conditions `quiet-near` or `quiet-far` only. Then, in this order:

1. `just speaker-calibration validate` checks the manifest, the hashes and the short-study matrix
   (counts per class, at least 2 genuine sessions, all four conditions, at least 3 impostors, every
   phrase covered).
2. `just speaker-calibration embed` computes the embeddings, and for every probe clip also the
   embedding of its **silence-trimmed** version. **Re-run `embed` after any capture or discard**:
   the analysis refuses a stale `embeddings.npz`.
3. `just speaker-calibration analyze` detects a short corpus by itself and writes the short
   report (`aggregate-report.md`; it refuses to overwrite one).

The short report compares, at the fixed threshold, **raw vs trimmed** probe clips (the clip as the
robot sends it, with its pre-roll and silent tail, against the clip with the leading and trailing
silence cut by a fixed energy rule) and **long-only vs long+short** references (the owner's long
phrases alone, against those plus the short confirmations). Each cell lists, per class, the total,
the clips accepted and the rate, the clips that were silent once trimmed, and the distance
minimum, mean and maximum (shown only for three or more clips). It also gives accepts by clip
length (1 to 1.5, 1.5 to 2 and 2 to 2.5 s) and the share of silence in the raw clips. Reading it:

- A variant is **eligible** only with **0 impostor accepts** on `impostor-short`. A variant with
  one or more is *not eligible* however well the owner does.
- With 0 accepts out of n impostor clips, the true false-accept rate is not shown to be zero: the
  rule of three bounds it at about 3/n at 95 % confidence (n = 18 gives about 17 %). The report
  states the sample size next to it.
- Genuine rates are **in-sample** (the owner's references and probes come from the same corpus), so
  they are optimistic.
- The result is a recommendation for a next plan (trim the embedding, enroll short confirmations,
  or keep asking for a longer answer), never a threshold change.

Privacy is as above: counts and ranges only, no sample ids, names or per-sample scores in chat or
docs. Use letter pseudonyms for impostors.

### Longitudinal-memory baseline — `just eval-longitudinal` (Plan 0046, CM-0)

An offline capability probe, not a `pytest` test. It runs the synthetic suite in
`tests/evals/golden_longitudinal_memory.yaml` against real Ollama and a
throwaway database, and never touches the configured production database. Full
rules: [`docs/evals/README.md`](../evals/README.md).

The recorded CM-0 baseline (2026-09-08, `ac43c58`, exit `1`) is
[`docs/evals/0046-longitudinal-memory-baseline.md`](../evals/0046-longitudinal-memory-baseline.md):
extraction is the only live seam (p/r `0.25`, `FAIL` — no CM-0 gate), every
other operation is `unsupported`, all four frozen gates `FAIL`.

```powershell
just services            # Ollama up, consolidation model pulled
just eval-longitudinal   # full gating baseline = no --only, --runs 3
# report -> docs/evals/longitudinal-memory-cm0.md  (never overwritten)
```

1. **Preflight.** The runner pings `GET {OLLAMA_URL}/api/version`. No answer →
   it writes no report, closes resources, exits `2`.
2. **Isolated run.** A `TemporaryDirectory` (`iroko-cm0-…`) holds a freshly
   migrated `brain.db`; `settings.brain_db_path` is repointed for the process
   only and always restored; the `.db`/`-wal`/`-shm` files are removed on exit.
3. **Report.** Markdown under `docs/evals/`. Refuses to overwrite an existing
   file — rename (add a date) instead of deleting.

Exit codes: `0` full suite with every frozen gate passing; `1` valid full suite
with at least one failed or unsupported case (**the expected CM-0 RED outcome** —
the runtime supports only single-turn extraction, so `propose` / `restart` /
`recall` / `correct` / `forget` / `inspect_derivatives` are honestly reported
`unsupported`); `2` bad dataset/config, unsafe path, unavailable provider,
incomplete run or internal harness error. A `--only` run is non-gating and can
never be `0` on the strength of the gates.

## 3. Security ladder — what Iroko can do at each tier

This is the actual, current state of progressive authentication (ADR-0008,
ADR-0009, ADR-0016). Each tier is strictly additive: a later tier never removes
an earlier one. The face is the daily way to identify the owner; the PIN is
optional and administrative, and when biometrics fail the recovery is local
administration on the server host, not a spoken step.

### Tier 0 — No authentication (default, unknown speaker)

Always available, nothing to turn on.

- **Can:** perceive mic/camera under existing local privacy settings,
  transcribe, hold bounded general conversation and speak through TTS. An
  unknown or ambiguous speaker keeps nothing between turns (ADR 0020): the
  turn is answered and forgotten, and it never touches the identified
  person's short-term session.
- **Cannot:** read, enumerate, or confirm personal/household memory;
  attribute a statement to the owner; mutate memory/identity/consent/
  credentials; control a device or the PC; enroll any biometric.
- A stranger asking *"¿quiénes son mis hijos?"* gets a non-disclosing
  denial — no name, no count, no hint the data exists.

### Tier 1 — PIN unlock (Plans 0025–0028, closed, real-hardware confirmed)

One spoken/typed local PIN issues one opaque, one-use grant (60 s TTL) that
authorizes exactly one `personal_protected_read` of `child_data` — nothing
else. Since Plan 0051 every grant is bound to the one operation named at unlock: the
robot's grant is always the read scope, a grant presented to the wrong operation is
refused **without being spent**, and "¿Quién soy?" and the "not connected yet"
household answer do not spend it either (only the children read does). The server log
shows `Owner grant refused: scope_mismatch` when that happens.

`POST /auth/owner/unlock` accepts four scopes: `personal_protected_read` (the default),
`biometric_admin`, and, since Plan 0060, `personal_memory_read` and `personal_memory_forget`.
The last two exist only as policy (nothing consumes them yet), so the robot never asks for
them and no spoken turn uses them; the endpoint still issues and echoes them, and an unknown
scope is a 422 whose body never contains the PIN.

```powershell
$env:ROBOT_OWNER_UNLOCK_PROMPT = "true"   # or set in .env
just run-robot
```

Prompts once at startup, via `getpass` — never echoed. Works with both
classic and streaming mode (Plan 0027 added streaming parity for the PIN
token; there is no start-time guard between `ROBOT_OWNER_UNLOCK_PROMPT` and
`ROBOT_STREAMING` — an older comment in `.env.example` claimed one existed,
corrected 2026-08-26; the only real robot startup guard is
`ROBOT_STREAMING` vs. the server's `VISION_ENABLED`, see §4).
**Limitation, by design:** this proves possession of the local secret, not
the physical identity of the speaker. One-use scope and the short TTL are
the accepted mitigation. Under ADR 0016 the PIN is not the daily path: it stays
as an optional `strong` factor when a token is presented and as the credential
of local administration (enrolling and revoking biometrics over loopback).

### Tier 2 — Face evidence (Plan 0029, code/tests merged 2026-08-25; first
real-hardware proof of concept 2026-08-27)

```env
FACE_AUTHENTICATION_ENABLED=true          # server
FACE_AUTHENTICATION_MATCH_THRESHOLD=0.5815  # measured by Plan 0030
ROBOT_FACE_AUTH_ENABLED=true              # robot
```

Enroll with `just onboard` (§6 covers the full identity+PIN+face flow; `just commission` is the guided alta that also enrols the voice and closes the commissioning, see `server/README.md`) — it
prompts for the owner PIN, warns before capturing ("Mira a la camara..."),
and calls the same endpoint `just face-auth-demo --enroll` uses directly if
you need the standalone tool. Revoke with `just face-auth-demo --revoke`,
which really deletes the stored face profiles, not a soft flag. Both scripts
unlock for `biometric_admin` themselves (Plan 0051): the enrolment and revocation
routes refuse a read grant with 401, and an administration grant never answers a
protected question, so enrolling and then asking a protected question takes two
unlocks.

After enrollment, a protected question is answered from the webcam frame
attached to that same turn — no PIN needed for it. Two-or-more detected
faces is a hard denial that does **not** fall back to asking for the PIN (a
stranger sharing the frame would still overhear the answer). Since Plan 0054 a
face that matches another enrolled person is also a hard denial, even when a PIN
token is presented, and it does not consume that token.

Validated live 2026-08-27: `just onboard` enrolled Pipec's face, then
`just run-robot` correctly identified Pipec on a real streaming turn
(`Turn actor: status=identified role=owner ... evidence=1`) and answered
"Tus hijos son nala y martina." with no PIN. **This is one successful run
on one person's hardware, not a calibrated study** — no threshold tuning,
no false-accept/false-reject measurement, no lighting/distance/glasses
variation.

**Known gap, not closed:** no liveness/anti-spoofing — a photo of the owner
held to the camera identifies at assurance `basic`, enough for ordinary private
data. The calibrated real-camera study closed as Plan 0030 (provisional). See
[`current-state.md`](../architecture/current-state.md) for the full
disclosure.

### Tier 3 — Voice evidence (PC-3B, Plan 0053; raises assurance since Plan 0054; replay not defended)

A consented, local speaker check. It never identifies anyone on its own: it is
consulted only after the owner's face matched, and a verified voice of the same
person raises the face's assurance from `basic` to `strong` (Tier 4). A voice with
no owner face in the frame is never even embedded. Off by default.

Enable and enrol (server on loopback, owner and PIN already configured):

1. Put `SPEAKER_AUTHENTICATION_ENABLED=true` in `.env` and restart
   `just run-server`. Optional but recommended: `HF_HUB_OFFLINE=1`, which stops
   `huggingface_hub` from its once-a-day request to `huggingface.co` (an agent
   registry lookup, not a model download; verified to load the model normally).
2. `just speaker-auth-demo --enroll` three times (5 s each, quiet room, normal
   distance). It asks for the PIN each time (it unlocks for `biometric_admin`) and keeps
   the audio in memory only.
   At least 3 references are required before any verification is attempted.
   The first call is slow (about 15 s) because it loads the model.
3. Ask a protected question through `just run-robot` with
   `ROBOT_FACE_AUTH_ENABLED=true`, so the turn carries your face. The server log
   shows `Speaker verdict: verified | unknown | unavailable` and the fusion outcome
   `Identity fusion: face_and_voice | face_only | backend_unavailable | ...`; no
   name, distance or score is ever logged. Without a frame the speaker is not
   consulted at all.
4. `just speaker-auth-demo --revoke` deletes the consent and **every** stored
   voiceprint (checked in SQLite: `voice_profiles` and active
   `voice_consent_grants` both 0). Revocation works even with the flag off.

Behaviour to expect: silence gives a 422 before the speaker check runs; a clip
shorter than 1.5 s gives `unknown` (the answer stays at `basic`); missing model
files give `unavailable` and a normal turn; enrolment returns 503 while the flag
is off. The threshold `0.4834` and the 1.5 s floor are **provisional**: Plan 0047
measured them in-sample on one owner, and **6 of 8 replay probes were accepted**,
so a recording of the owner can pass. Acceptance on 2026-09-29 (one owner, one
laptop microphone): 5 of 5 full-length genuine turns verified; impostors at
runtime, utterances between 1.5 s and 3 s and more than one acoustic condition
were not measured.

### Tier 4 — Face-default fusion (PC-4, Plan 0054, ADR 0016; accepted on real hardware 2026-09-30)

The face identifies the owner by default. A verified voice of the same person
raises the assurance; an optional PIN token is also `strong`. One deterministic
rule combines them, and no path adds a second authorization system:

| Evidence of the turn | Result | Assurance | Server log reason |
|---|---|---|---|
| Owner's face and a verified voice of the same person | answers | `strong` | `face_and_voice` |
| Owner's face only (voice unverified, muffled, or the backend down) | answers | `basic` | `face_only` / `backend_unavailable` |
| Optional PIN token, when the face did not identify | answers | `strong` | `pin` |
| Another enrolled person's face, or two or more faces (even with a token) | denies, token kept | — | `veto_other_person` / `veto_multiple_faces` |
| No face, unknown face, or a voice alone | denies | — | `no_evidence` |
| The face detector or the identity store failed | denies | — | `backend_unavailable` / `error` |

With the owner's face matched a presented PIN token is neither consulted nor spent, and the
robot attaches a frame on every turn while `ROBOT_FACE_AUTH_ENABLED` is on, so in practice
the PIN raises assurance only when the face fails (ADR 0016 §5/§6).

`basic` is enough for ordinary private data such as the child read. Reserved
categories (`security`: account numbers, passwords) need `strong`, but **no
reserved capability exists yet**, so that requirement is proven by policy tests
and cannot be tried on hardware. The denial text is always the same generic one;
only the server log (the fusion reason) and, for a reserved request, the authorization
audit row (`policy_id` `p0.5.assurance-required`) say why.

**Startup warm-up (Plan 0055).** With `FACE_AUTHENTICATION_ENABLED=true` and/or
`SPEAKER_AUTHENTICATION_ENABLED=true` the server loads the matching model while it
starts, before it reports ready, so start-up takes longer and the first protected turn
no longer pays for the load. With both flags off nothing is loaded and `torch` and
`insightface` are never imported. A failed warm-up only logs one warning (the exception
class, never its message) and the model loads lazily on first use, as before; for the
speaker model the 60 s load cool-down then applies, so a first turn within a minute of a
failed start degrades to `basic` instead of retrying. There is no startup deadline: a
blocked loader delays readiness. The earlier figures in this manual (about 15 s for the
speaker model; 8 to 13 s for the first protected turn on the development laptop, 2026-09-30)
are **historical, measured before the warm-up**. Hardware sample (Pipec, 2026-10-01, same laptop, face and speaker flags on, robot sending a frame): start-up took 9 s from `starting` to `ONLINE` (face model about 1 s, speaker model about 3 s, both inside start-up); the first protected turn after the restart (`face_only`; the speaker verdict was `unknown`) took 3.58 s end to end with no model-load line, against 8 to 13 s on 2026-09-30. One sample, not a controlled before/after: no run on `main` was made in the same session.

**Identity-store errors.** If the identity store raises an error while the face is being
resolved (matching, role, consent or label lookup), the face contributes no evidence and no
veto: one warning logs the exception class only, and resolution continues through the PIN
path. With no valid PIN token the actor is unknown and the usual generic denial is
returned instead of a server error; with a valid token the PIN still works. This guard
covers only the face lookups: it does not promise a graceful answer when PIN storage, the
authorization audit or the whole database is down.

**A face with no household role.** A face matched to an enrolled entity that has no
household role also vetoes, and a PIN token cannot bypass it (the conservative choice,
decision D-3 of Plan 0055). Such a profile is fixed through local administration, not from
a conversation.

The PIN is optional and administrative (loopback enrolment
and revocation); recovery when face or voice fail is `just face-auth-demo`,
`just speaker-auth-demo` or `just setup-personal` on the server host, never a
spoken step.

**Short-term continuity on a generic turn (Plan 0061, ADR 0020).** A conversation
turn that no protected branch claimed also names its speaker, by the face (`basic`)
or by a presented default-scope token that is only observed, never spent; the voice
is not consulted. An identified person gets one in-process session: the last
exchanges reach the next turn until 180 s pass without a written turn or 3000
characters are exceeded, another identified person replaces it, and an unknown or
ambiguous speaker suspends it for that turn without reading or erasing it. Nothing
is persisted and no durable memory opens. To follow it, read two server log lines
(closed reasons, never text): `Generic identification: identified | no_evidence |
veto_other_person | veto_multiple_faces | backend_unavailable | error (N ms)` and
`Continuity: started | continued | replaced | suspended | expired`. The face check
costs about 0.2 to 1.6 s on the development laptop (Plan 0061's acceptance). With
`MEMORY_ENABLED=false` none of this runs. `/vision/respond` is the public unknown
and neither reads nor writes the session. A restart forgets everything, by design.

**Known gaps, stated plainly:** a photograph of the owner still identifies at
`basic`; a photograph plus a recording of the exact question would satisfy
`strong` once a reserved capability exists. Replay and liveness are measured on
hardware, not defended. Pipec's real-hardware matrix (2026-09-30, one owner, one laptop
camera and microphone; [Plan 0054](../plans/completed/0054-face-default-identity-fusion.md))
passed the owner, muffled-voice, voice-recording-only, two-faces, covered-camera and
missing-voice-model cases; a phone-screen photo (3 attempts) and video (2 attempts) did not
identify, which says nothing about a better spoof; the optional PIN case was not run.

### Memory candidates and the memory dialogue (Plans 0062 and 0063, CM-3a, ADR 0021): off by default

A successful generic **voice** turn (classic or streaming `/transcribe`) can leave a
short-lived *memory candidate*: something the owner said about their own taste
("me gusta el mate"). It is not memory. A candidate lives for `MEMORY_CANDIDATE_TTL_SECONDS`
(24 h). On a later voice turn the robot **offers** to keep it, out loud, and only the owner's
spoken answer promotes it, through the one writer (`memory_writer.promote`), into a confirmed
fact. [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md) added the offer and the answer
(closed 2026-10-16); the hardware acceptance is
[`0063-memory-dialogue-acceptance.md`](../evals/0063-memory-dialogue-acceptance.md). `/chat` and
`/vision/respond` never propose, offer or answer.

**What has to be true for a candidate to be stored**, in the order the server checks it, the
cheap steps before the expensive ones:

1. `MEMORY_CANDIDATES_ENABLED=true` (and `MEMORY_ENABLED=true`).
2. The sentence passes a closed Spanish grammar of first-person tastes (`me gusta`, `no me
   gusta`, `odio`, `prefiero`, ...). The grammar is conservative on purpose: the expected
   failure is **too few candidates**, not a wrong one. Questions, "me gusta que ...",
   plurals and diminutives of person or sensitive words, a contrast inside one taste ("todo
   menos el café", "prefiero el mate al café") and capitalized names are refused;
   `No, me gusta el mate` is a `likes` candidate by design; places and names in lower case
   rely on the topic set.
3. The speaker was identified by **face** on that turn, with no PIN token.
4. The **voice** of that turn's own clip verified against the same person (no clip, a clip
   under `SPEAKER_MIN_VERIFICATION_S`, another voice or a backend failure means no candidate).
5. One extraction at a time and at most `MEMORY_CANDIDATE_EXTRACTIONS_PER_HOUR` per hour: the
   extractor is one model call that sees only the user's words, with no retry (about 41 s on
   the shared development laptop, in the background after the reply was sent).
6. A pure classifier accepts the model's triple, both consents (face and voice) are still
   active, the policy allows `propose_personal_memory` (the decision is audited before the
   effect) and the store accepts it (not a repeat, the person under `MEMORY_CANDIDATE_MAX_LIVE`).

**Turning it on safely.** It needs both identity flags and an enrolled owner:

1. `FACE_AUTHENTICATION_ENABLED=true` and `SPEAKER_AUTHENTICATION_ENABLED=true` on the server,
   `ROBOT_FACE_AUTH_ENABLED=true` on the robot (a frame per turn), and the owner enrolled for
   **both** face and voice (`just setup-personal status` and Tier 2 and Tier 3 above; at least
   `SPEAKER_MIN_REFERENCE_COUNT` voice references). With a face only, every matching turn ends
   as `dropped (strong_unreachable)` and nothing is stored.
2. Set `MEMORY_CANDIDATES_ENABLED=true` in `.env` and start the server yourself. The settings
   are read at start-up. The log must show `Candidates reconciled at start-up: 0 expired`
   (switch on; the migration that creates the table is number 9).
3. Say one matching sentence with the owner's face in frame. The log should show
   `Candidate proposal: stored=1 dropped=0` and `Candidate insert: inserted`. To count without
   reading anything, run `uv run python scripts/inspect_candidates.py` (see *Counting what
   happened* below). Do not select `value_text` into a shared terminal or ticket: it is exactly
   what the owner said.
4. The offer and the answer need no further switch: with `MEMORY_ENABLED=true` and
   `MEMORY_CANDIDATES_ENABLED=true` the voice routes offer and listen for answers (next
   subsection).

**The dialogue: what Iroko says and what you answer.** With the switch on, a stored candidate is
offered on a **later** turn of the same person, as a second voice clip after the reply (classic
`/transcribe`: the same audio; streaming: one more audio event after the reply). The text the
robot returns is the reply only; the offer is not written to the conversation history. Iroko
speaks, in this order:

1. The offer, with the stored phrase in place of `{x}`: «Antes me dijiste que te gusta(n) {x}.
   ¿Quieres que lo guarde? Dime: sí, autorizo.» (a dislike says «que no te gusta(n)», a preference
   «que prefieres»). The statement names the value and the question dictates the short answer, so
   say it back: «sí, autorizo.» is enough (Plan 0066; until then the offer asked to repeat the
   value, and that long answer still works).
2. To accept, a closed verb **alone** is enough: `autorizo`, `autoriza`, `apruebo`, `aprueba`,
   alone or followed by `guardar`, `a guardar`, `guardarlo`, `a guardarlo` or `que guardes` («autorizo», «sí, autorizo.»,
   «apruebo, gracias», «autorizo guardar»). `guarda` and `guárdalo` also work alone, but **only
   after a leading «sí»** («sí, guarda», «sí po, guárdalo»), because «guarda» is an ordinary
   imperative. The value stays optional: «autorizo guardar el mate», «autorizo a guardar …» and
   «apruebo que guardes …» still work, and the value that you say **must match the open offer**
   (a different or garbled value promotes nothing). The answer also survives how Whisper writes
   it (Plan 0064): the third person, a leading «ya», «dale» or «po», a trailing «po» and
   «mi»/«mis» before the value («sí po, autoriza a guardar mi café»). Iroko says «Listo, lo
   guardé.» and the taste becomes a confirmed fact. Since Plan 0067 the words people actually say
   also work: `acepto` and `acepta` are long verbs like `autorizo` («acepto», «sí, acepto»,
   «acepto guardar»), `guárdala` is a short verb like `guárdalo` (only after a leading «sí»:
   «sí, guárdala»), and after a long verb the courtesy words `guárdalo`, `guárdala` and `sí` are
   accepted («sí, autorizo, guárdalo»). Since Plan 0068 the long verbs also take «que lo
   guardes» and «que la guardes» («sí, autorizo que lo guardes»), the exact words the retry below
   dictates.
3. To decline: `no autorizo`, `no apruebo` (also `no autoriza`, `no aprueba`), `no acepto` and
   `no acepta` (Plan 0067), `no lo guardes` and `no guardes` work alone. `olvídalo` and `bórralo` still need the value («olvídalo el mate»):
   alone they are ordinary speech. Iroko says «Está bien, no lo guardo.» and the candidate's value
   is erased.
4. If the owner already has a different confirmed taste for the same thing, Iroko says «No lo
   guardé: ya tengo guardado algo distinto.» and writes nothing.
5. If the owner's own open offer was found but could not be settled (a database or policy
   failure), Iroko says «No pude guardarlo ahora. Dímelo de nuevo en un rato.» Nothing was
   written; answer again later.
6. **The retry (Plan 0068).** If your **face** is recognized and your open offer is the one your
   words answer, but the **voice check failed** (a short «sí, autorizo.» often does), Iroko says
   «No reconocí bien tu voz. Dímelo un poco más largo: sí, autorizo que lo guardes.» and the robot
   listens once more in reply mode. Say the longer sentence it dictates. Nothing was saved,
   audited or moved, and the 60 s window is **not** extended, so answer inside it. If you have
   revoked the voice consent there is no retry (the voice could never verify): the message is
   ordinary conversation, as before. In the log it is `Candidate answer: voice_retry`.

A bare «sí» (also «ya», «dale» or «po» alone), «guarda», «guárdalo» or «guárdala» without a leading «sí», and
a verb with a **different** value promote nothing: the message is ordinary conversation. A valueless
answer resolves the offer only when **exactly one** offer of yours is open inside the 60 s window
(zero or more than one: ordinary conversation). The short verbs (`guarda`, `guárdalo`, `olvídalo`,
`bórralo`) followed by a value need an article before it («guarda el mate»), so «guarda silencio»
or «olvídalo, no importa» never count.

**The rules around it.**

- **The turn must be long.** The offer needs the voice check of that turn's own clip, so the
  turn that carries it should be a full sentence of about 3 s or more. A short turn («hola»,
  about 1.5 s) usually fails the voice check, logs `Candidate offer: voice_unverified` and
  offers nothing; the candidate waits for a better turn.
- **One offer at a time per person**, and the answer window is `MEMORY_CANDIDATE_ANSWER_SECONDS`
  (60 s). After it the candidate returns to `proposed` and can be offered again, at most
  `MEMORY_CANDIDATE_MAX_OFFERS` (2) times; after the second offer it lapses unanswered.
- **Face and voice of the same person**, on the clip of the answering turn too. With another
  voice, no face or two faces the message is ordinary conversation, byte for byte: Iroko
  never says whether an offer exists. **One exception since Plan 0068:** when the owner's face is
  recognized and the voice alone failed, the retry above is spoken instead, which reveals that an
  offer is open; anyone speaking in front of the owner's face hears it too (an offer already
  spoken aloud in the room), and it writes nothing. A token, another person's face or no open
  offer still get ordinary conversation. The cost of that check (about 3 to 4 s over the
  speech-to-text, no model call) is paid by every message that has the shape of an answer, with
  or without an open offer. Since Plan 0066 that includes a bare «autorizo» or «sí, guarda» in
  ordinary conversation with **no open offer**: it costs those 3 to 4 s, saves nothing and gets an
  ordinary reply.
- **A recording is not defended.** Nothing in the answer proves it is live (ADR 0016 §9). Since
  Plan 0066 a recording of you saying «autorizo», played with your face in front of the robot
  inside the 60 s window of an open offer, would promote that offer without knowing its value
  ([ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9).
- **The robot listens to the reply in its own mode** (Plan 0067, robot streaming mode only; see
  *Listening for the reply* below). The classic route and the robot's classic path are unchanged.

**Listening for the reply (Plan 0067, robot streaming mode).** When the offer was actually
spoken, the stream's `done` event says so (`expects_short_reply: true`) and the robot listens
**once** in a reply mode: it waits longer for the end of your speech, so a pause inside
«sí… acepto» stays one clip, and it gives up sooner if you say nothing. Then it goes back to
normal listening. Two robot settings (in the robot's `.env`, read at start-up; defaults in
`.env.example`), first values to be tuned on hardware, not measured ones:

| Variable | Default | Effect |
|---|---|---|
| `VAD_REPLY_SILENCE_MS` | `1600` | Silence that ends the reply (normal listening: `VAD_SILENCE_MS`, 1200). Raise it if a pause inside the answer still cuts it in two; lower it if the robot waits too long after you finish. The clip that is uploaded is trimmed back to the normal tail, so a longer value does not make the voice check worse |
| `REPLY_WAIT_S` | `15` | Seconds to wait for you to start the reply (normal listening: 30). If nothing is heard the robot returns to normal listening by itself and the offer stays open until its 60 s window ends |

The reply is an ordinary request with one extra form field, `short_reply=true`, whose only effect
is a fixed list of hotwords for the speech-to-text (`sí`, `no`, `acepto`, `autorizo`, `apruebo`,
`guárdalo`, `guárdala`; `SHORT_REPLY_HOTWORDS` in `server/src/server/stt.py`). It changes nothing
about who may answer, the open-offer lookup or the words accepted: a reply that is not an answer
(«¿qué hora es?») gets the ordinary reply. An older robot ignores the hint and an older server
never sends it; both keep working. In the log a reply turn looks like any other turn: the same
`Speaker verdict`, `Identity fusion` and `Candidate answer` lines, and `Speaker verdict` is
unchanged (a `unknown` on a short clip is still the voice check, not a listening problem; since
Plan 0068 its `gate` and `distance` fields say why, and the retry above answers it). The log has no line for reply mode itself.

**Known limits, measured on hardware** (outcomes in
[`0063-memory-dialogue-acceptance.md`](../evals/0063-memory-dialogue-acceptance.md), one owner,
the shared laptop, no homelab):

- The explicit answer was parsed **2 of 4** times in the Plan 0063 acceptance: Whisper `small`
  writes «autoriza a guardar …», «sí po, …» or «mi» before the value. Plan 0064 widened the
  grammar for exactly those writings, and Plan 0066 made the value optional because a word
  inserted inside it was what failed (the answer that repeated the value was understood 1 of 2
  times in the Plan 0064 session; the first Plan 0066 session promoted 1 of 2; the other fell to
  ordinary conversation). The short answer and the reply mode are **not yet measured on
  hardware**: their acceptance counts are pending until Pipec runs Task 6 of Plan 0066 and Task 8
  of [Plan 0067](../plans/completed/0067-reply-listening-mode.md). The retry of Plan 0068 and the
  short-clip speaker measurement (Part B, above) are pending the same way. When an answer is still
  not understood, it falls through to ordinary conversation and nothing is written (the safe
  direction); say it again, slowly, or wait for the second offer.
- On a message that only has the *shape* of an answer (another voice, or no open offer), the
  language model used to say it saved something. **It did not.** Since Plan 0064 the robot
  replaces any model sentence that claims to have saved, registered or noted something with
  «Eso no lo he guardado.» (a bare «Anotado.» is left alone). Only the lines below prove a
  write.
- About 2 of 12 turns were answered partly or wholly in French. Since Plan 0064 every prompt asks
  for Spanish (the last block of the master prompt and the streaming contract) and the robot
  speaks tuteo everywhere; `just eval-chat --mode stream` reports the *Not in Spanish* count.
- The first chat turn after Ollama starts can fail while memory is short (the stream speaks its
  fallback phrase); warm the model first, with one ordinary sentence after the start. Since Plan
  0064 the server logs one warning at start-up when Ollama does not answer `/api/tags`; it does
  **not** detect this cold-start failure, because a model that is still loading answers
  `/api/tags`.
- Replay (a photo plus an earlier recording) was not measured.

**Reading the log.** Every line carries closed reasons, never a value, a transcript or an
exception message. `logs/server.log` is JSON Lines (one object per line: `ts`, `level`, `logger`,
`msg` and the structured fields), so `msg` holds the text in the table.

| Line | Meaning |
|---|---|
| `Candidate proposal: dropped (<reason>)` | The attempt ended early. Reasons: `gate_no_match` (no taste in the sentence; the usual case, no voice check and no model call), `not_a_taste`, `negation_unsupported`, `sensitive_topic`, `strong_unreachable` (no face actor, voice not verified, or a consent revoked), `busy`, `budget`, `denied` (switch off, model unreachable or malformed JSON, or the policy or its audit row refused) |
| `Candidate proposal: stored=N dropped=M` | The attempt reached the model. The reasons of the dropped triples (`gate_mismatch`, `not_grounded`, `sensitive_topic`, `not_a_taste`, `duplicate`, `capacity`, ...) are in the structured `reasons` field of that record, not in the message |
| `Candidate insert: <status>` | `inserted`, `duplicate`, `capacity` or `disabled` |
| `Candidate promotion: <outcome>` | The writer's own line: `promoted`, `already_present`, `contradiction`, `not_offered` or `denied`. It appears only after a spoken «sí, autorizo.» (or the long form that repeats the value) |
| `Candidate offer: <outcome>` | `offered` (the offer was spoken after the reply), `voice_unverified` (a candidate waited but the voice of that turn's clip did not verify as the same person, so nothing was offered) or `not_offerable` (the candidate lapsed or was taken between the check and the reply) |
| `Candidate answer: <outcome>` | The result of a spoken answer to an open offer: `promoted`, `already_present`, `contradiction`, `not_offered`, `denied` (the writer's outcomes, repeated), `rejected` (the owner declined) or `voice_retry` (Plan 0068: the face named the owner but the voice did not verify, the retry phrase was spoken and nothing was written; the line carries the candidate id only) |
| `Candidate offer failed (...)` / `Candidate answer failed (...)` | A warning (an error when the failure is not an operational class) with `error_type` and `site`, the file, line and function; never a message or a value. On an answer failure the owner heard the fixed failure phrase |
| `Speaker verdict: verified \| unknown \| unavailable` | Every voice check of the turn, offers and answers included. `verified` is the only verdict that lets an offer or an answer through; `unknown` is another voice, a very short clip or fewer than `SPEAKER_MIN_REFERENCE_COUNT` references; `unavailable` is the speaker model or its backend failing. Since Plan 0068 the record also carries `clip_s` (the uploaded clip's seconds, one decimal), `distance` (to the owner's references, three decimals; **absent** when none was computed, never 0) and `gate` (the first reason the verdict was not `verified`: `ok`, `energy`, `duration`, `references`, `distance`, `consent`, `role` or `unavailable`). Read an `unknown` on a short answer by its `gate`: `distance` with a `distance` just above 0.4834 is a clip that nearly passed; `duration` or `energy` means the clip never reached the model (shorter than `SPEAKER_MIN_VERIFICATION_S`, or no voiced energy); `references` means too few stored references. Never audio, a name or a value |
| `Identity fusion: <reason>` | Whom the turn is attributed to; `face_and_voice` is the only reason that can answer an offer, `face_only` or `no_evidence` mean the message went on as ordinary conversation |
| `Candidates voided at start-up: N` | Start-up with the switch **off**: N live candidates were erased |
| `Candidates reconciled at start-up: N expired` | Start-up with the switch **on**: N lapsed candidates were erased |
| `candidate.extraction_failed`, `candidate.enrolment_check_failed` | A warning with an `error_type`: the model call failed, or the consent read failed and the step was denied |
| `candidate.proposal_error` | A warning that carries `error_type`, `error_file`, `error_line`, `error_function` and `stored`: an unexpected failure in the background task, located but never quoted. The user's reply was already sent |

`aiosqlite` is held at `WARNING` because at `DEBUG` it prints statement parameters, which
would put a stored value in the log.

**Rolling back.** Either of these leaves no live candidate value in the database file:

- set `MEMORY_CANDIDATES_ENABLED=false` (and restart the server; settings are read at start-up).
  From the first turn after that start nothing is proposed, **offered or answered**: the voice
  routes inject neither the offer nor the answerer, so an answer-shaped message is ordinary
  conversation and the actor is not even resolved for it. The start-up logs
  `Candidates voided at start-up: N`, erases the values and truncates the write-ahead log; or
- with the server **stopped**, run `uv run python scripts/scrub_candidates.py data/omnibot.db`.
  It prints `Voided N live candidate(s)`, exits `0` when none remains (also for a database
  with no candidate table yet) and exits `1` when it could not scrub the file or truncate its
  log because another process holds it.

Facts already confirmed by a spoken «autorizo» are not candidates and stay in the
database; rolling back does not erase them.

**Counting what happened, without seeing a sentence.** With the server running or stopped (it
opens the file read-only):

```text
uv run python scripts/inspect_candidates.py
uv run python scripts/inspect_candidates.py path/to/omnibot.db
```

It prints one line per kind of count and never a value, a name or a transcript:
`candidates:` the number in each status (`proposed`, `offered`, `confirmed`, `rejected`,
`expired`, ...); `audit <action>:` the `allowed`, `denied` and `requires_confirmation` rows
of the three memory steps (`propose`, `read`, `confirm`); `confirmed facts:` the active
personal tastes that carry who confirmed them; and `missing tables:` when the file predates a
table, so a row of zeros is never mistaken for "nothing happened". Without a path it reads
`BRAIN_DB_PATH`. It exits `1` when the file does not exist or cannot be read.

**WARNING: never use `just reset-db` for this.** It deletes the **whole** database after a
backup: face and voice enrolments, the PIN, household data and every memory, not just the
candidates. To cancel what the dialogue left behind use the switch and
`scripts/scrub_candidates.py` above.

**`just reset-db` and backups.** `just reset-db` first runs `scripts/scrub_candidates.py`
(voids the live candidates, overwrites their bytes, truncates the log) and only then copies the
file to `data/backups`. When the scrub exits `1` it stops with `database was NOT copied`: close
whatever holds `data/omnibot.db` (an SQLite browser, a second server) and run it again.
The 14 backups that existed on 2026-10-15 predate migration 009 and hold no candidate table.
The connection runs with `PRAGMA secure_delete = ON`, so a resolved candidate's bytes are
overwritten, and a checkpoint that cannot finish is retried at the next store entry and
hourly; a start-up always truncates the log.

## 4. Feature-flag reference

| Variable | Default | Effect |
|---|---|---|
| `ROBOT_OWNER_UNLOCK_PROMPT` | `false` | Prompt once for the PIN at robot startup (`getpass`) — works in both classic and streaming mode |
| `ROBOT_STREAMING` | `false` | Use `/transcribe/stream` instead of classic `/transcribe` |
| `VISION_ENABLED` | `false` | Server: enables `/vision/describe`, `/vision/respond` scene description (unrelated to face auth) |
| `FACE_AUTHENTICATION_ENABLED` | `false` | Server: attempt face resolution when a frame is attached to a protected turn |
| `FACE_AUTHENTICATION_MATCH_THRESHOLD` | `0.5815` | Stricter, separate match bound for authentication (layered on top of `FACE_MATCH_THRESHOLD`); measured by Plan 0030, provisional |
| `ROBOT_FACE_AUTH_ENABLED` | `false` | Robot: capture and attach one webcam frame per turn |
| `FACE_MATCH_THRESHOLD` | `0.4` | Generic conversational face-recognition threshold (unrelated to authentication) |
| `SPEAKER_AUTHENTICATION_ENABLED` | `false` | Server: after the owner's face matched, consult the speaker resolver once per protected turn and raise the assurance to `strong` on a verified voice; enrolment returns 503 while off, revocation always works |
| `SPEAKER_AUTHENTICATION_MATCH_THRESHOLD` | `0.4834` | Cosine distance to the reference centroid; provisional and in-sample (Plan 0047) |
| `SPEAKER_MIN_REFERENCE_COUNT` | `3` | References required before verification is attempted |
| `SPEAKER_MIN_VERIFICATION_S` / `SPEAKER_MIN_ENROLLMENT_S` | `1.5` / `2.0` | Shortest clip embedded at a turn / accepted at enrolment; the first is a conservative guess, not measured |
| `SPEAKER_MODEL_RETRY_COOLDOWN_S` | `60` | Seconds to wait after a failed speaker-model load before trying again |
| `SPEAKER_EMBED_TIMEOUT_S` | `30` | Longest a protected turn waits for the embedding (the first call also loads the model, about 15 s); on expiry the turn degrades to `unavailable` |
| `SPEAKER_MODEL_CACHE_DIR` | unset | Optional override; defaults to `MODELS_DIR/speechbrain` |
| `MEMORY_ENABLED` | `true` | Server: the whole memory subsystem. Off, generic turns identify nobody, keep no session and touch no store |
| `WORKING_MEMORY_SIZE` | `20` | Upper bound on messages kept in the short-term session (below 2 keeps nothing) |
| `WORKING_MEMORY_MAX_CHARS` | `3000` | Characters of turn content the session may hold; whole oldest exchanges leave first |
| `WORKING_MEMORY_IDLE_SECONDS` | `180` | Seconds without a written turn after which the session is forgotten |
| `MEMORY_CANDIDATES_ENABLED` | `false` | Server: kill-switch of the memory-candidate path and its spoken dialogue (Plans 0062 and 0063; left `false` by default on purpose). Off, nothing is proposed, stored, offered, answered or promoted and every live candidate is voided at the next start-up. On, it needs `MEMORY_ENABLED`, `FACE_AUTHENTICATION_ENABLED` and `SPEAKER_AUTHENTICATION_ENABLED` on the server, `ROBOT_FACE_AUTH_ENABLED` on the robot, plus an enrolled owner face and voice (at least `SPEAKER_MIN_REFERENCE_COUNT` references), or every attempt ends as `strong_unreachable` |
| `MEMORY_CANDIDATE_TTL_SECONDS` | `86400` | How long a candidate lives before it lapses and its value is erased |
| `MEMORY_CANDIDATE_MAX_LIVE` | `5` | Live candidates one person may hold; at the cap a new one is dropped as `capacity`, nothing is evicted |
| `MEMORY_CANDIDATE_VALUE_MAX_CHARS` | `80` | Longest spoken object a candidate may carry; longer is `not_a_taste` |
| `MEMORY_CANDIDATE_MAX_OFFERS` | `2` | Times a candidate may be offered before it lapses (Plan 0063) |
| `MEMORY_CANDIDATE_ANSWER_SECONDS` | `60` | Seconds an offered candidate waits for an answer before it returns to `proposed` and can be offered again (Plan 0063) |
| `MEMORY_CANDIDATE_EXTRACTIONS_PER_HOUR` | `12` | Extraction model calls that may start in any rolling hour; beyond it a turn is dropped as `budget` (one at a time besides: `busy`) |
| `VAD_REPLY_SILENCE_MS` / `REPLY_WAIT_S` | `1600` / `15` | Robot, streaming mode: end-of-speech silence and wait for speech when the robot listens once to the reply to a spoken memory offer (Plan 0067); first values to tune, see the memory dialogue above |
| `UVICORN_WORKERS` | `1` | Must stay `1` — owner/face grants are process-local; the server refuses to start otherwise |

**The one real startup guard:** `ROBOT_STREAMING=true` on the robot plus
`VISION_ENABLED=true` on the server makes the robot refuse to start
(`SystemExit`, checked once at boot via `check_vision_enabled()`) — streaming
has no code path for visual questions yet (F-08). Every other flag
combination above is safe to mix.

## 5. Where the evidence lives

- Per-plan real-hardware acceptance records: `project-history/acceptance/*`
  (gitignored — local history, never cited as a plan's required reading).
- The combined P0 operator runbook:
  [`p0-runtime-acceptance.md`](p0-runtime-acceptance.md).
- Plan 0061 acceptance (short-term continuity, the face check's cost and the history
  stream measurements, outcomes only):
  [`0061-generic-turn-continuity-acceptance.md`](../evals/0061-generic-turn-continuity-acceptance.md).
- Plan 0062 local smoke (memory candidates: start-up paths on the real database, outcomes
  only): [`0062-memory-candidates-local-smoke.md`](../evals/0062-memory-candidates-local-smoke.md).
- Plan 0063 hardware acceptance (the spoken offer, the explicit answer and the firewall around
  them, outcomes only):
  [`0063-memory-dialogue-acceptance.md`](../evals/0063-memory-dialogue-acceptance.md).
- What's actually implemented right now, including open gaps:
  [`current-state.md`](../architecture/current-state.md).
- What's authorized to build next: [`docs/plans/README.md`](../plans/README.md).

## 6. What `just setup-personal` actually does, and a dead feature it should not be confused with

Verified 2026-08-26 by reading `personal_setup.py` end to end, not assumed.
This is the **only** thing that answers "Pipec is your owner" — nothing
conversational does this, see below.

### The exact write sequence

```powershell
just setup-personal          # requires run-server/run-robot stopped — single SQLite connection
```

Three writes, in order, all inside `apply_personal_setup()`:

1. **`_confirm_owner_entity`** — `upsert_entity(name=owner_name, type="person")`, then
   `bootstrap_initial_owner(person_entity_id, confirmed_person_entity_id)`. This is
   the actual anchor: one row in `household_role_assignments` with `role='owner'`,
   enforced singleton (`_active_owner_exists()` raises if one already exists).
   Reruns with the same name reuse the same entity — it does not duplicate.
2. **`_confirm_children`** — one entity + one `child_of` relation per name, in
   `entity_relations_v4`, pointed at the owner entity from step 1.
3. **`_confirm_credential`** — hashes the PIN with scrypt (`hash_pin`), stores it
   via `save_owner_pin_credential`. Reusing the same PIN is a no-op; a different
   one rotates the credential.

Everything the rest of this manual's Tier 1/Tier 2 sections depend on — `get_active_role()`,
the PIN unlock, the face resolver's owner check — reads back exactly these three writes.
There is no fourth, hidden mechanism.

### A dead feature that looks like an alternative onboarding — it is not one

The character prompt (`characters/iroko.py`) has a real, well-built conversational
onboarding block:

```
PRIMER ENCUENTRO — acabás de despertar y conocés a una persona del hogar por primera vez:
- Presentate en máximo 2 oraciones...
- Qué preguntar lo indica el PRÓXIMO OBJETIVO más abajo...
- UNA sola pregunta por turno...
```

Backed by an 8-slot checklist (`onboarding.py`): `nombre → fecha_nacimiento → vive_en
→ pareja_de → hijo_de → mascota_de → trabaja_en → le_gusta`. It looks like it should be
the conversational path to "the robot learns who its owner is." **It is not, for two
independent reasons, both verified against the current code:**

1. **It could never create the owner even if it worked.** The gate at
   `text_turn.py`'s `prepare_text_turn()` — the persistent context and the
   onboarding slot are loaded only when `_manual_evidence(...)` is not `None`, and
   a face- or token-identified turn gets the short-term history only
   (`onboarding=False`) — means this interview only starts for an
   ALREADY-identified actor. It was designed as a "get to know you better" layer on top of an
   existing owner, never as the mechanism that establishes one. `just setup-personal`
   has no conversational alternative today.
2. **It is fully disconnected, right now.** The one function that could pass real
   values into it, [`text_turn.py::_memory_prompt_state`](../../server/src/server/text_turn.py),
   builds the legacy memory context and always returns `onboarding=False` and no
   slot (a memory error degrades to a stateless turn). `onboarding.py::next_missing_slot()`
   has zero live callers anywhere in the repo — confirmed by grep, not inference.
   This matches what [ADR-0007](../adr/0007-first-boot-and-default-posture.md)
   flagged as "built, tested, zero production callers" back on 2026-08-19; it is
   still true after everything Plan 0029 added.

Three things look alike and must not be confused: `personal_security_ready` (an
active owner holds the active PIN credential — what `just setup-personal status`
reports), the legacy `onboarding_complete` flag (a separate, never-set meta flag of
this disabled interview) and biometric enrolment (consented face and voice
references). None of them proves that Iroko has learned anything conversationally.

**Do not reconnect this as-is if it ever comes up.** Its checklist reads/writes the
legacy v3 fact tables (`load_entity_with_facts`, `find_facts_by_predicate`), not the
v4 tables (`entity_relations_v4`) `setup-personal` uses — reconnecting it verbatim
would ask "¿tenés hijos?" again and store the answer somewhere `get_children()` never
looks. Any future reconnection needs its own bounded plan: migrate the checklist to
v4, then decide whether it should still gate on an existing owner or be scoped
narrower (e.g. only the optional/non-security slots — birthday, work, likes).

### The symptom this explains: "los hijos son Joaco..." instead of "tus hijos son Joaco..."

Before the deterministic child-name tool existed (or when a question's phrasing
doesn't match the intent resolver's known patterns and falls through to generic
LLM generation), the ONLY path available was free LLM generation over memory
context. That path carries an explicit rule (`_PRESENTATION_GUIDANCE` in
`characters/__init__.py`):

```
- Do not infer relationships, personal facts, or authorization from it.
```

Even with a name available in context, the LLM is forbidden from concluding
"so these are YOUR children" — it has no deterministic authorization to make that
claim. That is structurally why it degrades to third person. The fix is not a
prompt tweak: it's routing the question through the deterministic tool
(`controller.py::_household_tool_plan`, `response = f"Tus hijos son {names}."`,
never touching the LLM), which is what Plans 0021/0025–0028 already built and this
plan's Tier 1/Tier 2 sections describe. If this symptom reappears, the fault is
almost always an unrecognized phrasing in `cognition/intent_resolution.py`, not the
character prompt.
