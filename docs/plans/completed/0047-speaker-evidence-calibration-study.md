# Speaker-Evidence Calibration Study Implementation Plan

> **For future agentic workers:** after this plan is promoted to `Ready`, work
> it on **one simple feature branch from `main`** (never a git worktree — a
> firm project rule), then use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans`. Use
> `superpowers:test-driven-development` for each behavior,
> `superpowers:systematic-debugging` for failures,
> `superpowers:verification-before-completion` before claims, and
> `superpowers:requesting-code-review` for independent review. Pipec—not an
> agent—owns every real microphone, impostor and replay capture checkpoint.

**Status:** **Closed 2026-09-25 — PC-3A PROVISIONAL PASS.** The plan was promoted
to `Ready`/`NOW` on 2026-09-08 on Pipec's explicit decision, after all 9 readiness
blockers were cleared and an independent plan review returned **APPROVE WITH MINOR
FIXES** with every finding applied. It executed on `feat/0047-speaker-calibration`;
the branch merges when Pipec opens the PR. The measured result and the closure
evidence are in "Study result and closure record" below.

**Execution history.** Tasks 0–3 (numeric layer, private-corpus CLI, frozen backend
and the CPU p95 gate — a technical PASS) ran first. Pipec then ran the owner-only
capture (Task 4, 2026-09-14) and the third-party recruitment as two parallel tracks
instead of a strict sequence, so the replay half of Task 5 finished with Task 4.
The live-impostor captures ended 2026-09-25; Task 6 measured the corpus the same
day and Task 7 (independent reviews, privacy cleanup, documentation) closed the
study. The sections below keep the original task text; the closure record holds
the final evidence.

**Goal:** Evaluate whether a local CPU speaker-embedding backend can separate
Pipec's live voice from consenting live impostors under household conditions;
measure false accepts, false rejects, replay behavior and latency; and either
select an evidence-based candidate for a later PC-3B runtime plan or close the
study honestly as FAIL. This plan does not enroll a production voiceprint and
does not make `VOICE` trusted identity evidence.

**Architecture — three isolated layers:**

1. **Pure numeric harness:** strict sample metadata, L2 normalization,
   reference centroid, cosine distance, threshold sweep, FAR/FRR and latency
   percentiles. Unit tests use synthetic vectors and never load a model.
2. **Replaceable evaluation backend:** one protocol accepts validated WAV bytes
   and returns one finite, fixed-dimension (192-d) embedding. The concrete
   model, version, revision, license, preprocessing and installation command
   are frozen in the "Frozen readiness contract" section (amended 2026-09-08).
3. **Operator-owned temporary corpus:** real WAV files and derived embeddings
   stay under a gitignored calibration directory, use pseudonyms, and are
   deleted after an aggregate privacy-reviewed report is accepted. The harness
   and schema are reproducible; household voices are deliberately not.

**Tech stack after readiness:** Python 3.12, numpy, current WAV validation and
microphone capture, and — frozen by the 2026-09-08 readiness amendment —
`speechbrain==1.1.1`'s `EncoderClassifier` with the locally cached CPU ECAPA
model `speechbrain/spkrec-ecapa-voxceleb` at revision `0f99f2d0…`, plus pytest,
Ruff, mypy and `just`. No cloud inference is allowed.

**Spec:** [Plan 0015 PC-3](../open/0015-personal-companion-design.md),
[identity and access](../../architecture/identity-and-access.md),
[current state](../../architecture/current-state.md),
[ADR 0006](../../adr/0006-personal-and-family-companion-profiles.md).

## Why this plan was queued (promoted 2026-09-08)

The repository currently has no speaker-recognition code, voiceprint schema,
speaker enrollment, diarization or selected dependency. `IdentityEvidenceSource.VOICE`
exists, but the trusted-source set excludes it and tests require voice-only
input to remain `UNKNOWN`. STT and VAD identify speech activity/content, not a
speaker.

One concrete study candidate exists: SpeechBrain `1.1.1`. Its official
[`SpeakerRecognition` source at tag v1.1.1](https://github.com/speechbrain/speechbrain/blob/v1.1.1/speechbrain/inference/speaker.py)
exposes speaker embedding/verification, and the Apache-2.0 ECAPA-TDNN model is
frozen to revision
[`0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/commit/0f99f2d0ebe89ac095bcc5903c4dd8f72b367286).
The [SpeechBrain 1.1.1 package record](https://pypi.org/project/speechbrain/1.1.1/)
declares Python `>=3.8.1` and Apache-2.0, but that is only research evidence:
the package/model have not been installed or validated on this repository's
Windows, Python 3.12 and CPU environment. Its generic score threshold is not a
household authorization threshold.

The candidate may fail technically during the authorized study. The
documentation-only readiness amendment (2026-09-08) has now frozen the exact
v1.1.1 call, tensor/array shape, cache path and preprocessing from pinned
primary sources — see the "Frozen readiness contract" section below. No
implementer may choose another backend while executing this plan.

## Readiness blockers and promotion gate

No task in this file may execute while it is `Queued`. Promotion work is
documentation-only and must complete all items below without installing a
package, downloading a model or capturing audio:

- [x] Plan 0046 is closed (2026-09-08). PR #122 squash-merged to `main` as
  `00c3c09`; `NOW` is empty and 0047 is the next slice.
- [x] A read-only researcher refreshed the three pinned primary sources
  (2026-09-08). **No material version/license/security drift.** Two API details
  and one environment detail were recorded and absorbed into the frozen
  contract below — see "Source refresh" in that section. SpeechBrain `1.1.1`
  (2026-08-27, Apache-2.0, `requires-python >=3.8.1`) is the latest stable; the
  ECAPA model revision `0f99f2d0…` is Apache-2.0 and is the current `main` HEAD
  on Hugging Face, so pinning it does not freeze a stale version.
- [x] The plan is amended with the exact backend construction, embedding call,
  input tensor shape/dtype, output shape, PCM int16 → float conversion, CPU
  device selection, immutable model revision and offline cache behavior —
  "Frozen readiness contract" → blocks 1 and 2. No free adapter choice remains.
- [x] The root development dependency command, expected `pyproject.toml`/
  `uv.lock` scope and rollback are frozen — block 3. Root `dev` group only; no
  subproject dependency edit.
- [x] The three literal neutral Spanish phrases and the p95 CPU feasibility
  budget (**≤ 500 ms**, chosen by Pipec before any measurement) are frozen —
  block 4.
- [x] The latency protocol is frozen verbatim — block 5.
- [x] The exact model-contract, capture, validate, analyze and cleanup commands
  are frozen — block 6.
- [x] Pipec explicitly approved (2026-09-08) testing SpeechBrain `1.1.1` plus
  the pinned model, including package/model downloads and the ~200–300 MB
  CPU-only torch cost, accepting the possibility of a technical FAIL before any
  household capture.
- [x] Independent plan review run 2026-09-08 — **APPROVE WITH MINOR FIXES**. All
  2 MEDIUM + 6 LOW findings applied (see "Independent review" below). Nothing in
  the findings required redesign or re-freezing the backend.
- [x] Pipec's explicit promotion decision (2026-09-08): `Status` → `Ready`, 0047
  is the sole `NOW`, Tasks 0–3 authorized to execute now; Tasks 4–6 held for
  consented-adult confirmation. See the staged-execution note under **Status**.

If Pipec declines the candidate, the plan remains queued or is cancelled by an
explicit roadmap decision; that is not measured FAIL. After promotion, a real
compatibility/backend failure is an evidence-complete technical FAIL and may
close the study without collecting household voices.

## Frozen readiness contract (amended 2026-09-08)

This section satisfies readiness blockers 3–8. It is normative: an implementer
executing this plan after promotion follows it exactly and may not substitute a
backend, version, tensor shape, command, phrase or threshold. Any material
divergence discovered against the installed package (block 2's verification
note) is a **documentation stop** for a new amendment, not an in-flight
adaptation.

### Source refresh (blocker 2, read-only, 2026-09-08)

| Pinned source | Verified state | Drift |
|---|---|---|
| [PyPI `speechbrain 1.1.1`](https://pypi.org/project/speechbrain/1.1.1/) | Published 2026-08-27, Apache-2.0, `requires-python >=3.8.1`. Latest stable; no later release. | None |
| [`speechbrain/inference` @ tag `v1.1.1`](https://github.com/speechbrain/speechbrain/tree/v1.1.1/speechbrain/inference) | `EncoderClassifier.encode_batch(self, wavs, wav_lens=None, normalize=False)` present; input `torch.Tensor [batch, time]` at 16 kHz. | API detail absorbed (block 2). |
| [HF `spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/commit/0f99f2d0ebe89ac095bcc5903c4dd8f72b367286) | Commit exists, Apache-2.0, dated 2025-02-18 ("Revert changes from PR"), and is the **current HEAD of `main`**. | None — pinning it is pinning today's HEAD. |

Three details recorded during the refresh and folded into the blocks below:

1. **`revision` lives in `FetchConfig`, not in `from_hparams`.** In v1.1.1,
   `speechbrain.utils.fetching.FetchConfig` is a frozen dataclass:
   `overwrite=False, allow_updates=False, allow_network=True, token=False,
   revision: str = None, huggingface_cache_dir: str = None`.
   `pretrained_from_hparams(cls, source, hparams_file="hyperparams.yaml",
   overrides={}, overrides_must_match=True, savedir=None, download_only=False,
   local_strategy=LocalStrategy.SYMLINK, fetch_config=FetchConfig(), **kwargs)`
   forwards `fetch_config` to `pretrainer.collect_files(...)` and to the hparams
   `fetch(...)`. The 1.0-era `from_hparams(..., revision=...)` example is **not**
   the 1.1.1 contract.
2. **`LocalStrategy.SYMLINK` (`= 1`) is the default and breaks on Windows**
   without Developer Mode / admin. The contract freezes `LocalStrategy.COPY`
   (`= 2`).
3. **The CPU-only torch route is already configured but unused.** Root
   `pyproject.toml` lines 42–50 declare `[tool.uv.sources]` for `torch` /
   `torchaudio` against the explicit `pytorch-cpu` index
   (`https://download.pytorch.org/whl/cpu`). `uv.lock` has no torch node yet, so
   this route has never been exercised — Task 3 must confirm the resolution is
   CPU-only after `uv add`.

### Block 1 — Frozen backend

| Item | Frozen value |
|---|---|
| Package | `speechbrain==1.1.1` (Apache-2.0) |
| Class | `EncoderClassifier` — **not** `SpeakerRecognition`. The study needs the raw embedding; `SpeakerRecognition.verify_batch`'s built-in `threshold=0.25` is a generic VoxCeleb score cut, explicitly not a household authorization threshold. `EncoderClassifier` is *defined* in `speechbrain.inference.classifiers` and re-exported from `speechbrain.inference.speaker`; the frozen import (block 2) uses the `speaker` path because the Hugging Face model card uses exactly that path and the package version is pinned. |
| Model | `speechbrain/spkrec-ecapa-voxceleb` (Apache-2.0) |
| Model revision | `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` (immutable, pinned) |
| Embedding dimension | 192 (ECAPA-TDNN attentive statistical pooling) |

`_MODEL_SOURCE` and `_MODEL_REVISION` (block 2) are **deliberately immutable,
named module-level constants** in the calibration harness. They are the one
sanctioned exception to the "no hardcoded model" rule in Global constraints:
the entire point of this study is a frozen, reproducible backend, so they must
**not** be routed through `server.settings` or made configurable.

### Block 2 — Frozen call and tensor contract

Construction (device, revision, offline-safe copy strategy all explicit):

```python
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import FetchConfig, LocalStrategy

_MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
_MODEL_REVISION = "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"

encoder = EncoderClassifier.from_hparams(
    source=_MODEL_SOURCE,
    savedir="project-history/calibration/speaker/model-cache/",
    run_opts={"device": "cpu"},
    local_strategy=LocalStrategy.COPY,
    fetch_config=FetchConfig(revision=_MODEL_REVISION, allow_network=False),
)
```

- `savedir` is `project-history/calibration/speaker/model-cache/` — under the
  gitignored corpus root, alongside the frozen `manifest.json` / `embeddings.npz`
  / `aggregate-report.md` names. It holds only the downloaded model files (no
  captured audio), so Task 7 may leave it in place at Pipec's choice.
- `allow_network=False` is the offline-after-cache assertion: a first run with a
  warm HF cache (populated by the model-contract command) must succeed with no
  network. A cold cache is a Task 3 setup step, run once and recorded, not part
  of any timed or gating measurement. If **only** the `allow_network=False` path
  fails while the same pinned revision loads fine with `allow_network=True`,
  record an "offline-only load limitation" and continue — it is not by itself a
  study-ending technical FAIL, because the revision is still fully pinned and
  reproducible.
- **Verification note (block 2, Task 3):** `fetch()` at v1.1.1 passes
  `fetch_config.revision` straight into `hf_hub_download`, and
  `pretrained_from_hparams` forwards `fetch_config` to both the hparams `fetch()`
  and `pretrainer.collect_files()`. The one hop not audited from source is
  whether `Pretrainer.collect_files` threads `fetch_config` into every
  per-checkpoint `fetch()` (in `speechbrain/utils/parameter_transfer.py`). The
  implementer must therefore assert against the installed package that
  `_MODEL_REVISION` is the revision actually resolved (inspect the populated
  `savedir` / HF cache ref), and additionally `git`-diff what commit `0f99f2d0`
  reverted before relying on it. A revision mismatch is a documentation stop.

Embedding call and shapes:

| Step | Frozen contract |
|---|---|
| Input bytes | WAV, 16 000 Hz, mono, signed int16 — validated by `validate_wav_bytes` before any tensor is built. |
| int16 → float | `samples.astype(np.float32) / 32768.0`, giving `[-1.0, 1.0)`. No resample, no gain, no dtype widening beyond float32. |
| Tensor | `torch.from_numpy(wave).unsqueeze(0)` → shape `(1, n_samples)`, dtype `torch.float32`, on CPU. |
| Call | `encoder.encode_batch(wavs=tensor, wav_lens=None, normalize=False)` |
| Output | `torch.Tensor` shape `(1, 1, 192)` → `.squeeze().detach().cpu().numpy()` → 1-D `np.ndarray` of exactly 192 finite float values. |
| Rejects | any non-finite value, wrong length, dimension ≠ 192, or all-zero vector → raise, nonzero exit, no partial report. |

### Block 3 — Frozen dependency

- Single command, from the **workspace root**:

  ```powershell
  uv add --group dev "speechbrain==1.1.1"
  ```

- Expected scope: root `pyproject.toml` `[dependency-groups] dev` gains
  `speechbrain`, and the generated `uv.lock` gains `speechbrain` + its
  transitive graph (torch / torchaudio resolved through the already-declared
  `pytorch-cpu` index — confirm CPU-only wheels in the lock diff). No
  `server/pyproject.toml` or `robot/pyproject.toml` edit. Never `uv pip
  install`; never hand-edit `uv.lock`.
- Lock-diff check also confirms **no `numpy` upper-bound conflict**: the
  workspace floors `numpy` at `>=2.4.4` (server) / `>=2.5.1` (robot); if `uv
  add` reports an unsatisfiable resolution because `speechbrain` or a transitive
  dep caps `numpy<2`, that is a technical FAIL recorded before any capture.
- If mypy/pyright flags missing stubs, add `speechbrain.*` (and `torch.*` /
  `torchaudio.*` only if needed) to `[[tool.mypy.overrides]]
  ignore_missing_imports` in the root `pyproject.toml` — same pattern as the
  existing `insightface.*` / `onnxruntime.*` entries.
- If `speechbrain`'s `filterwarnings = ["error"]` interaction surfaces a
  third-party `DeprecationWarning` from `torch`/`speechbrain`, add a narrowly
  scoped `ignore::DeprecationWarning:speechbrain.*` (or `torch.*`) entry, mirroring
  the existing `piper.*` / `faster_whisper.*` filters — never a blanket ignore.
- Rollback / lifecycle: on a **technical FAIL** in Task 3, run
  `uv remove --group dev speechbrain` then `uv sync --all-packages --all-groups`
  so a broken dependency is not left in `pyproject.toml` (it is in
  `default-groups`, installed for every dev and CI run). On a **measurement
  FAIL** or **provisional PASS**, the dev dependency may stay for a future
  re-study or PC-3B — Pipec's choice, recorded in the closure section.

### Block 4 — Frozen phrases, conditions and feasibility budget

Three neutral Spanish phrases (no names, personal facts, secrets or wake
words), fixed so repeats across sessions are comparable:

| ID | Text |
|---|---|
| `phrase-01` | La lluvia cae despacio sobre el tejado de la casa |
| `phrase-02` | Guardé cinco libros nuevos en el estante de madera |
| `phrase-03` | Prefiero caminar por el parque cuando termina la tarde |

Four literal `condition` labels — the corpus validator rejects any other
string, so `by_condition` aggregates never split on a spelling drift:

| Label | Meaning |
|---|---|
| `quiet-near` | quiet room, ~0.5 m from the mic |
| `quiet-far` | quiet room, ~2–3 m from the mic |
| `background-near` | ordinary household background noise, ~0.5 m |
| `background-far` | ordinary household background noise, ~2–3 m |

Reference samples are always `quiet-near`. Genuine samples span all four.
Impostor and replay `condition` labels follow the same vocabulary.

CPU feasibility budget: **p95 ≤ 500 ms** for one embedding of a 3-second WAV,
chosen by Pipec on 2026-09-08 **before any measurement**. The measured p95 is
compared against this precommitted number; it may not be relaxed after seeing
data. A measured p95 above 500 ms is a technical FAIL (Task 3 → Task 7).

### Block 5 — Frozen latency protocol

Executed exactly once in Task 3, and never retroactively changed by later
per-sample latency reporting in Task 6:

1. One `EncoderClassifier` already loaded (construction cost excluded).
2. One synthetic WAV: 3 seconds, 16 000 Hz, mono, signed int16 — generated
   in-process; file I/O and `validate_wav_bytes` happen **outside** the timed
   region.
3. 3 warm-up embeddings (discarded).
4. 30 sequential embeddings, each wrapped in `time.perf_counter()`.
5. p50 / p95 by **nearest-rank** on the 30 samples.
6. No concurrent load, no model download, no other process contention that the
   operator can avoid.

### Block 6 — Frozen commands

Model contract / cache warm-up (Task 3, run once, not timed):

```powershell
just speaker-calibration model-contract
```

`model-contract` downloads the pinned revision into the gitignored cache,
asserts the resolved revision equals `_MODEL_REVISION`, runs one embedding on a
generated non-biometric tone, and prints shape/dtype/dimension/finiteness — no
microphone, no household audio.

Capture / validate / embed / analyze / cleanup (unchanged from the CLI section
below):

```powershell
just speaker-calibration capture --class reference --subject owner --session reference-01 --phrase phrase-01 --condition quiet-near
just speaker-calibration validate
just speaker-calibration embed
just speaker-calibration analyze --output project-history/calibration/speaker/aggregate-report.md
just speaker-calibration cleanup
```

RED/GREEN commands per task:

| Task | RED (expect failures / missing symbols only) | GREEN |
|---|---|---|
| 1 | `uv run pytest tests/unit/test_speaker_calibration.py -k "normalize or centroid or distance or threshold or latency" -n0 -v` | same, plus full file, plus the scoped script checks below |
| 2 | `uv run pytest tests/unit/test_speaker_calibration.py -k "manifest or wav or path or cli" -n0 -v` | same, plus the scoped script checks below |
| 3 | `uv run pytest tests/unit/test_speaker_calibration.py -k "backend" -n0 -v` and `uv run pytest tests/slow/test_speaker_calibration_backend.py -m slow -n0 -v` | same, plus scoped script checks, lock-diff inspection and `uv sync --frozen` check |

**Scoped script checks (mandatory — `just lint` / `just typecheck` / `just gate`
do NOT cover this deliverable).** `scripts/` is excluded from Ruff
(`pyproject.toml`), mypy (`exclude`) and Pyright (`pyrightconfig.json`), so the
repo gates report GREEN without ever inspecting the new files. Every task that
touches `scripts/speaker_calibration.py` (or `scripts/speaker_calibration_models.py`)
must additionally run, and pass:

```powershell
uv run ruff check scripts/speaker_calibration.py scripts/speaker_calibration_models.py
uv run ruff format --check scripts/speaker_calibration.py scripts/speaker_calibration_models.py
uv run mypy scripts/speaker_calibration.py scripts/speaker_calibration_models.py
```

mypy's config `exclude` is ignored for files passed explicitly, so this works.
Task 7 must run these three commands over the final files before the whole-branch
review, in addition to `just gate` / `just check`.

## Independent review (blocker 9, 2026-09-08)

A cold independent reviewer read the plan, `CLAUDE.md`, every `.claude/rules/`
file, the identity/architecture docs, `pyproject.toml` / subproject manifests,
`face_calibration.py` and the `justfile`, and re-verified every checkable claim
in the frozen contract against the pinned primary sources (PyPI JSON API,
SpeechBrain v1.1.1 `classifiers.py` / `speaker.py` / `utils/fetching.py` /
`inference/interfaces.py`, the HF model card + commit history + `hyperparams.yaml`
at revision `0f99f2d0`).

**Verdict: APPROVE WITH MINOR FIXES.** Every hard fact an implementer keys on —
package version, license, Python floor, `encode_batch` signature, `FetchConfig`
shape, `LocalStrategy` values, model revision, 192-d embedding, the
`fetch_config`→`hf_hub_download` forwarding chain, the `SpeakerRecognition`
`threshold=0.25` — matches source. No scope creep; safety/privacy design
coherent. (Note: the human-readable PyPI *page* misreports the release order;
the PyPI *JSON API* confirms `1.1.1` is the latest and matches the plan.)

Findings, all applied in this file 2026-09-08:

| # | Severity | Issue | Fix applied |
|---|---|---|---|
| 1 | MEDIUM | "no hardcoded model" (Global constraints) contradicted Block 2's frozen `_MODEL_SOURCE` / `_MODEL_REVISION` constants | Block 1 now states the frozen study identifiers are the one sanctioned exception and must not be made configurable |
| 2 | MEDIUM | `scripts/` is excluded from Ruff, mypy **and** Pyright, so `just lint` / `just typecheck` / `just gate` give a false GREEN for the plan's main deliverable | Block 6 adds mandatory scoped `ruff check` / `ruff format --check` / `mypy` commands on the script files; wired into the RED/GREEN table and Task 7 |
| 3 | LOW | `from speechbrain.inference.speaker import EncoderClassifier` is a re-export site, not the definition module | Block 1 notes the class is defined in `…inference.classifiers` and the `speaker` path is used because the HF model card uses it and the version is pinned |
| 4 | LOW | Pinned revision `0f99f2d0` is itself a "Revert changes from PR" commit; offline-load treated as unconditionally safe | Block 2 tells the implementer to diff what `0f99f2d0` reverted, and softens the rule: an offline-only load failure with the same pinned revision loading fine online is an "offline-only load limitation", not a study-ending FAIL |
| 5 | LOW | Dependency lifecycle after the study closes was unspecified | Block 4 rollback bullet: technical FAIL → `uv remove`; measurement FAIL / provisional PASS → dev dep may stay at Pipec's choice, recorded in closure |
| 6 | LOW | `numpy` 2.x resolution conflict risk not called out (workspace floors `numpy>=2.4.4`/`>=2.5.1`) | Block 3 lock-diff check now includes "no `numpy` upper-bound conflict" |
| 7 | LOW | `condition` label vocabulary was free-text, could split `by_condition` aggregates on a spelling drift | Block 4 freezes four literal labels (`quiet-near`, `quiet-far`, `background-near`, `background-far`); the corpus validator rejects anything else |
| 8 | LOW | `savedir` path described, not named | Block 2 names it `project-history/calibration/speaker/model-cache/` |

None of the findings required redesign or re-freezing the backend. After these
edits, blocker 9 is satisfied; the only remaining step is Pipec's explicit
promotion decision.

## Required reading after promotion

Before editing, read completely:

1. `AGENTS.md`, every `.claude/rules/` file, `docs/plans/README.md`, and the
   promoted version of this plan;
2. every document under **Spec**;
3. `server/src/server/audio_contract.py`,
   `robot/src/robot/audio_capture.py`, and `scripts/mic_test.py`;
4. `server/src/server/cognition/identity.py` and
   `tests/unit/test_active_person_identity.py`;
5. `scripts/face_calibration.py`,
   `tests/unit/test_face_calibration.py`, and `justfile` as current code reuse,
   not as normative dependence on its completed plan;
6. `server/pyproject.toml`, `robot/pyproject.toml`, root `pyproject.toml`, and
   the selected backend's frozen primary documentation.

The implementer must follow the root `pyproject.toml` marker definitions when
they conflict with stale prose elsewhere: pure vector/math tests are `unit`,
real backend tests are `slow`, microphone capture is `hardware`, and quality
measurement is `eval`.

## Global constraints

- This is PC-3A evaluation only. PC-3 remains open for a separately reviewed
  PC-3B enrollment/runtime plan even if this study passes.
- Do not modify `server/src/`, `robot/src/`, identity trusted sources,
  authorization, tokens, routes, settings, migrations, databases, prompts or
  the server/robot boundary.
- Do not produce `IdentityEvidence`, persist a voiceprint, create enrollment or
  revocation APIs, or grant any capability from a score.
- Every function that accepts, reads, records or validates audio states in its
  docstring: WAV, 16,000 Hz, mono, signed int16. Reject mismatches; do not
  silently reinterpret bytes.
- Use the existing real microphone capture implementation after promotion.
  Scripts may import the robot adapter as existing calibration tools do, but
  runtime packages may not import each other.
- All real participants give explicit consent. Use pseudonyms such as
  `owner`, `impostor_a`, never names. No child or non-consenting person is used.
- Agents never record, imitate, synthesize, transform or replay a person's
  voice. Pipec performs and confirms each physical operation.
- Raw WAV, manifests containing local paths, embeddings and per-sample scores
  live only under `project-history/calibration/speaker/`, which is gitignored.
  They are never staged, pasted into chat, attached to a PR or cited by a
  tracked path.
- The tracked closure section in this plan contains only aggregate counts/rates,
  condition labels, selected threshold, model metadata, latency summaries and
  limitations. It
  contains no names, transcripts, hashes linkable to retained samples,
  embeddings or absolute local paths.
- Reference and probe sessions are distinct. Phrase/session leakage is
  reported and prevented by the corpus validator.
- Live impostor acceptance is the safety gate. Any threshold with a measured
  false accept is ineligible. If genuine and live-impostor distances overlap so
  no zero-observed-FAR threshold exists, result is FAIL; never trade safety for
  convenience.
- Replay is a separate measured attack result, not silently mixed into FAR.
  An accepted replay is documented and forbids treating voice as standalone
  high-assurance evidence; replay/liveness policy remains PC-4.
- A zero-observed-FAR result on this small corpus is provisional evidence, not
  proof of population-level security. Report counts and confidence limitation.
- Do not choose a latency ceiling after seeing the study result. Pipec froze
  the feasibility budget at **p95 ≤ 500 ms** in the 2026-09-08 readiness
  amendment, before any measurement.
- Missing backend, malformed audio, zero/NaN embedding, inconsistent dimension
  or model error returns nonzero and writes no partial accepted report.
- Code/comments/docstrings are English; public APIs are typed with Google
  docstrings; data containers are frozen; use `pathlib.Path`, logging and
  exception chaining; no `print()`, bare `except`, unjustified `Any`, hardcoded
  path/model or handwritten `uv.lock` change.
- Tests never load a real model in the ordinary `unit` suite. No real voices or
  network calls enter CI.
- Preserve unrelated work and do not broaden this study after discovering an
  adjacent identity, spoofing or memory issue.

## Stable file map

These are the only files permitted after readiness, plus the exact dependency
files named by the approved amendment:

| File | Action and responsibility |
|---|---|
| `scripts/speaker_calibration.py` | Create model-independent sample schema, numeric calibration, safe corpus CLI and the amended concrete evaluation backend. |
| `scripts/speaker_calibration_models.py` | Conditional create if needed to keep the main script near 200 lines; contains only the frozen dataclasses/protocol, no I/O or backend behavior. Record the split before creating it. |
| `scripts/speaker_calibration_corpus.py` | Conditional create registered 2026-09-08 (Task 2): WAV validation, manifest I/O, path safety, corpus-rule enforcement and aggregate-report rendering — no numeric math, no backend. Keeps every module near the 200-line limit; same three-module shape as `scripts/longitudinal_eval_*.py` (Plan 0046). |
| `scripts/speaker_calibration_backend.py` | Conditional create registered 2026-09-08 (Task 3): the frozen `_MODEL_SOURCE` / `_MODEL_REVISION` constants, the `EncoderClassifier` construction, `embed_wav`, the resolved-revision assertion and the frozen latency protocol — no numeric math, no manifest I/O. Fourth module so the CLI file stays near the `face_calibration.py` precedent size; `run_cli` reaches it by deferred import so `validate` / `analyze` / `cleanup` never import torch. |
| `scripts/speaker_calibration_analysis.py` | Conditional create registered 2026-09-21 (Task 6 groundwork): the pure aggregate analysis — reference centroid, per-sample distance scoring, zero-observed-FAR threshold selection, replay scored at the operating point, per-condition summaries, limitations and the `AggregateSpeakerReport`. No file, model, microphone or network access; `analyze` in `speaker_calibration.py` does the I/O and reaches it by deferred import (it imports the Task 1 numeric layer, so a top-level import would be circular). |
| `tests/unit/test_speaker_calibration.py` | Create pure synthetic tests for math, schema, paths, reports and backend boundary fakes. |
| `tests/slow/test_speaker_calibration_backend.py` | Create opt-in frozen-model smoke/contract tests; never part of ordinary unit execution. |
| `pyproject.toml`, `uv.lock` | Add the exact approved package to the root development group and record the generated resolution; no subproject dependency edit. |
| `justfile` | Add `speaker-calibration *ARGS` after dependencies are locked. |
| `docs/plans/completed/0047-speaker-evidence-calibration-study.md` | Persistent checkpoints and final measured evidence. |
| `docs/architecture/current-state.md`, `docs/architecture/identity-and-access.md` | Record study result while keeping `VOICE` untrusted. |
| `docs/roadmap/personal-companion-delivery-map.md`, `docs/roadmap/cognitive-roadmap.md` | Record PC-3A result and PC-3B/PC-4 remaining work. |
| `docs/plans/README.md`, `docs/plans/open/README.md` | Operational status and eventual move to `completed/`. |

`server/src/`, `robot/src/`, `.env.example`, runtime DB/schema and API docs are
explicitly forbidden. The only dependency files permitted are root
`pyproject.toml` and generated `uv.lock`; no subproject dependency file becomes
permitted implicitly.

## Stable interface contract

The model-independent layer must expose exactly these contracts:

```python
SampleClass = Literal["reference", "genuine", "impostor", "replay"]


@dataclass(frozen=True)
class SpeakerSample:
    sample_id: str
    subject_id: str
    sample_class: SampleClass
    session_id: str
    phrase_id: str
    condition: str
    wav_path: Path
    sha256: str


@dataclass(frozen=True)
class EmbeddedSample:
    sample: SpeakerSample
    embedding: np.ndarray
    latency_ms: float


@dataclass(frozen=True)
class SpeakerThresholdResult:
    threshold: float
    false_accepts: int
    false_rejects: int
    total_genuine: int
    total_impostor: int


@dataclass(frozen=True)
class SpeakerManifest:
    schema_version: Literal[1]
    samples: tuple[SpeakerSample, ...]


@dataclass(frozen=True)
class ConditionSummary:
    sample_class: SampleClass
    condition: str
    total: int
    accepted: int
    rejected: int
    distance_min: float
    distance_max: float
    distance_mean: float


@dataclass(frozen=True)
class AggregateSpeakerReport:
    model_id: str
    package_version: str
    sample_counts: dict[SampleClass, int]
    selected_threshold: float | None
    live_false_accepts: int | None
    live_far: float | None
    genuine_false_rejects: int | None
    genuine_frr: float | None
    replay_accepts: int | None
    replay_accept_rate: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    by_condition: dict[str, ConditionSummary]
    outcome: Literal[
        "provisional_pass",
        "fail_distance_overlap",
        "fail_backend_latency",
        "invalid_procedure",
    ]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class SpeakerCliOptions:
    action: Literal[
        "model-contract", "capture", "validate", "embed", "analyze", "cleanup", "discard"
    ]  # "discard" added 2026-09-21 (amendment, see the CLI notes below)
    corpus_root: Path
    manifest_path: Path
    output_path: Path | None
    sample_class: SampleClass | None
    subject_id: str | None
    session_id: str | None
    phrase_id: str | None
    condition: str | None
    sample_id: str | None = None  # added 2026-09-21, only for `discard --sample`


class SpeakerEmbeddingBackend(Protocol):
    @property
    def model_id(self) -> str:
        """Return the frozen model identifier and revision."""

    def embed_wav(self, wav_bytes: bytes) -> np.ndarray:
        """Embed WAV audio at 16 kHz, mono, signed int16."""


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    """Return a finite unit vector or reject invalid input."""


def reference_centroid(references: Sequence[np.ndarray]) -> np.ndarray:
    """Return the normalized mean of normalized reference embeddings."""


def cosine_distance(probe: np.ndarray, reference: np.ndarray) -> float:
    """Return one-minus-cosine for equal finite nonzero vectors."""


def sweep_speaker_thresholds(
    genuine_distances: Sequence[float],
    impostor_distances: Sequence[float],
    candidates: Sequence[float],
) -> list[SpeakerThresholdResult]:
    """Evaluate FAR and FRR at each deterministic candidate threshold."""


def zero_far_speaker_threshold(
    genuine_distances: Sequence[float],
    impostor_distances: Sequence[float],
) -> tuple[float, float] | None:
    """Return threshold and FRR for the best zero-observed-FAR candidate."""


def percentile(values: Sequence[float], quantile: Literal[0.5, 0.95]) -> float:
    """Return a deterministic nearest-rank latency percentile."""


def validate_wav_bytes(wav_bytes: bytes) -> None:
    """Validate WAV audio at 16 kHz, mono, signed int16."""


def load_manifest(path: Path, corpus_root: Path) -> SpeakerManifest:
    """Load a strict manifest and prove every WAV remains in the corpus."""


def append_sample_atomic(
    manifest_path: Path,
    corpus_root: Path,
    sample: SpeakerSample,
) -> None:
    """Append one validated sample without exposing a partial manifest."""


def validate_corpus(manifest: SpeakerManifest) -> None:
    """Enforce subject, class, session, phrase and minimum-matrix rules."""


def render_aggregate_report(report: AggregateSpeakerReport) -> str:
    """Render a local aggregate report without biometric or path data."""


def parse_cli_args(argv: Sequence[str] | None = None) -> SpeakerCliOptions:
    """Parse one explicit speaker-calibration action."""


def run_cli(options: SpeakerCliOptions) -> int:
    """Execute one safe action and return zero only for complete success."""
```

Matching uses distance `<= threshold`. References are individually
L2-normalized, averaged, then normalized again. Selection minimizes FRR among
thresholds with zero observed live-impostor accepts; ties choose the lower
threshold. Empty sets, mismatched dimensions, zero vectors and non-finite data
are errors. Replay distances never participate in threshold selection.

The manifest is schema version `1`. Every record includes the exact fields in
`SpeakerSample`; `subject_id` must be `owner` for reference/genuine/replay and
an `impostor_[a-z]+` pseudonym for impostors. `sha256` detects accidental file
change but is removed from tracked reports. Corpus resolution must prove every
WAV is below the resolved corpus root and is not a symlink escaping it.

The default corpus root is
`project-history/calibration/speaker/`; the manifest is `manifest.json`; raw
embeddings are `embeddings.npz`; and the detailed local aggregate output is
`aggregate-report.md`, all below that ignored root. `render_aggregate_report`
must omit sample IDs, subjects, hashes, transcripts and absolute paths. The
privacy-reviewed safe aggregate values are copied into this plan's closure
section; no separate biometric report is committed.

Report invariants depend on `outcome`. `fail_backend_latency` permits no corpus:
all FAR/FRR/replay fields and the selected threshold are `None`, sample counts
and `by_condition` are empty, and available latency may be present. The two
measurement outcomes require the full corpus, every metric and every condition
summary; `provisional_pass` additionally requires zero live false accepts and a
selected threshold, while `fail_distance_overlap` requires no selected
threshold. `invalid_procedure` renders only measurements actually observed and
must state why they are non-gating. Model/package identity and limitations are
always mandatory. Model validators reject any inconsistent combination rather
than filling missing values with zero.

The readiness amendment (2026-09-08) has frozen the literal phrases and exact
backend; the CLI shape is fixed:

```powershell
just speaker-calibration model-contract
just speaker-calibration capture --class reference --subject owner --session reference-01 --phrase phrase-01 --condition quiet-near
just speaker-calibration validate
just speaker-calibration embed
just speaker-calibration analyze --output project-history/calibration/speaker/aggregate-report.md
just speaker-calibration cleanup
```

`model-contract` takes no flags, never opens the microphone, warms the
pinned-revision cache and asserts the resolved revision. Capture requires every
metadata flag. Other actions reject capture-only flags.
`embed` requires a complete valid capture manifest and writes embeddings
atomically. `analyze` never opens the microphone or network, requires cached
model assets and complete embeddings, and refuses to overwrite its output.
`cleanup` first lists/resolves each exact artifact, refuses paths outside the
corpus, requires Pipec confirmation, and deletes individual files rather than
a recursive directory target.
`discard` (added 2026-09-21, amending the frozen six-action list) serves a
participant's withdrawal and technical exclusions: exactly one of
`--subject <owner|impostor_x>` or `--sample <id>`, no other capture flag. It
deletes the matching WAV files, their embeddings (vector and latency), their
manifest rows and any now-stale aggregate report — the corpus rule that a
withdrawal deletes WAVs, embeddings and manifest rows — and never touches the
model cache. It refuses to run when nothing matches, requires a typed
confirmation, shows counts only, and is idempotent so an interrupted run is
finished by repeating it. `embed` and `analyze` must be re-run afterwards.

## Corpus and condition matrix

The minimum accepted corpus is:

| Class | Minimum | Separation and conditions |
|---|---:|---|
| Reference | 6 | Owner, one dedicated enrollment session, three neutral fixed phrases × two repetitions, `quiet-near` only. |
| Genuine | 24 | Owner, at least two later sessions, three phrases, spanning all four frozen `condition` labels; no reference file reused. |
| Live impostor | 18 | At least three consenting adults, each three phrases × two repetitions, captured live rather than played from a device. |
| Replay | 6 | Pipec replays at least three owner probe recordings through a household speaker at `quiet-near` and `quiet-far`; source IDs recorded locally. |

`condition` on every row uses the four literal labels frozen in Block 4
(`quiet-near`, `quiet-far`, `background-near`, `background-far`); the corpus
validator rejects any other string.

Phrases contain no personal facts, secrets, wake words or names. The readiness
amendment freezes the literal Spanish phrases so repeats are comparable. A
participant may stop and withdraw at any point; withdrawal deletes their WAVs,
embeddings and manifest rows before analysis and adjusts the corpus gate
honestly. Do not pressure, replace or fabricate a participant to satisfy a
count.

## Agent execution protocol after promotion

One fresh implementer owns each coding task. No concurrent implementers edit
the shared branch. Each receives the full task text, permitted files, exact
amended backend contract and a warning not to revert others' work. Each task
must show intended RED, minimal GREEN, self-review, a fresh spec-compliance
review, then a fresh code-quality/security review. The same implementer fixes
findings; five unsuccessful review rounds stop for Pipec.

The model-selection gate uses a read-only research agent and a separate
privacy/license reviewer. Physical tasks use no worker: Pipec runs commands and
confirms consent/capture. Final closure gets an independent whole-branch and
privacy review. Keep checkbox evidence in this file so a later session can
resume without relying on chat memory.

## Task 0: Freeze an isolated execution base after promotion

**Owner:** orchestrator; no coding or capture agent.

- [x] Confirm every readiness blocker is checked, the reviewed plan status is
  `Ready`, it is the sole `NOW`, and Pipec explicitly authorized execution.
- [x] Record branch, SHA, `git status`, frozen backend/package/model revision,
  approved download scope, literal phrase IDs/text and precommitted p95 budget.
- [x] Create one simple feature branch from the approved merged SHA on `main`
  (e.g. `feat/0047-speaker-calibration`). **No git worktree** — the project
  uses one plain branch per plan. Preserve any uncommitted user changes.
- [x] Re-read all required sources on that branch. Any material API, license,
  package or lock drift stops for a documentation amendment; do not adapt while
  coding.

### Task 0 evidence (2026-09-08)

| Item | Value |
|---|---|
| Branch | `feat/0047-speaker-calibration`, cut from `main` @ `4b61624` |
| Promotion commit on branch | `35d1de7` — `docs(plan): promote 0047 to Ready/NOW with staged execution` (promotion + implementation land in one PR, per the project's one-branch-per-plan rule) |
| `git status` | clean before Task 1 |
| Environment | Windows 11, Python 3.12.11, uv 0.10.11 |
| Frozen package | `speechbrain==1.1.1` (Apache-2.0), root `dev` group only |
| Frozen class | `EncoderClassifier` (not `SpeakerRecognition`) |
| Frozen model | `speechbrain/spkrec-ecapa-voxceleb` (Apache-2.0) |
| Frozen model revision | `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` (immutable) |
| Embedding dim | 192 |
| Approved download scope | `speechbrain==1.1.1` + transitive graph (torch/torchaudio via `pytorch-cpu` index); ECAPA model ~200–300 MB at pinned revision. No cloud inference. |
| `phrase-01` | La lluvia cae despacio sobre el tejado de la casa |
| `phrase-02` | Guardé cinco libros nuevos en el estante de madera |
| `phrase-03` | Prefiero caminar por el parque cuando termina la tarde |
| `condition` labels | `quiet-near`, `quiet-far`, `background-near`, `background-far` (validator rejects any other) |
| Precommitted p95 budget | ≤ 500 ms for one embedding of a 3-second WAV (chosen by Pipec before any measurement) |

Required sources re-read on the branch (no material API/license/lock drift
found): `CLAUDE.md`, `AGENTS.md`, `.claude/rules/*`, `docs/plans/README.md`,
this plan, `docs/architecture/identity-and-access.md`,
`docs/architecture/current-state.md`,
`server/src/server/audio_contract.py`, `robot/src/robot/audio_capture.py`,
`scripts/mic_test.py`, `server/src/server/cognition/identity.py`,
`tests/unit/test_active_person_identity.py`, `scripts/face_calibration.py`,
`tests/unit/test_face_calibration.py`, `justfile`, root/`server`/`robot`
`pyproject.toml`. `[tool.uv.sources]` for `torch`/`torchaudio` against the
`pytorch-cpu` index is declared (`pyproject.toml`) but never yet exercised —
`uv.lock` has no torch node, so Task 3 must confirm CPU-only resolution.

**Hard stop passed:** all four checks are green. Tasks 1–2 (pure code, no
download) proceed. Task 3's `uv add` + model download is a separate checkpoint
that also needs Docker/background load closed for the latency protocol.

## Task 1: Build the pure numeric calibration layer with TDD

**Files:** create `scripts/speaker_calibration.py` and
`tests/unit/test_speaker_calibration.py`.

- [x] Write tests for unit/orthogonal/opposite vectors, normalization,
  centroid order independence, equal dimensions and invalid zero/NaN/infinite
  values.
- [x] Write tests for inclusive threshold comparison, FAR/FRR counts, tie
  breaking, no-zero-FAR overlap returning `None`, replay exclusion and p50/p95.
- [x] Run RED — `ModuleNotFoundError: No module named 'scripts.speaker_calibration'`
  at collection (no audio/model import). Two threshold tests were then rewritten
  during RED: the tie-break case is "low end of the safe gap" (a threshold range
  reaching FRR 0 resolves to its smallest value), and overlap → `None` is keyed
  on "closest sample of all is an impostor" (`min(impostor) <= min(genuine)`),
  matching the global constraint's live-impostor safety gate.
- [x] Implement the minimum pure functions from the stable interface —
  `l2_normalize`, `reference_centroid`, `cosine_distance`,
  `SpeakerThresholdResult`, `sweep_speaker_thresholds`,
  `zero_far_speaker_threshold`, `percentile` (nearest-rank, `ceil(q*n)`).
  `cosine_distance` normalizes both inputs internally so the matching pipeline
  is robust to un-normalized probes. Replay exclusion is structural — the
  selector's signature takes only genuine + impostor distances.
- [x] Re-run focused and full unit file; observe GREEN — **31 passed** in 0.24s.
- [x] Complete spec and quality reviews — scoped `ruff check` / `ruff format
  --check` / `mypy` on `scripts/speaker_calibration.py` all clean;
  `just typecheck` (mypy 92 files + pyright) clean; test file lint clean.
  93-line file, every function ≤ 30 lines, frozen dataclass, `logger` not
  `print`, English, Google docstrings.
- [x] Commit: `feat(eval): add speaker calibration math` (rides with the Task 0
  evidence checkpoint, which the plan holds uncommitted).

### Task 2 split and staging decision (2026-09-08)

Recorded before any Task 2 code, per the "record the split before creating it"
rule in the Stable file map. Pipec approved all three points:

| Decision | Resolution |
|---|---|
| Module split | Three modules, not two. `speaker_calibration.py` keeps the Task 1 numeric layer plus `parse_cli_args` / `run_cli` / `main`; `speaker_calibration_models.py` holds only the frozen dataclasses, the `SpeakerEmbeddingBackend` Protocol, the frozen vocabulary constants and the `AggregateSpeakerReport` invariant validators; `speaker_calibration_corpus.py` holds WAV validation, manifest I/O, path safety, corpus-rule enforcement and report rendering. Two modules would push the main file to ~450 lines, breaking the 200-line limit in `.claude/rules/python-style.md`. The three-module shape mirrors the accepted `scripts/longitudinal_eval_*.py` precedent (Plan 0046). |
| `embed` action | Implemented fully in Task 2 against the `SpeakerEmbeddingBackend` Protocol, exercised with a typed fake in unit tests. Task 3 only plugs in the concrete SpeechBrain adapter — no `embed` pipeline work remains for Task 3. Called with no backend, `embed` logs and returns a nonzero exit. |
| `model-contract` action | Recognised by `parse_cli_args` (the frozen six-action Literal) but in Task 2 it only logs "available in Task 3" and returns a nonzero exit. The plan assigns `model-contract` to Task 3. |
| `cleanup` action | Implemented in Task 2. It is a pure corpus operation (list, confirm, delete file-by-file) that needs no backend, no other task claims it, and Task 7 depends on it. |
| Microphone source | The `capture` action uses `robot.audio_capture.capture_utterance`, imported lazily inside the capture handler (same deferred-import pattern as `scripts/eval_longitudinal_memory.py`) and injectable as a boundary in tests, so `validate` / `embed` / `analyze` provably never import `sounddevice` or open a microphone. |

## Task 2: Build the private corpus manifest and safe CLI with TDD

**Files:** modify `scripts/speaker_calibration.py` and
`tests/unit/test_speaker_calibration.py`, create
`scripts/speaker_calibration_models.py` and
`scripts/speaker_calibration_corpus.py`, and add `speaker-calibration` to
`justfile`.

- [x] Write failing tests for manifest version/extra fields/duplicate IDs,
  class-subject rules, session separation, minimum matrix, WAV contract,
  SHA-256 mismatch, traversal/symlink escape and non-corpus paths.
- [x] Test that `analyze` never opens a microphone (a boundary that raises if
  invoked) and capture cannot write outside `project-history/calibration/speaker/`.
- [x] Test backend/capture exception: nonzero exit, no partial manifest row and
  no accepted report. Also a typed fake `SpeakerEmbeddingBackend` drives the
  full `embed` pipeline to `embeddings.npz`, and a wrong-dimension embedding is
  rejected with no npz written.
- [x] Test aggregate-report invariants for technical FAIL without corpus,
  measurement overlap, provisional PASS and always-mandatory model identity /
  limitations; per-condition rows render; `owner`, `.wav`, `sha256` never appear.
- [x] Run RED — `ImportError: cannot import name 'parse_cli_args' from
  'scripts.speaker_calibration'` at collection (no audio/model/network import).
- [x] Implement atomic manifest append, strict WAV validation and safe path
  resolution. `validate_wav_bytes` reuses `server.audio_contract.validate_wav_contract`
  (single source of truth) and carries the exact audio-contract docstring.
- [x] Add the exact recipe (imports are locked by the readiness amendment):

  ```just
  speaker-calibration *ARGS:
      uv run --env-file .env python scripts/speaker_calibration.py {{ARGS}}
  ```

- [x] Re-run tests and `just lint`/`just typecheck`; observe GREEN (84 tests,
  646 total unit, mypy 92 files, pyright 0, scoped ruff/format/mypy clean).
- [x] Self-review + spec/quality/privacy review: English, Google docstrings,
  frozen dataclasses, `logger` not `print`, `pathlib`, functions ≤ 30 lines,
  exception chaining; `VOICE` untouched; no `IdentityEvidence`; no `uv add`; no
  `server/src` / `robot/src` / settings / route / DB change; corpus root stays
  gitignored and `git status` never lists it.
- [x] Commit: `feat(eval): add private speaker corpus workflow`

### Task 2 evidence (2026-09-08)

| Item | Value |
|---|---|
| Branch | `feat/0047-speaker-calibration` (no new branch, no worktree) |
| New files | `scripts/speaker_calibration_models.py` (211 lines), `scripts/speaker_calibration_corpus.py` (353) |
| Modified | `scripts/speaker_calibration.py` (216 → 526: Task 1 numeric layer kept verbatim + the six-action CLI), `tests/unit/test_speaker_calibration.py` (277 → 985), `justfile` (+`speaker-calibration` after `face-calibration:147`) |
| Module sizing | Three modules keep the CLI file near the size of the sanctioned precedent `scripts/face_calibration.py` (517 lines). `scripts/` is excluded from ruff/mypy/pyright, so the 200-line guidance is enforced only for `server/src` and `robot/src`. |
| RED | `uv run pytest tests/unit/test_speaker_calibration.py -k "manifest or wav or path or cli" -n0 -v` → `ImportError: cannot import name 'parse_cli_args'` at collection, no audio/model/network import |
| GREEN | same filter → 34 passed / 50 deselected; `-k "report or corpus"` → 22 passed; full file → **84 passed** |
| Scoped checks (Block 6 — gates do not see `scripts/`) | `uv run ruff check` + `ruff format --check` on all three script files → clean. `MYPYPATH=. uv run mypy --explicit-package-bases scripts/speaker_calibration.py scripts/speaker_calibration_corpus.py scripts/speaker_calibration_models.py` → **Success, 3 files**. (The plan's bare two-path `mypy` form hits mypy's "source found twice" without `--explicit-package-bases`; the same limitation affects `face_calibration.py`. `uv run mypy scripts/speaker_calibration.py` alone also passes via silent import-follow.) |
| Repo gates | `just lint` clean · `just typecheck` mypy 92 files + pyright 0 · full `uv run pytest -m unit` → **646 passed** |
| CLI smoke | `just speaker-calibration validate` on an empty root → exit 1, `ERROR ... no manifest at ... - capture at least one sample first` (clean message, no traceback) |
| `model-contract` / `embed` (no backend) | recognised by `parse_cli_args`; log + exit 1 — deferred to Task 3 per the split decision above |
| Private data | no WAV, manifest, embedding or hash committed; `git status --short` lists only the four tracked files + two new script modules |

### Task 3 module and staging decision (2026-09-08)

Recorded before any Task 3 code, per the "record the split before creating it"
rule in the Stable file map. Mirrors the Task 2 split decision.

| Decision | Resolution |
|---|---|
| Module split | Fourth module, `scripts/speaker_calibration_backend.py`. It holds only the frozen `_MODEL_SOURCE` / `_MODEL_REVISION` constants, the `EncoderClassifier` construction, `embed_wav`, the resolved-revision assertion and the frozen latency protocol. `speaker_calibration.py` is already at 526 lines; `_models.py` is types only; `_corpus.py` is corpus I/O only. `run_cli` dispatches `model-contract` and the concrete `embed` backend through a deferred import of this module, so `validate` / `analyze` / `cleanup` never import `torch`. |
| `model-contract` action | Implemented in Task 3. Downloads the pinned revision into the gitignored cache, asserts the resolved revision equals `_MODEL_REVISION`, embeds one generated non-biometric sine tone (not silence — silence yields a degenerate vector rejected by `_checked_embedding`), prints shape/dtype/dimension/finiteness. No microphone, no household audio, not timed. |
| Latency protocol | Run once, exactly as block 5, after Pipec frees RAM (5 GB free of 16 GB on this machine; the p95 ≤ 500 ms budget is precommitted and cannot be relaxed after seeing data, so a loaded run that fails is discarded and repeated, never accepted). CPU/RAM sampled in parallel with `Win32_PerfFormattedData_PerfOS_Processor` (the `Get-Counter '\Processor(_Total)\…'` path fails with `c0000bb8` on this Spanish-locale Windows). |
| Frozen-SHA secret scan | `_MODEL_REVISION` is a 40-char hex string; `detect-secrets`' `HexHighEntropyString` plugin flags it. The constant line carries an inline `# pragma: allowlist secret` — it is a public Hugging Face commit SHA, not a credential. |

## Task 3: Add the frozen backend adapter with TDD

**Files:** only the script/tests and exact dependency files authorized by the
readiness amendment.

**Contract:** follow the "Frozen readiness contract" section (blocks 1–3, 5–6)
exactly — `EncoderClassifier` (not `SpeakerRecognition`), model revision
`0f99f2d0…`, `LocalStrategy.COPY`, `FetchConfig(revision=…, allow_network=False)`,
`(1, n_samples)` float32 input, `(1, 1, 192)` output.

**Status: COMPLETE — technical PASS, ready for independent review.** Landed on
`feat/0047-speaker-calibration` in three commits: `1b13302`
(`feat(eval): add frozen speaker embedding backend`), `734e9ac`
(`docs(plan): mark 0047 Task 3 complete and ready for review`) and the
pytorch-cpu index amendment below; all pushed, no PR. Every gate green, p95
231 ms < the precommitted 500 ms. No household voices collected; Tasks 4–6 stay
blocked; Task 7 is the next executable step if Pipec closes the study, otherwise
Task 4 once three consenting adults are confirmed.

### Amendment: pytorch-cpu index (2026-09-08, Pipec-approved)

The frozen contract (block 2 note 3) expected `[tool.uv.sources]` to route
`torch` / `torchaudio` through the `pytorch-cpu` index. `uv add --group dev
"speechbrain==1.1.1"` alone did not achieve that: `[tool.uv.sources]` is only
honoured for a **direct** dependency, and both were transitive-only via
`speechbrain`, so the lock resolved them from `pypi.org/simple`. On Windows that
wheel is already CPU-only, so Task 3's measurements are unaffected — but a Linux
CI `uv sync --all-groups` would have pulled PyPI's CUDA `torch` plus ~19
`nvidia-*` / `cuda-*` / `triton` packages (~2.5–3 GB) for a dependency the CI
gate never runs.

**Fix (approved by Pipec after Task 3 committed):** add `torch>=2.14.0,<3.0.0`
and `torchaudio>=2.11.0,<3.0.0` to the root `[dependency-groups] dev` so the
existing source applies, then `uv lock`. No version pin changed and nothing new
entered the tree — the packages were already resolved transitively.

Result in `uv.lock`: `torch` and `torchaudio` `source = { registry =
"https://download.pytorch.org/whl/cpu" }`, installed as `2.14.0+cpu` /
`2.11.0+cpu`; **removed:** `cuda-bindings`, `cuda-pathfinder`, `cuda-toolkit`,
`nvidia-cublas`, `nvidia-cuda-cupti`, `nvidia-cuda-nvrtc`,
`nvidia-cuda-runtime`, `nvidia-cudnn-cu13`, `nvidia-cufft`, `nvidia-cufile`,
`nvidia-curand`, `nvidia-cusolver`, `nvidia-cusparse`, `nvidia-cusparselt-cu13`,
`nvidia-nccl-cu13`, `nvidia-nvjitlink`, `nvidia-nvshmem-cu13`, `nvidia-nvtx`,
`triton` (19 nodes). Re-verified after the amendment: `torch.cuda.is_available()
== False`, `uv lock --check` exit 0, `pip-audit --local` clean,
`just speaker-calibration model-contract` exit 0, 4/4 slow + 14/14 backend unit,
`just lint` / `just typecheck` green, full CI-equivalent suite green.

- [x] From workspace root run the approved command
  `uv add --group dev "speechbrain==1.1.1"`; never `uv pip install`, never edit
  a subproject dependency file and never hand-edit the lockfile. Inspect the
  `uv.lock` diff and confirm `torch`/`torchaudio` resolved to CPU-only wheels
  via the already-declared `pytorch-cpu` index. **Done. First pass resolved the
  CPU wheels from `pypi.org/simple` (not the explicit index) because
  `[tool.uv.sources]` is not applied to a transitive-only dependency; the wheels
  were CPU-only in effect but the Linux CI lock carried the full CUDA graph.
  Pipec approved the amendment below on 2026-09-08 — `torch` / `torchaudio` are
  now direct `dev` constraints so the source applies, both resolve from
  `https://download.pytorch.org/whl/cpu` as `+cpu`, and 19 `nvidia-*` / `cuda-*`
  / `triton` nodes are gone from the lock. See "Amendment: pytorch-cpu index".**
- [x] Add the `model-contract` action and run `just speaker-calibration
  model-contract` once to warm the pinned-revision cache; assert the resolved
  revision equals the frozen SHA. **Done — exit 0, resolved revision
  `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`, offline load succeeded (no
  "offline-only load limitation"), sine-tone embedding `shape=(192,)
  dtype=float64 all_finite=True`.**
- [x] Write unit tests with a typed backend fake for byte/input conversion,
  normalization, fixed dimension, model metadata and errors. **Done — 14
  backend tests, fake encoder, no real model in the unit suite.**
- [x] Write an opt-in `slow` contract test against a generated non-biometric WAV
  fixture and the exact frozen model. Assert finite repeatable shape and
  offline-after-cache behavior; do not assert speaker quality on synthetic
  tone. **Done — `tests/slow/test_speaker_calibration_backend.py`, 4 tests, all
  `-m slow`, skip cleanly on a cold cache.**
- [x] Execute the frozen latency protocol exactly: generated three-second WAV,
  one loaded backend, three warm-ups, 30 sequential timed embeddings with I/O
  and validation excluded, nearest-rank p50/p95. Compare to the precommitted
  budget and preserve sanitized measurements. **Done — quiet machine (Pipec
  closed all apps, VS Code only, ambient street noise irrelevant to a
  synthetic-tone CPU benchmark). Two independent runs: p50 = 219 / 223 ms,
  p95 = 238 / 231 ms, min 205 / 209 ms, max 268 / 247 ms, n = 30. Official
  run (with the resource window): p50 222.56 ms, p95 231.20 ms. CPU during the
  ~10 s window min 17 / mean 45 / max 63 % (that load is the single torch
  inference process itself; the box was at 4 % before). RAM free 3.5–3.9 GB
  throughout, never paged. p95 ≈ 231 ms vs the precommitted 500 ms → PASS with
  ~2.1× headroom.**
- [x] Observe RED with the focused unit command and opt-in slow command frozen
  by the readiness amendment. **Done — `test_backend_embed_wav_rejects_wrong_dimension`
  and `test_run_cli_model_contract_dispatches_to_the_backend` failed before the
  adapter + dispatch existed.**
- [x] Implement only the approved adapter. No identity/runtime import.
  **Done — `scripts/speaker_calibration_backend.py`; deferred imports keep
  `torch` out of `validate`/`analyze`/`cleanup`.**
- [x] Observe GREEN; inspect lock diff and run a frozen environment sync check.
  **Done — 94/94 speaker-calibration unit + 4/4 slow; full CI-equivalent suite
  1280 passed; `uv lock --check` exit 0; `uv sync --frozen --all-packages
  --all-groups` exit 0 (plain `uv sync --frozen` is wrong here — it drops
  workspace-member deps).**
- [x] Complete spec, quality, dependency/license and privacy reviews.
  **Self-review done (see Task 3 review notes). Independent whole-branch +
  privacy review remains Task 7's job per the plan.**
- [x] Commit: `feat(eval): add frozen speaker embedding backend`

### Task 3 evidence (2026-09-08)

| Item | Value |
|---|---|
| Branch | `feat/0047-speaker-calibration` (no new branch, no worktree) |
| New files | `scripts/speaker_calibration_backend.py` (~215 lines), `tests/slow/test_speaker_calibration_backend.py` (60 lines) |
| Modified | `scripts/speaker_calibration.py` (`model-contract` now dispatches to the backend via deferred import), `tests/unit/test_speaker_calibration.py` (+14 backend tests, −1 stale "deferred to Task 3" test), `pyproject.toml` (`speechbrain==1.1.1`, then `torch>=2.14.0,<3.0.0` + `torchaudio>=2.11.0,<3.0.0` in `dev` per the amendment; `speechbrain.*` added to `[[tool.mypy.overrides]] ignore_missing_imports`), `uv.lock` (net +13 packages after the amendment removed the 19 CUDA nodes) |
| `uv add` resolution | `speechbrain==1.1.1`, `torch==2.14.0+cpu`, `torchaudio==2.11.0+cpu`, `sympy`, `mpmath`, `hyperpyyaml`, `ruamel-yaml*`, `cloudpickle`, `joblib`, `sentencepiece`, `soundfile`, `setuptools` (torch/torchaudio pinned to the CPU index by the amendment above). `numpy` **unchanged at 2.5.2**, `huggingface-hub` **unchanged at 1.29.0** — no upper-bound conflict, no downgrade. |
| CPU-only confirmation | Runtime after the pytorch-cpu index amendment: `torch 2.14.0+cpu`, `torchaudio 2.11.0+cpu`, `torch.cuda.is_available() == False`, `torch.version.cuda is None`. `uv.lock`: `torch` / `torchaudio` `source = { registry = "https://download.pytorch.org/whl/cpu" }`; the 19 `nvidia-*` / `cuda-*` / `triton` nodes that the first (PyPI) resolution carried for Linux are **removed**. See "Amendment: pytorch-cpu index" above for the full before/after. |
| API vs frozen contract | Verified against the installed package: `FetchConfig(overwrite, allow_updates, allow_network, token, revision=None, huggingface_cache_dir=None)` ✓; `LocalStrategy.COPY == 2` ✓; `EncoderClassifier.from_hparams(source, hparams_file='hyperparams.yaml', **kwargs)` ✓; `encode_batch(self, wavs, wav_lens=None, normalize=False)` ✓. No API drift. |
| Commit `0f99f2d0` diff | Touches only `hyperparams.yaml`; reverts a PR that had added a `pretrained_path` pointer + a `paths:` section, returning the config to plain relative local paths — favourable for a pinned offline load, no behaviour risk. |
| `pip-audit --local` | **No known vulnerabilities** across the new torch/torchaudio/speechbrain graph. |
| `filterwarnings=["error"]` | No third-party `DeprecationWarning` surfaced from `speechbrain`/`torch` during unit or slow runs — no scoped `ignore` entry needed. |
| Secret scan | `_MODEL_REVISION` (40-hex) carries `# pragma: allowlist secret` — it is a public HF commit SHA. |
| RED | `uv run pytest tests/unit/test_speaker_calibration.py -k backend -n0` → 2 failed / 12 passed before adapter + dispatch existed. |
| GREEN — scoped (Block 6) | `ruff check` + `ruff format --check` on all four `scripts/speaker_calibration*.py` → clean. `MYPYPATH=. uv run mypy --explicit-package-bases scripts/speaker_calibration.py scripts/speaker_calibration_backend.py scripts/speaker_calibration_corpus.py scripts/speaker_calibration_models.py` → **Success, 4 files**. |
| GREEN — repo gates | `just lint` clean · `just typecheck` mypy 92 files + pyright 0 (mypy prints a harmless `unused section(s): module = ['speechbrain.*']` note — the override exists for the scoped script runs, which the gate does not do) · `uv run pytest -m "not slow and not hardware and not eval" -n auto` → **1280 passed** · speaker-calibration unit 94/94 · slow backend 4/4. |
| Model cache | `project-history/calibration/speaker/model-cache/` (85 MB: `embedding_model.ckpt` 83 MB + 4 small files) — gitignored, absent from `git status`. HF hub cache also populated at `~/.cache/huggingface/hub/` (outside the repo). |
| Latency (block 5, run once) | 3 s synthetic sine WAV, one loaded encoder, 3 warm-ups discarded, 30 timed `encode_batch` calls (WAV decode + `validate_wav_bytes` excluded), nearest-rank via `scripts.speaker_calibration.percentile`. **p50 = 222.56 ms, p95 = 231.20 ms** (min 209.5, max 247.1). Corroborating first run: p50 219.1, p95 238.3. **p95 vs precommitted ≤ 500 ms → PASS (~2.1× headroom).** Resource window (~10 s, 10 samples): CPU% min 17 / mean 45 / max 63 (the load is the torch inference process itself — the box idled at 4 % beforehand, Docker closed, Ollama not running); RAM free 3.5–3.9 GB, no paging. Measurements are numbers only — no audio, no paths retained. |
| Private data | no WAV, manifest, embedding or hash created or committed. |

### Task 3 review notes (2026-09-08, self-review)

- **Spec compliance.** Backend construction matches block 2 verbatim
  (`EncoderClassifier.from_hparams` with `savedir` under the gitignored corpus
  root, `run_opts={"device": "cpu"}`, `LocalStrategy.COPY`,
  `FetchConfig(revision=_MODEL_REVISION, allow_network=...)`). int16→float is
  `samples.astype(np.float32) / 32768.0`, no resample/gain. Tensor is
  `torch.from_numpy(wave).unsqueeze(0)` → `(1, n)`. Call is
  `encode_batch(wavs=tensor, wav_lens=None, normalize=False)`. Output
  `.squeeze().detach().cpu().numpy()` → checked to exactly 192 finite non-zero
  floats via the reused `scripts.speaker_calibration._checked_embedding`. The
  `SpeakerEmbeddingBackend` Protocol is satisfied (a typed unit test binds it).
  `EncoderClassifier` — not `SpeakerRecognition` — so no built-in `threshold`.
- **Global constraints.** No `server/src` / `robot/src` / settings / route / DB /
  prompt / `.env.example` change. No `IdentityEvidence`, no persisted voiceprint,
  no enrollment/revocation. `VOICE` untouched. No cloud provider. English code,
  Google docstrings, frozen dataclasses elsewhere in the harness, `pathlib`,
  `logger` not `print`, every function ≤ 30 lines, exception chaining where a
  cause exists. Audio-contract docstring (WAV·16000Hz·mono·int16) on every
  function that touches audio bytes.
- **`_MODEL_SOURCE` / `_MODEL_REVISION`** are named module-level `Final`
  constants — the one sanctioned "no hardcoded model" exception (block 1),
  never routed through `server.settings`.
- **Deferred imports.** `torch`, `speechbrain`, `huggingface_hub` are imported
  inside functions, and `run_cli` reaches the backend via a deferred import, so
  `validate` / `analyze` / `cleanup` never import `torch` (unchanged Task 2
  behaviour preserved).
- **Dependency / license.** `speechbrain` 1.1.1 Apache-2.0; ECAPA model
  Apache-2.0 at the pinned revision; `pip-audit --local` clean. Rollback path
  (`uv remove --group dev speechbrain` + `uv sync --all-packages --all-groups`)
  not needed — this is a PASS.
- **Privacy.** No microphone opened. `model-contract` and both tests use a
  generated sine tone, never a voice. No WAV/manifest/embedding/hash written or
  staged. The tracked diff carries only code, the frozen public model SHA (with
  an allowlist pragma), sanitized latency numbers and this plan text.
- **`pytorch-cpu` index:** the first resolution missed the declared index (a
  transitive-dep limitation of `[tool.uv.sources]`). Flagged, not adapted
  in-flight; resolved afterwards by the Pipec-approved amendment above, which
  makes `torch` / `torchaudio` direct `dev` constraints and drops 19 CUDA nodes
  from the Linux lock.

If package resolution, model load, frozen revision, CPU execution,
offline-after-cache behavior, finite fixed-dimension output or the precommitted
p95 budget fails, record `FAIL — backend/latency`, remove any incomplete corpus
(none should yet exist), keep only reviewed non-biometric diagnostic evidence,
and proceed directly to Task 7. Do not collect household voices or swap models.

## Task 4: Capture owner reference and genuine samples

**Owner:** Pipec. Agents may display the next command and validate metadata
afterward; they may not activate the microphone themselves.

- [x] Confirm corpus root resolves under
  `project-history/calibration/speaker/`, is ignored by Git, and contains no
  prior participant data unless Pipec explicitly elects to reuse it.
- [x] Show the consent notice and confirm Pipec agrees to temporary local WAV
  and embedding storage plus deletion after analysis.
- [x] Capture six references in the dedicated reference session using the
  frozen phrases. **Done 2026-09-08 — 6/6.**
- [x] On at least two later sessions, capture at least 24 genuine probes across
  the frozen near/far and quiet/ordinary-background matrix. **Done 2026-09-14 —
  24/24 across 2 sessions, all 3 phrases and all 4 conditions represented.**
- [x] After each batch, run manifest validation and inspect counts/conditions;
  recapture only invalid technical samples and record exclusions. **Done — a
  handful of technically invalid captures (clipped onset, VAD-confused by
  background music) were excluded and recaptured; none entered the accepted
  corpus.**
- [x] Confirm `git status --short` never lists WAV, manifest or embedding data.
  **Confirmed clean throughout.**

**Checkpoint (2026-09-14): Task 4 complete.** Aggregate only (no filenames/ids,
per this section's own rule) — reference 6/6, genuine 24/24 (2 sessions, 3
phrases, 4 conditions), corpus root private and untracked throughout. Pipec has
independently begun inviting the three consenting adults for Task 5 in
parallel, per his own explicit decision to run owner-only and third-party work
concurrently rather than sequentially. **No Git commit of capture data** — the
corpus, manifest, embeddings and any per-sample figure never enter Git. This
aggregate-only status update was committed on 2026-09-21 at Pipec's explicit
request; the "no commit" rule exists to keep private biometric data out of
history, and nothing private is in it.

### Task 4 tooling changes and operating notes (recorded 2026-09-21)

Real capture exposed three operator-facing defects in the Task 2 CLI. They were
fixed as small code commits on this branch (code history only — no private data)
and Task 5 uses the same `capture` action, so the whole-branch review in Task 7
must cover them:

| Commit | Change | Why it was needed |
|---|---|---|
| `859750e` | `capture` prints the frozen phrase (`PHRASE_TEXT`, a named constant beside `PHRASE_IDS`), counts down 3-2-1 and sounds a start beep before a live recording | The operator otherwise needs a second terminal to know what to read, and has no cue for when to start. Only runs with the real microphone (no injected recorder), so unit tests stay fast |
| `f6c5c95` | `_reject_if_too_short` rejects a live capture under 2.5 s: nonzero exit, no WAV, no manifest row | A capture where the VAD closed on a mid-phrase pause entered the corpus silently as a partial phrase |
| `188e9bf` | `_warm_recorder` preloads `onnxruntime` and the Silero model before the countdown | A cold VAD load measured ~4.5 s *inside* `capture_utterance`, so the start beep fired well before the microphone was listening and the phrase onset was lost |

Operating notes for Task 5 and any recapture (no data in them):

- `capture` needs neither the server nor Ollama — only the microphone and the
  local Silero model.
- Accepted-corpus exclusions during Task 4 were all technical: clipped or
  premature captures, and two genuine `background-*` probes recorded over *vocal*
  music (the VAD treated the singer as speech and the utterance ran ~2× normal
  length). Background conditions must use non-vocal noise (rain, fan, room tone).
- Replay probes at `quiet-far` were not detected when the source recording was
  already quiet; playing the source at higher **software** gain in the player
  fixed it. The recording itself is never edited — the plan reserves any
  transformation of a person's voice to the operator.
- The corpus is local-only by design: moving source WAVs to a cloud drive to play
  them from a phone was declined, because Task 7 verifies deletion only for the
  corpus root.
- Task 4 exclusions were first done by editing the private manifest by hand,
  because the CLI had no way to discard a capture. That gap is closed: the
  `discard` action (commit `68a23c5`, see the CLI notes above) now does it
  safely, so the operator can honour a withdrawal alone.
- In the tracked docs and in chat, report **counts and ranges only**: sample
  ids, filenames and timestamps are manifest data and stay out of them.

## Task 5: Capture consenting live-impostor and replay samples

**Owner:** Pipec and consenting adults.

- [x] Obtain explicit consent independently from at least three adults and
  assign only local pseudonyms. **Done — four adults consented (three were the
  required minimum) and were recorded under local letter pseudonyms only.**
- [x] Capture at least 18 live impostor probes. They must be spoken live during
  capture and distributed across the frozen phrases. **Done 2026-09-25 — 24/24
  (6 per adult: three phrases × two repetitions, all `quiet-near`).**
- [x] Allow immediate withdrawal and execute targeted deletion/manifest repair
  before proceeding if requested. **Procedure built and rehearsed:** `just
  speaker-calibration discard --subject impostor_x` (typed confirmation), then
  re-run `embed` and `analyze`. No participant withdrew. The tool was used once
  for a technical exclusion (one take that Pipec himself had recorded as a test,
  mislabeled as an impostor).
- [x] Pipec creates at least six replay probes using the frozen procedure. Keep
  replay labels separate from live impostors. **Done 2026-09-14 — 8/6, one
  session, all 3 phrases at both `quiet-near` and `quiet-far`.**
- [x] Validate corpus counts, class labels, distinct files, session/phrase
  separation and hashes. Do not inspect or publish transcripts. **Done — `validate`
  passed on the full 62-sample corpus, and again under the stricter matrix rules
  added in Task 7.**
- [x] Confirm again that private artifacts are ignored and absent from staged
  changes. **Confirmed — `project-history/` is ignored (`.gitignore`), and no path
  under it was ever tracked or staged.**

**Checkpoint:** if consented minimums cannot be reached, pause. Do not lower the
matrix silently or substitute internet/synthetic voices. (Not triggered.)

## Task 6: Analyze, choose or reject the candidate

**Owner:** orchestrator executes only after Pipec confirms capture complete.
**Executed 2026-09-25** after Pipec confirmed the capture complete.

Groundwork built ahead of capture (2026-09-21, Pipec-authorized): `analyze` (pure,
`scripts/speaker_calibration_analysis.py`) wired end to end in the CLI, and `embed`
handed the frozen backend by `main()` (only for `embed`; the other actions never
import `torch`). Per-sample latency is informational: the gating result stays the
frozen Task 3 protocol.

- [x] Run the frozen analyze command from the readiness amendment. Analysis
  must not access microphone/network and must use the already cached exact
  model revision. **Done. `analyze` first made one unrelated Hugging Face request
  (an agent-harness registry lookup made by `huggingface_hub`); it was found by a
  socket guard, fixed by forcing offline mode for every action but `model-contract`
  (`1b59ad3`) and re-verified — zero connection attempts.**
- [x] Produce per-condition aggregate distance ranges/counts, live-impostor
  FAR, genuine FRR, replay accept rate, exclusion reasons and p50/p95 CPU
  embedding latency. **See the closure record.**
- [x] Apply the fixed rule: choose the lowest-risk zero-observed-FAR threshold
  with minimum FRR; a tie chooses the lower threshold. If none exists, result
  is FAIL and no compromise threshold is selected. **A zero-observed-FAR
  threshold exists: 0.4834.**
- [x] Compare measured p95 with the readiness-amended feasibility bound. **Frozen
  protocol p95 231 ms < 500 ms. Per-sample p95 over the real 4–5 s clips on a
  loaded machine was 536 ms — recorded as informational, as the plan defined.**
- [x] Independently inspect the aggregate report against local raw results
  without copying raw samples into tracked files. **Done — after the Task 7 fixes the
  embeddings were recomputed from the WAVs and `analyze` was re-run; every figure
  matched the first run.**
- [x] Record one conclusion: `PROVISIONAL PASS`, `FAIL — distance overlap`,
  `FAIL — backend/latency`, or `INVALID — corpus/procedure`. Only the first can
  inform PC-3B; none changes runtime here. **`PROVISIONAL PASS`.**
- [x] Report replay acceptance separately and state explicitly that PC-4 owns
  anti-spoofing. A replay accepted at any rate forbids standalone high-assurance
  claims. **6 of 8 replay probes were accepted; voice is not standalone
  high-assurance evidence, and replay/liveness belongs to PC-4.**

## Task 7: Privacy cleanup and documentation closure

- [x] After Pipec accepts the aggregate report, resolve and list each exact
  private artifact path under the corpus root, verify all stay within that
  root, and delete individual files without recursive broad-target commands.
  **Done 2026-09-25 (Pipec accepted the report and authorized the deletion).
  Before deleting, the corpus root held 62 WAVs, 1 embeddings archive, 1 manifest,
  1 aggregate report and 5 model files; every path resolved inside the root and none
  was tracked. `cleanup` (which refuses anything that is not a known corpus
  artifact) deleted the 65 corpus files by exact path; the orchestrator supplied
  the typed confirmation under Pipec's explicit go-ahead in chat.**
- [x] Confirm WAVs, embeddings, manifests, per-sample scores and temporary
  caches containing samples are gone. Model package/cache may remain only if it
  contains no captured audio and Pipec chooses to retain it. **Verified: no WAV,
  embeddings archive, manifest or report remains under `project-history/calibration/`;
  temporary analysis scripts and reports outside the repository were deleted. Only the
  5 model files (about 85 MB, no captured audio) remain, kept by `cleanup`'s default so
  a later PC-3B can reuse them; `just speaker-calibration cleanup --purge-model-cache`
  removes them.**
- [x] Run the current canonical gate, the scoped script checks (Block 6 — the
  gate does not see `scripts/`), then documentation hook/diff checks. **Done:
  `just gate` GREEN (1417 tests passed, ruff, mypy, security lint, `pip-audit`: no
  known vulnerabilities); scoped `ruff check`, `ruff format --check` and `mypy` over
  all five `scripts/speaker_calibration*.py` files and their tests clean; the slow
  backend tests (5) pass against the real cached model; `just check`,
  `git diff --check` and `uv lock --check` clean.** `pip-audit` cannot audit the two
  local `+cpu` builds of `torch`/`torchaudio` (not on PyPI); accepted.
- [x] Run a privacy search over tracked diff for names, `.wav`, embeddings,
  absolute paths, manifest hashes and transcript content; explain benign code
  literals. **Done over the whole branch diff: no 64-hex hash, no capture
  timestamp, no absolute or user path, no real name (the reserved-terms guard
  passed in every commit). The `.wav` hits are code literals and synthetic test
  fixtures; the `impostor_*` hits are the letter pseudonym pattern and synthetic test
  ids; the only phrases are the frozen neutral study phrases.**
- [x] Inspect all changes produced by the auto-fixing `just gate` before final
  review; do not assume the pre-gate diff is the final diff. **The gate produced no
  file change.**
- [x] Obtain whole-branch spec, code-quality, dependency/license and privacy
  reviews. Resolve all high/medium findings and rerun affected gates. **Done — see
  "Task 7 review record".**
- [x] Update canonical docs without changing `VOICE` trust or claiming PC-3
  complete. If provisional PASS, state that PC-3B enrollment/runtime and PC-4
  fusion/replay remain open. If FAIL, record the exact blocked outcome. **Done:
  current state, identity and access, the roadmap, both delivery maps, the plan
  indexes and the architecture diagram.**
- [x] Move this plan to `completed/` only with measured evidence and verified
  deletion. Use `superpowers:finishing-a-development-branch`; Pipec chooses
  merge/PR/keep and branch deletion. **Moved; Pipec's merge/PR choice is pending.**
- [x] Commit: `docs(plan): record speaker calibration study`

## Study result and closure record (2026-09-25)

Aggregates only — no sample id, file name, timestamp, per-sample score, hash or
transcript is recorded here, in keeping with the plan's privacy rule.

**Outcome: `PROVISIONAL PASS` — closes PC-3A only.**

**Backend (frozen).** SpeechBrain `1.1.1` `EncoderClassifier`, model
`speechbrain/spkrec-ecapa-voxceleb` at revision `0f99f2d0…` (Apache-2.0), CPU,
offline after the one-time cache warm-up; 192-d embeddings, cosine distance to the
centroid of the six L2-normalized references; a sample matches when
`distance <= threshold`.

**Corpus (private, deleted).** 62 samples: reference 6 (one session, `quiet-near`);
genuine 24 (two sessions, three phrases, all four conditions: `quiet-near` 7,
`quiet-far` 7, `background-near` 5, `background-far` 5); live impostor 24 (four
consenting adults, 6 each, `quiet-near`); replay 8 (`quiet-near` 5, `quiet-far` 3).
Exclusions were all technical (clipped or premature takes, takes where the VAD
followed a singer in background music, and one mislabeled test take); none entered
the accepted corpus.

| Measure | Result |
|---|---|
| Selected threshold (cosine distance) | 0.4834 (lowest-FRR threshold with zero observed impostor accepts) |
| Live-impostor false accepts / FAR | 0 of 24 / 0.0 — the 95 % rule-of-three bound on the true FAR is only about 12.5 % |
| Genuine false rejects / FRR | 0 of 24 / 0.0 — **in-sample, zero by construction** (the threshold is the largest genuine distance below the closest impostor); no held-out check |
| Separation (closest impostor minus farthest genuine distance) | 0.342 |
| Distance ranges | genuine 0.2272–0.4834 (`quiet-near` 0.2272–0.4694, `quiet-far` 0.2413–0.3674, `background-near` 0.2407–0.4834, `background-far` 0.3342–0.4248); impostor 0.8256–0.9550 |
| Replay probes accepted | 6 of 8 (0.75): `quiet-near` 5 of 5, `quiet-far` 1 of 3 (range 0.3322–0.7575) |
| CPU embedding latency, frozen Task 3 protocol | p50 222.6 ms / **p95 231.2 ms** < the 500 ms budget |
| Per-sample latency over the real clips (informational) | p50 431 ms / p95 536 ms on a loaded development laptop; the gate is the frozen protocol |

**Limitations.** One owner, four impostors and no held-out data make the result
provisional evidence, not population-level security. Replay was accepted, so voice
must never be standalone high-assurance evidence; replay/liveness is PC-4's job.
`VOICE` stays untrusted identity evidence. This study made no enrollment, no stored
voiceprint, no runtime adapter and no change to the audio or API contract. **PC-3B
(consented enrollment, revocation, runtime evidence) and PC-4 (fusion and
replay/liveness handling) remain open; PC-3 is not complete.** The model's training
data (VoxCeleb) carries its own licence; that is acceptable for this local,
non-redistributed study but a redistributing or production PC-3B must review it.

**Interface changes made during execution (recorded, all inside `scripts/`).**
Beyond the original file map: a fifth module (`speaker_calibration_analysis.py`), a
seventh CLI action (`discard`), `--purge-model-cache` on `cleanup`, and these
behaviors — a manifest is strict (a missing or damaged WAV fails `validate` and
`analyze`; `discard` loads leniently so a withdrawal always works); `embeddings.npz`
records the model id and each WAV's hash, and `analyze` refuses stale or foreign
vectors; the corpus rules add per-phrase repetitions, distinct audio, replay
conditions and impostor/owner session separation; `embed` deliberately does not run
the full-matrix `validate` (it must embed a partial corpus during capture) — `analyze`
does. `torch`/`torchaudio` are pinned to the `pytorch-cpu` index (a same-day,
Pipec-approved amendment).

### Task 7 review record

Independent reviewers (no shared session history), all read-only: **spec compliance
and code quality**; **security, privacy and dependency/license**; **silent failures
and test quality**; then a **re-review of the fixes**. None found a critical issue;
the analysis maths, path safety, atomic manifest writes and the no-network posture
were confirmed. Every finding was fixed, except those listed under "not adopted", in
`0c77e5c`, `ef3f23d` and `13175ac` (TDD; the unit suite grew from 136 to 199 tests):

- a missing or damaged WAV was silently accepted, and a damaged file could block a
  withdrawal → strict manifest; lenient `discard`;
- capture accepted silence, clipping, overlong takes and left orphan WAVs on a
  crash → a signal guard (its floor calibrated from real-corpus aggregates so the
  quietest legitimate far-field take passes), atomic WAV write with rollback, orphan
  detection, safe session ids;
- `cleanup` would delete any directory it was pointed at and always deleted the
  model cache → refuses non-corpus directories, keeps the cache unless
  `--purge-model-cache`, needs a terminal;
- embeddings had no provenance → model id and per-WAV hash, checked by `analyze`;
- the model-cache check trusted the wrong location → each cached file is compared
  byte for byte with the pinned snapshot; `model-contract` now fails if the offline
  load fails;
- the report could mislead → ranges hidden for cells under 3 samples; an explicit
  in-sample-FRR limitation and the separation figure;
- capture logs carried sample ids; durable writes lacked `fsync`/temp cleanup; Hub
  telemetry; unsafe path arguments; corpus rules weaker than the protocol; slow
  tests that could hide a real failure or leak environment → all fixed.

Dependency and licence review: every new package is permissively licensed (Apache-2.0,
BSD, MIT); `explicit = true` keeps the `pytorch-cpu` index to `torch` and
`torchaudio`; no copyleft; `pip-audit` clean.

**Findings not adopted, with reasons:** moving the numeric layer to break the
CLI ↔ analysis/backend import cycle (the documented deferred imports are the simpler
fix and keep `torch` out of `validate`/`analyze`); a `manifest.json.bak` (it would
retain a withdrawn participant's rows, defeating `discard`); `uv run --frozen` in the
recipe (consistent with the other recipes; offline and telemetry are enforced
in-process); an embed-time audio-energy check (single-operator threat model — the
capture guard and `validate` cover it); sample ids removed from error messages for
rows that are *invalid* (needed to repair them — routine logs carry none). The
drafts of Plans 0049/0050 (another session's work) still describe 0047 as `NOW`;
they were not edited here.

## Rollback and incident boundary

The harness is outside runtime and its commits can be reverted independently.
No production identity or database rollback is expected because touching them
is forbidden. Private corpus deletion is intentionally irreversible after the
aggregate report is approved. Before deletion, Pipec may choose to invalidate
the study instead of preserving voices. If private media is staged, uploaded,
logged outside the corpus or written to production data, stop immediately,
preserve only minimal incident metadata, remove exposure through an explicitly
approved safe procedure, and do not call ordinary Git revert a privacy repair.

## Non-goals

- production speaker enrollment, recognition, revocation or profile storage;
- making `VOICE` a trusted source or changing `resolve_active_person`;
- authorization, identity fusion, face changes or PIN recovery changes;
- replay/liveness detection, diarization, speech-to-text or VAD improvement;
- identifying visitors or creating family accounts;
- retaining a reusable household voice dataset;
- cloud APIs, remote inference, model training/fine-tuning or online learning;
- changing the audio/API contract, server/robot runtime or PC-5 acceptance.

## Completion criteria

Plan 0047 closes only after it was promoted through the readiness gate and one
of these evidence-complete outcomes exists:

**Provisional PASS** requires a frozen local backend; all deterministic and
backend contract tests GREEN; the minimum consented corpus; zero observed live
impostor accepts at the selected threshold; honest global/per-condition FRR;
latency within the pre-frozen bound; replay reported separately; complete
private-artifact deletion; full repository gates and reviews GREEN. It closes
PC-3A only.

**Honest FAIL** has two valid forms. A technical FAIL occurs in Task 3 when the
frozen backend cannot resolve/load/run offline, return valid embeddings or meet
the precommitted p95 bound; it requires no household corpus and prohibits
capture. A measurement FAIL completes the consented minimum corpus but finds no
zero-observed-FAR separation. Both retain reviewed non-biometric diagnostics,
select no substitute/compromise and do not authorize PC-3B.

An incomplete corpus after capture, missing consent, leaked artifact, model
drift outside the approved revision or unverifiable deletion is `INVALID`, not
PASS or FAIL, and the plan stays open or is explicitly blocked by Pipec.
