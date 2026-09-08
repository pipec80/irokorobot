# Completed plan archive

> **Status:** Historical execution evidence. Nothing in this directory is an
> active instruction or authorization.

These plans preserve decisions, tests, commits, migrations, and acceptance
evidence from completed or superseded slices. A few entries (0014, 0020,
0024, 0031) are umbrella/design documents that never had their own
executable code or gates — they moved here because every slice they
governed already closed elsewhere, not because they were themselves
executed. Current work must use the
[canonical architecture](../../architecture/README.md),
[current state](../../architecture/current-state.md),
[roadmap](../../roadmap/cognitive-roadmap.md), and
[open-plan index](../open/README.md).

[Plan 0043](0043-dependency-refresh.md) refreshed the workspace lock to the
latest stable resolution on 2026-09-02 and recorded the framework capabilities
measured against the installed packages. It is transversal rather than part of
any milestone.

[Plan 0032](0032-server-privacy-and-request-observability.md) is the first
executed child of the server-production capsule: it stopped fourteen log sites
from writing household content and introduced request correlation.

[Plan 0048](0048-fastapi-baseline-final-hardening.md) is a bounded follow-up
to a second independent audit of the server (2026-09-07), not a 0031 child:
it closed four small edges (semantic `max_length`, the streaming
one-terminal-event guarantee, the NDJSON 200 OpenAPI contract, `/health`
wording + injectable `create_app`) and left only Uvicorn concurrency
calibration open, as its own `perf(...)` plan.

[Plan 0046](0046-reproducible-longitudinal-memory-baseline.md) closed CM-0 on
2026-09-08: it delivered a longitudinal-memory **benchmark and a measured RED
baseline**, not longitudinal memory. It repaired the two stale eval entrypoints,
added an 8-module out-of-runtime observation instrument
(`scripts/eval_longitudinal_memory.py` + `longitudinal_eval_*`), the synthetic
9-scenario suite `tests/evals/golden_longitudinal_memory.yaml`, and
`just eval-longitudinal`. `just gate` is GREEN; `just eval-longitudinal --runs 3`
recorded [`docs/evals/0046-longitudinal-memory-baseline.md`](../../evals/0046-longitudinal-memory-baseline.md)
at `ac43c58` with exit `1` — extraction (the only live seam) scored p/r `0.25`
(`FAIL`, no CM-0 gate), every other operation is honestly `unsupported`, all four
frozen gates `FAIL`, and the production DB hash was unchanged. The plan's file
map, smoke scenario id, and one scoring-denominator leak were adjusted during
execution (rulings recorded in the plan's closure banner). No runtime memory,
authorization, prompt, model, or API change.

Do not modify a completed plan to create a new decision. Record architecture
changes in a new ADR and create a new open plan.
