"""Bounded, per-file upload reads shared by every multipart endpoint.

`UploadFile.read()` with no argument loads the whole client-controlled body
into memory before any size decision runs — the exact gap Plan 0034 closes.
This module owns the one safe way to read an untrusted file: never more than
`limit + 1` bytes, regardless of what the client claims or sends.

The raw request body itself is bounded earlier, at the ASGI layer, by
Starlette's `RequestBodyLimitMiddleware` (registered in `main.py`). This
module is the second, per-file layer beneath it — required because one
request (`/transcribe`) can legitimately carry two files with different
budgets, which a single raw-body ceiling cannot express.
"""

from fastapi import UploadFile

from server.exceptions import UploadTooLargeError


async def read_limited_upload(upload: UploadFile, *, limit: int) -> bytes:
    """Read at most `limit + 1` bytes from an untrusted upload.

    Args:
        upload: Multipart file part to read. Its `filename` is
            client-controlled metadata and is never inspected here.
        limit: Maximum number of bytes this file may contain.

    Returns:
        The file's full contents when they are within `limit`. Emptiness is
        a semantic decision for the caller, not this function.

    Raises:
        UploadTooLargeError: If the file contains more than `limit` bytes.
            The oversized payload itself is never included in the error.
    """
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise UploadTooLargeError(limit)
    return data
