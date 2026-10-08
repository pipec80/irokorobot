# 0018 — Decide the user's emotion apart from the streamed reply

- **Status:** Proposed (2026-10-08) — becomes Accepted when the measurement of
  [Plan 0059](../plans/open/0059-user-emotion-apart.md) meets its gate (Task 6); until then
  nothing in `server/src` follows it
- **Date:** 2026-10-08
- **Builds on:** [ADR 0004](0004-local-first-cognitive-policy.md),
  [ADR 0012](0012-line-delimited-stream-terminal-events.md)
- **Replaces:** [ADR 0017](0017-streaming-reply-protocol.md), which was never Accepted
- **Implemented by:** [Plan 0059](../plans/open/0059-user-emotion-apart.md)

## Context

`POST /transcribe/stream` asks the local model for plain text whose first line is
`EMOTION:<emotion>`, then speaks the reply sentence by sentence while the model is still
generating. When the reply does not match the expected shape, one fixed phrase is spoken
instead of the reply.

**Why ADR 0017 is replaced.** ADR 0017 kept the tag and made the parser tolerant: a tag sharing
its line with the text, a reply with no tag (rescued as `neutral`), and an undecided start that
waits. [Plan 0058](../plans/open/0058-stream-protocol-repair.md) implemented that and measured it
(`docs/evals/0058-stream-protocol-repair.md`, in the evidence PR; `qwen2.5:3b`, the generator
only, a non-dedicated laptop). In seed 57 the fallback rate of turns with memory context was
**35.00 %** (21 of 60) after the tolerant grammar, against 51.67 % before it, with a gate of 5 %.
Twenty of the 21 remaining fallbacks came from a tag that shares its line with a word that is not a
known emotion. In public turns, which carry no memory context, the rate was 0.00 %. The tolerant
grammar halved the problem but did not close it, and each further rule would only chase the next
shape a 3B model invents. ADR 0017 never became Accepted; this ADR supersedes it.

**What the tag is for.** The `emotion` field of the stream is the label of the turn. The server
uses it for the user-emotion window of the tone adaptation (`working.get_recent_emotion`), which
ignores `neutral`; the robot requires exactly one `emotion` event before the first `audio` event
(`robot/stream_validation.py`) and never reads the value beyond a log line. The classic prompt
already defines it as the **user's** state: "La emoción describe el estado del USUARIO". So the
streaming path asks a small model to produce, inside the reply, a label that is about the user and
not about the reply, and a failure of that label costs the whole reply.

**Hardware reality.** The development machine is a non-dedicated laptop that runs a 3B model
(measured `llm_ms` far above the homelab estimate). A second model call per turn would load the
same small model again, and Ollama may serialise concurrent calls on that machine, so the second
call would add its latency to the first speech instead of running beside it.

The owner's expectation of a companion is that it answers. A reply the model wrote well and the
protocol refused because of a label is a worse failure than a reply with a neutral label.

## Decision

### 1. The model answers in plain text

The streaming contract in the prompt (`llm_streaming._STREAMING_OUTPUT_CONTRACT`) asks for plain
text only: no JSON, no tags. It no longer mentions `EMOTION:`. The tag grammar, the tolerant start
and the rescue of ADR 0017 are not implemented.

### 2. The emotion of a turn is the user's, decided by a pure function

The `emotion` of a turn is the **user's** emotion, as the classic prompt already defines it. It is
decided from the text the user said by one pure, deterministic function
(`user_emotion.classify_user_emotion(text) -> str`) with no I/O and no logging. It returns a
member of `VALID_EMOTIONS` and defaults to `neutral`. It is **precision-first**: it fires only on
an explicit statement of a feeling; negation, quotation, questions about feelings, sarcasm and
social nuance stay `neutral`. A wrong `neutral` costs nothing the system uses today; a wrong
non-neutral label would bend the tone adaptation.

The function sits behind one signature so that a model-based classifier can replace it, with the
same inputs and outputs, when a larger model exists. **No second LLM call is made** and no setting
is added.

### 3. The wire does not change

The field and the event keep the name `emotion`. Exactly one `emotion` event precedes the first
`audio` event (ADR 0012); `done` still follows audio only. The emotion is fixed at the start of
the turn and sent with the first content of the reply that passes the start guards, and only if
every sentence closed in that same step passes the tag guard. If a later sentence is rejected,
the fallback phrase therefore follows an `emotion` event that already carries the user's emotion;
if the first content itself is rejected, nothing was promoted and the fallback sends `neutral`.
The *value* of the single event on a fallback can thus depend on how the text was split into
deltas; its *count and position* never do, and the fallback can always send it. The robot, the
schemas, the settings and the dependencies are untouched.

### 4. A tag the model writes anyway is never spoken

A model may still write a tag by habit or imitation of its history. Two rules cover it:

- **At any position:** no spoken sentence, and no unfinished tail, that mentions `EMOTION`
  followed by a colon is spoken, in any letter case, with up to three symbols between the word and
  the colon (`**EMOTION**:`, `_EMOTION_:`), after Unicode NFKC normalisation and dropping
  invisible format characters (so a fullwidth colon or fullwidth letters do not hide it);
  `demotion:`, `1EMOTION:` and `emotion_name:` do not count. **Known limits**, which need output
  no model is asked for: more than three symbols between the word and the colon, and a sentence
  terminator between them (`EMOTION.:`; the sentence splitter cuts there first) are not caught.
  Sentences already spoken before a rejection stay spoken.
- **At the start:** a reply that **starts** with a tag, with JSON (`{` or `[`) or with a code
  fence is refused: the fixed fallback phrase is spoken, with no retry. This is conservative on
  purpose; the share of such replies is measured, and a later plan may rescue them if it matters.

While the beginning of the body is still a proper prefix of `EMOTION:` or of a code fence (`E`, a
lone backtick), the start is undecided: nothing is promoted or spoken, and at the end of the
stream an undecided prefix is ordinary text if nothing else is wrong with it. The verdict is the
same under every split of the text into deltas.

### 5. The robot's expression is out of scope

The facial **expression** of the robot is a different signal: a transient, contextual reaction
chosen for the future face, which need not equal the user's feeling (a robot may look amused at a
sad story told lightly) and must not become a persistent mood of the robot. It is explicitly not
decided here. The name `expression` is **reserved** for it. It will be decided when the robot gets
its face, probably with a larger model and its own event, without reusing the `emotion` field.

### What is carried over from ADR 0017

Only what still holds: a forbidden prefix split across deltas gets the same verdict as the whole
text; a tag is never spoken; the fallback is one fixed phrase with no retry; exactly one `emotion`
event precedes the first `audio`; a rejected sentence promotes no emotion. Its decisions 1 to 3
(the tolerant tag grammar, the undecided start of the reply, and the rescue of a reply with no
tag) and its decision 7 (a rescued reply as a normal turn) are **abandoned**: they exist only to
tolerate a tag that this ADR stops requesting, and the measurement above showed they do not
suffice anyway.

## Alternatives considered

- **Tolerate more shapes of the tag.** The route ADR 0017 took. Measured to cut the context
  fallback from 51.67 % to 35.00 %, still seven times over the gate, with the residue made of
  one open-ended shape (a tag followed by a word on the same line). Rejected: it chases the model.
- **Strip only the `EMOTION:` word and speak the rest.** Cheap, but when the word after the tag
  is not an emotion the sentence is mutilated or the label is read as speech; the stored history
  would then carry the damage into the next turns. Rejected.
- **Retry once on a rejected reply.** Doubles the cost of the case that already costs seconds on
  this hardware and leaves the cause in place. Rejected.
- **A second small LLM call in parallel to classify the user's text.** Rejected: it loads the
  same small model, and Ollama may serialise the two calls on the laptop, delaying the first
  speech. Remains the natural implementation of the pluggable function when a larger model or a
  dedicated server exists.
- **Tag the stored history.** The history sent to the model holds untagged replies while the old
  prompt demanded a tag; a small model may imitate the history. Plan 0057 fit that only in part.
  With no tag requested the question disappears, so it is not needed.
- **A schema-constrained stream.** Plan 0057 found Ollama delivers it incrementally, but the
  object must be parsed while incomplete and the classic path already shows how JSON replies
  fail. Not chosen; remains available.
- **Remove the emotion entirely.** Ends the failure class, but also ends the user-emotion window
  of the tone adaptation and still needs a `neutral` event on the wire for the robot. Rejected:
  the classifier keeps both at no model cost.

## Consequences

### Positive

- The dominant measured failure ends at its cause: the model is not asked to write a tag, so a
  tag in the wrong place cannot cost a reply.
- The prompt is shorter and simpler for a 3B model, and the parser is smaller than ADR 0017's.
- The `emotion` value no longer depends on the model's compliance; it is deterministic and
  testable with a table of invented sentences.
- The emotion is known at the start of the turn, so the `emotion` event never waits for the
  model.
- The wire, the schema, the robot, the settings and the dependencies do not change; no extra
  model call is made.

### Negative

- Most turns will be `neutral`, which the tone-adaptation window ignores: the precision-first
  classifier adapts less often than a model that labels freely would.
- Shade is lost against a model: sarcasm, understatement and implied feelings are not detected.
- A model that still writes a tag at the start of its reply falls back to the fixed phrase; the
  share of such replies is measured and reported, not gated.
- Honest text that mentions `emotion:` falls back or is cut, as in ADR 0017.
- The user's emotion and the robot's expression are two different signals that today share one
  wire field named `emotion`; until the face exists, the field carries only the first.
- The stored history of past turns keeps whatever labels earlier code wrote; nothing is migrated.

## Review

Revisit when a larger model is available (a model-based classifier behind the same function),
when the robot gets its face (the `expression` signal and its own event, decided apart from the
user's emotion), if a model change makes replies that start with a tag common enough to rescue,
or if the real use of the companion shows the classifier is silent often enough to matter for the
tone adaptation.
