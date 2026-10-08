# 0017 — Speak what the model means: a tolerant, bounded streaming reply protocol

- **Status:** Superseded by [ADR 0018](0018-user-emotion-decided-apart.md) (2026-10-08) — never Accepted; Plan 0058 did not meet its gate
- **Date:** 2026-10-07
- **Builds on:** [ADR 0004](0004-local-first-cognitive-policy.md),
  [ADR 0012](0012-line-delimited-stream-terminal-events.md)
- **Replaces:** the streaming reply rules that lived only in code and tests (the strict
  `EMOTION:` line and "plain text without the tag is a fallback"); no earlier ADR governed them
- **Implemented by:** [Plan 0058](../plans/open/0058-stream-protocol-repair.md)

## Context

`POST /transcribe/stream` asks the local model for plain text whose first line is
`EMOTION:<emotion>`, then speaks the reply sentence by sentence while the model is still
generating. When the reply does not match the expected shape, one fixed phrase is spoken
instead of the reply.

**What holds today (verified in code, 2026-10-07, `main` at `747bca6`).**

1. A reply is speakable only if it opens with `^EMOTION:\s*(\w+)\s*\n`
   (`streaming_protocol.py`). Everything else is discarded and the fallback phrase is spoken,
   **including plain text with no tag at all**. There is no retry.
2. A reply the grammar cannot place is only known to be wrong at the **end** of the stream: the
   buffer grows until the model stops. The median fallback is therefore not faster than a good
   reply (4.3 s against 4.2 s, p95 15.0 s against 8.5 s in Plan 0057's first run).
3. The start of the body is judged **once**, with the first non-blank fragment
   (`streaming_render._consume_body`). A second tag or a code fence split across two deltas
   (`E` + `MOTION:`) is spoken, and nothing is looked at again after the first sentence.
4. The contract text in the prompt is `llm_streaming._STREAMING_OUTPUT_CONTRACT`. The robot
   requires exactly **one `emotion` event before the first `audio` event**
   (`robot/stream_validation.py`) and never reads its value beyond a log line. The server uses
   the value only for the user-emotion window (`working.get_recent_emotion`), which ignores
   `neutral`.

**What was measured** ([Plan 0057](../plans/completed/0057-stream-protocol-diagnosis.md),
[record](../evals/0057-stream-protocol-diagnosis.md); `qwen2.5:3b`, 820 streams over two seeds,
the generator only, a non-dedicated laptop; exploratory, one model):

- The baseline falls back in **43 to 52 %** of turns that carry memory context and **1.7 to
  3.3 %** of context-free turns.
- The dominant failure shape is a tag that shares its line with the text (`tag_same_line`,
  85 to 97 % of the context fallbacks), then a reply with no tag (`no_tag`).
- Moving the contract to the start of the prompt made the tag disappear in 120 of 120 runs
  (one seed), so the prompt is not touched by this decision.
- A schema-constrained reply reached the client spread over time (5 of 5 probes), which is
  evidence against the claim in `llm_streaming.py`'s header that Ollama withholds it.

The owner's expectation of a companion is that it answers. A reply the model wrote well and the
parser refused on a technicality is a worse failure than a reply with a missing label.

## Decision

### 1. A reply may start in three ways

The start is read after ignoring leading whitespace and the letter case of `EMOTION:`.

| Start | Example (invented) | Result |
|---|---|---|
| Tag on its own line | `EMOTION:joy` + newline + `¡Hola!` | emotion `joy`; an unknown word means `neutral` |
| Tag and text on one line | `EMOTION:joy ¡Hola! ¿Qué tal?` | emotion `joy`, **only if the word is a known emotion** |
| No tag | `Hola. ¿Qué tal?` | the whole reply is the body, emotion `neutral` (a **rescued** reply) |

### 2. A tag that can never become valid is refused at once

Refused as soon as the text shows it: an unknown word on the same line (`EMOTION: Hola, ...`,
which would otherwise speak a mutilated sentence), a word glued to punctuation (`EMOTION:joy.`),
a wrapped or bracketed word (`EMOTION:<joy>`), a tag with no word. The fallback is then spoken
without waiting for the end of the stream.

### 3. An undecided prefix waits and never speaks

While the buffer is a proper prefix of `EMOTION:` (`E`, `EMO`, `EMOTION`) the start is
undecided. The same holds for the start of the body while it is a proper prefix of `EMOTION:` or
of a code fence (`E`, a lone backtick). Nothing is promoted or spoken meanwhile. At the end of
the stream an undecided **start** is a violation (fallback); an undecided **body** prefix is
ordinary text if nothing else is wrong with it.

### 4. The body may not start with structure or a second tag

A body (after any tag, or the whole rescued reply) that starts with `{`, `[`, a code fence or
`EMOTION:` is refused. JSON without a tag is not rescued: the classic JSON contract is a
different route.

### 5. A tag is never spoken

No sentence, and no unfinished tail, that mentions `EMOTION` followed by a colon is spoken, at any
position, in any letter case, with up to three symbols between the two (`**EMOTION**:`) and either
colon width; `demotion:` does not count. Whatever had already been spoken stays; the fallback phrase
follows (logged as `protocol_fallback`).

### 6. The fallback stays one fixed phrase, with no retry

Exactly one `emotion` event still precedes the first `audio` (`neutral` when none was promoted),
and `done` still only follows audio (ADR 0012). A rejected sentence promotes no emotion, so the
fallback can always send that one event.

### 7. A rescued reply is a normal turn

It is spoken, recorded in working and long-term memory like any turn with the emotion `neutral`,
and logged as outcome `rescued_no_tag`. The wire does not change: no new field, event or code, and
the robot is untouched.

## Alternatives considered

- **Keep the strict grammar and retry once.** Doubles the cost of the case that already costs
  about 4 s, and leaves the cause (a tag the parser would accept with one more rule) in place.
- **Remove the emotion from the model in streaming.** Ends the whole class of failures, but also
  ends the user-emotion window in streaming and still needs a `neutral` event; kept as a later
  option if rescued replies prove too common.
- **A schema-constrained stream.** Plan 0057 found Ollama delivers it incrementally, but the
  object must be parsed while it is incomplete and the classic path already shows how JSON
  replies fail. Not chosen; remains available.
- **Move the contract to the start of the prompt.** Measured to remove the tag in 120 of 120 runs
  (one seed). Rejected on that evidence.
- **Reword the contract or add an example.** Changes the prompt and the parser together, so the
  measurement could not attribute the effect; left for a later decision.
- **Tag the assistant turns of the stored history.** The history sent to the model holds untagged
  replies while the prompt demands a tag; a small model may imitate the history and omit the tag. The
  Plan 0057 data fit that only in part (turns with history fell back 43 to 52 %, context-free turns
  1.7 to 3.3 %, but removing only the memory block cut it to 17 %), so it is a hypothesis for a later
  measurement, not a decision here.
- **Another model.** Out of scope of this decision (ADR 0004 keeps Ollama the only runtime); the
  protocol must work for the model in use.

## Consequences

### Positive

- The dominant measured failure (a tag on the text's line) and the missing tag are spoken instead
  of replaced by a phrase that says the robot is still waking up.
- A reply that cannot be valid is refused as soon as that is known, not after the whole
  generation.
- The fragmentation defect closes: a forbidden prefix split across deltas gets the same verdict (speak
  or fall back) as the whole text, under every split. What had already been spoken before a rejection
  can still differ with the split.
- No wire, schema, robot, setting or dependency change.

### Negative

- A model that ignores the contract is now **spoken**, not hidden: a label that does not use the English
  keyword (`Emoción: joy`) is read aloud, and nothing marks the turn except the `rescued_no_tag` log
  line. A spoken label also enters the stored history of the next turns.
- JSON or a code fence in the **middle** of a reply (decision 4 is about how a body starts) is spoken.
- A late tag after untagged speech (`Claro. EMOTION:joy`...) speaks the first sentence and then the
  fallback phrase (`protocol_fallback`).
- Honest text that mentions `emotion:` falls back.
- Rescued turns carry emotion `neutral`, which the user-emotion window ignores, so adaptation sees
  nothing from them.
- Rule 4 of the previous behaviour ("plain text without the tag is a fallback") is reversed on
  purpose; it is gone from the code and its tests.

## Review

Revisit if, in real use, replies that carry no tag are common enough that the contract is
effectively ignored (the diagnosis counts them as *tolerated*), if a model change moves the
shapes, if a spoken label or markup is reported, or if a schema-constrained stream becomes the
cheaper way to carry the emotion.

Revisit too when the robot gets its face. The `emotion` event is the context for a future facial
expression (the eyes), so a rescued reply, which always carries `neutral`, would show no
expression. That is the moment to decide whether the emotion should stop depending on the model
writing a tag (classified apart, or carried by a schema).
