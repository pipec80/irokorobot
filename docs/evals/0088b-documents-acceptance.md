# Plan 0088 Part B — hardware acceptance of the owner's documents (ADR 0034, D-21)

> **Status:** run by Pipec on 2026-11-24 and accepted by him that day. Branch
> `feat/0088b-documents` (PR #307). Real database upgraded to version 23 by the server's own start.
> The server had `MEMORY_ENABLED`, `RECALL_ENABLED`, `DOCUMENTS_ENABLED` and
> `FACE_AUTHENTICATION_ENABLED` on; the robot had `ROBOT_FACE_AUTH_ENABLED` on.
> Document thresholds: `DOCUMENT_MAX_DISTANCE` 0.22 and `DOCUMENT_WORD_MAX_DISTANCE` 0.61.
> Outcomes only: no document text, reading, transcript or reply is recorded here. The counts come
> from the `document.read`, `vision.read`, `identity.fusion` and `turn.decision` lines of
> `logs/server.log`.

## Before the run

- The backup `pre-0088b-<stamp>` equalled the real database (version 22, 26 tables). Its restore
  proof passed the integrity check, the foreign-key check and equal counts.
- Migration 023 was rehearsed on a copy: version 23, health exit 0, and no count changed.
- After the real upgrade, `iroko-admin health` reported «sana».
- Three test fixtures were loaded with `iroko-admin docs add`, with Pipec typing the PIN and `SI`:
  - the `.md` manual at `normal` (9 sections);
  - the `.txt` recipe at `normal` (7 sections);
  - the `.pdf` care guide at `sensitive` (3 sections).

  Every section was embedded.

## The routes

The robot refuses to start in streaming mode while the server has `VISION_ENABLED` on. This is the
startup guard of the July 2026 audit (F-08); Plan 0088 may not change the robot. So:

- blocks 1 and 2 ran on **streaming** with `VISION_ENABLED` off;
- block 3 ran on the **classic** route with `VISION_ENABLED` on.

Lifting the guard is Plan 0089's work.

A first attempt at block 1 had `DOCUMENTS_ENABLED` off, so its turns went to the generic model.
It does not count, and its recall leftovers are noted below.

## The cases

| # | Case | Route | Log | Expected | Result |
|---|---|---|---|---|---|
| 1 | A named document, asked by its words | stream | `document.read` weak `found`, 3 hits; `need=document`, `llm_ms=0` | «Según {título}: …» from that document | **pass** |
| 2 | Another named document, with a word the first also holds | stream | `found`, 3 hits | its own document, never the first | **pass** on the second try (in the first, the STT heard «Quién dice…», which is no document cue) |
| 3 | A document that does not exist, strong cue | stream | strong `nothing_found`, 0 hits, 19 rejected | «No lo encuentro en tus documentos.» | **pass** |
| 4 | A weak cue naming something that is no document | stream | weak `no_document` | converses | **pass** |
| 5 | A recall cue about a document's topic | stream | `need=recall` | never answered from a document | **pass** |
| 6a | The `sensitive` document, the owner alone | stream | strong `found`, 1 hit | «Según {título}: …» | **pass** |
| 6b | The same question with a second face in view | stream | `identity.fusion` `veto_multiple_faces`, actor `ambiguous` | the generic denial, the same as for a document that does not exist | **pass** |
| 7a | «Iroko, lee esto» with a handwritten card beside the face | classic | `need=read_text`, `vision.read`, 102 s (cold VLM) | reads it and offers «sí, guárdalo» | **pass for the flow**; the VLM misread the handwriting (see below) |
| 7b | «Sí, guárdalo» on the next turn | classic | `need=read_text`; one source added (channel `voice_camera`); its vector stored at once | «Listo, lo guardé en tus documentos.» | **pass** |
| 7c | The kept note asked through a document cue | classic | — | «Según Nota del …: …» | **not run validly**: the STT cut the question, and the note's text was misread anyway |
| 8 | `iroko-admin docs remove` of the note, with Pipec's PIN and `SI` | CLI | 4 sources → 3 | «Documento borrado.» | **pass** |

Pipec accepted block 3 as run. The reading, the offer and the keeping work. The quality of the
reading and the speed of the vision model are Plan 0089's subject. Case 7c's search path is the one
cases 1 to 6a already accepted.

## Findings

- **The laptop ran out of memory during block 3.** Three later readings each failed with a
  `VisionError` after 137 to 152 s. A generic turn took 73 s; such turns usually take 8 to 20 s.
  Whisper, Piper, the 3B text model, the VLM and the embedding model share the 15.7 GB; Pipec had
  to restart the PC. The failure cause was not logged then. **Fixed in `27e215d`:** a failed
  reading now logs `vision.read_failed` with the exception type or `nothing_read`, and never a text.
- **A PDF heading was read glued to its sentence** («…dolor Tome…»). **Fixed in `27e215d`:** a page
  line with no closing mark, followed by a line that opens a sentence, ends a sentence. A line
  wrapped inside a sentence stays one sentence.
- **The STT dropped a letter of the reading phrase** («Iroko, le esto»), which is no reading
  request. Clearer and more tolerant camera phrases (reading and describing) go to Plan 0089, with
  the vision model's budget and a thorough reading test (printed text, a phone screen, good light).
- **The handwritten card was misread.** Pipec's handwriting is hard to read; printed text was not
  tried this time.
- **Leftovers of the first attempt:** its turns entered the conversation diary while documents were
  off, and case 5 answered one of them. Removing them with `iroko-admin forget` is left to Pipec.

## After the run

- `iroko-admin health` exit 0 («sana»).
- The backup `post-0088b-<stamp>` equals the real database (version 23, 3 documents, 19 sections).
  Its restore copy passed integrity and health with exit 0, and its counts were equal.
- The `pre-0088b` backup was deleted after Pipec's acceptance.
