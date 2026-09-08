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

**Status:** Queued — readiness amendment complete 2026-09-08 (backend, model
revision, dependency command, tensor contract, latency protocol, frozen phrases
and p95 budget are all locked in the "Frozen readiness contract" section
below). Plan 0046 (CM-0) closed 2026-09-08, clearing the sequencing blocker.
Two blockers remain before promotion: an independent plan review, and Pipec's
explicit authorization to change `Status` to `Ready` and put 0047 in `NOW`. No
code, dependency download or real-voice capture begins until both clear.

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

**Spec:** [Plan 0015 PC-3](0015-personal-companion-design.md),
[identity and access](../../architecture/identity-and-access.md),
[current state](../../architecture/current-state.md),
[ADR 0006](../../adr/0006-personal-and-family-companion-profiles.md).

## Why this plan is queued

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
- [ ] Run an independent plan review. **Open — this is the last blocker.** Only
  then may Pipec change `Status` to `Ready`, put 0047 in `NOW`, and give
  explicit implementation authorization.

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
| Class | `speechbrain.inference.speaker.EncoderClassifier` — **not** `SpeakerRecognition`. The study needs the raw embedding; `SpeakerRecognition.verify_batch`'s built-in `threshold=0.25` is a generic VoxCeleb score cut, explicitly not a household authorization threshold. |
| Model | `speechbrain/spkrec-ecapa-voxceleb` (Apache-2.0) |
| Model revision | `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` (immutable, pinned) |
| Embedding dimension | 192 (ECAPA-TDNN attentive statistical pooling) |

### Block 2 — Frozen call and tensor contract

Construction (device, revision, offline-safe copy strategy all explicit):

```python
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import FetchConfig, LocalStrategy

_MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
_MODEL_REVISION = "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"

encoder = EncoderClassifier.from_hparams(
    source=_MODEL_SOURCE,
    savedir=<gitignored local cache dir under the corpus root>,
    run_opts={"device": "cpu"},
    local_strategy=LocalStrategy.COPY,
    fetch_config=FetchConfig(revision=_MODEL_REVISION, allow_network=False),
)
```

- `allow_network=False` is the offline-after-cache assertion: a first run with a
  warm HF cache (populated by the model-contract command) must succeed with no
  network. A cold cache is a Task 3 setup step, run once and recorded, not part
  of any timed or gating measurement.
- **Verification note (block 2, Task 3):** the source refresh shows
  `fetch_config` reaching `fetch()` via `pretrainer.collect_files`, but the
  implementer must still assert against the installed package that
  `_MODEL_REVISION` is the revision actually resolved (e.g. by inspecting the
  populated `savedir` / HF cache ref). A mismatch is a documentation stop.

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
- If mypy/pyright flags missing stubs, add `speechbrain.*` (and `torch.*` /
  `torchaudio.*` only if needed) to `[[tool.mypy.overrides]]
  ignore_missing_imports` in the root `pyproject.toml` — same pattern as the
  existing `insightface.*` / `onnxruntime.*` entries.
- If `speechbrain`'s `filterwarnings = ["error"]` interaction surfaces a
  third-party `DeprecationWarning` from `torch`/`speechbrain`, add a narrowly
  scoped `ignore::DeprecationWarning:speechbrain.*` (or `torch.*`) entry, mirroring
  the existing `piper.*` / `faster_whisper.*` filters — never a blanket ignore.
- Rollback: `uv remove --group dev speechbrain` then
  `uv sync --all-packages --all-groups`.

### Block 4 — Frozen phrases and feasibility budget

Three neutral Spanish phrases (no names, personal facts, secrets or wake
words), fixed so repeats across sessions are comparable:

| ID | Text |
|---|---|
| `phrase-01` | La lluvia cae despacio sobre el tejado de la casa |
| `phrase-02` | Guardé cinco libros nuevos en el estante de madera |
| `phrase-03` | Prefiero caminar por el parque cuando termina la tarde |

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
| 1 | `uv run pytest tests/unit/test_speaker_calibration.py -k "normalize or centroid or distance or threshold or latency" -n0 -v` | same, plus full file |
| 2 | `uv run pytest tests/unit/test_speaker_calibration.py -k "manifest or wav or path or cli" -n0 -v` | same, plus `just lint` / `just typecheck` |
| 3 | `uv run pytest tests/unit/test_speaker_calibration.py -k "backend" -n0 -v` and `uv run pytest tests/slow/test_speaker_calibration_backend.py -m slow -n0 -v` | same, plus lock-diff inspection and `uv sync --frozen` check |

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
| `tests/unit/test_speaker_calibration.py` | Create pure synthetic tests for math, schema, paths, reports and backend boundary fakes. |
| `tests/slow/test_speaker_calibration_backend.py` | Create opt-in frozen-model smoke/contract tests; never part of ordinary unit execution. |
| `pyproject.toml`, `uv.lock` | Add the exact approved package to the root development group and record the generated resolution; no subproject dependency edit. |
| `justfile` | Add `speaker-calibration *ARGS` after dependencies are locked. |
| `docs/plans/open/0047-speaker-evidence-calibration-study.md` | Persistent checkpoints and final measured evidence. |
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
    action: Literal["model-contract", "capture", "validate", "embed", "analyze", "cleanup"]
    corpus_root: Path
    manifest_path: Path
    output_path: Path | None
    sample_class: SampleClass | None
    subject_id: str | None
    session_id: str | None
    phrase_id: str | None
    condition: str | None


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

## Corpus and condition matrix

The minimum accepted corpus is:

| Class | Minimum | Separation and conditions |
|---|---:|---|
| Reference | 6 | Owner, one dedicated enrollment session, three neutral fixed phrases × two repetitions, quiet/near. |
| Genuine | 24 | Owner, at least two later sessions, three phrases, near/far and quiet/ordinary-background conditions; no reference file reused. |
| Live impostor | 18 | At least three consenting adults, each three phrases × two repetitions, captured live rather than played from a device. |
| Replay | 6 | Pipec replays at least three owner probe recordings through a household speaker at two distances; source IDs recorded locally. |

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

- [ ] Confirm every readiness blocker is checked, the reviewed plan status is
  `Ready`, it is the sole `NOW`, and Pipec explicitly authorized execution.
- [ ] Record branch, SHA, `git status`, frozen backend/package/model revision,
  approved download scope, literal phrase IDs/text and precommitted p95 budget.
- [ ] Create one simple feature branch from the approved merged SHA on `main`
  (e.g. `feat/0047-speaker-calibration`). **No git worktree** — the project
  uses one plain branch per plan. Preserve any uncommitted user changes.
- [ ] Re-read all required sources on that branch. Any material API, license,
  package or lock drift stops for a documentation amendment; do not adapt while
  coding.

**Hard stop:** no code, dependency/model download or voice capture occurs
unless all four checks pass. No commit.

## Task 1: Build the pure numeric calibration layer with TDD

**Files:** create `scripts/speaker_calibration.py` and
`tests/unit/test_speaker_calibration.py`.

- [ ] Write tests for unit/orthogonal/opposite vectors, normalization,
  centroid order independence, equal dimensions and invalid zero/NaN/infinite
  values.
- [ ] Write tests for inclusive threshold comparison, FAR/FRR counts, tie
  breaking, no-zero-FAR overlap returning `None`, replay exclusion and p50/p95.
- [ ] Run RED:

  ```powershell
  uv run pytest tests/unit/test_speaker_calibration.py -k "normalize or centroid or distance or threshold or latency" -n0 -v
  ```

  Expected: missing symbols/behavior only; no audio/model import.
- [ ] Implement the minimum pure functions from the stable interface.
- [ ] Re-run focused and full unit file; observe GREEN.
- [ ] Complete spec and quality reviews.
- [ ] Commit: `feat(eval): add speaker calibration math`

## Task 2: Build the private corpus manifest and safe CLI with TDD

**Files:** modify the script/unit test and add `speaker-calibration` to
`justfile`.

- [ ] Write failing tests for manifest version/extra fields/duplicate IDs,
  class-subject rules, session separation, minimum matrix, WAV contract,
  SHA-256 mismatch, traversal/symlink escape and non-corpus paths.
- [ ] Test that `--analyze` never opens a microphone and capture cannot write
  outside `project-history/calibration/speaker/`.
- [ ] Test backend/capture exception: nonzero exit, no partial manifest row and
  no accepted report.
- [ ] Test aggregate-report invariants for technical FAIL without corpus,
  measurement overlap, provisional PASS and invalid procedure; test
  per-condition ranges/counts and omission of private fields.
- [ ] Run RED:

  ```powershell
  uv run pytest tests/unit/test_speaker_calibration.py -k "manifest or wav or path or cli" -n0 -v
  ```

- [ ] Implement atomic manifest append, strict WAV validation and safe path
  resolution. Every audio-touching function carries the exact audio-contract
  docstring.
- [ ] Add the exact recipe only after the readiness amendment has locked all
  imports:

  ```just
  speaker-calibration *ARGS:
      uv run --env-file .env python scripts/speaker_calibration.py {{ARGS}}
  ```

- [ ] Re-run tests and `just lint`/`just typecheck`; observe GREEN.
- [ ] Complete spec, quality and privacy reviews.
- [ ] Commit: `feat(eval): add private speaker corpus workflow`

## Task 3: Add the frozen backend adapter with TDD

**Files:** only the script/tests and exact dependency files authorized by the
readiness amendment.

**Contract:** follow the "Frozen readiness contract" section (blocks 1–3, 5–6)
exactly — `EncoderClassifier` (not `SpeakerRecognition`), model revision
`0f99f2d0…`, `LocalStrategy.COPY`, `FetchConfig(revision=…, allow_network=False)`,
`(1, n_samples)` float32 input, `(1, 1, 192)` output.

- [ ] From workspace root run the approved command
  `uv add --group dev "speechbrain==1.1.1"`; never `uv pip install`, never edit
  a subproject dependency file and never hand-edit the lockfile. Inspect the
  `uv.lock` diff and confirm `torch`/`torchaudio` resolved to CPU-only wheels
  via the already-declared `pytorch-cpu` index.
- [ ] Add the `model-contract` action and run `just speaker-calibration
  model-contract` once to warm the pinned-revision cache; assert the resolved
  revision equals the frozen SHA. This is a one-time setup step, not timed.
- [ ] Write unit tests with a typed backend fake for byte/input conversion,
  normalization, fixed dimension, model metadata and errors.
- [ ] Write an opt-in `slow` contract test against a generated non-biometric WAV
  fixture and the exact frozen model. Assert finite repeatable shape and
  offline-after-cache behavior; do not assert speaker quality on synthetic
  tone.
- [ ] Execute the frozen latency protocol exactly: generated three-second WAV,
  one loaded backend, three warm-ups, 30 sequential timed embeddings with I/O
  and validation excluded, nearest-rank p50/p95. Compare to the precommitted
  budget and preserve sanitized measurements.
- [ ] Observe RED with the focused unit command and opt-in slow command frozen
  by the readiness amendment.
- [ ] Implement only the approved adapter. No identity/runtime import.
- [ ] Observe GREEN; inspect lock diff and run a frozen environment sync check.
- [ ] Complete spec, quality, dependency/license and privacy reviews.
- [ ] Commit: `feat(eval): add frozen speaker embedding backend`

If package resolution, model load, frozen revision, CPU execution,
offline-after-cache behavior, finite fixed-dimension output or the precommitted
p95 budget fails, record `FAIL — backend/latency`, remove any incomplete corpus
(none should yet exist), keep only reviewed non-biometric diagnostic evidence,
and proceed directly to Task 7. Do not collect household voices or swap models.

## Task 4: Capture owner reference and genuine samples

**Owner:** Pipec. Agents may display the next command and validate metadata
afterward; they may not activate the microphone themselves.

- [ ] Confirm corpus root resolves under
  `project-history/calibration/speaker/`, is ignored by Git, and contains no
  prior participant data unless Pipec explicitly elects to reuse it.
- [ ] Show the consent notice and confirm Pipec agrees to temporary local WAV
  and embedding storage plus deletion after analysis.
- [ ] Capture six references in the dedicated reference session using the
  frozen phrases.
- [ ] On at least two later sessions, capture at least 24 genuine probes across
  the frozen near/far and quiet/ordinary-background matrix.
- [ ] After each batch, run manifest validation and inspect counts/conditions;
  recapture only invalid technical samples and record exclusions.
- [ ] Confirm `git status --short` never lists WAV, manifest or embedding data.

**Checkpoint:** report aggregate counts only and wait for Pipec before inviting
other participants. No Git commit.

## Task 5: Capture consenting live-impostor and replay samples

**Owner:** Pipec and consenting adults.

- [ ] Obtain explicit consent independently from at least three adults and
  assign only local pseudonyms.
- [ ] Capture at least 18 live impostor probes. They must be spoken live during
  capture and distributed across the frozen phrases.
- [ ] Allow immediate withdrawal and execute targeted deletion/manifest repair
  before proceeding if requested.
- [ ] Pipec creates at least six replay probes using the frozen procedure. Keep
  replay labels separate from live impostors.
- [ ] Validate corpus counts, class labels, distinct files, session/phrase
  separation and hashes. Do not inspect or publish transcripts.
- [ ] Confirm again that private artifacts are ignored and absent from staged
  changes.

**Checkpoint:** if consented minimums cannot be reached, pause. Do not lower the
matrix silently or substitute internet/synthetic voices.

## Task 6: Analyze, choose or reject the candidate

**Owner:** orchestrator executes only after Pipec confirms capture complete.

- [ ] Run the frozen analyze command from the readiness amendment. Analysis
  must not access microphone/network and must use the already cached exact
  model revision.
- [ ] Produce per-condition aggregate distance ranges/counts, live-impostor
  FAR, genuine FRR, replay accept rate, exclusion reasons and p50/p95 CPU
  embedding latency.
- [ ] Apply the fixed rule: choose the lowest-risk zero-observed-FAR threshold
  with minimum FRR; a tie chooses the lower threshold. If none exists, result
  is FAIL and no compromise threshold is selected.
- [ ] Compare measured p95 with the readiness-amended feasibility bound.
- [ ] Independently inspect the aggregate report against local raw results
  without copying raw samples into tracked files.
- [ ] Record one conclusion: `PROVISIONAL PASS`, `FAIL — distance overlap`,
  `FAIL — backend/latency`, or `INVALID — corpus/procedure`. Only the first can
  inform PC-3B; none changes runtime here.
- [ ] Report replay acceptance separately and state explicitly that PC-4 owns
  anti-spoofing. A replay accepted at any rate forbids standalone high-assurance
  claims.

## Task 7: Privacy cleanup and documentation closure

- [ ] After Pipec accepts the aggregate report, resolve and list each exact
  private artifact path under the corpus root, verify all stay within that
  root, and delete individual files without recursive broad-target commands.
- [ ] Confirm WAVs, embeddings, manifests, per-sample scores and temporary
  caches containing samples are gone. Model package/cache may remain only if it
  contains no captured audio and Pipec chooses to retain it.
- [ ] Run the current canonical gate, then documentation hook/diff checks:

  ```powershell
  just gate
  just check
  git diff --check
  ```

- [ ] Run a privacy search over tracked diff for names, `.wav`, embeddings,
  absolute paths, manifest hashes and transcript content; explain benign code
  literals.
- [ ] Inspect all changes produced by the auto-fixing `just gate` before final
  review; do not assume the pre-gate diff is the final diff.
- [ ] Obtain whole-branch spec, code-quality, dependency/license and privacy
  reviews. Resolve all high/medium findings and rerun affected gates.
- [ ] Update canonical docs without changing `VOICE` trust or claiming PC-3
  complete. If provisional PASS, state that PC-3B enrollment/runtime and PC-4
  fusion/replay remain open. If FAIL, record the exact blocked outcome.
- [ ] Move this plan to `completed/` only with measured evidence and verified
  deletion. Use `superpowers:finishing-a-development-branch`; Pipec chooses
  merge/PR/keep and branch deletion.
- [ ] Commit: `docs(plan): record speaker calibration study`

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
