# 0091 — More document formats (R2b): Office, photos, voice and video, scanned PDFs

> **Status:** **`Ready`** (2026-11-26, approved by Pipec with every decision answered the same day).
> Execution runs in a new session, on its own branch (`feat/0091-more-document-formats`), one PR.
>
> **Source:** row **9b** of the
> [path to the finish line](../../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory)
> (R2b, Pipec 2026-11-23), the cross-cutting row *File ingestion threat model* (Pipec, 2026-11-24:
> an ADR before more formats arrive), and Pipec's decisions of 2026-11-26 (below). Writes
> **ADR 0042** (the threat model of a loaded file), already drafted as
> [`docs/adr/0042-the-threat-model-of-a-loaded-file.md`](../../adr/0042-the-threat-model-of-a-loaded-file.md).
> Adds the scanned PDF, which the roadmap had left to R4: since Plan 0090 the OCR reads a page in
> seconds (Pipec, 2026-11-26).
>
> **Goal.** `iroko-admin docs add` (and the alta's `documents/` folder) accepts the files a
> household keeps — Word, Excel, CSV, photos and screenshots of papers, voice notes and recorded
> talks, and scanned PDFs — as documents with their text, under one threat model: checked, capped,
> parsed in a child process, never executed. Asked about by voice exactly as today's documents.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md`,
> `AGENTS.md` and every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans` (or `superpowers:subagent-driven-development` for the parallel
> tasks), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion`, `superpowers:requesting-code-review` and
> `superpowers:receiving-code-review` for Task 9, `superpowers:finishing-a-development-branch`.
> Review agents and parallel workers run on `sonnet` and read `.claude/` in full first. **Pipec's
> rules win over the skills:** one plain branch from `main`, never a git worktree; one commit per
> task; every test seen RED for the stated reason first; a discovery the goal does not need is
> recorded, not built. **The Bash tool loses backslashes and non-ASCII characters in heredocs:**
> edit with the Write and Edit tools, or a Python script written with Write. Commit titles:
> Conventional Commits, at most 72 characters; never pipe `git commit`; `git add` with explicit
> paths. Suite with `MEMORY_ENABLED=false`, as CI. Never `uv sync` without `--extra cuda`. No
> `just gate` while Pipec rehearses. Before pushing: `pyright` and `mypy` over the project,
> `uv run ruff check .`, `uv run ruff format --check .`, `ruff` with explicit paths on `scripts/`.
> A new runtime dependency is tried first in an ephemeral layer (`uv run --with …`), never in the
> real `.venv`, then added with `uv add` from `server/`.

## Required reading

[Implementation guardrails](../../architecture/implementation-guardrails.md);
[ADR 0034](../../adr/0034-documents-and-reading-through-the-camera.md) (decisions 1, 4, 6 and
deviations 4, 8, 13); [ADR 0041](../../adr/0041-reading-and-explaining-a-paper.md) (the OCR);
[ADR 0042](../../adr/0042-the-threat-model-of-a-loaded-file.md) (this plan's spec);
[ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md) (the cheapest schema change);
the operator manual's `iroko-admin docs` section.

## What the code does today (verified 2026-11-26 on `main` at `40466fe`)

Re-verify each item on `main` in Task 0; **stop and report** if one is false.

1. `memory/document_extract.py`: `EXTRACTORS` maps `.md`, `.txt`, `.pdf` to their extractor;
   `extract_text(path)` refuses an unknown extension (`_UNKNOWN_FORMAT`) and any file over
   `MAX_FILE_BYTES` (10 MB) before its extractor runs. A PDF must hold `%PDF-` in its first
   kilobyte, then runs in a child (`python -I -m server.memory.document_extract FILE`) killed at
   `EXTRACT_TIMEOUT_S` (30 s), with pypdf's decompression limits set. The child refuses encrypted
   (exit 3), over `MAX_PAGES` 200 (exit 4), active content **or a code in an image** (exit 5,
   `pdf_inspect.holds_active_content` / `holds_codes`, both checked **before** the text is read),
   and no text at all (exit 3). `clean_text` strips control and invisible characters.
2. `ExtractedText(format, pages)`; `DocumentFileFormat = Literal["md", "txt", "pdf"]`
   (`document_extract.py`), `DocumentFormat = Literal["md", "txt", "pdf", "camera"]`
   (`document_store.py`), and `migration_023_documents.sql` holds
   `format TEXT NOT NULL CHECK (format IN ('md', 'txt', 'pdf', 'camera'))` on `document_sources`,
   with the trigger `document_sources_scope_locked` and the index
   `document_sources_loaded_by_idx`. Migration 022 rebuilt `admin_audit` the same way this plan
   must rebuild `document_sources` (the runner turns foreign keys off for such a migration).
3. `memory/admin_docs.py` `run_docs` (`docs add / list / remove`), audited, shows the sections
   and the first lines before `SI`; `memory/seed_run.py` loads the alta's `documents/` folder
   through `extract_text` too.
4. `vision/ocr_reader.py`: `decode_frame(image) -> np.ndarray`, the private `_read_lines(frame)`
   that loads RapidOCR once, and the async `ocr_read_text(image)`; `_clean` drops other scripts.
5. `stt.py`: `run_whisper(model, audio, options, hotwords)` takes WAV bytes (16 kHz, mono,
   int16); `_get_model()` loads `settings.whisper_model` on `settings.whisper_device`. PyAV
   (`av`, constrained `<19`) is installed with faster-whisper.
6. Tests: `tests/integration/test_document_extract.py`, `tests/integration/test_admin_docs.py`,
   `tests/unit/test_document_sections.py`, fixtures in `tests/fixtures/documents/`.

## Pipec's decisions (2026-11-26)

1. **Write the plan with the scanned PDF in it** (moved here from R4: the OCR made it cheap).
2. **A code in a photograph or a scanned page is never decoded and does not refuse the file:** the
   OCR reads the printed text only. Rejected: refusing them whole as today.
3. **A text-layer PDF keeps ADR 0034 deviation 13:** a code in one of its images still refuses it,
   so an electronic bill with the SII stamp (a PDF417 barcode) stays refused. Rejected: the same
   rule for every PDF.
4. **No `.heic`:** its only Python reader bundles the GPL `x265`; the robot asks for a JPG.
   Rejected: researching another reader in this plan.
5. **Audio and video: at most 60 minutes and 500 MB**, the video's audio track only. Rejected:
   15 min / 100 MB and 3 h / 2 GB.
6. **Scanned PDF: at most 1,000 pages and 300 MB**, with the progress shown. Rejected: 200 pages.
7. **Row 10 (the home server) stays before the finish line**, after row 9c.

The executor's calls, for Pipec's review (from ADR 0042 decision 2): CSV read as UTF-8, else
Windows-1252 (Excel's Spanish export), with `;` or `,`; `.doc`, `.xls`, `.docm`, `.xlsm` refused;
`xlsx` cached values only; 20,000 rows per sheet or CSV; images up to 20 MB and 40 megapixels.

## Global constraints

- The API contract and the robot are unchanged; this plan touches the server's document loading
  and `iroko-admin` only. Nothing runs while the server serves a turn (`docs add` needs the server
  stopped, as today).
- Every parser runs in the child, with its time limit (ADR 0042 decision 4); the parent never
  parses a file's content. No file, frame or audio sample is stored; only the text.
- Licences read before `uv add`: permissive only, never AGPL or GPL (ADR 0034 decision 1).
  Candidates: `python-docx` (MIT), `openpyxl` (MIT), `pypdfium2` (Apache-2.0 / BSD-3); `av` and
  `rapidocr` are installed.
- Nothing logs a file's text; refusals are closed Spanish reasons in neutral tuteo.
- Invented canaries only in tests and fixtures; real files of Pipec's stay out of the repository
  and the hardware record holds outcomes only.

## Review focus

1. **A file that is not what it says:** a `.docx` that is a renamed `.exe`, a `.png` that is a PDF,
   a `.mp3` with no audio stream: refused before a parser runs.
2. **A bomb:** an Office ZIP that unpacks to gigabytes, an image of 1 gigapixel, a scanned PDF
   with 10,000 pages, a media file that claims 10 hours: refused by its cap or killed by the child's
   time limit; the server process is never touched.
3. **Something active:** a macro part in a `.docx` (`vbaProject.bin`), an external link or an
   embedded object, a formula: never executed; a macro-enabled file refused.
4. **The code rule:** a scanned bill with a barcode loads its text; a text-layer PDF with a barcode
   is still refused (decision 3).
5. **A long load:** the 750-page PDF or a 60-minute recording shows progress and finishes, or is
   killed cleanly with its reason; `iroko-admin` never hangs.

## Parallel work

| Can run at the same time | Files | Must wait for |
|---|---|---|
| Task 4 (Office and CSV) | `memory/document_office.py`, its test | Task 3 |
| Task 5 (photographs) | `memory/document_image.py`, `vision/ocr_reader.py`, their tests | Task 3 |
| Task 6 (scanned PDF) | `memory/document_scanned.py`, its test | Task 3 and Task 5's `ocr_lines` |
| Task 7 (voice and video) | `memory/document_media.py`, its test | Task 3 |

Each worker writes only its task's files; the main session wires the table (`document_extract`)
in Task 8 and makes every commit, one per task, in task order.

---

## Permitted files

Paths under `server/src/server/` unless they start with `tests/`, `docs/` or the root; a need
outside the list stops the plan for Pipec.

| Task | Files |
|---|---|
| 1 | root `pyproject.toml`, `server/pyproject.toml`, `uv.lock` |
| 2 | `memory/migration_024_document_formats.sql` (new), `memory/document_store.py` (the literal), `memory/document_extract.py` (the literal); `tests/integration/test_documents_schema.py` |
| 3 | `memory/document_gate.py` (new), `memory/document_extract.py` (the child's dispatch and progress); `tests/unit/test_document_gate.py` (new), `tests/integration/test_document_extract.py` |
| 4 | `memory/document_office.py` (new); `tests/unit/test_document_office.py` (new) |
| 5 | `memory/document_image.py` (new), `vision/ocr_reader.py` (a public sync `ocr_lines`); `tests/unit/test_document_image.py` (new), `tests/unit/test_ocr_reader.py`, `tests/slow/test_ocr_reading.py` |
| 6 | `memory/document_scanned.py` (new), `memory/document_extract.py` (the scanned branch), `memory/pdf_inspect.py` (only if the order of checks needs it); `tests/unit/test_document_scanned.py` (new), `tests/slow/test_scanned_pdf.py` (new) |
| 7 | `memory/document_media.py` (new); `tests/unit/test_document_media.py` (new), `tests/slow/test_media_transcript.py` (new) |
| 8 | `memory/document_extract.py` (the table), `memory/admin_docs.py` (progress and the new reasons), `memory/seed_run.py` (only the literal); `tests/integration/test_admin_docs.py`, `tests/integration/test_document_extract.py`, `tests/fixtures/documents/` (generated canaries) |
| 10 | `docs/runbooks/operator-manual.md`, `docs/architecture/current-state.md`, the Archify diagrams if they show document loading (validate then deliver), `docs/evals/0091-formats-acceptance.md` (new), ADR 0042 (accepted), ADR 0034 (an *Amended by ADR 0042* note), the roadmap (rows 9b and the threat-model row), the plan board, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, Pipec's local `docs/roadmap/tabla-tareas.md` |

**Rollback boundary.** Before the merge, the branch. After it, a revert plus migration 024's own
down path is not provided: the migration only widens a `CHECK`, so rows of the new formats would
have to be removed first (`iroko-admin docs remove`); the revert of the code is otherwise clean.

---

## Task 0: Re-audit and baseline

- [ ] `git switch main && git pull`, create `feat/0091-more-document-formats`.
- [ ] Verify items 1 to 6 above; confirm how migrations are registered (file name or list in
  `db.py`) and whether an architecture guard limits what `memory/` may import from `vision/`.
  **Stop and report** if an item is false.
- [ ] Baseline: the CI selection, `pyright`, `mypy`, `ruff`; record the counts in Task 1's commit.

## Task 1: The three readers, licences first

- [ ] Read the licence and last release of `python-docx`, `openpyxl` and `pypdfium2` (code and
  bundled binaries: PDFium is BSD-3); refuse any AGPL, GPL or non-commercial term. Try each in an
  ephemeral layer (`uv run --with …`) on one canary file. Record name, version and licence in
  ADR 0042's *Decision 2* table as a note.
- [ ] `uv add` them from `server/`; `uv sync --all-packages --all-groups --extra cuda`; `just audit`.

## Task 2: The new formats in the schema

- [ ] **RED** (`tests/integration/test_documents_schema.py`): inserting a source of each format
  `docx`, `xlsx`, `csv`, `image`, `audio`, `video` succeeds after migration 024; `exe` is refused
  by the `CHECK`; every row, index, trigger and foreign key of `document_sources` survives the
  rebuild (a section of an existing source still cascades on delete).
- [ ] **GREEN:** `migration_024_document_formats.sql` rebuilds `document_sources` with the wider
  `CHECK`, as migration 022 rebuilt `admin_audit`; the two `Literal`s widen to match.

## Task 3: The gate and the child's dispatch (ADR 0042 decisions 1, 2, 4)

**Produces:** `memory/document_gate.py`:

```python
@dataclass(frozen=True)
class FormatRule:
    stored: DocumentFormat      # "docx", "xlsx", "csv", "pdf", "image", "audio", "video", ...
    max_bytes: int
    child: bool                 # parsed in the child process
def rule_for(path: Path) -> FormatRule            # DocumentRefusedError(_UNKNOWN_FORMAT)
def check_file(path: Path, rule: FormatRule) -> None  # size, magic bytes, ZIP checks
```

Magic bytes: PDF `%PDF-` (today), ZIP `PK\x03\x04` with `[Content_Types].xml` naming the Word or
Excel main part, JPEG `FF D8 FF`, PNG `89 50 4E 47`, media by PyAV's probe in the child. ZIP
checks without extracting: total uncompressed ≤ 100 MB, every member's ratio ≤ 100, no
`vbaProject.bin` or other macro part, no member name with `..` or an absolute path. The child is
`python -I -m server.memory.document_extract --format <stored> FILE`, killed at its format's limit
(30 s; 5 s per page + 60 s for a scanned PDF; twice the duration + 120 s for media), writing its
pages as JSON to stdout and progress lines (`progress <done> <total>`) to stderr.

- [ ] **RED** (`tests/unit/test_document_gate.py`): each extension maps to its rule and cap from
  ADR 0042's table; `.heic` is refused with «Esa foto está en HEIC; guárdala como JPG y vuelve a
  intentarlo.»; `.doc`, `.xls`, `.docm`, `.xlsm` refused; a renamed file (a PNG named `.docx`, a
  text named `.jpg`) refused with `_NOT_WHAT_IT_SAYS`; a ZIP bomb (a member that declares 200 MB),
  a high-ratio member, a macro part and a `../` member each refused; files over each cap refused
  without being opened.
- [ ] **GREEN:** the gate; `extract_text` asks the gate first, then the extractor.

## Task 4: Word, Excel and CSV (`memory/document_office.py`)

**Produces:** `docx_pages(path) -> tuple[str, ...]`, `xlsx_pages(path) -> tuple[str, ...]`,
`csv_pages(path) -> tuple[str, ...]`, run in the child.

- [ ] **RED:** a canary `.docx` built in the test with `python-docx` (a heading «Garantía
  qqlavaqq», two paragraphs, a table «Pieza | Precio») gives a page whose heading is a Markdown
  heading and whose table rows read «Pieza: filtro; Precio: $9.990»; an `.xlsx` built with
  `openpyxl` (two sheets, a header row, a formula cell) gives one page per sheet, each row with its
  headers, the formula's cached value and never the formula; a CSV in Windows-1252 with `;` and
  «Año;Monto» reads its accents right; a sheet or CSV past 20,000 rows is refused; an empty file is
  `_EMPTY`.
- [ ] **GREEN:** the three readers (`openpyxl.load_workbook(read_only=True, data_only=True,
  keep_links=False)`).

## Task 5: Photographs (`memory/document_image.py`)

**Consumes / produces:** `vision/ocr_reader.ocr_lines(frame: np.ndarray) -> list[str]` (the
public, synchronous form of `_read_lines` plus `_clean`; `ocr_read_text` calls it);
`image_pages(path) -> tuple[str, ...]`, run in the child with Pillow's and OpenCV's pixel limits
(40 megapixels).

- [ ] **RED:** with a fake engine, a canary PNG gives its lines; an image over 40 megapixels and an
  undecodable one are refused; **an image holding a barcode is read, not refused** (decision 2);
  nothing read is `_NO_TEXT_IN_IMAGE` («No encontré texto en esa foto.»). The slow test reads a
  canary card with the real OCR.
- [ ] **GREEN:** the reader.

## Task 6: Scanned PDF (`memory/document_scanned.py`)

**Produces:** `scanned_pages(path, *, max_pages: int = 1000, dpi: int = 200,
progress: Callable[[int, int], None]) -> tuple[str, ...]`: each page rendered by `pypdfium2`,
read by `ocr_lines`.

- [ ] **RED:** in the child's PDF branch, the checks run in this order: encrypted → active content
  (refused whole, always) → text layer: if any page has text, today's path (`MAX_PAGES` 200 and
  `holds_codes`, decision 3); if none, the scanned path (`max_pages` 1,000, no `holds_codes`,
  decision 2). With a fake renderer and OCR: 3 pages give 3 pages of text and 3 progress calls; a
  1,001-page PDF is refused with «Ese PDF escaneado pasa de 1.000 páginas; no lo leo.»; a scanned
  PDF with a barcode on a page loads; a text-layer PDF with a barcode is still refused. The slow
  test builds a two-page image-only PDF with Pillow (canary text drawn) and reads it.
- [ ] **GREEN:** the branch and the reader; a PDF up to 300 MB passes the gate.

## Task 7: Voice notes and video (`memory/document_media.py`)

**Produces:** `media_pages(path, *, max_seconds: int = 3600,
progress: Callable[[int, int], None]) -> tuple[str, ...]`: PyAV opens the container, refuses one
with no audio stream or a duration over `max_seconds`, decodes **only the audio stream** resampled
to 16 kHz mono int16, and Whisper (`stt._get_model`, `stt.run_whisper`, the server's own decode
options) transcribes it; one line per segment, Whisper's known-hallucination filter applied.

- [ ] **RED:** with a fake model: a canary WAV gives its segments as lines; a video gives the same
  from its audio track and no frame is ever decoded (the decoder is asked for audio only); no
  audio stream → «Ese archivo no tiene sonido que pueda transcribir.»; over 60 minutes → «Esa
  grabación pasa de 60 minutos; no la leo.»; progress is reported in minutes. The slow test
  synthesises a canary sentence with Piper, muxes it into an `.m4a` and an `.mp4` with PyAV, and
  transcribes both with the real Whisper.
- [ ] **GREEN:** the reader.

## Task 8: The table, `iroko-admin` and the alta's folder

- [ ] **RED** (`test_admin_docs.py`, `test_document_extract.py`): `docs add` of each canary format
  shows its sections and first lines and stores it with its format; a long load prints
  «Leyendo… página 3 de 3» (or minutes) as it goes; each refusal prints its closed reason and
  writes one audit row with no content; the alta's folder loads a `.docx` and a `.jpg`.
- [ ] **GREEN:** `EXTRACTORS` gains every row of ADR 0042's table; `admin_docs` streams the child's
  progress lines (`subprocess.Popen`, stderr read line by line; the time limit still kills it).

## Task 9: Verification and review

- [ ] The CI selection, `just gate` (not while Pipec rehearses), the slow tests of Tasks 5-7,
  `pyright`, `mypy`, `ruff`, the reserved-terms guard, `just audit`; a `sonnet` review over the
  five review-focus points; fixes with `superpowers:receiving-code-review`.

## Task 10: Hardware acceptance, and close

Pipec at the laptop, the server stopped, one step per message. Pipec's own files stay out of the
repository; the record holds outcomes only. With `iroko-admin docs add`:

1. A Word file and an Excel file of Pipec's: stored, sections shown.
2. A CSV exported from Excel: accents right.
3. A photo of a paper taken with the phone (JPG) that carries a barcode: its text stored.
4. A WhatsApp voice note (`.opus`) and a short `.mov`: transcribed.
5. Pipec's 4-page scanned PDF: read with progress; then his 750-page one if he wants (about 30 to
   50 minutes).
6. Then, with the server up, one voice question per kind («¿qué dice mi documento … sobre …?»):
   answered by quotation, as today.

Record in `docs/evals/0091-formats-acceptance.md` (times and outcomes); update the documents of
Task 10's row; ADR 0042 `Accepted`; the plan to `completed/`.

## Completion criteria

1. Every format of ADR 0042's table loads a canary through `iroko-admin docs add` and the alta's
   folder, and is found by a document question; every refusal of the table has its test.
2. The gate refuses a renamed file, a bomb, a macro file and a `.heic` before any parser runs.
3. A photograph or a scanned page with a code loads; a text-layer PDF with a code is refused.
4. A scanned PDF up to 1,000 pages and a recording up to 60 minutes load with progress.
5. The CI selection, `just gate`, the slow tests, the type checkers, `ruff`, `just audit` and the
   reserved-terms guard pass; Task 10's script passes on hardware; ADR 0042 accepted.

## Non-goals

Reading a QR code's or a barcode's content; `.heic`; `.doc`, `.xls`, macro-enabled Office files;
describing or interpreting an image (never a medical one); handwriting beyond what the OCR reads
(R4); keeping the original files; loading documents by voice or remotely; the figures spoken by
locale (its own row); any change to the camera reading of Plan 0090, the API or the robot.

## Self-review (2026-11-26)

- **Spec coverage:** ADR 0042 decisions 1 to 5 map to Tasks 3 (gate, caps, child, times), 4-7
  (the readers), 6 (decisions 2 and 3, the code rule), 2 (stored formats) and 8 (progress).
  Pipec's decisions 1 to 6 each have a test (Tasks 3, 5, 6, 7); decision 7 is the roadmap's.
- **Interfaces:** `FormatRule`, `rule_for`, `check_file` (Task 3) are used by Tasks 4-8;
  `ocr_lines` (Task 5) by Task 6; `progress(done, total)` by Tasks 6, 7, 8.
- **Proportion:** signatures, caps and test assertions only; no reader's body is written here.
