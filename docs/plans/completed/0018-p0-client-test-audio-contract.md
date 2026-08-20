# P0-C3 — Client QA audio-contract parity

> **Status:** Implemented in the current feature branch — automated gates
> green; operator acceptance pending.
> **Scope:** `scripts/client_test.py --text` only. No robot/server API change.

## Objective

Make the no-microphone QA path produce valid WAV input for the existing
`POST /transcribe` contract. Piper voices may emit their native sample rate
(the configured medium voice emits 22 050 Hz), while the public server accepts
only 16 kHz, mono, signed int16. `just test-client --text ...` must therefore
normalize and validate locally before any HTTP request.

## Evidence revalidated

- The prior `scripts/client_test.py::synthesize_locally` wrote the Piper WAV
  unchanged, despite its docstring claiming 16 kHz mono int16; C3 now converts
  and validates the bytes locally.
- `server/src/server/audio_contract.py::validate_wav_contract` rejects a rate
  other than 16 kHz.
- `server/src/server/tts.py::_resample_to_contract` already provides the
  project-local, tested PCM conversion needed by this diagnostic script.
- `tests/unit/test_audio_contract.py` proves the conversion preserves duration
  and leaves valid 16 kHz audio byte-identical.

## Invariants

1. Preserve CLI flags, server URL, POST multipart field, response display, and
   optional playback.
2. Keep the script-only use of `print` approved by its existing `# noqa: T201`
   diagnostics; production code remains logger-only.
3. `--text` returns only WAV that passes the canonical 16 kHz/mono/int16
   validator, or raises a clear local error before `call_server`.
4. `--file` and microphone modes are not silently resampled in C3; the server
   remains the authoritative validator for externally supplied audio.
5. Reuse the existing project resampler. Do not duplicate DSP logic or add a
   dependency.

## Non-goals

- No server API, robot client, VAD, TTS provider, streaming, model, or audio
  contract change.
- No automatic repair of an arbitrary external `--file` WAV.
- No hardware or real-model acceptance claim from unit tests alone.

## TDD slices

### 1. RED — local postcondition

Create focused script tests proving:

- a mocked Piper WAV at 22 050 Hz is passed through the shared conversion and
  the final bytes satisfy `validate_wav_contract` at 16 kHz, mono, int16;
- a mocked valid 16 kHz output is accepted unchanged by the conversion seam;
- if final validation fails, `synthesize_locally` raises locally and no HTTP
  request is needed to expose the issue.

Run the tests before production change. The first two must fail because the
current function returns Piper-native bytes unchanged.

### 2. GREEN — reuse canonical converter and validator

In `scripts/client_test.py::synthesize_locally`:

1. synthesize Piper output into a temporary WAV buffer;
2. normalize with `server.tts._resample_to_contract`;
3. validate using `server.audio_contract.validate_wav_contract`;
4. log the resulting contract-compliant byte size and return it.

Do not alter any other input mode.

### 3. Regression and operator evidence

Run the script tests plus audio-contract tests. In combined P0 acceptance, run
`just test-client --text "Hola Iroko" --no-play` against the disposable server
and record that it reaches `/transcribe` without the historical `422 ... got
22050 Hz` error.

## Verification

```powershell
uv run pytest -n0 tests/unit/test_client_test_audio.py tests/unit/test_audio_contract.py -v
just lint
just typecheck
just test
just audit
just check
git diff --check
```

## Rollback

The change is confined to a diagnostic script, creates no data and changes no
public API. Revert the C3 commit if the script cannot load the existing local
converter in supported invocation modes.

## Execution evidence

Observed on 2026-08-14 before merge or operator-acceptance claims:

- **RED:** mocked 22,050 Hz Piper output was returned unchanged and the final
  local-validator test did not raise.
- **GREEN:** `3` C3 script tests plus `10` audio-contract tests passed; the
  full repository suite later passed `589` tests.
- **Static gates:** final `just lint`, `just typecheck`, `just audit`, and
  `just check` passed. `git diff --check` passed.

Still required: execute `just test-client --text "Hola Iroko" --no-play`
against the disposable acceptance server and record the real HTTP result.
