# 0074 — Acceptance of the profile card on real hardware (CM-5a)

> **Status:** prepared 2026-10-28, **to be filled in by Pipec**. Outcomes only: never write the preferred
> name, a taste, a person's name or any stored value in this file (the rule of
> [`implementation-guardrails.md`](../architecture/implementation-guardrails.md)). Procedure and meaning
> of each setting: [operator manual, «The profile card»](../runbooks/operator-manual.md).

## Conditions

| Item | Value |
|---|---|
| Date | |
| Commit of the branch | |
| Database | a database **loaded by the import** (or `just admin add`): a preferred name, a form of address and at least two tastes |
| Switches | `MEMORY_ENABLED=true`, `PROFILE_CARD_ENABLED=true`, `FACE_AUTHENTICATION_ENABLED=true` (robot: `ROBOT_FACE_AUTH_ENABLED=true`) |
| Mode | classic `/transcribe` and streaming `/transcribe/stream` (note which) |
| Model and hardware | |

The server and the robot are started by Pipec. Before each case: `uv run python scripts/inspect_candidates.py`
and note the `audit read_personal_conversation_memory:` counts (to see one row per identified turn).

## Cases

| # | Case | Expected | Outcome (pass / fail / partial, one line, no values) |
|---|---|---|---|
| 1 | Owner's face in frame: «¿qué sabes de mí?» | The robot lists the preferred name, the form of address and the tastes in the fixed template; the model is not asked | |
| 2 | Owner's face in frame, an ordinary turn («hola, ¿cómo estás?») | The reply uses the preferred name naturally (or at least does not invent anything about the person) | |
| 3 | A second face in frame, the same ordinary turn and the question | No card, no list: the unknown phrase on the question | |
| 4 | An unknown speaker (no owner face): the question | «Todavía no puedo confirmar quién eres para contarte lo que sé de ti.», never the list | |
| 5 | `PROFILE_CARD_ENABLED=false` (restart): the same ordinary turn and the question | The behaviour of `main`: no card, the question is ordinary conversation, no new audit row | |
| 6 | Median extra latency of the card over 10 ordinary turns (face in frame), with and without the switch | Number in ms; the card costs one local read | |
| 7 | `address_form=usted` tried once (`just admin change address_form`) | Outcome in one line; `usted` reaches only the model's own sentences, never the fixed ones | |
| 8 | Both `PROFILE_CARD_POSITION` values (`with_memory`, `before_language`), the same five turns each | Which one the model follows better (uses the name, does not drift in language), and the one to keep | |

## Also look at

- The log of a case-1 turn carries `Profile card:` lines with closed reasons and **no value**; with
  `LOG_CONVERSATION_TEXT=true` the spoken line of the summary is the marker «resumen del perfil».
- A token-only speaker (PIN, no face) gets no card and no audit row.
- The audit counts moved by one row per identified turn read, not more.

## Result

| Item | Outcome |
|---|---|
| Cases passed | |
| Measured latency (median, ms) | |
| `PROFILE_CARD_POSITION` kept | |
| Anything unexpected | |
