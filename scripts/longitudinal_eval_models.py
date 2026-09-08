"""Frozen typed models for the longitudinal-memory evaluation suite (Plan 0046).

This module holds only the strict Pydantic schema for the versioned synthetic
suite: enums, actors, steps, expectations and their containers. It carries no
behavior -- loading, semantic validation, privacy checks, scoring, the runtime
driver and the report renderer live in ``scripts.eval_longitudinal_memory`` and
later tasks of Plan 0046.

The models are deliberately strict. The suite is external YAML parsed by the
loader, i.e. a boundary / untrusted input, so ``ConfigDict(extra="forbid")``
is the load-time mechanism that rejects unknown or misspelled fields.
"""

from __future__ import annotations

import enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LongitudinalCategory(enum.StrEnum):
    """Canonical longitudinal-memory capability a step exercises."""

    EXTRACTION = "extraction"
    MULTI_SESSION = "multi_session"
    TEMPORALITY = "temporality"
    UPDATE = "update"
    ABSTENTION = "abstention"
    PROVENANCE = "provenance"
    CROSS_PERSON_PRIVACY = "cross_person_privacy"
    COMPLETE_DELETION = "complete_deletion"
    FALSE_MEMORY_RESISTANCE = "false_memory_resistance"


class CapabilityStatus(enum.StrEnum):
    """Outcome of one scored step; ``UNSUPPORTED`` never counts as a pass."""

    PASS = "pass"  # noqa: S105  # enum status member, not a credential
    FAIL = "fail"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class LongitudinalOperation(enum.StrEnum):
    """Seam a step drives against the current runtime."""

    EXTRACT = "extract"
    PROPOSE = "propose"
    RESTART = "restart"
    RECALL = "recall"
    CORRECT = "correct"
    FORGET = "forget"
    INSPECT_DERIVATIVES = "inspect_derivatives"


class EvaluationActor(BaseModel):
    """One synthetic participant referenced by a scenario's steps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: str
    role: Literal["subject", "other", "unknown"]


class ExpectedObservation(BaseModel):
    """Deterministic expectations scored against one probe observation.

    Attributes:
        required_any: Each inner list is an OR-group; every group must be
            satisfied by the response for the step to pass.
        forbidden: Substrings that must not appear in the response.
        expected_items: Canonical extraction keys expected to be observed.
        forbidden_items: Canonical extraction keys that must never appear.
        expected_provenance: Expected ``subject``/``assertor``/``source``
            attribution, independent of any extracted fact subject/object.
        required_absent_derivatives: Derivative layers that must be inspected
            and reported absent after a deletion.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_any: list[list[str]]
    forbidden: list[str]
    expected_items: list[str]
    forbidden_items: list[str]
    expected_provenance: dict[Literal["subject", "assertor", "source"], str]
    required_absent_derivatives: list[str]


class LongitudinalStep(BaseModel):
    """One actor message and its expected longitudinal-memory behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    category: LongitudinalCategory
    operation: LongitudinalOperation
    session: int
    actor_id: str
    message: str
    expected: ExpectedObservation


class LongitudinalScenario(BaseModel):
    """An ordered, independently understandable sequence of steps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    tags: list[str]
    actors: dict[str, EvaluationActor]
    steps: list[LongitudinalStep]


class LongitudinalSuite(BaseModel):
    """Top-level versioned container for every scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    scenarios: list[LongitudinalScenario]
