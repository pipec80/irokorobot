# P0-S2 desktop security and drift implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans`
> task-by-task. Steps use checkbox syntax for tracking.

**Status:** Complete

**Revalidated:** 2026-08-12 at `e944b4d` (`main`, P0-S1 merged).

**Goal:** Make desktop development least-exposed by default and reconcile
configuration, scripts, demonstrations, and current-state documentation with
the runtime delivered by P0.2 and Plan 0002a.

**Architecture:** This is configuration and documentation hardening, not an
authorization system or character rewrite. Python settings are the technical
source of defaults; `.env.example` communicates a loopback desktop default and
explicit LAN opt-in. `services.ps1` reads only the model-related entries from
`.env` (or `.env.example` when absent) without importing the application.
Scripts must not promise identity, enrollment, or memory behavior removed by
P0.2/P0-S1.

**Tech stack:** Python 3.12, Pydantic Settings, PowerShell, pytest, Markdown.

## Global constraints

- Revalidate `main` after P0-S1 before promotion to `Ready`.
- Do not add authentication, household authorization, enrollment, dependency,
  cloud, schema, audio, robot, or controller work.
- `SERVER_HOST=0.0.0.0` remains a documented explicit LAN deployment option.
- Do not choose a face-match threshold without current calibration evidence.
- Preserve Iroko's fiction; correct only operational owner/permanent-memory
  claims that conflict with implemented policy.

## Revalidated findings

- `Settings.server_host` and `.env.example` both default to `0.0.0.0`; `main.py`
  passes that setting directly to Uvicorn.
- `.env.example` still contains `VOICE_CONVERSATION_ID=voice-primary`, while
  current public turns use fresh interaction scopes.
- `scripts/services.ps1` hard-codes `nomic-embed-text` and `qwen2.5:3b`, while
  the checked-in example and active local configuration can select a distinct
  consolidation model.
- `memory_test.py` documents `--introduce`/`--recall` as persistent-memory
  proof, and `faces_demo.py` documents public enrollment and recognition; both
  claims contradict P0.2/P0-S1 public behavior.
- The technical face threshold remains `0.4`; the sample override remains
  `0.65`. No reproducible calibration was run, so this plan does not alter
  either value.

## Required reading when promoted

1. `AGENTS.md` and `docs/architecture/README.md`.
2. `docs/plans/p0-s-hardening-design.md` and completed Plan 0002b.
3. `server/src/server/settings.py`, `main.py`, `.env.example`, and
   `scripts/services.ps1`.
4. `scripts/memory_test.py`, `scripts/faces_demo.py`, and related tests.
5. `docs/architecture/current-state.md`, `p0-s-hardening-audit.md`, roadmap,
   and portfolio.

## Expected file scope

| File | Purpose |
|---|---|
| `server/src/server/settings.py` | Change only the desktop bind default after a RED settings test. |
| `.env.example` | Align example defaults and remove obsolete voice scope. |
| `tests/unit/test_settings.py` | Assert loopback default and explicit environment override. |
| `tests/unit/test_desktop_hardening.py` | Protect configuration, script, and prompt claims against drift. |
| `scripts/services.ps1` | Read model requirements from local configuration without downloads. |
| `scripts/memory_test.py` | Stop promising unknown-speaker persistent recall. |
| `scripts/faces_demo.py` | Stop promising public enrollment or public face identity response. |
| `justfile` | Align task descriptions with the corrected diagnostic scripts. |
| `server/src/server/characters/iroko.py` | Neutralize conflicting operational language only. |
| `server/src/server/characters/__init__.py` | Neutralize the active-memory owner heading only. |
| `docs/architecture/current-state.md` | Record the completed hardening state at its merge commit. |
| `docs/architecture/p0-s-hardening-audit.md` | Record disposition and threshold deferral. |
| `docs/roadmap/cognitive-roadmap.md` | Mark P0-S complete and keep P0.3 Draft pending revalidation. |
| `docs/plans/README.md`, `docs/plans/p0-cognitive-plan-portfolio-design.md`, this plan | Record plan progression and observed evidence. |

## Planned tasks when Ready

### Task 1: Bind loopback by default with explicit LAN override

**Files:** `tests/unit/test_settings.py`, `server/src/server/settings.py`,
`.env.example`.

- [x] **Step 1: Add the failing settings contract.**

```python
def test_server_settings_default_binds_loopback() -> None:
    settings = ServerSettings(_env_file=None)
    assert settings.server_host == "127.0.0.1"


def test_server_settings_accepts_explicit_lan_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    settings = ServerSettings(_env_file=None)
    assert settings.server_host == "0.0.0.0"
```

- [x] **Step 2: Observe RED.** Run
  `uv run pytest tests/unit/test_settings.py -v`; the default assertion must
  fail because it is currently `0.0.0.0`.
- [x] **Step 3: Implement the smallest configuration change.** Set the Python
  and sample-environment defaults to `127.0.0.1`; document that setting
  `SERVER_HOST=0.0.0.0` is the explicit LAN option. Do not modify `main.py`.
- [x] **Step 4: Observe GREEN.** Re-run the focused settings test. This proves
  configuration construction only; it does not prove a real LAN bind.

### Task 2: Remove obsolete scope and synchronize service guidance

**Files:** `tests/unit/test_desktop_hardening.py`, `.env.example`,
`scripts/services.ps1`.

- [x] **Step 1: Add failing artifact assertions.** The test must assert that
  `.env.example` selects loopback, contains no `VOICE_CONVERSATION_ID`, and
  documents explicit LAN opt-in. It must also assert that `services.ps1` loads
  `.env` or `.env.example` and refers to `OLLAMA_MODEL`, `EMBEDDING_MODEL`, and
  `CONSOLIDATION_MODEL`, rather than defining a hard-coded model list.
- [x] **Step 2: Observe RED.** Run
  `uv run pytest tests/unit/test_desktop_hardening.py -v`; assertions must fail
  against the stale example/script.
- [x] **Step 3: Implement the smallest drift correction.** Remove the stale
  voice scope and explain request-local isolation. In PowerShell, parse only
  simple `KEY=VALUE` entries for the named model settings; select `.env` first
  and `.env.example` as a read-only fallback. Include `VLM_MODEL` only when
  `VISION_ENABLED=true`. The script must only report missing models, never
  download one.
- [x] **Step 4: Observe GREEN and run the normal service check.** Re-run the
  focused test and `just services`. Record the actual result; do not assert a
  model is installed unless the command reports it.

### Task 3: Align demos, language, and implementation snapshot

**Files:** `tests/unit/test_desktop_hardening.py`, `scripts/memory_test.py`,
`scripts/faces_demo.py`, `justfile`, `server/src/server/characters/iroko.py`,
`server/src/server/characters/__init__.py`, and the documentation paths listed
above.

- [x] **Step 1: Extend the artifact test with failing claim assertions.** It
  must reject `--introduce`, `--recall`, direct `/vision/enroll`, `--enroll`,
  and `--who` claims in the two scripts. It must require clear wording that
  public unknown turns do not prove persistent recall, that visual demo is
  scene-only, that memory is authorized rather than owner-only, and that Iroko
  does not promise permanent retention.
- [x] **Step 2: Observe RED.** Re-run the focused artifact test; it must fail
  only because the listed stale strings still exist.
- [x] **Step 3: Make the minimal behavior-preserving wording changes.** Retire
  the scripted public-memory recall and public enrolment/recognition CLI paths;
  preserve microphone, frame capture, scene description, audio contracts, and
  local DB inspection. Change only operational owner/permanence language in
  Iroko and the memory heading. Do not alter `nova.py`, stored data, models, or
  API contracts.
- [x] **Step 4: Update the canonical snapshot.** Mark P0-S2 complete only after
  verification, record the tested commit and threshold deferral, and leave
  P0.3 Draft until its own revalidation.
- [x] **Step 5: Run final gates.** Execute `just lint`, `just typecheck`,
  `just test`, `just audit`, and `git diff --check`; then review file scope.

## Face-threshold stop condition

`Settings.face_match_threshold` and `.env.example` currently differ. Before
changing either value, record a reproducible calibration observation and decide
which value is the technical default versus recommended household override. If
that evidence is unavailable, document the difference and defer the numeric
change; do not choose a threshold by intuition.

## Acceptance criteria when completed

- New desktop settings bind loopback unless a user explicitly chooses LAN.
- No obsolete `VOICE_CONVERSATION_ID` configuration remains in active examples.
- Service/demo guidance matches P0.2, P0-S1, and Plan 0002a behavior.
- Current-state, roadmap, audit, and portfolio identify implemented versus
  planned capabilities at a named commit.
- No uncalibrated face-threshold behavior change is introduced.
- All declared tests and quality gates complete successfully.

## Completion evidence

- **RED:** the initial focused run reported 5 failures and 6 passes: loopback
  default, stale example scope, static model list, stale demo claims, and
  owner/permanent-memory wording. A subsequent service-check assertion also
  failed until the script used the same local `ollama list` capability it
  requires for model inspection.
- **GREEN:** `uv run pytest tests/unit/test_settings.py
  tests/unit/test_desktop_hardening.py -v` passed 11 tests. The two diagnostic
  CLIs expose only their supported public operations, and `just services`
  reported the configured local chat, embedding, consolidation, and VLM models
  available.
- **Final gates:** `just lint`, `just typecheck`, `just test` (500 passed), and
  `just audit` passed. `git diff --check` passed before commit.
- **Deferred:** the technical default `0.4` and sample override `0.65` for face
  matching remain unchanged because no reproducible calibration was performed.
  P0.3 remains Draft; this plan did not alter authorization, memory schema,
  audio/API contracts, or biometric lifecycle.
