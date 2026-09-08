"""Per-step deterministic scoring for the longitudinal-memory eval (Plan 0046).

Pure functions only: no LLM judge, no IO, no ``server`` imports, no network or
database. ``score_step`` turns one :class:`ProbeObservation` into a
:class:`ScoredStep`. ``ERROR`` / ``UNSUPPORTED`` observations keep that status
(never a silent pass, never a fabricated observation). Text matching is
case/accent-insensitive (NFKD -> strip combining marks -> casefold -> collapse
whitespace) and never mutates the stored expected text. Whole-run aggregation
and the exit-code contract live in ``scripts.longitudinal_eval_aggregation``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple
import unicodedata

from scripts.longitudinal_eval_models import CapabilityStatus, ScoredStep, StepResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.longitudinal_eval_models import (
        ExpectedObservation,
        LongitudinalStep,
        ProbeObservation,
    )

_VALID_OBSERVATION: frozenset[CapabilityStatus] = frozenset(
    {CapabilityStatus.PASS, CapabilityStatus.FAIL}
)


def _normalize_text(text: str) -> str:
    """Return *text* case/accent-folded, whitespace-collapsed (match-time only)."""
    decomposed = unicodedata.normalize("NFKD", text)
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(bare.casefold().split())


class _ItemScore(NamedTuple):
    expected: int
    matched: int
    unexpected: int
    forbidden: list[str]


class _ProvScore(NamedTuple):
    expected: int
    matched: int
    mismatches: dict[str, tuple[str, str | None]]


class _Core(NamedTuple):
    status: CapabilityStatus
    missing: list[list[str]]
    forbidden: list[str]
    items: _ItemScore
    provenance: _ProvScore
    derivatives: dict[str, bool]


def _score_items(expected: ExpectedObservation, observed: Sequence[str]) -> _ItemScore:
    want = {_normalize_text(key) for key in expected.expected_items}
    got = {_normalize_text(key) for key in observed}
    banned = [k for k in expected.forbidden_items if _normalize_text(k) in got]
    return _ItemScore(len(want), len(want & got), len(got - want), banned)


def _score_provenance(expected: dict[str, str], observed: dict[str, str]) -> _ProvScore:
    matched = 0
    mismatches: dict[str, tuple[str, str | None]] = {}
    for field, want in expected.items():
        got = observed.get(field)
        if got is not None and _normalize_text(got) == _normalize_text(want):
            matched += 1
        else:
            mismatches[field] = (want, got)
    return _ProvScore(len(expected), matched, mismatches)


def _resolve_status(observed: CapabilityStatus, *, ok: bool) -> CapabilityStatus:
    if observed not in _VALID_OBSERVATION:
        return observed
    return CapabilityStatus.PASS if ok else CapabilityStatus.FAIL


def _score_core(step: LongitudinalStep, observation: ProbeObservation) -> _Core:
    expected = step.expected
    text = _normalize_text(observation.response)
    missing = [
        group
        for group in expected.required_any
        if not any(_normalize_text(option) in text for option in group)
    ]
    forbidden = [term for term in expected.forbidden if _normalize_text(term) in text]
    items = _score_items(expected, observation.observed_items)
    provenance = _score_provenance(
        dict(expected.expected_provenance), dict(observation.observed_provenance)
    )
    derivatives = {
        name: observation.inspected_derivatives.get(name, True)
        for name in expected.required_absent_derivatives
    }
    ok = not (
        missing
        or forbidden
        or items.forbidden
        or items.matched != items.expected
        or provenance.mismatches
        or any(present is not False for present in derivatives.values())
    )
    status = _resolve_status(observation.status, ok=ok)
    return _Core(status, missing, forbidden, items, provenance, derivatives)


def _build_step_result(
    scenario_id: str, step: LongitudinalStep, observation: ProbeObservation, core: _Core
) -> StepResult:
    return StepResult(
        scenario_id=scenario_id,
        step_id=step.step_id,
        category=step.category,
        operation=step.operation,
        status=core.status,
        response=observation.response,
        latency_ms=observation.latency_ms,
        missing_required=core.missing,
        forbidden_found=core.forbidden,
        expected_item_count=core.items.expected,
        matched_item_count=core.items.matched,
        unexpected_item_count=core.items.unexpected,
        forbidden_items_found=core.items.forbidden,
        provenance_expected_count=core.provenance.expected,
        provenance_matched_count=core.provenance.matched,
        provenance_mismatches=core.provenance.mismatches,
        derivative_presence=core.derivatives,
        reason=observation.reason,
    )


def score_step(
    scenario_id: str, step: LongitudinalStep, observation: ProbeObservation
) -> ScoredStep:
    """Score one deterministic observation without hiding unsupported work.

    ``ERROR`` / ``UNSUPPORTED`` observations keep that status. Otherwise the
    step passes only when every expectation holds; a ``forbidden`` or
    ``forbidden_items`` hit fails it even when ``required_any`` is satisfied.
    ``reason`` is preserved.
    """
    expected = step.expected
    core = _score_core(step, observation)
    inspected = tuple(
        name
        for name in expected.required_absent_derivatives
        if name in observation.inspected_derivatives
    )
    return ScoredStep(
        result=_build_step_result(scenario_id, step, observation, core),
        expected_item_keys=tuple(expected.expected_items),
        observed_item_keys=tuple(observation.observed_items),
        required_derivative_names=tuple(expected.required_absent_derivatives),
        inspected_derivative_names=inspected,
        passed=core.status is CapabilityStatus.PASS,
    )
