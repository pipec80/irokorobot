"""What a PDF may not carry before its text is read (Pipec, 2026-11-24, Plan 0088 Task B10).

A loaded document is only ever read as text, and nothing in it is executed, followed or opened.
Still, a PDF that carries active content is refused whole, so the parser is never asked to touch
it: JavaScript, an action run on opening or on a page, an embedded or attached file, a link or
any other action annotation, a form with a signature field or an XFA form, rich media, and an
image holding a QR code or a barcode. Run only inside the extraction's child process.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final, cast
import warnings

if TYPE_CHECKING:
    from pypdf import PageObject, PdfReader
    from pypdf.generic import DictionaryObject

__all__ = ["MAX_IMAGES", "MAX_IMAGE_PIXELS", "holds_active_content", "holds_codes"]

#: Pixels one image may declare before decoding refuses it (about 20 MB of gray), and images
#: inspected at most in one PDF.
MAX_IMAGE_PIXELS: Final = 20_000_000
MAX_IMAGES: Final = 400

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


def _declared_images(reader: PdfReader) -> list[int]:
    """The declared pixel count (``/Width`` times ``/Height``) of every image XObject, page by page.

    Read from the dictionaries only: no image is decoded. An image with no usable size counts as
    over any budget.
    """
    sizes = []
    for page in reader.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        objects = cast("DictionaryObject", resources.get_object()).get("/XObject")
        if objects is None:
            continue
        for reference in cast("DictionaryObject", objects.get_object()).values():
            xobject = cast("DictionaryObject", reference.get_object())
            if xobject.get("/Subtype") != "/Image":
                continue
            width, height = xobject.get("/Width"), xobject.get("/Height")
            if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                sizes.append(width * height)
            else:
                sizes.append(-1)
    return sizes


def holds_codes(
    reader: PdfReader, *, max_images: int = MAX_IMAGES, max_pixels: int = MAX_IMAGE_PIXELS
) -> bool:
    """Whether an image of the PDF holds a QR code or a barcode (OpenCV's detectors).

    Fails closed. Before anything is decoded, every image XObject of a page is counted and sized
    from its dictionary: more than *max_images* images, or one over *max_pixels* or with no usable size,
    counts as holding a code (a household document never needs them). Then each image is decoded
    with OpenCV's and PIL's own pixel limits set; one that does not decode counts as holding a
    code too, and so does the image past *max_images* in that walk, which also finds the inline
    images and the ones inside forms the first count does not see.

    Args:
        reader: The opened, not encrypted PDF.
        max_images: How many images a PDF may hold.
        max_pixels: The declared pixels one image may have.

    Returns:
        ``True`` when the PDF is refused: a code found, or an image too many, too large or
        undecodable.
    """
    sizes = _declared_images(reader)
    if len(sizes) > max_images or any(size < 0 or size > max_pixels for size in sizes):
        return True
    os.environ["OPENCV_IO_MAX_IMAGE_PIXELS"] = str(max_pixels)
    import cv2  # noqa: PLC0415 - heavy, and needed only when a PDF has images
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    Image.MAX_IMAGE_PIXELS = max_pixels
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    qr = cv2.QRCodeDetector()
    barcode = cv2.barcode.BarcodeDetector()
    seen = 0
    try:
        for page in reader.pages:
            # Inline images and images inside forms are not among the page's own XObjects: every
            # image pypdf finds is counted again, before its data is touched.
            for image in page.images:
                seen += 1
                if seen > max_images:
                    return True
                data = np.frombuffer(image.data, dtype=np.uint8)
                pixels = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
                if pixels is None or qr.detect(pixels)[0] or barcode.detect(pixels)[0]:
                    return True
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, MemoryError, ValueError):
        return True
    return False
