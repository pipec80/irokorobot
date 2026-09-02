"""Unit tests for bounded upload reads (Plan 0034).

`UploadFile.read()` with no limit loads the whole client-controlled body into
memory before any size check runs. `read_limited_upload` reads at most
`limit + 1` bytes, so an oversized upload is detected without ever holding
more than one byte over budget in memory.
"""

import io

from fastapi import UploadFile
import pytest
from server.exceptions import UploadTooLargeError
from server.uploads import read_limited_upload


def _upload(data: bytes) -> UploadFile:
    """Build a real UploadFile backed by an in-memory buffer."""
    return UploadFile(file=io.BytesIO(data), filename="probe.bin")


@pytest.mark.unit
async def test_a_file_within_the_limit_is_returned_whole() -> None:
    """The common case: nothing rejected, all bytes returned."""
    result = await read_limited_upload(_upload(b"hello"), limit=10)

    assert result == b"hello"


@pytest.mark.unit
async def test_a_file_exactly_at_the_limit_is_accepted() -> None:
    """The boundary itself must not be rejected — only strictly over it."""
    data = b"x" * 10

    result = await read_limited_upload(_upload(data), limit=10)

    assert result == data


@pytest.mark.unit
async def test_a_file_one_byte_over_the_limit_is_rejected() -> None:
    """Exactly the case a naive `len(data) > limit` check misses until too late."""
    data = b"x" * 11

    with pytest.raises(UploadTooLargeError):
        await read_limited_upload(_upload(data), limit=10)


@pytest.mark.unit
async def test_a_far_oversized_file_never_loads_past_limit_plus_one() -> None:
    """The whole point: memory use is bounded, not just the final decision."""
    huge = _upload(b"x" * 1_000_000)

    with pytest.raises(UploadTooLargeError):
        await read_limited_upload(huge, limit=10)

    # Only limit+1 bytes were ever pulled from the underlying stream.
    remaining = huge.file.read()
    assert len(remaining) == 1_000_000 - 11


@pytest.mark.unit
async def test_an_empty_file_is_returned_as_empty_bytes() -> None:
    """Emptiness is a semantic decision for the caller, not this helper's job."""
    result = await read_limited_upload(_upload(b""), limit=10)

    assert result == b""


@pytest.mark.unit
async def test_a_hostile_filename_never_changes_the_outcome() -> None:
    """`UploadFile.filename` is client-controlled and must never reach the filesystem.

    No upload is persisted today, so there is no path-construction bug to
    reproduce — this locks the convention going forward: whatever the
    client names the file, only its bytes decide the result.
    """
    hostile = UploadFile(file=io.BytesIO(b"hello"), filename="../../etc/passwd")

    result = await read_limited_upload(hostile, limit=10)

    assert result == b"hello"
