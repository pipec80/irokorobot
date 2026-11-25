"""Plan 0089 D-13: free memory read from the operating system, never an exception in a turn."""

import pytest

from server import system_memory

pytestmark = pytest.mark.unit


def test_this_machine_reports_a_positive_number_of_megabytes() -> None:
    free = system_memory.available_ram_mb()

    assert isinstance(free, int)
    assert free > 0


def test_an_unknown_platform_reports_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_memory.sys, "platform", "plan9")

    assert system_memory.available_ram_mb() is None


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_a_failing_os_call_reports_none(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    def broken() -> int:
        raise OSError("canary")

    monkeypatch.setattr(system_memory.sys, "platform", platform)
    monkeypatch.setattr(system_memory, "_windows_available_mb", broken)
    monkeypatch.setattr(system_memory, "_linux_available_mb", broken)

    assert system_memory.available_ram_mb() is None


def test_meminfo_s_available_line_is_read_in_megabytes() -> None:
    meminfo = "MemTotal:       16000000 kB\nMemFree:  100 kB\nMemAvailable:    8192000 kB\n"

    assert system_memory.parse_meminfo(meminfo) == 8000


def test_meminfo_without_an_available_line_is_none() -> None:
    assert system_memory.parse_meminfo("MemTotal: 16000000 kB\n") is None
