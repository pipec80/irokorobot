# 0034 — Documents in the memory engine, and reading through the camera

- **Status:** Proposed (2026-11-11). Written from ADR 0031 decision 13, the RAG architecture
  document, the research of the memory engine (kept in the ignored `project-history/`) and Pipec's
  four decisions of 2026-11-11 (see *Pipec's decisions and where they land*). It becomes `Accepted`
  when the plan that implements it closes.
- **Date:** 2026-11-11
- **Builds on:** [ADR 0025](0025-remote-administration-backup-updates-and-telemetry.md) (`iroko-admin`),
  [ADR 0028](0028-recall-what-the-owner-told.md) (the search),
  [ADR 0029](0029-it-knows-who-is-listening.md) (levels and the camera check),
  [ADR 0031](0031-the-memory-engine-boundary.md) (decisions 6 and 13: documents are one more source),
  [ADR 0032](0032-block-c-hygiene-correct-forget-and-years.md) (forgetting).
- **Amends:** [ADR 0024](0024-seed-load-senses-secrets-and-channels.md) (the commissioning loads a
  reviewed `documents/` folder beside the seed file, decision 1);
  [ADR 0031](0031-the-memory-engine-boundary.md) decision 13 («after CM-7 + PC-5» becomes
  row 9 of the path, before the home server; Pipec, 2026-11-11) and adds the camera as a source.
- **Delivers:** R2 and the reading through the camera, row 9 of the
  [path to the finish line](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory).
  Reserved since 2026-11-06.

## Context

1. **The engine holds what the owner told and loaded, not what the owner keeps on paper.** A manual,
   a recipe, a medical report or a letter has no place today. ADR 0031 decision 13 already made
   documents «one more source of the engine», with their own provenance and apart from what a person
   told, and fixed the first formats: Markdown, plain text and PDF with a text layer.
2. **The search exists.** Recall (ADR 0028) is FTS5 + `vec0` + RRF behind a calibrated gate, three
   results at most, zero allowed. A recall unit, though, points at a conversation record
   (`source_record_id` is required), so a document cannot be a recall unit as it stands.
3. **The server already reads images.** The local vision model (`qwen3-vl:2b`, through Ollama, the
   perception route) describes a camera frame and can read the text in it. Pipec asked to use it as
   an OCR for short texts (2026-11-11).
4. **A document is untrusted text.** It may hold instructions («ignora tus reglas…»), personal data
   of others, or health data. ADR 0031 decision 6 gives it the origin `document`, never `reported`.

## Decision

### 1. Documents are loaded at the alta as a folder, and later one by one with `iroko-admin` (*Pipec, 2026-11-11*)

**At the alta (the main path).** Most documents arrive once, with the household's data: the
builder and the owner prepare a `documents/` folder beside the seed file, with a small manifest
that names each file and its level (decision 2; `normal` when not said). The commissioning loads
it like the seed file (ADR 0024): a dry run that lists every document, its sections and its level,
the owner's review and `SI`, one transaction with the commissioning record, `--replace` only
while commissioning. A builder may preload documents the owner will want (the robot's own
manual, the household's appliances, a care guide); they are the owner's documents like any other.

**Afterwards (the occasional path).** `iroko-admin docs add <file>` (server stopped, like every `iroko-admin` amendment) extracts the
text, shows the owner how many sections and characters it found and the first lines, asks the
level (decision 2) and an `SI`, then stores it in one transaction with one audit row that holds no
content. `docs list` and `docs remove` complete it. Accepted: `.md`, `.txt` and `.pdf` with a text
layer, under a size and page cap set by the plan; a PDF without text is refused with a message
pointing to R4. The PDF library is pure Python with a permissive licence (MIT, BSD or Apache),
read before it ships; a copyleft one (AGPL) is not used.

### 2. Each document has a level chosen at load (*Pipec, 2026-11-11*)

| Level | Examples | Who hears it |
|---|---|---|
| `normal` (default) | A manual, a recipe, a list | The owner's face (`basic`), as recall |
| `sensitive` | A medical report, a contract, a bank letter | The owner's face **and** no other face in view, the camera check of ADR 0029 decision 3 |

A document is the owner's (`personal`); nobody else hears it, and a stranger or an unknown face
hears the generic denial. `security` is not a document level: codes and keys never enter a
document (ADR 0029 decision 5 still holds; a document that holds one is refused at load if the
secret guard sees it, and the owner is told why).

### 3. Documents are searched only on an explicit cue, and the answer names its source (*Pipec, 2026-11-11*)

A **document cue** («¿qué dice el manual de la lavadora sobre…?», «según mis documentos…», «en la
receta de…») is a closed controller branch, apart from the recall cue: a question about what the
owner told never searches documents, and a document question never searches memories. The answer
is worded from the found sections only, like recall (ADR 0028), and always names the document
(«Según el manual de la lavadora: …»); nothing found says «No lo encuentro en tus documentos.».
The found text enters the answer prompt as a delimited quotation marked as data; an instruction in
it is never followed (decision 5).

### 4. Storage: the same search over its own tables

Documents get their own tables: a source (title, file hash, version, format, level, loaded at, by
whom) and its sections (text, position, hash), with their own FTS5 and `vec0` indexes and the
embedding-model guard of ADR 0032 decision 1. The search code of recall (RRF, the gate, at most
three results, zero allowed) is reused, not copied; the data stays apart, so documents never mix
with the diary. Sections are cut by headings and paragraphs with a size cap; the plan measures it
on a Spanish corpus. Forgetting a document follows ADR 0032 decision 2 (the source and every
section and index row, physically, with a line in the deletion register).

### 5. «Iroko, lee esto»: read aloud always, kept only when the owner confirms (*Pipec, 2026-11-11*)

- The phrase is a closed controller branch. The robot takes one frame, the local vision model reads
  the text in it (a fixed prompt that asks for the text only), and the robot reads it aloud,
  capped in length. Reading needs no identity: it says what is in front of the camera.
- Then it offers: «¿Lo guardo? Dime: sí, guárdalo.». The answer is the closed dialogue of ADR 0021,
  on the **next** turn, with the owner's face in view (holding a paper, the camera may not see the
  face on the reading turn). Kept, it becomes a `normal` document titled by the day and the first
  words, origin `document`, transformation `extracted`; the frame itself is never stored.
- Good for short, large text (a note, a label, a recipe card, a medicine box); a full page of small
  print is the PDF's job. The body's camera reads worse than the laptop's: the reading is measured
  again on the body after the line.

### 6. What is trusted, and where the guards stand

| Boundary | Risk | Guard |
|---|---|---|
| A loaded file | A malformed or huge PDF; hidden text | Pure-Python parser, size and page caps, a timeout; the owner sees the extraction before `SI` |
| Document text in an answer prompt | Prompt injection | Quoted as data, answer only from found sections, never in the generic prompt; tested with an injected instruction |
| A camera frame | Someone else's paper or screen read aloud | Reading is aloud and stores nothing; keeping needs the owner's face and the closed verb |
| A sensitive document | Heard by a visitor | The sensitive level and the camera check |

## Pipec's decisions and where they land

| # | Decision | Date | Where |
|---|---|---|---|
| 1 | Close the RAG before the electronics: R2 and the camera at row 9, before the home server | 2026-11-11 | *Amends*, *Delivers* |
| 2 | Load mostly at the alta as a reviewed folder with a manifest; later one by one with `iroko-admin docs` | 2026-11-11 | Decision 1 |
| 3 | A level chosen at load: `normal` by default or `sensitive` | 2026-11-11 | Decision 2 |
| 4 | Documents searched only on an explicit cue, naming the source | 2026-11-11 | Decision 3 |
| 5 | The camera reads aloud and keeps only on the owner's confirmation | 2026-11-11 | Decision 5 |

The author's calls, for Pipec's review: own tables with the shared search; no `security` level for
documents; the permissive-licence rule for the PDF library; the threat table of decision 6.

## Not decided here

| Subject | Owner |
|---|---|
| Scanned PDF with a dedicated OCR, tables, a reranker | R4, only by measurement |
| Searching images or video (multimodal) | R6, after P2.1 |
| Loading documents remotely or by voice | The remote dashboard (ADR 0025), after the line |
| A `public` level (a document anyone in the home may hear, such as the robot's manual) | The family stage (P3), if a household asks for it |
| Documents of other household members | The family stage (P3) |
| The exact caps, the section size, the PDF library and the cue word list | The implementing plan |

## Alternatives considered

- **A watched folder that indexes by itself.** Rejected: nothing reviews what enters. The folder
  idea stays, as the alta's reviewed `documents/` folder (decision 1).
- **Documents as recall units.** Rejected: a unit needs a conversation record, and mixing a manual
  with what the owner told breaks ADR 0031 decision 6.
- **Searching documents with every recall question.** Rejected by Pipec: the answer would mix the
  owner's life with a manual.
- **Keeping every camera reading.** Rejected by Pipec: a stranger's paper would become a document.
- **A dedicated OCR engine now.** Rejected: the vision model already reads short text; R4 decides a
  real OCR by measurement.

## Consequences

### Positive

- The owner's papers join the memory with their source named, under the same levels and guards.
- One search serves memories and documents without mixing them.
- The camera reads short texts aloud with no new model.

### Negative

- Two new tables with their indexes, and a parser dependency to vet.
- The vision model shares the laptop's RAM with Whisper and the chat model; reading a frame is slow.
- A reading of small print is poor, and the body's camera reads worse until recalibrated.

## Test consequences

- Load: a Markdown, a text and a text-layer PDF load; a PDF without text is refused; a huge file
  is refused; an audit row holds no content; `docs remove` leaves nothing searchable.
- Answer: a document cue finds the right section and names the document; a recall cue never returns
  a document; nothing found says the fixed phrase; an injected instruction in a document is not
  followed; a sensitive document is refused with a second face.
- Camera: a canary card is read aloud; nothing is stored without the closed verb and the owner's
  face on the next turn; the frame is never kept.

## Docs to update

The ADR index; the roadmap (row 9); the RAG architecture document (R2); `current-state.md` and the
architecture diagrams when the plan closes; the operator manual (`iroko-admin docs`); ADR 0031
decision 13 (an *Amended by ADR 0034* note, when this ADR is accepted).
