"""The phone of a care contact is international or it is nothing (Plan 0070 Task 6, ADR 0024)."""

from __future__ import annotations

import pytest
from server.memory.care_contacts import normalize_phone

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw",
    [
        "+56900000001",
        "+56 9 0000 0001",
        "+56-900000001",
        "(+56) 900.000.001",
        "  +56 9 0000 0001  ",
    ],
)
def test_a_phone_is_stripped_of_spaces_hyphens_dots_and_parentheses(raw: str) -> None:
    assert normalize_phone(raw) == "+56900000001"


@pytest.mark.parametrize(
    "raw",
    [
        "0900000001",
        "56900000001",
        "+0900000001",
        "+56abc",
        "+5690",
        "+1234567",
        "+1234567890123456",
        "",
        "   ",
        "+",
        "++56900000001",
        "+56900000001x",
        "+٥٦٩٠٠٠٠٠٠٠١",
    ],
)
def test_anything_that_is_not_a_plus_and_eight_to_fifteen_digits_is_refused(raw: str) -> None:
    assert normalize_phone(raw) is None


def test_the_shortest_and_the_longest_international_numbers_are_accepted() -> None:
    assert normalize_phone("+12345678") == "+12345678"
    assert normalize_phone("+123456789012345") == "+123456789012345"
