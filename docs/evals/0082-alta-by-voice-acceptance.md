# 0082 — The whole alta by voice: hardware acceptance

> **Status:** **accepted** on 2026-11-12 by Pipec (streaming route, laptop body), in two sittings the
> same morning. Code of [Plan 0082](../plans/completed/0082-the-whole-alta-by-voice.md), branch
> `feat/0082-alta-by-voice`. Pipec runs every case; the agent starts nothing. **Counts, outcomes and
> yes/no only:** no transcript, no reply, no name, no phone and no household datum is written here.
> The only text quoted is a fixed phrase of the robot, as it stands in the code.

## Setup

- `.env`: memory on, `SENSITIVE_READ_ENABLED=true`, `ALTA_READ_ENABLED=true`,
  `SPEAKER_AUTHENTICATION_ENABLED=true`, `FACE_AUTHENTICATION_ENABLED=true`,
  `CONVERSATION_RECORD_ENABLED=true`, `RECALL_ENABLED=true`, `LOG_CONVERSATION_TEXT=true` (console
  only; never on in production).
- The owner's face and voice enrolled and the alta closed (Plan 0072); the contacts and the rest of
  the profile loaded at the alta (Plans 0071 and 0072). A database backup was taken first.
- **Streaming route only**, as in Plans 0077 to 0081: both routes take the same controller decision
  and `tests/integration/test_sensitive_routes.py` runs the cases on `/transcribe` and
  `/transcribe/stream`.
- How to tell who answered: the server's `sensitive.read` line (topic, level, outcome, a count, never
  a text); the record's markers were counted in a throwaway copy of the database (counts only).

## Acceptance

| # | Case | Result |
|---|---|---|
| 1 | A contact's phone by relationship, only the owner's face in view | **Pass** on the second sitting: `contact_phone answered`; the first sitting missed the grammar (*Found on hardware*) |
| 2 | The phone of call order 1, two phrasings («contacto 1», «primer contacto») | **Pass** 2 of 2: `contact_phone answered`, the contact of order 1, its second phone said too |
| 3 | «Llama a mi contacto …» | **Pass**: `contact_call answered`, opens with «Todavía no puedo hacer llamadas.», then the name and the phone |
| 4 | Who holds a key | **Pass**: `key_holders answered` |
| 5 | Three profile topics (vision, mobility, coverage) | **Pass** 3 of 3: `answered`; one speech-to-text accent slip absorbed by the folding |
| 6 | «¿Vivo solo?» in a longer sentence, face and voice | **Pass** on the second sitting: `lives_alone answered` at the security level |
| 6b | «¿Vivo solo?» short | **Pass** 2 of 2: `retry_voice`, «No reconocí bien tu voz. Pregúntamelo de nuevo con una frase completa.» |
| 7 | A second face (a photo on a phone) and a contact question | **Pass** on the second sitting: `not_alone`, «Te lo digo cuando estemos solos.»; the first sitting fell to the household protection (safe, no value said) |
| 8 | Somebody else's phone («los bomberos») | **Pass**: ordinary conversation, no `sensitive.read` line, nothing read |
| 9 | The record keeps the marker | **Pass**: 9 «[dato sensible leído]» for the 9 answers that said a stored value; the refusals carry no marker |

## Found on hardware

- **«Tiene el teléfono de mi …»** (2 misses, first sitting): Whisper wrote «tiene» for «tienes» (or it
  was the usted form), which the grammar did not hold, so case 1 went to the model and case 7 to the
  household protection. Fixed in `505a54e` with the usted forms and «tiene el», «me da el», «me puede
  dar el», «llame a», «puede llamar a» (fixture red then green); both cases passed after a restart.
- **Short security questions** need a longer sentence to verify the voice (a known limit, Plan 0075):
  «Oye Iroko, una pregunta, ¿vivo solo?» passed. A short question at the sensitive level («¿uso
  lentes?») needs only the face and passed.
- No value reached `logs/server.log`: every `sensitive.read` line (12 in the two sittings) carries a
  topic, an outcome and a count.

## Not run

- The classic route on hardware (the route tests cover it).
- A contact asked by name alone (ordinary conversation by design, D-6) and a contact with no stored
  label (the unit tests cover both).
