"""The current-runtime driver for the longitudinal-memory eval (Plan 0046, CM-0).

An observation instrument, never a second memory system. ``execute_step`` calls
only audited public seams:

* ``EXTRACT`` -> the repaired real consolidation evaluator
  (``scripts.eval_consolidation.extract_case_items``) with the run-owned HTTP
  client. The assistant turn is a fixed neutral acknowledgement -- context only,
  never a fact source.
* every other longitudinal operation (``PROPOSE`` / ``RESTART`` / ``RECALL`` /
  ``CORRECT`` / ``FORGET`` / ``INSPECT_DERIVATIVES``) has no safe public seam
  yet, so it is recorded ``UNSUPPORTED`` with the exact missing capability. It
  is never imitated with an injected context, a legacy ``assert_fact()`` write
  relabelled as a candidate, or a database reconnect relabelled as a restart.

Provider/network failure during ``EXTRACT`` is a harness error (``status=ERROR``,
no household content in ``reason``); the runner turns that into exit ``2``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import httpx
from server.exceptions import LLMError

from scripts.eval_consolidation import extract_case_items
from scripts.longitudinal_eval_models import (
    CapabilityStatus,
    LongitudinalOperation,
    ProbeObservation,
)

if TYPE_CHECKING:
    from scripts.longitudinal_eval_models import LongitudinalScenario, LongitudinalStep

# Context-only assistant turn handed to the extraction seam. Deliberately inert:
# the assistant reply is never a grounding source for a stored fact.
_NEUTRAL_ACK = "Entendido."

# The exact missing seam for every operation the current runtime cannot support
# safely. These strings are the load-bearing output of a RED baseline.
_UNSUPPORTED_REASON: dict[LongitudinalOperation, str] = {
    LongitudinalOperation.PROPOSE: (
        "no public candidate-lifecycle seam: memory writes go through legacy assert_fact()"
    ),
    LongitudinalOperation.RESTART: (
        "no process-restart seam: only a DB reconnect is available and that is not a restart"
    ),
    LongitudinalOperation.RECALL: (
        "no authorized-longitudinal-recall seam: generic conversation does not carry the "
        "resolved actor"
    ),
    LongitudinalOperation.CORRECT: (
        "no candidate-correction seam: legacy assert_fact() cannot supersede a prior fact by policy"
    ),
    LongitudinalOperation.FORGET: (
        "no cascade-forget seam: no public call deletes a fact plus its "
        "episode/embedding/summary/cache derivatives"
    ),
    LongitudinalOperation.INSPECT_DERIVATIVES: (
        "no derivative-inspection seam: derivative layers are not exposed through a public read"
    ),
}


def _elapsed_ms(start: float) -> float:
    """Return milliseconds since ``start`` (a ``time.perf_counter`` reading)."""
    return (time.perf_counter() - start) * 1000.0


def unsupported_observation(operation: LongitudinalOperation) -> ProbeObservation:
    """Return the honest ``UNSUPPORTED`` observation for ``operation``.

    Args:
        operation: The longitudinal operation with no safe public seam.

    Returns:
        A ``ProbeObservation`` naming the missing capability, with no fabricated
        response, items, provenance or derivative inspection.
    """
    return ProbeObservation(
        status=CapabilityStatus.UNSUPPORTED,
        response="",
        observed_items=(),
        observed_provenance={},
        latency_ms=0.0,
        reason=_UNSUPPORTED_REASON[operation],
        inspected_derivatives={},
    )


class CurrentRuntimeDriver:
    """CM-0 driver: real single-turn extraction, every other operation UNSUPPORTED."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        """Store the run-owned HTTP client (one per CLI run)."""
        self._client = client

    async def execute_step(
        self,
        scenario: LongitudinalScenario,
        step: LongitudinalStep,
    ) -> ProbeObservation:
        """Execute one step against a real supported seam.

        Args:
            scenario: The owning scenario (unused today; the seam is per-step).
            step: The step to execute.

        Returns:
            A real extraction observation for ``EXTRACT``; otherwise the honest
            ``UNSUPPORTED`` observation for the step's operation.
        """
        _ = scenario
        if step.operation is LongitudinalOperation.EXTRACT:
            return await self._extract(step)
        return unsupported_observation(step.operation)

    async def _extract(self, step: LongitudinalStep) -> ProbeObservation:
        """Delegate to the repaired consolidation extraction seam."""
        start = time.perf_counter()
        try:
            keys = await extract_case_items(self._client, step.message, _NEUTRAL_ACK)
        except (LLMError, httpx.HTTPError) as exc:
            return ProbeObservation(
                status=CapabilityStatus.ERROR,
                response="",
                observed_items=(),
                observed_provenance={},
                latency_ms=_elapsed_ms(start),
                reason=f"provider failure during extraction ({type(exc).__name__}); no content",
                inspected_derivatives={},
            )
        return ProbeObservation(
            status=CapabilityStatus.PASS,
            response=f"extraction seam returned {len(keys)} folded item key(s)",
            observed_items=keys,
            observed_provenance={},
            latency_ms=_elapsed_ms(start),
            reason=None,
            inspected_derivatives={},
        )
