"""The free memory of the machine, read from the operating system (Plan 0089 D-13).

The turn's trace logs it at the start and the end of a turn, so a turn that ran the laptop out of
memory shows it. Only the standard library: ``ctypes`` on Windows, ``/proc/meminfo`` on Linux
(the server board). Anywhere else, or on any error, the answer is ``None``: reading the memory
never breaks a turn.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
import re
import sys
from typing import Final

__all__ = ["available_ram_mb", "parse_meminfo"]

_MEMINFO: Final = Path("/proc/meminfo")
_AVAILABLE_LINE: Final = re.compile(r"^MemAvailable:\s+(\d+)\s+kB$", re.MULTILINE)
_KB_PER_MB: Final = 1024
_BYTES_PER_MB: Final = 1024 * 1024


class _MemoryStatusEx(ctypes.Structure):
    """The ``MEMORYSTATUSEX`` structure of the Win32 ``GlobalMemoryStatusEx`` call."""

    _fields_ = (
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    )


def parse_meminfo(text: str) -> int | None:
    """Return the ``MemAvailable`` line of ``/proc/meminfo`` in megabytes, or ``None``.

    Args:
        text: The content of ``/proc/meminfo``.
    """
    match = _AVAILABLE_LINE.search(text)
    return None if match is None else int(match.group(1)) // _KB_PER_MB


def _linux_available_mb() -> int | None:
    return parse_meminfo(_MEMINFO.read_text(encoding="ascii"))


def _windows_available_mb() -> int | None:
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    # ``ctypes.windll`` exists only on Windows. It is read dynamically so this module type-checks
    # on every platform; ``available_ram_mb`` calls this function only on Windows.
    windll = getattr(ctypes, "windll")  # noqa: B009
    if not windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullAvailPhys) // _BYTES_PER_MB


def available_ram_mb() -> int | None:
    """Return the machine's available physical memory in megabytes, or ``None``.

    Returns:
        The free megabytes on Windows and Linux; ``None`` on any other platform or when the
        operating system call fails. Never raises.
    """
    # A plain ``str``: comparing ``sys.platform`` itself makes the type checkers drop the branch
    # of every other platform as unreachable.
    platform: str = sys.platform
    try:
        if platform == "win32":
            return _windows_available_mb()
        if platform.startswith("linux"):
            return _linux_available_mb()
    except (OSError, ValueError, AttributeError):
        return None
    return None
