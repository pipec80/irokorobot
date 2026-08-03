# 0003 — Require Python 3.12+

- **Status:** Accepted
- **Date:** 2026-08-03

## Context
The codebase uses modern typing and syntax and targets a small, controlled set
of machines (dev PC, homelab, Raspberry Pi 5), so a recent Python is feasible.

## Decision
Require `>=3.12` across the workspace (`requires-python`), pin `3.12` via
`.python-version`, and target `py312` in Ruff and mypy.

## Alternatives considered
- **3.11**: wider availability but misses 3.12 typing / `type` statement niceties.
- **3.13**: some binary wheels (the ML stack) lag; risk on the Pi and CI.

## Consequences
### Positive
- Modern typing (PEP 695 `type`, better generics) and consistent behavior everywhere.

### Negative
- Excludes environments stuck on ≤3.11; requires 3.12 wheels for all native deps
  (torch CPU, onnxruntime, faster-whisper, insightface).

## Review
Revisit when 3.13 has stable wheels for the full ML stack, or if a target
platform cannot provide 3.12.
