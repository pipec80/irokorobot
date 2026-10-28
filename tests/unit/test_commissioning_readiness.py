"""The readiness report: a capability is ready only with its data and its hardware (Plan 0072).

ADR 0024 decision 14: for each capability that exists today the report derives whether its pool
data is present (from the section statuses) and combines it with a typed hardware status. A stored
phone enables no call and approving the form turns nothing on.
"""

from __future__ import annotations

import pytest
from server.memory.commissioning import Section, SectionStatus
from server.memory.commissioning_readiness import (
    CATALOGUE,
    Capability,
    CapabilityReadiness,
    HardwareStatus,
    Verdict,
    evaluate_readiness,
    readiness_from_json,
    readiness_to_json,
)

pytestmark = pytest.mark.unit

_ALL_HARDWARE = HardwareStatus(supported=True, configured=True, verified=True)
_NO_HARDWARE = HardwareStatus(supported=False, configured=False, verified=False)


def _verdict(
    report: tuple[CapabilityReadiness, ...], capability: Capability
) -> CapabilityReadiness:
    (one,) = (item for item in report if item.capability is capability)
    return one


def test_the_catalogue_is_exactly_the_seven_capabilities_that_exist_today() -> None:
    assert {entry.capability for entry in CATALOGUE} == set(Capability)
    assert {capability.value for capability in Capability} == {
        "speak_reply",
        "understand_speech",
        "recognize_face",
        "recognize_voice",
        "remember_taste",
        "answer_profile",
        "describe_scene",
    }


def test_answering_the_profile_needs_no_pool_data_but_its_own_hardware_check() -> None:
    """Plan 0074: the card reads what the import loaded, so no section is required here."""
    report = evaluate_readiness({}, {})

    one = _verdict(report, Capability.ANSWER_PROFILE)
    assert one.data_present is True
    assert one.verdict is Verdict.BLOCKED_BY_HARDWARE


def test_a_capability_that_needs_no_pool_data_is_always_data_present() -> None:
    report = evaluate_readiness({}, {})

    assert _verdict(report, Capability.SPEAK_REPLY).data_present is True


@pytest.mark.parametrize(
    "status,present",
    [
        (SectionStatus.PROVIDED, True),
        (SectionStatus.NONE, False),
        (SectionStatus.NOT_ASKED, False),
        (SectionStatus.DECLINED, False),
        (SectionStatus.UNKNOWN, False),
    ],
)
def test_describe_scene_needs_the_function_section_provided(
    status: SectionStatus, present: bool
) -> None:
    report = evaluate_readiness({Section.FUNCTION: status}, {})

    assert _verdict(report, Capability.DESCRIBE_SCENE).data_present is present


def test_ready_only_with_the_data_and_all_three_hardware_booleans() -> None:
    hardware = {Capability.DESCRIBE_SCENE: _ALL_HARDWARE}

    report = evaluate_readiness({Section.FUNCTION: SectionStatus.PROVIDED}, hardware)

    assert _verdict(report, Capability.DESCRIBE_SCENE).verdict is Verdict.READY


@pytest.mark.parametrize(
    "function_status,hardware,verdict",
    [
        (SectionStatus.PROVIDED, _ALL_HARDWARE, Verdict.READY),
        (SectionStatus.PROVIDED, _NO_HARDWARE, Verdict.BLOCKED_BY_HARDWARE),
        (SectionStatus.NOT_ASKED, _ALL_HARDWARE, Verdict.BLOCKED_BY_DATA),
        (SectionStatus.NOT_ASKED, _NO_HARDWARE, Verdict.BLOCKED_BY_BOTH),
    ],
)
def test_the_four_verdicts(
    function_status: SectionStatus, hardware: HardwareStatus, verdict: Verdict
) -> None:
    report = evaluate_readiness(
        {Section.FUNCTION: function_status}, {Capability.DESCRIBE_SCENE: hardware}
    )

    assert _verdict(report, Capability.DESCRIBE_SCENE).verdict is verdict


def test_a_partial_hardware_status_is_not_ready() -> None:
    hardware = {Capability.DESCRIBE_SCENE: HardwareStatus(True, True, False)}

    report = evaluate_readiness({Section.FUNCTION: SectionStatus.PROVIDED}, hardware)

    assert _verdict(report, Capability.DESCRIBE_SCENE).verdict is Verdict.BLOCKED_BY_HARDWARE


def test_a_capability_with_no_typed_hardware_is_blocked_by_hardware() -> None:
    report = evaluate_readiness({}, {})

    assert _verdict(report, Capability.SPEAK_REPLY).verdict is Verdict.BLOCKED_BY_HARDWARE


def test_the_report_round_trips_through_json() -> None:
    report = evaluate_readiness(
        {Section.FUNCTION: SectionStatus.PROVIDED},
        {Capability.SPEAK_REPLY: _ALL_HARDWARE, Capability.DESCRIBE_SCENE: _NO_HARDWARE},
    )

    assert readiness_from_json(readiness_to_json(report)) == report
