# Iroko technical documentation

> Status: Documentation portal. It is not an implementation plan.

## Start here

Begin with the public [Iroko profile](product/iroko-profile.md), then use the [architecture index](architecture/README.md) and its [current state](architecture/current-state.md) to distinguish evidence from future intent. The reproducible audio setup guide is delivered by Slice 2.

## Choose your route

| Reader | Start with | Then use |
| --- | --- | --- |
| Visitor | [Iroko profile](product/iroko-profile.md) | [Root welcome](../README.md) |
| New developer | [Root welcome](../README.md) | [Architecture index](architecture/README.md) and [current state](architecture/current-state.md) |
| Contributor | [Current state](architecture/current-state.md) | [Cognitive roadmap](roadmap/cognitive-roadmap.md) and [plans index](plans/README.md) |
| Codex/architect | [Architecture index](architecture/README.md) | [Current state](architecture/current-state.md), [roadmap](roadmap/cognitive-roadmap.md), and [plans](plans/README.md) |
| Maintainer/releaser | [AGENTS.md](../AGENTS.md) | [justfile](../justfile), [current state](architecture/current-state.md), and [plans index](plans/README.md) |

## What is implemented today

**Implemented:** the [current state](architecture/current-state.md) is the evidence-backed record of behavior available in the current repository. Do not infer additional runtime, provider, or hardware support from this portal.

## Canonical authority

English is the canonical technical source. The [architecture index](architecture/README.md), [current state](architecture/current-state.md), [cognitive roadmap](roadmap/cognitive-roadmap.md), and [plans index](plans/README.md) govern current technical direction; the Spanish portal is its maintained equivalent.

## Documentation provenance

The [pre-electronics roadmap](architecture/roadmap-cerebro-agnostico-pre-electronica.md) and [cognitive foundation audit](architecture/cognitive-foundation-audit.md) are historical context, not executable plans. M3/M4 are historical context; M4 is implemented with historical closure not demonstrated. New work follows the canonical architecture index, current state, cognitive roadmap, and the active [P0 runtime-policy hardening design](plans/0014-p0-runtime-policy-hardening-design.md). The personal-companion design is intentionally proposed until P0-C acceptance passes.

## Documentation status labels

- **Implemented** means behavior verified in code, a test, or the [current state](architecture/current-state.md).
- **Planned** means future intent linked to the [roadmap](roadmap/cognitive-roadmap.md) or a [plan](plans/README.md).
- **Historical** means preserved context, not current operational guidance.

## Current scope boundary

This portal documents a PC development experience. Raspberry Pi, homelab, OMNiBot 2000, electronics, physical action, and deployment procedures remain future vision rather than supported operating procedures. Autonomous action and operational cloud escalation are not implemented.
