# P0-S hardening audit

**Observed:** 2026-08-12

**Revision:** `a936cf8` on `main`

**Scope:** targeted read-only audit before P0-S implementation planning.

## Disposition

| Finding | Status | Evidence | Next plan |
|---|---|---|---|
| Direct cloud LLM runtime | Resolved | `Settings.llm_provider` accepts only `ollama`; no direct Anthropic runtime references remain. | None; cloud gateway remains P2. |
| HTTP biometric enrollment | Resolved | `/vision/enroll` returns a fixed 503 before reading an upload or calling `enroll_person()`. | 0002b completed; P0.5 owns the replacement policy. |
| Conversational biometric enrollment | Resolved | `/vision/respond` routes enrollment phrases to fixed guidance without calling `enroll_from_frame()` or scene perception. | 0002b completed; P0.5 owns the replacement policy. |
| Default all-interface bind | Confirmed | `Settings.server_host` and `.env.example` use `0.0.0.0`. | 0002c |
| Obsolete voice scope example | Confirmed | `.env.example` retains `VOICE_CONVERSATION_ID=voice-primary`; runtime creates interaction scopes. | 0002c |
| Service/demo/current-state drift | Confirmed | Scripts and `current-state.md` disagree with P0.2/0002a behavior. | 0002c |
| Face threshold mismatch | Confirmed, deferred | Default and example differ; no calibration evidence was run. | 0002c stop condition |
| Owner/permanent-memory wording | Confirmed | Prompt assembly retains conflicting operational language. | 0002c |

## Security conclusion

`VISION_ENABLED` is an availability kill switch, not authentication or consent.
P0-S1 now quarantines both reachable public enrollment paths before any
biometric write: direct HTTP returns a fixed 503 and conversational phrases
continue through the normal spoken-response envelope with fixed guidance.
The change neither deletes nor alters existing face profiles, entities, facts,
or migrations. P0.5 remains responsible for a future local administration,
consent, and authorization policy.

## Verification limits

The post-implementation suite verified 496 tests, including no-write tests for
both public paths and ordinary visual-scene dialogue. It did not enroll a real
person, use a camera, measure face-match calibration, or bind a live server to
a LAN interface. Those outcomes are not inferred from test doubles.
