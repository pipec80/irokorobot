# 0074 — Acceptance of the profile card on real hardware (CM-5a)

> **Status:** run by Pipec on 2026-10-28 on the development laptop (Windows, `qwen2.5:3b` through
> Ollama on the CPU, Whisper `medium` on the GPU), streaming mode. Outcomes only: no preferred name,
> taste, person or stored value is written in this file (the rule of
> [`implementation-guardrails.md`](../architecture/implementation-guardrails.md)). Procedure and
> meaning of each setting: [operator manual, «The profile card»](../runbooks/operator-manual.md).

## Conditions

| Item | Value |
|---|---|
| Date | 2026-10-28 |
| Commit under test | `e16ef67` (the branch `feat/0074-cm5a-profile-card`; cases 1 to 3 ran at `11f7a2a`, the `sabe` and `tu`-line fixes came in between) |
| Database | the owner's own, loaded by the import plus `just admin add likes` (a preferred name, a form of address and several tastes) |
| Switches | `MEMORY_ENABLED`, `FACE_AUTHENTICATION_ENABLED`, `SPEAKER_AUTHENTICATION_ENABLED`, `MEMORY_CANDIDATES_ENABLED` on; `PROFILE_CARD_ENABLED` on except case 5 |
| Mode | streaming `/transcribe/stream` (`ROBOT_STREAMING=true`) |
| Second face | a photograph on a tablet in front of the camera (there was nobody else to speak) |

## Cases

| # | Case | Outcome |
|---|---|---|
| 1 | Owner's face: «¿qué sabes de mí?» | **Pass.** The fixed template listed the name, the form of address and the tastes; `need=profile_summary`, no model call; the server's spoken-text log showed only the marker «resumen del perfil» (the robot's own opt-in console printed the text, which is the wire's). Also passed with face and voice verified |
| 2 | Owner's face, ordinary turn | **Pass after one fix.** The first run opened two of three replies with «Tú, bien.» (the model read the line «Trato: tú.» as conversation); with that line removed (`e16ef67`) 6 of 6 replies were coherent and used the name. The model sometimes mentions a taste unasked in the first turns |
| 3 | A second face in frame | **Pass for the question, twice.** `Identity fusion: veto_multiple_faces`, `status=ambiguous`, the fixed unknown phrase, no audit row. The ordinary turn with two faces was not run live (covered by the automated matrix test) |
| 4 | Camera covered (unknown speaker) | **Pass.** `no_evidence`, no card, no audit row. The first run exposed that Whisper wrote «sabe» for «sabes» and the question fell to the model; fixed in `13e89aa`, and the repeat gave the fixed phrase |
| 5 | `PROFILE_CARD_ENABLED=false` | **Pass.** The question was an ordinary turn (`no-plan-channel-generates`), the model answered generically, the audit count did not move |
| 6 | Latency of the card | Median time to first audio **3.73 s without** the card (6 turns) and **3.92 s with** it (5 turns): about **+0.2 s**. Small samples, noisy; the model's `llm=` rose more (1.46 s to 2.07 s) because it spoke longer, which mixes two effects |
| 7 | `address_form=usted` | **Partial.** The summary said «Te trato de usted.» (pass). The ordinary replies were incoherent («Tú también, como esté haciendo?» and an unrelated sentence) in 2 of 2 turns; back on `tu` the replies were coherent again. Likely cause: the card says «Trato: usted.» while the language rule of the same prompt demands tuteo, and the 3B model cannot hold both. Decision (Pipec, option A): a documented limit; do not use `usted` with this model until the language rule follows the form |
| 8 | `PROFILE_CARD_POSITION` | **`with_memory` kept.** With it 0 of 6 replies opened with «Tú, …» and all used the name; with `before_language` 5 of 5 opened with «Tú, muy bien.», none used the name and each added a meaningless third sentence. First audio median about 3.9 s against 4.3 s (4 turns, not reliable) |

## Also observed

- The audit grew by exactly one row per identified turn read (4 rows after cases 1 to 3, 20 after case 7),
  never for an unknown, ambiguous or covered-camera speaker, and not with the switch off.
- A clip of 0.8 s with `no_speech=0.62` was transcribed as the Whisper hotwords plus the initial prompt
  («echo» of the bias); `is_prompt_echo` does not catch an echo that carries the hotwords in front. Outside
  this plan (see the roadmap, cross-cutting table).
- «¿Qué ves en la foto?» on the streaming route answers «no puedo mirar desde este canal»: the known
  limitation F-08, unrelated.

## Result

| Item | Outcome |
|---|---|
| Cases | 1 to 6 and 8 pass; 7 partial (limit accepted) |
| Measured extra latency | about +0.2 s to the first audio |
| `PROFILE_CARD_POSITION` kept | `with_memory` (the default) |
| Fixes the run produced | `13e89aa` (the `sabe` form of the question), `e16ef67` (the prompt never says the `tu` form) |
