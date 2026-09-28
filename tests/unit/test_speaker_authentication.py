"""Unit tests for the pure speaker verdict table (Plan 0053, Task 2)."""

import pytest
from server.cognition.identity import HouseholdRole
from server.cognition.speaker_authentication import SpeakerVerdict, evaluate_speaker_verification
from server.settings import settings


def _evaluate(**overrides: object) -> SpeakerVerdict:
    """Evaluate the table from the all-satisfied case with named overrides."""
    kwargs: dict[str, object] = {
        "reference_count": settings.speaker_min_reference_count,
        "distance": settings.speaker_authentication_match_threshold - 0.01,
        "consent_active": True,
        "role": HouseholdRole.OWNER,
        "backend_available": True,
    }
    kwargs.update(overrides)
    return evaluate_speaker_verification(**kwargs)  # type: ignore[arg-type]


def test_all_conditions_satisfied_verifies() -> None:
    assert _evaluate() is SpeakerVerdict.VERIFIED


def test_distance_exactly_at_the_threshold_verifies() -> None:
    """The study's rule is `distance <= threshold`, not `<`."""
    assert _evaluate(distance=settings.speaker_authentication_match_threshold) is (
        SpeakerVerdict.VERIFIED
    )


def test_backend_unavailable_is_unavailable_not_unknown() -> None:
    assert _evaluate(backend_available=False) is SpeakerVerdict.UNAVAILABLE


@pytest.mark.parametrize(
    "override",
    [
        {"reference_count": 0},
        {"reference_count": 2},
        {"distance": None},
        {"distance": 0.9},
        {"consent_active": False},
        {"role": HouseholdRole.ADULT},
        {"role": HouseholdRole.UNKNOWN},
    ],
)
def test_every_other_failure_is_unknown(override: dict[str, object]) -> None:
    assert _evaluate(**override) is SpeakerVerdict.UNKNOWN


def test_unavailable_wins_over_a_matching_distance() -> None:
    """A dead backend is never reported as a match, whatever else is true."""
    assert _evaluate(backend_available=False, distance=0.0) is SpeakerVerdict.UNAVAILABLE
