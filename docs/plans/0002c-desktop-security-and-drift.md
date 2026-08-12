# P0-S2 desktop security and drift implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans`
> task-by-task. Steps use checkbox syntax for tracking.

**Status:** Draft — revalidate after P0-S1 merges.

**Goal:** Make desktop development least-exposed by default and reconcile
configuration, scripts, demonstrations, and current-state documentation with
the runtime delivered by P0.2 and Plan 0002a.

**Architecture:** This is configuration and documentation hardening, not an
authorization system or character rewrite. Python settings are the technical
source of defaults; `.env.example` communicates recommended overrides. Scripts
must not promise identity or memory behavior removed by P0.2.

**Tech stack:** Python 3.12, Pydantic Settings, PowerShell, pytest, Markdown.

## Global constraints

- Revalidate `main` after P0-S1 before promotion to `Ready`.
- Do not add authentication, household authorization, enrollment, dependency,
  cloud, schema, audio, robot, or controller work.
- `SERVER_HOST=0.0.0.0` remains a documented explicit LAN deployment option.
- Do not choose a face-match threshold without current calibration evidence.
- Preserve Iroko's fiction; correct only operational owner/permanent-memory
  claims that conflict with implemented policy.

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
| `scripts/services.ps1` | Align required models with active local configuration without downloads. |
| `scripts/memory_test.py` | Stop promising unknown-speaker persistent recall. |
| `scripts/faces_demo.py` | Stop promising public enrollment or public face identity response. |
| `server/src/server/characters/iroko.py` | Neutralize conflicting operational language only. |
| `server/src/server/characters/__init__.py` | Neutralize the active-memory owner heading only. |
| `docs/architecture/*.md`, `docs/roadmap/cognitive-roadmap.md`, `docs/plans/*` | Record verified state and plan progression. |

## Planned tasks when Ready

### Task 1: Bind loopback by default with explicit LAN override

- [ ] Add a failing `ServerSettings(_env_file=None)` assertion for
  `server_host == "127.0.0.1"` and an environment override assertion for
  `SERVER_HOST=0.0.0.0`.
- [ ] Run `uv run pytest tests/unit/test_settings.py -v` and observe the current
  all-interface default fail.
- [ ] Change only `Settings.server_host` and `.env.example`; retain `main.py`
  consumption of `settings.server_host`.
- [ ] Run focused settings tests. Do not claim a LAN runtime test unless one is
  actually run.

### Task 2: Remove obsolete scope and synchronize service guidance

- [ ] Add a text/configuration regression assertion that `.env.example` has no
  `VOICE_CONVERSATION_ID` and service guidance names active local models.
- [ ] Run it RED before updating examples/scripts.
- [ ] Remove the obsolete variable and explain request-local scopes. Use a
  PowerShell parser only if it reads `.env` without a new dependency; stop if
  importing the Python application or duplicating parser semantics is required.
- [ ] Run the focused assertion GREEN. Run `just services` only when its normal
  local start behavior is acceptable in the workstation.

### Task 3: Align demos, language, and implementation snapshot

- [ ] Add focused assertions for each changed claim: unknown speakers do not
  get persistent recall and public visual paths do not enroll faces.
- [ ] Update only the conflicting script/prompt wording; do not rewrite persona
  fiction or package names.
- [ ] Replace `current-state.md` with a dated commit snapshot and preserve
  `COGNITIVE_AUDIT.md` as historical pre-0002a evidence with a supersession
  notice.
- [ ] Run targeted tests followed by `just lint`, `just typecheck`, `just test`,
  `just audit`, and `git diff --check`.

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
