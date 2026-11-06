# 0079 — Sensitive read by voice and spoken secrets: hardware acceptance

> **Status:** **accepted** on 2026-11-06 by Pipec (streaming route, laptop body). Code of
> [Plan 0079](../plans/completed/0079-block-b-sensitive-read-and-spoken-secrets.md), branch
> `feat/0079-sensitive-read`. Pipec runs every case; the agent starts nothing. **Counts, outcomes and
> yes/no only:** no transcript, no reply, no name and no household datum is written here. The only
> text quoted is a fixed phrase of the robot, as it stands in the code.

## Setup

- `.env`: memory on, `SENSITIVE_READ_ENABLED=true`, `SPEAKER_AUTHENTICATION_ENABLED=true`,
  `FACE_AUTHENTICATION_ENABLED=true`, `CONVERSATION_RECORD_ENABLED=true` (consent granted at the
  alta), `LOG_CONVERSATION_TEXT=true` (console only: it prints what Whisper heard, a secret
  included; never on in production).
- The owner's face and voice enrolled and the alta closed (Plan 0072); the owner's health, home and
  birth dates, the children and the reference entries loaded at the alta (Plans 0071 and 0072).
- **Streaming route only.** The classic route is not run on hardware: the robot uses streaming and
  both routes take the same controller decision; `tests/integration/test_sensitive_routes.py` runs
  the cases on `/transcribe` and `/transcribe/stream`. Same call as Plans 0077 and 0078.
- How to tell who answered: the server's `Sensitive read:` line (`sensitive.read`: topic, level,
  outcome, a count) and `Turn decision` (`need=sensitive_read`, `source=deterministic`); the
  `identity.fusion` line gives the fusion reason. None of them holds a text.

## Acceptance

| # | Case | Result |
|---|---|---|
| 1 | A medication question, only the owner's face in view | **Pass**: answered, fusion `face_only`, nothing asked back |
| 2 | The address | **Pass** on the third attempt: answered with `face_and_voice`; one attempt missed the grammar (see *Found on hardware*) |
| 3a | The owner's own birthday | **Pass**: answered |
| 3b | The children's birthdays | **Pass**: answered, 2 entries |
| 4 | The security reference (who knows a code), a long full sentence | **Pass** after the opener fix: answered with `face_and_voice`. First run: the phrase missed the grammar and reached the model, which holds no stored value: nothing was disclosed |
| 5 | A short security question | **Pass**: the retry phrase «No reconocí bien tu voz. Pregúntamelo de nuevo con una frase completa.», twice (`face_only`) |
| 6 | A second face in view (a photograph on a phone) | **Pass**: «Te lo digo cuando estemos solos.» (`veto_multiple_faces`), nothing read |
| 7 | The camera covered | **Pass**: the generic denial (`no_evidence`) |
| 8 | A stated secret | **Pass**: the fixed refusal «Las claves y los códigos no los guardo ni los repito.»; no actor resolved, no model call |
| 9 | A mention of a password in an ordinary sentence | **Pass**: ordinary model reply, twice |
| 10 | An allergy question with nothing stored | **Pass**: `not_registered` |

All ten cases pass. Closed labels read from `logs/server.log` for 2026-11-06 (20 turns with an
`identity.fusion` line, 10 `sensitive.read` lines, 1 `secret.turn` line):

| Label | Count |
|---|---|
| `identity.fusion` reason `face_only` / `face_and_voice` / `veto_multiple_faces` / `no_evidence` | 14 / 4 / 1 / 1 |
| `sensitive.read` outcome `answered` / `retry_voice` / `not_alone` / `denied` / `not_registered` | 5 / 2 / 1 / 1 / 1 |
| `secret.turn` kind `stated` | 1 |

The voice verified on 4 of the 20 turns and stayed `unknown` on the short ones, consistent with
Plan 0075; the security level answered only on a turn where the voice verified.

## What the record kept

Counted on a read-only copy of the database, counts only:

| Check | Count |
|---|---|
| The secret turn stored as «[dato de seguridad omitido]» | 1 |
| Sensitive answers stored as «[dato sensible leído]» | 4 |
| Stated digits kept in any turn | 0 |
| Recall units holding a marker or the digits | 0 |
| Memory candidates from these turns | 0 |

The two turns that missed the grammar became ordinary recall units marked `location` and `security`
by the word classifier, so voice recall never reads them. Audit rows: every one is `allowed`; the
denied, not-alone and retry outcomes write none, by design (nothing is read).

## Found on hardware and fixed in this plan

| Finding | Fix | Amends |
|---|---|---|
| Two real phrasings missed the grammar (2 shapes): a request introducer before the question («una pregunta, …») and a polite request («¿me puede decir …?»); the phrase reached the model, which holds nothing stored, so nothing was disclosed | `4a80b38`: a closed list of introducers is stripped from the sentence body in `sensitive_questions.py` only; the phrase must still open what remains, so a mention stays ordinary | ADR 0029 decision 4 (Ruling 36) |

The independent reviews of the plan, run before the hardware, also changed the secret rule (an
offered secret, plural words, the slang «es clave») and the grammar («mis»); those are the
builder's calls recorded in ADR 0029.

## Residual risks (ADR 0029 *Consequences*, unchanged by the run)

- A photograph plus a recording of the question can draw the owner's sensitive data, never a
  secret's value (none is stored); replay stays measured, not defended (ADR 0016 §9, ADR 0029
  decision 2).
- Someone off camera who asks in the first person while the owner is in view is answered; the
  first-person grammar is only a partial filter (decision 13).
- A secret said without a secret word, or without a value the rule recognizes, is kept as an
  ordinary turn, unreadable by voice.

## Checks

On the closing commit (2026-11-06): the CI selection (`MEMORY_ENABLED=false pytest -m "not slow and not
hardware and not eval" -n auto`) ran **6438** tests, all passed (baseline 5976 on `main` before
the plan; 6415 at `752369b`); `pyright`, `mypy server/src robot/src`, `ruff check .`,
`ruff format --check .`, `ruff check` on every `scripts/*.py` and `scripts/check_reserved_terms.py`
pass.
