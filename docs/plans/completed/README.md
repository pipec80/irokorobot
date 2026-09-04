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

Do not modify a completed plan to create a new decision. Record architecture
changes in a new ADR and create a new open plan.
