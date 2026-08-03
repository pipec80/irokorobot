# Architecture Decision Records

This directory records significant architecture decisions for Iroko / OMNiBot 2000
using lightweight [ADRs](https://adr.github.io/).

An ADR is immutable once accepted. To change a decision, add a new ADR that
supersedes it and update the old one's status.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-use-uv-workspace.md) | Use uv with a workspace | Accepted |
| [0002](0002-server-robot-separation.md) | Separate server (brain) and robot (senses) | Accepted |
| [0003](0003-python-312-minimum.md) | Require Python 3.12+ | Accepted |

New ADRs start from [`0000-adr-template.md`](0000-adr-template.md).
