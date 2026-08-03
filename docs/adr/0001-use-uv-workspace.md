# 0001 — Use uv with a workspace

- **Status:** Accepted
- **Date:** 2026-08-03

## Context
The project has two Python components (`server`, `robot`) that share tooling and
concepts but ship to different hardware. It needs fast, reproducible dependency
management on Windows (dev) and Linux (Raspberry Pi, homelab, CI).

## Decision
Use [uv](https://docs.astral.sh/uv/) as the single dependency manager, with a
workspace whose members are `server/` and `robot/`. All shared tool config and
dependency groups live in the root `pyproject.toml`; `uv.lock` is committed.

## Alternatives considered
- **pip + venv**: no lockfile, slow, manual multi-package handling.
- **Poetry**: slower, weaker monorepo/workspace story, separate lock format.
- **PDM / Hatch**: viable, but uv is faster and unifies Python + tool installs.

## Consequences
### Positive
- One fast tool for Python, environments, dependencies, and the lockfile.
- Hashed, reproducible `uv.lock`; the workspace resolves both members together.
- Native dependency groups; `uvx` / `uv run` for tools.

### Negative
- Newer tool; some ecosystem gaps (Dependabot/deptry workspace quirks handled
  with per-member config).
- Contributors must install uv, not just pip.

## Review
Revisit if uv's workspace or build-backend support regresses, or if a component
must be published to PyPI with a different toolchain.
