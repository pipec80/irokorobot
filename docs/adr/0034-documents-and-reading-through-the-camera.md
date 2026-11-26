# 0034 — Documents in the memory engine, and reading through the camera

- **Status:** **Accepted** (2026-11-24, Pipec's hardware acceptance of Plan 0088 Part B,
  [record](../evals/0088b-documents-acceptance.md)); Proposed 2026-11-11. *Implemented by
  [Plan 0088](../plans/completed/0088-close-the-rag-gate-and-documents.md) Part B*, with the
  deviations listed in *Deviations made by Plan 0088*. Written from ADR 0031 decision 13, the RAG
  architecture document, the research of the memory engine (kept in the ignored `project-history/`)
  and Pipec's four decisions of 2026-11-11 (see *Pipec's decisions and where they land*).
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
- **Amended by [ADR 0041](0041-reading-and-explaining-a-paper.md) (Plan 0090, 2026-11-26): the
  paper waits and answers, and a dedicated OCR reads.** The reader is RapidOCR
  (`READING_ENGINE=rapidocr`) on the frame as taken, no longer the vision model by default, with no
  fallback between them; this settles the alternative «a dedicated OCR engine now» rejected below.
  The read text, whole, waits in its own slot bound to the person identified on the reading turn
  and is answered by quotation («Según el papel: …») to a closed list of questions; it is still
  kept only after «sí, guárdalo».

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

## Deviations made by Plan 0088 (2026-11-23, still `Proposed`)

[Plan 0088](../plans/completed/0088-close-the-rag-gate-and-documents.md) Part B implements this ADR
with these changes, each with its reason; Pipec approved them on 2026-11-23.

1. **No version column** (decision 4 lists «version»). A changed file is a new source and the
   owner removes the old one; a version is built when a re-load is asked for (YAGNI, Plan 0088
   D-8). The same file twice is refused by its hash.
2. **The level is asked, or given by a flag** (decision 1): `docs add` asks it when `--level` is
   absent; the alta's manifest gives it, `normal` when absent (D-16).
3. **The reading uses the turn's own frame** (decision 5 said «the robot takes one frame»). The
   frame the voice routes already carry for face authentication is handed to the controller
   through a per-request seam, so neither the robot nor the wire changes and both voice routes
   answer. It works only with `ROBOT_FACE_AUTH_ENABLED` on the robot and
   `FACE_AUTHENTICATION_ENABLED` on the server, plus `VISION_ENABLED` and `DOCUMENTS_ENABLED`
   (D-17). While a reading waits, «sí, guárdalo» belongs to it, not to a memory candidate offered
   earlier (ADR 0021's verb keeps its meaning when no reading waits).
4. **The transformation follows from the format** (ADR 0031 decision 6): `original` for `md` and
   `txt`, `extracted` for `pdf` and `camera`; no column holds it (D-8).
5. **What a document reply leaves behind:** a document answer and a camera reading are recorded
   with the markers «[respuesta de un documento]» and «[texto leído por la cámara]», so no section
   or read text enters the conversation record, the diary, a recall unit or an export by the voice
   routes; a document cue, a reading and its «sí, guárdalo» tell nothing (D-18).
6. **Three `memory/` modules import `server.cognition`**, exactly as their recall twins:
   `document_access` (the policy), `document_search` (the cue) and `document_answer` (the reply
   plan). They are the documents' share of the coupling ADR 0031 decision 11 removes after CM-7 +
   PC-5; a guard lists every such module and the list may shrink, never grow (D-20).
7. **The audit of `iroko-admin docs`:** `admin_audit` has closed checks, so migration 023 rebuilds
   it as migration 022 did, adding the target kind `document` and the operation `list` (`docs
   list` is audited too, since a title can be sensitive). The audit row holds no title and no
   text.
8. **The caps, measured** (decision 1 and 4 left them to the plan): 10 MB per file, 200 pages,
   30 s of extraction in a child process killed at the limit, `pypdf` 7.1.1 (BSD-3-Clause, `pip-audit`
   clean) with its decompression limit set explicitly, 2,000 sections per document, and a section
   cap of 1,200 characters under the embedding model's 512-token window. Measured on one long
   text-layer PDF of Pipec's own (99 pages, 93,504 characters, 10.1 s, 13.5 MB peak in the child)
   and on the document bench; three scanned PDFs of Pipec's (4 to 750 pages) gave no text at all,
   so they wait for R4. Counts only; no file entered the repository.

9. **The answer quotes; no model words it** (decision 3 said «worded from the found sections
   only»). On the plan's bench the local 3B model obeyed an order planted in a section in 12 of
   24 answers, and no grounding check can see it, since the planted words are in the section.
   Pipec delegated the call (2026-11-23: the laptop runs only the 3B model, its CPU and RAM shared
   with Whisper, Piper and the vision model). The answer is «Según {título}:» and the found
   sections' best-matching sentences, with every sentence in the closed shapes of an order and
   every one the secret detector flags left out: 0 of 24 on the same eval, and no model call. A
   planted order in other words is still read aloud as what the document says: a known limit of
   a deterministic guard. A better model may word the answer later through the answer seam, with
   the eval run again.

10. **A second face denies the whole cue** (decision 2 said the `sensitive` level needs no
    other face). With two faces in view the face check identifies nobody, so the owner is not
    known: a document cue hears the generic denial, the same with or without a `sensitive`
    document (no oracle). The level filter stays as a second wall for when the face check can
    tell the owner among several faces.
11. **A reading is kept only by the person seen on its turn** (decision 5 allowed the face on the
    next turn only). A reading with nobody identified is read aloud and cannot be kept: anyone on
    the network could plant one for the owner's next «sí, guárdalo».
12. **The secret guard needs a secret word** (decision 2). Measured on one real medical text, a
    rule on lone digit runs refused 89 of 128 sections (record and episode numbers), so it is
    gone: a code is flagged with its secret word before or after it, a card number by its
    groups or a card word, an IBAN by its shape. A code written with no word near it is read: a
    known limit.

13. **A file is checked before its text is taken** (Pipec, 2026-11-24; decision 6 named only
    caps and a timeout). It must be what its extension says (a PDF starts with `%PDF-`, a text
    holds no binary); control and invisible characters are removed; and a PDF with active content
    is refused whole: JavaScript, actions, embedded or attached files, links, signature fields,
    XFA, rich media, or an image holding a QR code or a barcode. Nothing of a document is ever
    executed or followed, so these checks only keep the parser from touching what a document of
    the household never needs. The formats stay a closed list: Office, JPG and PNG, audio and
    video (with the iPhone's HEIC and MOV) are the next ones (R2b), each with its own check; a
    threat model of file ingestion is its own ADR before them.

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
