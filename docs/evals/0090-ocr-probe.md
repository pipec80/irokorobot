# Plan 0090 — the isolated OCR probe (Task 1 record)

> **Status:** Recorded 2026-11-26, Pipec at the laptop. Numbers and outcomes only: no read text,
> no value of a real paper and no photograph enters this file. The photographs stay in the ignored
> `.superpowers/sdd/0090/images/` and are deleted at the plan's close.

## Setup

- **Machine:** the development laptop, Windows 11, 15.7 GiB of RAM (about 4.1 GB free during the
  run). The server, the robot and Ollama were **off**: the reader was proved alone (amended D-1).
- **Engine:** RapidOCR **3.10.0** (code Apache-2.0; its PP-OCR models derive from PaddleOCR's,
  Apache-2.0, redistributed under the same terms; no AGPL, GPL or non-commercial term found), with
  its default models: PP-OCRv6 small, whose recognition covers Spanish (`es`). It ran from an
  ephemeral layer, `uv run --with rapidocr==3.10.0`, on the installed `onnxruntime` 1.32.0; the
  `.venv` and the lock did not change. The `latin` recognition model is refused for PP-OCRv6.
- **Tool:** `scripts/ocr_probe.py`, one JSON line per read; each photograph read as taken and with
  the contrast step (grayscale and CLAHE, OpenCV).
- **Photographs:** taken with the robot's capture path (`robot.camera_capture`), the room's
  ordinary light. The invented bill of Plan 0089's sheet («qqluzqq», total and due date), the
  canary list «Lista qqcanarioqq: pan, té, fósforos» written by Pipec in block capitals in blue
  ballpoint and in graphite (the graphite sheet has print on its back, which shows through), and,
  as an extra real case, Pipec's own utility bill (outcomes only).

## The three photographs of the plan (640x480, the robot's size today)

| Photograph | Variant | Read ms | Lines | Bill exact | Canary words |
|---|---|---:|---:|---|---:|
| Invented bill | as taken | 1075 | 4 | yes | — |
| Invented bill | contrast | 784 | 4 | yes | — |
| Blue ballpoint | as taken | 772 | 1 | — | 2/5 |
| Blue ballpoint | contrast | 628 | 2 | — | 3/5 |
| Graphite | as taken | 686 | 2 | — | 1/5 |
| Graphite | contrast | 835 | 3 | — | 2/5 |

- **Load:** 8.4 s once (the models load on the first call), with no measurable drop of free RAM.
- **Handwriting:** the words a person reads are mostly there with one or two wrong letters; the
  canary «qq» written by hand is read as other symbols, which is most of the missed count. The
  contrast step adds one word on each note, and on the graphite sheet it also reads the mirrored
  print showing through from the back. The multilingual model once returned two Chinese
  characters on the graphite note.

## The real bill (extra, outcomes only)

| Frame | Size | Labels («Total a pagar», «Vencimiento») | Total to pay | Due date |
|---|---|---|---|---|
| Whole bill | 640x480 | partly | not read | not read |
| Closer, framed with a live preview | 640x480 | read | not read | not read |
| Same framing, as taken | **1280x720** | read | **exact** | **exact** |
| Same framing, contrast step | 1280x720 | read | **one digit wrong** | exact |

The webcam supports 1280x720, the image contract's maximum; `robot.camera_capture` requests no
size, so it gets 640x480. At that size a utility bill's figures are a few pixels high. The limit
for a real paper was the frame, not the reader.

## Pipec's choice (2026-11-26)

1. **The reader:** RapidOCR with the contrast step (against RapidOCR alone, and against keeping
   the vision model). It enters with `uv add` in Task 3.
   **Amended the same day:** the first check of the real bill searched the as-taken and the
   contrast outputs together. Read apart (Task 3), the contrast step misread one digit of the
   total; as taken, both figures are exact. Pipec dropped the contrast step: a wrong figure read
   aloud is worse than one handwritten word fewer. **The reader reads the frame as taken.**
2. **The camera:** the robot requests 1280x720 in this plan (Task 3), within the image contract,
   with the face check and the frame's size checked on hardware (Task 9).

## Compared with the vision model (Plan 0089's bench)

The vision model read printed text exactly too, in **70 to 120 s** per frame on this laptop; the
OCR reads it in about **1 s**. Neither was measured here against the other on the same frames
(left out by the amendment of 2026-11-26).
