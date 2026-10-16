# Memory dialogue, hardware acceptance (Plan 0063)

Outcomes only: no sentence, preference value, name or token is recorded here. This is the
hardware acceptance of [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md)
(*Acceptance*), run by Pipec on the real stack: the spoken offer, the explicit answer and the
firewall around them.

- date: 2026-10-16
- code: branch `feat/0063-cm3a-memory-dialogue` at `bcf3a0d` (9 task commits and 6 review-fix
  commits on top of `0a07719`); `just gate` green with 3217 tests
- database: the real `data/omnibot.db` at schema version 9, one owner with a face enrolment and a
  voice enrolment of 3 references (enrolled 2026-10-15)
- stack: the shared laptop (no homelab), `qwen2.5:3b` for chat, Whisper `small`, Piper, the
  streaming route (`ROBOT_STREAMING=true`); `FACE_AUTHENTICATION_ENABLED`,
  `SPEAKER_AUTHENTICATION_ENABLED`, `ROBOT_FACE_AUTH_ENABLED` and `MEMORY_CANDIDATES_ENABLED` on
  for the run, and `MEMORY_CANDIDATES_ENABLED` set back to `false` at the end (decision D-3)
- processes: services, server and robot were started by the lead on the first attempt and by
  Pipec afterwards; Pipec spoke. Counts come from `scripts/inspect_candidates.py` and from the
  structured server log, never from a transcript
- substitutes (decision D-14, Pipec lives alone): "another voice" was a translator app, or a
  Windows text-to-speech voice, played near the microphone while Pipec's face was in frame;
  "another face" was a photo of someone else on a phone held next to Pipec's face

## Cases

| # | Case | Expected | Outcome |
|---:|---|---|---|
| 1 | Accept | taste stored, offer spoken on a later turn, «sí, autorizo guardar …» promotes | **pass**. The filler form of a taste («la verdad es que …», Task 1) was accepted by the gate; voice `verified`, one `proposed` row about 30 s after the turn. The offer was spoken after the reply of a generic turn of about 4 s; the answer 30 s later gave `Identity fusion: face_and_voice`, `Candidate promotion: promoted`, `need=memory_answer`, `llm_ms=0`. Inspector: `confirmed=1`, `read allowed=1`, `confirm allowed=1`, `confirmed facts: 1` |
| 2 | Reject | «no autorizo guardar …» rejects and erases the value | **pass**. Stored about 60 s after the turn; offered after a generic turn; the answer 36 s later gave `Candidate answer: rejected`, `llm_ms=0`. Inspector: `rejected=1`, `confirm allowed=2`, no new fact; no `rejected`, `confirmed` or `expired` row holds a value |
| 3 | Another voice, the owner's face | ordinary reply, nothing changes | **pass**. With an offer open (`offered=1`, `read allowed=3`), the answer played by a translator gave `Speaker verdict: unknown` and `Identity fusion: face_only`; the model replied as to any message, the candidate stayed `offered`, `confirm allowed` stayed at 2. An earlier attempt had no open offer and counts only as partial evidence |
| 4a | No face in frame, a taste said | no candidate | **pass**: `Identity fusion: no_evidence`, no proposal scheduled |
| 4b | A second face in frame, a taste said | no candidate | **pass**: `Identity fusion: no_evidence` (a second face identifies nobody), no proposal scheduled |
| 4c | The owner's face, another voice says a taste | no candidate | **pass**, with a Windows text-to-speech voice (the translator was not transcribed): `Speaker verdict: unknown`, `Candidate proposal: dropped (strong_unreachable)`, nothing stored |
| 5 | Restart between the offer and the answer | offered again, then promoted | **partial**. The server restarted with `Candidates reconciled at start-up: 0 expired` (not `voided`); the same candidate was offered again (`offer_count` 2). The answer was heard by the speech-to-text as a different verb («autoriza a guardar …»), so it fell through; promotion after an offer is proven by case 1 |
| 6a | An answer with no open offer | ordinary turn, no write | **pass**: the actor was resolved (`face_and_voice`) because the message has the shape of an answer, no offer was found, the turn went on as any other, no audit row |
| 6b | An answer naming another value while an offer waits | ordinary turn, no write | **pass**: same path; `confirm allowed` unchanged |
| 7 | A sentence about a move, not a taste | no candidate | **pass**: `Candidate proposal: dropped (negation_unsupported)` |
| 8 | Measurements (laptop only, decision D-4) | recorded | see below |
| 9 | Replay: a photo plus an earlier recording | recorded | **not run**: needs a second person or device; the replay defence stays unmeasured (ADR 0016 §9) |

## Case 8, measurements

- Voice check to row inserted: 30 s and 60 s on the two clean runs, on the shared laptop with the
  chat model resident and the extraction model loading. Not measured on a homelab: **not
  available, not run**.
- Offer: prepared in parallel with the reply, so the voice check of a generic turn (about 1 to
  2 s) is hidden behind the model's own time. The answer turn costs the face check, the voice
  check and the promotion, about 3 to 4 s over speech-to-text, with no model call.
- The offer needs a clip long enough for the voice check. Three turns of about 1.5 s («hola»
  and the like) gave `Speaker verdict: unknown` and `Candidate offer: voice_unverified`, with no
  audit row and nothing offered; of the owner's turns of about 3 s or more, all but two were
  `verified`. The operator manual asks for a full sentence.
- **False rejection of the explicit answer: 2 of 4** answers were parsed (the owner's, with an
  offer open). Both failures were Whisper `small` writing «autoriza a guardar …» (and once «mi»
  for «el») for «autorizo guardar el …». Nothing was written in either case, which is the safe
  direction. Widening the closed verbs is a decision for the owner (D-2); a smaller change, the
  speech-to-text hotwords, was not tried because they already leak into noise clips.
- Cold start: the first chat turn after Ollama started failed with a 500 twice (the machine had
  about 460 MB of free memory while the model loaded) and the stream spoke the fallback phrase;
  the next turn worked. Time to first audio ran from 7 s to 90 s depending on the machine's load.

## Findings and follow-ups

1. **The model claims to have saved.** On a message that has the shape of an answer but is not
   one (another voice, no open offer), the ordinary turn is generated by the model, which twice
   said it had saved or registered something. Nothing was written. This is the price of the
   no-oracle rule; it needs its own change (constrain the model, or answer with a fixed phrase
   the rule can still allow).
2. **Replies in French.** Two generic or fall-through turns in about twelve answered partly or
   wholly in French (the open language item of Plans 0059 and 0062).
3. **Closed answer and speech-to-text.** See case 8; decide whether the grammar admits the
   common mis-hearings.
4. **Short turns cannot carry an offer.** By design (the firewall needs the voice of that turn);
   document it, and measure it again with a homelab.
5. **Cold-start Ollama** fails when memory is short; warm the model first.
6. The fall-back phrase when the model is unreachable is still in voseo (ADR 0021 asks for tuteo in new phrases).
7. Case 9, the homelab measurements and a second person for the "another face" cases are left
   for a later run.

## Clean-up

- The robot and the server were stopped; `scripts/scrub_candidates.py data/omnibot.db` printed
  `Voided 1 live candidate(s)`; afterwards no candidate row holds a value (`confirmed` 1,
  `rejected` 1, `expired` 3). `just reset-db` was never run on the real database.
- The one confirmed taste fact stays in the owner's local database: it is the product of case 1.
