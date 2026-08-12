# P0-S hardening audit

**Observed:** 2026-08-12

**Revision:** `a936cf8` on `main`

**Scope:** targeted read-only audit before P0-S implementation planning.

## Disposition

| Finding | Status | Evidence | Next plan |
|---|---|---|---|
| Direct cloud LLM runtime | Resolved | `Settings.llm_provider` accepts only `ollama`; no direct Anthropic runtime references remain. | None; cloud gateway remains P2. |
| HTTP biometric enrollment | Confirmed | `/vision/enroll` accepts image/name and calls enrollment without policy. | 0002b |
| Conversational biometric enrollment | Confirmed | `/vision/respond` routes enrollment phrases to `enroll_from_frame()`. | 0002b |
| Default all-interface bind | Confirmed | `Settings.server_host` and `.env.example` use `0.0.0.0`. | 0002c |
| Obsolete voice scope example | Confirmed | `.env.example` retains `VOICE_CONVERSATION_ID=voice-primary`; runtime creates interaction scopes. | 0002c |
| Service/demo/current-state drift | Confirmed | Scripts and `current-state.md` disagree with P0.2/0002a behavior. | 0002c |
| Face threshold mismatch | Confirmed, deferred | Default and example differ; no calibration evidence was run. | 0002c stop condition |
| Owner/permanent-memory wording | Confirmed | Prompt assembly retains conflicting operational language. | 0002c |

## Security conclusion

`VISION_ENABLED` is an availability kill switch, not authentication or consent.
When enabled, a reachable caller can submit a name and image through either
public enrollment path. P0-S1 quarantines both writes before P0.5; it preserves
existing data and does not build authorization early.

## Verification limits

This audit inspected code and tests. It did not enroll a real person, use a
camera, measure face-match calibration, or bind a live server to a LAN
interface. Those outcomes are not inferred from static evidence.
