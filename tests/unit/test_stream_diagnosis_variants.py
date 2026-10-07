"""How diagnosis turns are varied, ordered and prompted (Plan 0057, Task 3)."""

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import httpx
import pytest
from server.schemas import ConversationTurn, MemoryContext

from scripts.eval_stream_protocol import StreamTurn
from scripts.stream_diagnosis_variants import (
    VARIANT_DESCRIPTIONS,
    DiagnosisUnit,
    StreamVariant,
    build_units,
    generate_contract_first,
    generator_for,
    plan_runs,
    prompt_chars,
)
from server import llm_streaming

if TYPE_CHECKING:
    from server.cognition.identity import ActivePersonContext

type StreamGenerator = Callable[..., AsyncIterator[str]]


def _client() -> httpx.AsyncClient:
    return cast("httpx.AsyncClient", Mock(spec=httpx.AsyncClient))


def _turn(
    label: str = "t", *, source: str = "context", person: bool = False, history: bool = False
) -> StreamTurn:
    return StreamTurn(
        label=label,
        source=source,
        text="hola",
        context=MemoryContext() if source == "context" else None,
        history=[ConversationTurn(role="user", content="antes")] if history else None,
        active_person=cast("ActivePersonContext", Mock()) if person else None,
    )


def _unit(variant: StreamVariant = StreamVariant.FULL) -> DiagnosisUnit:
    return DiagnosisUnit(variant, _turn())


@pytest.mark.unit
def test_units_skip_variants_that_would_change_nothing() -> None:
    golden = [_turn("g1"), _turn("g2", person=True), _turn("g3", history=True)]
    public = [_turn("p1", source="public"), _turn("p2", source="public")]

    units = build_units(golden, public)
    names = [(u.turn.label, u.variant.value) for u in units]

    # g1: full, full_repeat, no_context, contract_first. g2 and g3 add question_only and
    # no_person / no_history. Each public turn: full, full_repeat, contract_first and
    # public_with_context.
    assert len(units) == 4 + 6 + 6 + 2 * 4
    assert ("g1", "no_person") not in names
    assert ("g2", "no_person") in names
    assert ("g1", "no_history") not in names
    assert ("g3", "no_history") in names
    assert ("p1", "no_context") not in names


@pytest.mark.unit
def test_a_bare_question_is_not_run_when_it_equals_dropping_the_context() -> None:
    """Without a person or a history, ``question_only`` sends what ``no_context`` sends."""
    golden = [_turn("g1"), _turn("g2", person=True), _turn("g3", history=True)]

    names = [(u.turn.label, u.variant.value) for u in build_units(golden, [])]

    assert ("g1", "question_only") not in names
    assert ("g2", "question_only") in names
    assert ("g3", "question_only") in names


@pytest.mark.unit
def test_no_two_interventions_of_a_turn_send_the_same_inputs() -> None:
    golden = [_turn("g1"), _turn("g2", person=True), _turn("g3", history=True)]
    public = [_turn("p1", source="public")]
    seen: dict[str, list[str]] = {}

    for unit in build_units(golden, public):
        if unit.variant is StreamVariant.FULL_REPEAT:
            continue  # the noise control repeats ``full`` on purpose
        turn = unit.turn
        key = repr((unit.variant is StreamVariant.CONTRACT_FIRST, turn.context, turn.history))
        key += f"|{id(turn.active_person)}"
        seen.setdefault(turn.label, []).append(key)

    assert all(len(keys) == len(set(keys)) for keys in seen.values())


@pytest.mark.unit
def test_every_turn_gets_the_noise_control_and_it_repeats_full() -> None:
    """The noise is read per comparison, so each turn needs its own control."""
    golden = [_turn("g", person=True, history=True)]
    public = [_turn("p", source="public")]

    units = build_units(golden, public)
    repeats = {u.turn.label: u.turn for u in units if u.variant is StreamVariant.FULL_REPEAT}

    assert repeats == {"g": golden[0], "p": public[0]}


@pytest.mark.unit
def test_every_variant_says_what_it_changes() -> None:
    assert set(VARIANT_DESCRIPTIONS) == set(StreamVariant)
    assert all(text.strip() for text in VARIANT_DESCRIPTIONS.values())


@pytest.mark.unit
def test_each_variant_changes_exactly_the_factor_it_names() -> None:
    golden = [_turn("g", person=True, history=True)]

    by_variant = {u.variant: u.turn for u in build_units(golden, [])}

    assert by_variant[StreamVariant.FULL] is golden[0]
    assert by_variant[StreamVariant.FULL_REPEAT] is golden[0]
    assert by_variant[StreamVariant.NO_CONTEXT].context is None
    assert by_variant[StreamVariant.NO_CONTEXT].history is not None
    assert by_variant[StreamVariant.NO_PERSON].active_person is None
    assert by_variant[StreamVariant.NO_PERSON].context is not None
    assert by_variant[StreamVariant.NO_HISTORY].history is None
    assert by_variant[StreamVariant.NO_HISTORY].active_person is not None
    only = by_variant[StreamVariant.QUESTION_ONLY]
    assert (only.context, only.history, only.active_person) == (None, None, None)
    assert by_variant[StreamVariant.CONTRACT_FIRST] is golden[0]


@pytest.mark.unit
def test_a_public_question_borrows_a_golden_context_in_rotation() -> None:
    golden = [_turn("g1"), _turn("g2")]
    public = [_turn(f"p{i}", source="public") for i in range(3)]

    borrowed = [
        u.turn
        for u in build_units(golden, public)
        if u.variant is StreamVariant.PUBLIC_WITH_CONTEXT
    ]

    assert [t.context for t in borrowed] == [
        golden[0].context,
        golden[1].context,
        golden[0].context,
    ]
    assert all(t.source == "public" for t in borrowed)


@pytest.mark.unit
def test_the_variant_filter_keeps_only_what_was_asked() -> None:
    units = build_units([_turn("g")], [_turn("p", source="public")], {StreamVariant.NO_CONTEXT})

    assert [u.variant for u in units] == [StreamVariant.NO_CONTEXT]


@pytest.mark.unit
def test_the_plan_is_seeded_complete_and_interleaved() -> None:
    units = build_units([_turn("g1"), _turn("g2")], [])

    first = plan_runs(units, 3, seed=57)

    assert first == plan_runs(units, 3, seed=57)
    assert first != plan_runs(units, 3, seed=58)
    assert sorted(first, key=lambda item: (id(item[0]), item[1])) == sorted(
        [(unit, run) for unit in units for run in (1, 2, 3)],
        key=lambda item: (id(item[0]), item[1]),
    )
    variants_in_order = [unit.variant for unit, _run in first]
    assert variants_in_order != sorted(variants_in_order, key=lambda v: v.value)


async def _captured_messages(
    generate: StreamGenerator, unit: DiagnosisUnit, monkeypatch: pytest.MonkeyPatch
) -> list[dict[str, str]]:
    captured: list[list[dict[str, str]]] = []

    async def fake_stream(
        _client: httpx.AsyncClient, messages: list[dict[str, str]], **_kwargs: object
    ) -> AsyncIterator[str]:
        captured.append(messages)
        yield "EMOTION:joy\nHola."

    monkeypatch.setattr(llm_streaming, "ollama_chat_stream", fake_stream)
    turn = unit.turn
    async for _delta in generate(
        _client(),
        turn.text,
        context=turn.context,
        history=turn.history,
        active_person=turn.active_person,
    ):
        pass
    return captured[0]


@pytest.mark.unit
@pytest.mark.parametrize("variant", [StreamVariant.FULL, StreamVariant.CONTRACT_FIRST])
async def test_prompt_chars_equals_what_the_generator_really_sends(
    variant: StreamVariant, monkeypatch: pytest.MonkeyPatch
) -> None:
    unit = DiagnosisUnit(variant, _turn(history=True))

    sent = await _captured_messages(generator_for(variant), unit, monkeypatch)

    assert prompt_chars(unit) == sum(len(m["content"]) for m in sent)


@pytest.mark.unit
async def test_contract_first_moves_the_contract_and_changes_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = _unit()
    production = await _captured_messages(llm_streaming.generate_response_stream, unit, monkeypatch)
    moved = await _captured_messages(generate_contract_first, unit, monkeypatch)
    contract = llm_streaming._STREAMING_OUTPUT_CONTRACT.strip()

    assert production[0]["content"].endswith(contract)
    assert moved[0]["content"].startswith(contract)
    assert moved[0]["content"].count(contract) == 1
    assert sorted(moved[0]["content"].split()) == sorted(production[0]["content"].split())
    assert moved[1:] == production[1:]
