"""What a PDF may not carry before its text is read (Pipec, 2026-11-24, Plan 0088 Task B10).

A loaded document is only ever read as text, and nothing in it is executed, followed or opened.
Still, a PDF that carries active content is refused whole, so the parser is never asked to touch
it: JavaScript, an action run on opening or on a page, an embedded or attached file, a link or
any other action annotation, a form with a signature field or an XFA form, rich media, and an
image holding a QR code or a barcode. Run only inside the extraction's child process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from pypdf import PageObject, PdfReader
    from pypdf.generic import DictionaryObject

__all__ = ["holds_active_content", "holds_codes"]

_CATALOG_KEYS: Final = frozenset({"/OpenAction", "/AA", "/Perms"})
_NAME_TREES: Final = frozenset({"/JavaScript", "/EmbeddedFiles"})
_ANNOTATIONS: Final = frozenset(
    {"/Link", "/FileAttachment", "/RichMedia", "/Screen", "/Movie", "/Sound", "/3D"}
)
_ACTIONS: Final = frozenset(
    {"/URI", "/Launch", "/JavaScript", "/GoToR", "/GoToE", "/SubmitForm", "/ImportData"}
)


def _signed_form(catalog: DictionaryObject) -> bool:
    form = catalog.get("/AcroForm")
    if form is None:
        return False
    form = form.get_object()
    if "/XFA" in form:
        return True
    return any(field.get_object().get("/FT") == "/Sig" for field in form.get("/Fields", []))


def _active_annotation(annotation: DictionaryObject) -> bool:
    if annotation.get("/Subtype") in _ANNOTATIONS or "/AA" in annotation:
        return True
    if annotation.get("/FT") == "/Sig":
        return True
    action = annotation.get("/A")
    return action is not None and action.get_object().get("/S") in _ACTIONS


def _active_page(page: PageObject) -> bool:
    if "/AA" in page:
        return True
    return any(_active_annotation(a.get_object()) for a in page.get("/Annots", []) or [])


def holds_active_content(reader: PdfReader) -> bool:
    """Whether the PDF carries scripts, actions, files, links, signatures or rich media.

    Args:
        reader: The opened, not encrypted PDF.

    Returns:
        ``True`` when any closed kind of active content is present.
    """
    catalog = cast("DictionaryObject", reader.trailer["/Root"].get_object())
    if _CATALOG_KEYS & set(catalog.keys()) or _signed_form(catalog):
        return True
    names = catalog.get("/Names")
    if names is not None and _NAME_TREES & set(cast("DictionaryObject", names.get_object()).keys()):
        return True
    return any(_active_page(page) for page in reader.pages)


def holds_codes(reader: PdfReader) -> bool:
    """Whether an image of the PDF holds a QR code or a barcode (OpenCV's detectors).

    Args:
        reader: The opened, not encrypted PDF.

    Returns:
        ``True`` at the first image with a code; an image OpenCV cannot decode is skipped.
    """
    import cv2  # noqa: PLC0415 - heavy, and needed only when a PDF is loaded
    import numpy as np  # noqa: PLC0415

    qr = cv2.QRCodeDetector()
    barcode = cv2.barcode.BarcodeDetector()
    for page in reader.pages:
        for image in page.images:
            pixels = cv2.imdecode(np.frombuffer(image.data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if pixels is None:
                continue
            if qr.detect(pixels)[0] or barcode.detect(pixels)[0]:
                return True
    return False
