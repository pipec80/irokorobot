# P0-S hardening audit

**Observed:** 2026-08-12

**Baseline:** `e944b4d` on `main` before P0-S2 execution.

**Scope:** targeted read-only audit before P0-S implementation planning.

## Disposition

| Finding | Status | Evidence | Next plan |
|---|---|---|---|
| Direct cloud LLM runtime | Resolved | `Settings.llm_provider` accepts only `ollama`; no direct Anthropic runtime references remain. | None; cloud gateway remains P2. |
| HTTP biometric enrollment | Resolved | `/vision/enroll` returns a fixed 503 before reading an upload or calling `enroll_person()`. | 0002b completed; P0.5 owns the replacement policy. |
| Conversational biometric enrollment | Resolved | `/vision/respond` routes enrollment phrases to fixed guidance without calling `enroll_from_frame()` or scene perception. | 0002b completed; P0.5 owns the replacement policy. |
| Default all-interface bind | Resolved | `Settings.server_host` and `.env.example` default to loopback; a user must explicitly select LAN in untracked `.env`. | 0002c completed |
| Obsolete voice scope example | Resolved | `.env.example` removes `VOICE_CONVERSATION_ID` and describes request-local interaction scopes. | 0002c completed |
| Service/demo/current-state drift | Resolved | Services read configured local models; public demos and canonical current state match P0.2/P0-S behavior. | 0002c completed |
| Face threshold mismatch | Confirmed, deferred | Default and example differ; no calibration evidence was run. | 0002c stop condition |
| Owner/permanent-memory wording | Resolved | Active memory and Iroko operational wording are household-oriented and retention-aware. | 0002c completed |

## Security conclusion

`VISION_ENABLED` is an availability kill switch, not authentication or consent.
P0-S1 now quarantines both reachable public enrollment paths before any
biometric write: direct HTTP returns a fixed 503 and conversational phrases
continue through the normal spoken-response envelope with fixed guidance.
The change neither deletes nor alters existing face profiles, entities, facts,
or migrations. P0.5 remains responsible for a future local administration,
consent, and authorization policy.

P0-S2 completed its bounded configuration and documentation hardening without
changing the numeric face-match threshold, data schema, public audio contract,
or biometric lifecycle. The loopback default reduces desktop exposure; it is
not a substitute for P0.5 authorization. P0.3 remains Draft pending its own
revalidation.

## Verification limits

The P0-S2 branch passed `just lint`, `just typecheck`, `just test` (500 tests),
and `just audit`; `just services` verified the locally configured models. It
did not enroll a real person, use a camera, measure face-match calibration, or
bind a live server to a LAN interface. Those outcomes are not inferred from
test doubles.
