# 0042 — The threat model of a loaded file, and the formats of R2b

- **Status:** **Proposed** (2026-11-26). Accepted when
  [Plan 0091](../plans/open/0091-more-document-formats.md) closes on real hardware. Pipec's
  decisions of 2026-11-24 (the roadmap row *File ingestion threat model*) and 2026-11-26 (the
  plan's *Pipec's decisions*) are its source.
- **Date:** 2026-11-26
- **Builds on:** [ADR 0034](0034-documents-and-reading-through-the-camera.md) (documents, and its
  deviations 8 and 13: the caps, the child process, the file checks),
  [ADR 0041](0041-reading-and-explaining-a-paper.md) (the OCR), [ADR 0023](0023-speech-to-text-model-and-decoding.md)
  (Whisper).
- **Amends:** ADR 0034 deviation 13 (an image holding a QR code or a barcode refused a PDF whole):
  it still does for a PDF with a text layer, and no longer for a photograph or a scanned PDF,
  whose code is never decoded (Pipec, 2026-11-26).
- **Delivers:** the threat model row 9b needs before more formats arrive, and the formats of R2b,
  row 9b of the [path](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory).

## Context

1. **A loaded file is untrusted input** parsed on the server. Today three formats enter (`.md`,
   `.txt`, a `.pdf` with a text layer), each checked: it must be what its extension says, it is
   capped in size and pages, and a PDF is parsed in a child process killed at 30 s, refused whole
   with active content or a code in an image (ADR 0034 deviations 8 and 13).
2. **A household keeps more.** Word and Excel files, CSV exports, photos and screenshots of papers,
   voice notes and recorded talks, and scanned PDFs (Pipec's own: 4 to 750 pages, no text layer).
   Each new parser is new attack surface: a ZIP bomb in an Office file, a macro, a decompression
   bomb in an image, a malformed media container, a PDF built to hang its renderer.
3. **The server already holds the readers** that turn them into text: the OCR of ADR 0041
   (RapidOCR, about 1 s per photograph) and Whisper `medium` (ADR 0023). A file is loaded with
   `iroko-admin docs add` with the server stopped (or in the alta's folder), so a long reading
   competes with nothing.

## Decision

### 1. One rule for every format: checked, capped, parsed apart, never executed

Every file passes, in order: its extension in a closed table; its size under its format's cap;
its bytes are what the extension says (magic bytes, and for an Office file its content types);
then its parser runs **in a child process** with a time limit, and its text is cleaned of control
and invisible characters (today's `clean_text`). Nothing of a file is ever executed, followed or
opened: no macro, no link, no embedded object, no formula evaluated, no code decoded. Every
refusal is a closed Spanish reason for the person at the terminal; nothing logs a file's text.

### 2. The table of formats

| Extension | Stored format | Reader | Size cap | Other caps | Refused |
|---|---|---|---|---|---|
| `.md`, `.txt` | `md`, `txt` | UTF-8 (today) | 10 MB | — | not UTF-8, binary |
| `.csv` | `csv` | standard library; UTF-8, else Windows-1252 (Excel's Spanish export); `;` or `,` | 10 MB | 20,000 rows | binary |
| `.docx` | `docx` | `python-docx`: paragraphs (headings kept as headings) and tables row by row | 10 MB | 100 MB unpacked, ratio 100 | `.doc`, `.docm`, a macro part, not a Word ZIP |
| `.xlsx` | `xlsx` | `openpyxl`, read-only, cached values (no formula is evaluated), each sheet row by row with its headers | 10 MB | 100 MB unpacked, ratio 100, 20,000 rows | `.xls`, `.xlsm`, a macro part, not an Excel ZIP |
| `.pdf` with a text layer | `pdf` | `pypdf` (today) | 300 MB | 200 pages | active content; a QR code or a barcode in an image (ADR 0034 deviation 13 stands) |
| `.pdf` with no text layer (scanned) | `pdf` | each page rendered by `pypdfium2` at 200 DPI, read by the OCR | 300 MB | 1,000 pages | active content |
| `.jpg`, `.jpeg`, `.png` | `image` | the OCR, the image as taken | 20 MB | 40 megapixels | `.heic` (its only Python reader bundles the GPL x265 encoder: «guárdala como JPG») |
| `.mp3`, `.m4a`, `.ogg`, `.opus`, `.wav` | `audio` | PyAV decodes, Whisper transcribes | 500 MB | 60 minutes | no audio stream |
| `.mp4`, `.mov` | `video` | PyAV decodes the audio track only (no frame is decoded), Whisper transcribes | 500 MB | 60 minutes | no audio stream |

The table is closed: a format outside it is «Ese formato todavía no lo leo.».

### 3. A code in a photograph or a scanned page is never decoded, and does not refuse the file

A photograph or a scanned page is read by the OCR, which reads printed characters only: a QR code
or a barcode in it is never decoded, followed or stored (Pipec, 2026-11-26: nearly every bill
carries one). A PDF with a text layer keeps ADR 0034 deviation 13: a code in one of its images
refuses it (Pipec, the same day). Reading a code's content stays out (the roadmap's QR row).

### 4. Time and memory in the child

A child is killed at its format's limit: 30 s for text, Office and a text-layer PDF (today's);
5 s per page plus 60 s for a scanned PDF; twice the media's duration plus 120 s for audio and
video. A Pillow and OpenCV pixel limit and pypdf's decompression limits are set in every child
that decodes. A long reading prints its progress (pages or minutes) to the terminal.

### 5. What is stored

The text only, cut into sections as today, with the format of the table; the transformation is
`original` for `md` and `txt` and `extracted` for every other format (ADR 0034 deviation 4). The
file itself, a frame of a video and an audio's samples are never stored.

## Alternatives considered

- **Read a code's content now:** a QR code may carry a link or an instruction; it waits for its own
  row, as before.
- **Accept `.heic` with `pillow-heif`:** its wheels bundle `x265` (GPL); never GPL (ADR 0034
  decision 1). An iPhone exports JPG.
- **Read scanned pages from the images pypdf finds:** scanned PDFs often use JBIG2 or CCITT images
  that need external decoders; rendering the page with PDFium reads them all.
- **Parse in the server's own process:** a parser crash or a bomb would take the server down;
  the child is the boundary, as for PDFs today.
- **The vision model for photographs:** 70 to 120 s each on the laptop; the OCR reads print in
  about 1 s (ADR 0041).

## Consequences

### Positive

- The household's usual files become documents, with their source named, under the same levels
  and guards; Pipec's scanned PDFs are readable at last.
- One threat model for every format, so the next format adds a row, not a design.

### Negative

- Three dependencies more (`python-docx`, `openpyxl`, `pypdfium2`), to vet and keep current; PDFium
  is a large C++ parser, run only in a child.
- A long scanned PDF or a recording takes minutes to load; handwriting stays partial.
- A text-layer PDF with the SII stamp (a PDF417 barcode) is still refused (Pipec's choice).

## Review

Revisit when a format the household needs is refused, when a parser has a known vulnerability,
or when a text-layer bill's stamp should be accepted.
