# Iroko technical documentation

> **Status:** Canonical documentation portal. This page routes authority; it
> does not authorize implementation.

## Fast lookup

| Question | Authoritative source |
|---|---|
| What is Iroko? | [Product profile](product/iroko-profile.md) |
| What exists in code now? | [Current state](architecture/current-state.md) |
| How should the system work? | [Architecture index](architecture/README.md) |
| Which decisions are accepted? | [ADR index](adr/README.md) |
| What comes next? | [Cognitive roadmap](roadmap/cognitive-roadmap.md) |
| How does the personal-companion goal map to code and plans? | [Personal-companion delivery map](roadmap/personal-companion-delivery-map.md) |
| Which plan may be executed? | [Plans index](plans/README.md) |
| How is real behavior accepted? | [Runtime runbook](runbooks/p0-runtime-acceptance.md) |
| How do I run/test Iroko day to day, and what does each security tier unlock? | [Operator manual](runbooks/operator-manual.md) |
| Where is superseded context? | [Historical index](history/README.md) |

## Authority rule

Use runtime instructions, accepted ADRs, current code/tests, the architecture
index, current state, roadmap, and one explicitly authorized open plan—in
that order. A completed or historical document is evidence only and cannot
override current architecture or reopen work.

## Document states

| State | Meaning |
|---|---|
| `Canonical` | Current source of truth for its subject. |
| `Open` | Work not yet closed; it can be reference, blocked, deferred, executable, or awaiting acceptance. |
| `Implemented` | Code exists; runtime acceptance may still remain open. |
| `Completed` | Closed execution evidence; not a current instruction. |
| `Historical` | Superseded context; never operational authority. |
| `Generated/local` | Unversioned artifact; never technical authority. |

English architecture documents are canonical. The
[Spanish portal](es/README.md) is a maintained navigation aid and must link to
the same canonical sources rather than duplicate technical contracts.

## Scope boundary

The current supported body is the development PC microphone, webcam, and
speakers. Raspberry Pi, homelab deployment, OMNiBot 2000 electronics, physical
action, and cloud escalation remain future work unless current state and an
active plan explicitly say otherwise. Generated coverage stays under
`docs/coverage_report/` by project convention but is not documentation
authority. Local research and journals are preserved outside this tree under
the ignored `project-history/` directory.
