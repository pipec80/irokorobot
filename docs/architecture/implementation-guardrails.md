# Implementation guardrails for cognitive work

> **Status:** Canonical tracked handoff
>
> **Purpose:** Preserve the repository constraints a future agent needs even
> when local-only `AGENTS.md`, `CLAUDE.md`, `.claude/`, or
> `project-history/local-docs/` files are absent.

Runtime agent instructions supplied by the environment still apply. This
document records the project-specific rules that cognitive plans must not leave
implicit.

## Project and execution baseline

- Iroko modernizes an OMNiBot 2000 as a local-first household companion.
- The development workspace is Windows, Python 3.12, and a root `uv` workspace.
- The robot target is Raspberry Pi 5; heavier local AI processing may run on a
  homelab server. CPU operation and simple replaceable adapters are preferred.
- Use the root `justfile` for standard workflows. Relevant commands are
  `just lint`, `just typecheck`, `just test`, `just check`, and `just audit`.
- Tool configuration belongs in the root `pyproject.toml`, not duplicated in
  subprojects.

## Hard server/robot boundary

The server is a generic audio/cognitive API and must not know that a specific
robot exists. The robot is a generic audio client and must not know which STT,
LLM, TTS, memory, or vision provider the server uses. They share only explicit
API contracts.

Hardware, simulated devices, and future boards are adapters. Cognitive domain
models must not import drivers, camera SDKs, GPIO, ROS2, provider clients, HTTP
routers, or database connections.

## Existing audio and API compatibility

Audio crossing the established contract is:

```text
WAV, 16,000 Hz, mono, signed int16
```

The established endpoint is:

```text
POST /transcribe
multipart/form-data field: audio

200 response:
{ text_heard, llm_response, audio_base64, duration_ms, emotion }
```

Adding backward-compatible response fields may be planned. Removing or
renaming fields, changing audio format, or coupling the endpoint to one device
is a breaking change and requires explicit user approval plus a migration plan.

## Coding constraints for future plans

- Prefer small typed Python services and ordinary functions.
- Use strict type hints on every function signature and Google-style docstrings
  on public APIs.
- Use logging, not `print()`.
- No bare `except`; exceptions are specific and preserve causes.
- Avoid `Any`; every justified use needs a clear boundary explanation.
- Every `type: ignore` needs a local explanation.
- Never block asynchronous code with `time.sleep()`.
- Use `pathlib.Path`, not `os.path` in new code.
- Configuration comes from settings/environment, never hard-coded secrets,
  absolute machine paths, or model credentials.
- Use `httpx` for robot HTTP work and current `Annotated` FastAPI style.
- Do not add dependencies or environment variables unless the named plan
  explicitly requires them; update lock/config/example files when it does.
- Do not weaken lint, type, test, security, or coverage configuration to make a
  change pass.
- Follow KISS and YAGNI: no code for later roadmap phases.

## Cognitive constraints

- No giant orchestration framework, multi-agent runtime, autonomous loop, or
  plugin ecosystem.
- The LLM is one tool inside a small typed controller, not the owner of truth,
  memory policy, authorization, arithmetic, or physical safety.
- Identity and authorization are evaluated before private retrieval.
- Missing authentication leaves protected capabilities locked, not the whole
  companion: bounded public conversation remains available, while private
  memory, persistent mutation, and protected actions remain unavailable.
- Authentication grants only its named, expiring capability. It is never a
  master session for unrelated memory, home, computer, or physical actions.
- `unknown`, `ambiguous`, `contradictory`, and `unauthorized` are valid results.
- Local operation is the default; cloud use requires the explicit escalation
  policy and never becomes a hidden provider fallback.
- SQLite and `sqlite-vec` remain the persistence baseline unless measurements
  and an accepted ADR justify a change.
- Telemetry, current world state, events, and long-term memory remain separate.
- The brain proposes physical actions only through a later authorization and
  safety boundary; it never calls actuators directly.

## Task discipline

For a cognitive implementation, read:

1. this file;
2. [`README.md`](README.md), the canonical architecture index;
3. the single plan explicitly named by the user;
4. only the additional sources that plan lists.

Respect the plan's permitted files and non-goals. If current code contradicts a
contract, stop and report the exact evidence rather than silently changing the
architecture or scanning and refactoring unrelated areas.

No plan implicitly authorizes a commit, push, pull request, deployment,
dependency update, database mutation outside tests, cloud request, or hardware
action. These require the user's request or an explicit plan scope.

## Verification and completion

A plan defines its exact checks. At minimum, production changes normally need:

```powershell
just lint
just typecheck
just test
```

Tests should be offline and deterministic unless a separately marked hardware
or network acceptance test is explicitly requested. A task is complete only
when its deliverables and behavioral tests pass and no out-of-scope file was
changed. Do not commit directly to `main`; do not commit at all unless asked.
