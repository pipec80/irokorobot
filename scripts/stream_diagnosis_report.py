"""Markdown report of the streaming diagnosis (Plan 0057): counts and rates only.

Nothing here reads, prints or stores model output; the rules behind each reading live
in ``stream_diagnosis_stats`` and ``stream_diagnosis_probes``. The headline and the
failure shapes describe the baseline (``full``); every other variant is read apart.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.eval_stream_protocol import StreamOutcome
from scripts.stream_diagnosis_probes import ArrivalPattern, RunStatus
from scripts.stream_diagnosis_stats import (
    DRIFT_THRESHOLD_PP,
    PERCENT,
    SIGNAL_THRESHOLD_PP,
    baseline_observations,
    comparisons,
    dominant_shape,
    drift_flagged,
    drift_rates,
    group_by_variant_and_source,
    per_case_counts,
    percentiles,
    shape_counts,
    summarize,
)
from scripts.stream_diagnosis_variants import VARIANT_DESCRIPTIONS, StreamVariant

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from scripts.eval_stream_diagnosis import Observation
    from scripts.stream_diagnosis_probes import StructuredProbeResult

_SOURCES = ("context", "public")


@dataclass(frozen=True)
class ReportContext:
    """What the run was made against and with."""

    model: str
    ollama_version: str
    model_digest: str
    runs: int
    seed: int


def _percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * PERCENT:.2f} %"


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return [*lines, ""]


def _fraction(fallbacks: int, graded: int) -> str:
    rate = fallbacks / graded if graded else None
    return f"{fallbacks}/{graded} ({_percent(rate)})"


def _legend_section() -> list[str]:
    rows = [(variant.value, VARIANT_DESCRIPTIONS[variant]) for variant in StreamVariant]
    return ["## Variants", "", *_table(("Variant", "What it changes"), rows)]


def _variant_section(observations: Sequence[Observation]) -> list[str]:
    rows = []
    for (variant, source), items in group_by_variant_and_source(observations).items():
        s = summarize(items)
        rows.append(
            (
                variant.value,
                source,
                s.valid,
                s.invalid_protocol,
                s.empty_stream,
                s.errors,
                _percent(s.fallback_rate),
                s.undue_accept,
                s.inconsistent,
            )
        )
    header = (
        "Variant",
        "Source",
        "Valid",
        "Invalid",
        "Empty",
        "Errors",
        "Fallback rate",
        "Undue accept",
        "Split-dependent",
    )
    return ["## 1. Fallback by variant and source", "", *_table(header, rows)]


def _comparison_section(observations: Sequence[Observation], runs: int) -> list[str]:
    rows = []
    for c in comparisons(observations, runs):
        change = "n/a" if c.change_pp is None else f"{c.change_pp:+.1f}"
        noise = "n/a" if c.noise_pp is None else f"{c.noise_pp:.1f}"
        rows.append(
            (
                c.variant.value,
                c.paired_cases,
                c.excluded_cases,
                _fraction(c.baseline_fallbacks, c.baseline_graded),
                _fraction(c.variant_fallbacks, c.variant_graded),
                change,
                noise,
                c.reading,
            )
        )
    rule = (
        f"Each row compares one intervention with `full` on the turns where `full`, the "
        f"variant and the `full_repeat` control all have the {runs} expected runs graded; a "
        f"turn missing any of them is excluded, never compared on a different sample, and a "
        f"row with no complete control is `incomplete`, never a signal. The noise of a row "
        f"is the mean absolute difference, turn by turn, between `full` and `full_repeat` "
        f"on that row's own turns (opposite swings never cancel). A signal is a change of "
        f"at least {SIGNAL_THRESHOLD_PP:.0f} points that also exceeds that noise. It is an "
        f"exploratory signal, not a cause: confirm with another seed before attributing one."
    )
    note = (
        "`question_only` runs only on turns that have a person or a history; elsewhere it "
        "sends what `no_context` sends and is not repeated."
    )
    header = (
        "Variant",
        "Paired",
        "Excluded",
        "`full`",
        "Variant",
        "Change (pp)",
        "Noise (pp)",
        "Reading",
    )
    return [
        "## 2. Interventions against `full` (exploratory)",
        "",
        rule,
        "",
        *_table(header, rows),
        note,
        "",
    ]


def _shape_section(observations: Sequence[Observation]) -> list[str]:
    lines = ["## 3. Failure shapes", ""]
    baseline = baseline_observations(observations)
    for source in _SOURCES:
        counts = shape_counts(o for o in baseline if o.source == source)
        total = sum(counts.values())
        lines.extend(
            _table(
                (f"Shape in `full` ({source})", "Count", "Share"),
                [(shape, n, _percent(n / total)) for shape, n in counts.items()],
            )
        )
        dominant = dominant_shape(counts)
        if not counts:
            lines.extend([f"No fallbacks in `full` ({source}).", ""])
        elif dominant:
            lines.extend([f"Dominant shape in `full` ({source}): `{dominant}`.", ""])
        else:
            lines.extend([f"No shape holds half of the fallbacks in `full` ({source}).", ""])
    rows = []
    for (variant, source), items in group_by_variant_and_source(observations).items():
        if variant is StreamVariant.FULL:
            continue
        rows.extend((variant.value, source, shape, n) for shape, n in shape_counts(items).items())
    lines.extend(["Shapes of each intervention, apart (never merged into the baseline):", ""])
    return [*lines, *_table(("Variant", "Source", "Shape", "Count"), rows)]


def _case_section(observations: Sequence[Observation], runs: int) -> list[str]:
    cases = per_case_counts(observations, StreamVariant.FULL, runs)
    some = sum(1 for c in cases.values() if c.fallbacks)
    always = sum(1 for c in cases.values() if c.fell_every_run)
    incomplete = sum(1 for c in cases.values() if not c.complete)
    rows = [(label, c.fallbacks, c.errors, c.graded, c.expected) for label, c in cases.items()]
    summary = (
        f"Turns with at least one fallback: {some} of {len(cases)}; that fell back in every "
        f"expected run: {always}; incomplete turns: {incomplete}."
    )
    header = ("Turn", "Fallbacks", "Provider errors", "Graded", "Expected")
    return ["## 4. Turns under `full`", "", *_table(header, rows), summary, ""]


def _timing_cells(group: Sequence[Observation]) -> list[str]:
    cells = []
    for pick in (
        lambda o: o.first_delta_ms,
        lambda o: o.speech_start_ms,
        lambda o: o.end_ms,
    ):
        found = percentiles([v for v in (pick(o) for o in group) if v is not None])
        cells.append("n/a" if found is None else f"{found[0]} / {found[1]}")
    return cells


def _timing_section(observations: Sequence[Observation]) -> list[str]:
    rows = []
    by_variant: dict[StreamVariant, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_variant[obs.variant].append(obs)
    for variant in StreamVariant:
        items = by_variant.get(variant, [])
        for name, group in (
            ("valid", [o for o in items if o.outcome is StreamOutcome.VALID]),
            ("fallback", [o for o in items if o.fell_back]),
        ):
            if group:
                rows.append([variant.value, name, len(group), *_timing_cells(group)])
    header = ("Variant", "Outcome", "n", "First delta", "Speech start", "End")
    note = (
        "p50 / p95 by the nearest-rank method. Speech start is when production would hand "
        "its first sentence, or the fallback, to TTS (TTS time excluded)."
    )
    return ["## 5. Timing (ms)", "", *_table(header, rows), note, ""]


def _drift_section(observations: Sequence[Observation]) -> list[str]:
    rates = drift_rates(observations)
    rows = [(f"Q{i}", _percent(rate)) for i, rate in enumerate(rates, start=1)]
    verdict = (
        f"Quarters differ by {DRIFT_THRESHOLD_PP:.0f} points or more: repeat with another seed."
        if drift_flagged(rates)
        else "No order effect above the rule."
    )
    note = (
        "Quarters of the shuffled execution order, all variants together: it describes the "
        "experiment, not the baseline."
    )
    return [
        "## 6. Execution order",
        "",
        note,
        "",
        *_table(("Quarter", "Fallback rate"), rows),
        verdict,
        "",
    ]


def _prompt_section(observations: Sequence[Observation]) -> list[str]:
    by_variant: dict[StreamVariant, list[int]] = defaultdict(list)
    for obs in observations:
        by_variant[obs.variant].append(obs.prompt_chars)
    rows = [
        (
            v.value,
            min(by_variant[v]),
            round(sum(by_variant[v]) / len(by_variant[v])),
            max(by_variant[v]),
        )
        for v in StreamVariant
        if v in by_variant
    ]
    return [
        "## 7. Prompt size (characters sent)",
        "",
        *_table(("Variant", "Min", "Mean", "Max"), rows),
    ]


def probe_reading(constrained: StructuredProbeResult, plain: StructuredProbeResult | None) -> str:
    """Read the two probes together, never claiming more than a client can see.

    A burst at the client is what a withheld reply, fast generation and buffering all
    look like; only a spread-out arrival of the schema-constrained reply is evidence
    (against the claim, being compatible with incremental generation), and a contrast
    with the plain-text control is a hint, not a proof.
    """
    verdict = constrained.verdict
    if verdict is ArrivalPattern.INCREMENTAL:
        return (
            "The schema-constrained reply reached this client spread over time, which is "
            "compatible with incremental generation: streaming with a JSON schema is a "
            "candidate protocol and this is evidence against the `llm_streaming.py` claim "
            "that Ollama withholds it, though a client cannot see when generation ended."
        )
    if verdict is ArrivalPattern.INCONCLUSIVE:
        return (
            "No conclusion: the schema-constrained runs show no clear pattern, or too few "
            "were complete. This is not evidence that the `llm_streaming.py` header is right."
        )
    control = None if plain is None else plain.verdict
    if control is ArrivalPattern.INCREMENTAL:
        return (
            "The schema-constrained reply reached this client as a burst while the plain-text "
            "control arrived spread over time. That differs from the plain-text control and is "
            "consistent with Ollama withholding schema output, but a client cannot prove the "
            "cause: the "
            "`llm_streaming.py` claim stays unproven."
        )
    if control is ArrivalPattern.BURST:
        return (
            "Both the schema-constrained reply and the plain-text control reached this client "
            "as bursts: this probe cannot tell generation from buffering here, so the "
            "`llm_streaming.py` claim stays unproven."
        )
    return (
        "The schema-constrained reply reached this client as a burst, and without a "
        "plain-text control that reads clearly this cannot show that Ollama withholds it "
        "(fast generation and buffering look the same): the `llm_streaming.py` claim stays "
        "unproven."
    )


def _probe_table(probe: StructuredProbeResult) -> list[str]:
    rows = []
    for i, run in enumerate(probe.runs, start=1):
        a = run.arrivals
        rows.append(
            (
                i,
                run.status.value,
                "n/a" if a is None else a.chunks,
                "n/a" if a is None else f"{a.paced_gaps}/{a.gaps}",
                "n/a" if a is None else a.pattern.value,
            )
        )
    counts = (
        f"Complete runs: {probe.count(RunStatus.COMPLETE)} of {len(probe.runs)}; "
        f"provider errors: {probe.count(RunStatus.PROVIDER_ERROR)}; "
        f"incomplete: {probe.count(RunStatus.INCOMPLETE)}; "
        f"off schema: {probe.count(RunStatus.OFF_SCHEMA)}. "
        f"Verdict: {probe.verdict.value}."
    )
    header = ("Run", "Status", "Chunks", "Paced gaps / gaps", "Pattern")
    return [*_table(header, rows), counts, ""]


def _probe_section(
    constrained: StructuredProbeResult | None, plain: StructuredProbeResult | None
) -> list[str]:
    if constrained is None:
        return ["## 8. Stream arrival probe", "", "Not run.", ""]
    note = (
        "The probe sees the chunks as this client received them. It cannot tell a reply "
        "that Ollama withheld from fast generation, from buffering or from the client's own "
        "reading, so a burst never proves the `llm_streaming.py` header; only a "
        "spread-out arrival of the schema-constrained reply is evidence against it."
    )
    lines = [
        "## 8. Stream arrival probe",
        "",
        note,
        "",
        "### Schema-constrained",
        "",
        *_probe_table(constrained),
    ]
    if plain is None:
        lines.extend(["Plain-text control: not run.", ""])
    else:
        lines.extend(["### Plain-text control", "", *_probe_table(plain)])
    return [*lines, f"Reading: {probe_reading(constrained, plain)}", ""]


def _head(observations: Sequence[Observation], context: ReportContext) -> list[str]:
    total = summarize(observations)
    baseline = baseline_observations(observations)
    by_source = ", ".join(
        f"{source} {_percent(summarize(o for o in baseline if o.source == source).fallback_rate)}"
        for source in _SOURCES
    )
    return [
        "# Streaming protocol diagnosis (Plan 0057)",
        "",
        f"- model: {context.model} (digest `{context.model_digest}`)",
        f"- ollama version: {context.ollama_version}",
        "- generation options: server defaults (production passes none)",
        f"- runs per turn and variant: {context.runs}; shuffle seed: {context.seed}",
        f"- observations (all variants): {len(observations)} "
        f"(graded {total.graded}, provider errors {total.errors})",
        f"- baseline (`full`) fallback rate: {by_source}",
        f"- replies spoken that the whole text rejects (all variants): {total.undue_accept}",
        "",
    ]


def render_diagnosis_report(
    observations: Sequence[Observation],
    context: ReportContext,
    probe: StructuredProbeResult | None,
    plain_control: StructuredProbeResult | None = None,
) -> str:
    """Render the diagnosis as Markdown: counts and rates only, never model output.

    Args:
        observations: Every observation of the run, in any order.
        context: The facts of the run (model, Ollama, runs per variant, seed).
        probe: The schema-constrained probe result, or ``None`` when it was skipped.
        plain_control: The plain-text control probe, or ``None`` when it was skipped.

    Returns:
        The Markdown report. The headline and the failure shapes describe ``full``;
        interventions appear apart.
    """
    sections = [
        _head(observations, context),
        _legend_section(),
        _variant_section(observations),
        _comparison_section(observations, context.runs),
        _shape_section(observations),
        _case_section(observations, context.runs),
        _timing_section(observations),
        _drift_section(observations),
        _prompt_section(observations),
        _probe_section(probe, plain_control),
    ]
    return "\n".join(line for section in sections for line in section)
