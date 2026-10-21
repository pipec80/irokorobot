# Historical documentation index

> **Status:** Preserved, non-authoritative context. These files must never be
> executed as current instructions.

## Audits

- [`COGNITIVE_AUDIT.md`](audits/COGNITIVE_AUDIT.md): repository snapshot from
  2026-08-11.
- [`cognitive-foundation-audit.md`](audits/cognitive-foundation-audit.md): old
  Plan 0001 readiness protocol.
- [`p0-s-hardening-audit.md`](audits/p0-s-hardening-audit.md): resolved P0-S
  disposition evidence.

The still-open runtime-policy disposition remains canonical in
[`architecture/p0-runtime-policy-audit.md`](../architecture/p0-runtime-policy-audit.md)
until its remaining active plans close.

## Earlier roadmaps and bootstrap notes

- [`roadmap-cerebro-agnostico-pre-electronica.md`](roadmaps/roadmap-cerebro-agnostico-pre-electronica.md)
  is superseded by the [cognitive roadmap](../roadmap/cognitive-roadmap.md).
- [`bootstrap/`](bootstrap/) preserves initial setup, tooling, and repository
  scaffolding notes. Use root `AGENTS.md`, `justfile`, `pyproject.toml`, and the
  current documentation portal instead.

## Evaluation runs kept for the record

- [`evals/2026-10-21-192351-chat-stream-ollama.md`](evals/2026-10-21-192351-chat-stream-ollama.md):
  the `just eval-chat --mode stream --runs 10` run (360 graded turns, 0 protocol fallbacks, 0 of 326
  replies outside Spanish) that kept Ollama busy while Plan 0069 timed the speech-to-text under load.
  It measures the language model's stream, not the speech-to-text, so it is not part of that plan's
  [record](../evals/0069-stt-owner-voice.md).

Unversioned research, electronics notes, bitácoras, evaluations, and assistant
runbooks are preserved outside `docs/` under ignored `project-history/`.
