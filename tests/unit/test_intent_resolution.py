"""Unit tests for server.cognition.intent_resolution — the P0-C5 pure resolver.

Covers the reviewed Spanish corpus, precedence, normalization stability,
rule-ID privacy, and immutability. This resolver never identifies a speaker,
grants access, or calls an LLM/VLM/embedding/database — see
docs/plans/open/0021-p0-typed-intent-resolution.md.
"""

import json
from pathlib import Path

from pydantic import ValidationError
import pytest
from server.cognition import intent_resolution as resolver_module
from server.cognition.intent_resolution import (
    IntentMatch,
    IntentResolution,
    resolve_information_need,
)
from server.cognition.response_plan import InformationNeed
import yaml

_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "intent_resolution_es.json"
_CORPUS: list[dict[str, object]] = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize("row", _CORPUS, ids=[str(row["text"]) for row in _CORPUS])
def test_resolver_matches_the_reviewed_corpus(row: dict[str, object]) -> None:
    """Every reviewed phrase resolves to its exact expected need/match/rule."""
    expected = IntentResolution(
        need=InformationNeed(row["need"]),
        match=IntentMatch(row["match"]),
        rule_id=row["rule_id"],  # type: ignore[arg-type]  # str | None from JSON
    )

    result = resolve_information_need(str(row["text"]))

    assert result == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "variant,canonical",
    [
        ("¿QUÉ FECHA ES HOY?", "¿Qué fecha es hoy?"),
        ("que    fecha    es    hoy", "¿Qué fecha es hoy?"),
        ("¿Qué, fecha... es hoy?!", "¿Qué fecha es hoy?"),
        ("qué fecha es hoy", "¿Qué fecha es hoy?"),
    ],
)
def test_normalization_is_stable_across_case_spacing_and_punctuation(
    variant: str, canonical: str
) -> None:
    """Case, accents, repeated whitespace, and punctuation must not change the result."""
    assert resolve_information_need(variant) == resolve_information_need(canonical)


@pytest.mark.unit
def test_rule_id_never_contains_the_utterance_or_a_name() -> None:
    """rule_id is closed operational metadata, never the raw message or a name."""
    result = resolve_information_need("¿Cuándo nació mi hijo Joaquín?")

    assert result.rule_id is not None
    assert "joaquin" not in result.rule_id.lower()
    assert "nacio" not in result.rule_id.lower()
    assert "cuando" not in result.rule_id.lower()


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "Aprende mi cara, soy PersonaDePrueba.",
        "Aprende mi cara.",
    ],
)
def test_enrollment_rule_id_never_contains_the_utterance_or_a_name(text: str) -> None:
    """The resolver never extracts or retains a name — same rule_id either way."""
    result = resolve_information_need(text)

    assert result.need is InformationNeed.BIOMETRIC_ENROLLMENT
    assert result.rule_id == "enrollment.biometric.v1"
    assert "personadeprueba" not in result.rule_id.lower()


@pytest.mark.unit
def test_resolution_is_frozen_and_rejects_mutation() -> None:
    """IntentResolution must be immutable, matching every other cognitive contract."""
    result = resolve_information_need("Hola, ¿cómo estás?")

    with pytest.raises(ValidationError):
        result.need = InformationNeed.CURRENT_DATE  # type: ignore[misc]  # proving frozen


# Plan 0079, Task 5: two information needs behind two flags, in a fixed rule order (D-1).
_ADDRESS_QUESTION = "¿Cuál es mi dirección?"
_STATED_VALUE = "Mi clave es 1234."
_ASKED_VALUE = "¿Cuál es mi clave del banco?"
_SECURITY_QUESTION = "¿Quién conoce la clave de la alarma?"
_CHILD_BIRTHDAY_QUESTION = "¿Cuándo es el cumpleaños de mi hijo?"


@pytest.mark.unit
@pytest.mark.parametrize("recall", [False, True])
def test_with_every_flag_off_the_rules_are_unchanged(recall: bool) -> None:
    """The defaults and the explicit ``False`` flags agree on the whole reviewed corpus.

    With recall off, each corpus row also matches the fixture's need and rule id; with recall on,
    only the agreement of the two calls is asserted (the recall rules change some rows on purpose).
    """
    for row in _CORPUS:
        text = str(row["text"])
        by_default = resolve_information_need(text, recall=recall)
        explicit = resolve_information_need(text, recall=recall, sensitive=False, secrets=False)

        assert explicit == by_default
        assert explicit.model_dump_json() == by_default.model_dump_json()
        if not recall:
            assert by_default.need is InformationNeed(row["need"])
            assert by_default.rule_id == row["rule_id"]


@pytest.mark.unit
@pytest.mark.parametrize("recall", [False, True])
def test_a_sensitive_question_needs_the_flag(recall: bool) -> None:
    """Without ``sensitive`` the question is ordinary; with it, a read with a topic rule id."""
    off = resolve_information_need(_ADDRESS_QUESTION, recall=recall, secrets=True)
    on = resolve_information_need(_ADDRESS_QUESTION, recall=recall, sensitive=True)

    assert off.need is InformationNeed.GENERIC_CONVERSATION
    assert on == IntentResolution(
        need=InformationNeed.SENSITIVE_READ,
        match=IntentMatch.EXACT,
        rule_id="sensitive.address.v1",
    )


@pytest.mark.unit
@pytest.mark.parametrize("message", [_STATED_VALUE, _ASKED_VALUE])
def test_a_secret_needs_the_flag(message: str) -> None:
    """Without ``secrets`` a secret turn is ordinary; with it, a secret value."""
    off = resolve_information_need(message, sensitive=True)
    on = resolve_information_need(message, secrets=True)

    assert off.need is InformationNeed.GENERIC_CONVERSATION
    assert on.need is InformationNeed.SECRET_VALUE
    assert on.match is IntentMatch.EXACT


@pytest.mark.unit
def test_the_secret_rule_ids_tell_stated_from_asked() -> None:
    """Each kind has its own closed rule id, never the words."""
    stated = resolve_information_need(_STATED_VALUE, secrets=True)
    asked = resolve_information_need(_ASKED_VALUE, secrets=True)

    assert stated.rule_id == "secret.stated.v1"
    assert asked.rule_id == "secret.asked.v1"


@pytest.mark.unit
@pytest.mark.parametrize("recall", [False, True])
def test_an_offered_secret_resolves_to_a_secret_value_only_with_the_flag(recall: bool) -> None:
    """«Guarda mi contraseña» gives no value yet; it must not reach the model and invite one."""
    message = "Iroko, recuerda mi clave del banco"

    off = resolve_information_need(message, recall=recall, sensitive=True)
    on = resolve_information_need(message, recall=recall, secrets=True)

    assert off.need is not InformationNeed.SECRET_VALUE
    assert on == IntentResolution(
        need=InformationNeed.SECRET_VALUE,
        match=IntentMatch.EXACT,
        rule_id="secret.offered.v1",
    )


@pytest.mark.unit
@pytest.mark.parametrize("recall", [False, True])
def test_a_stated_secret_wins_over_a_sensitive_question(recall: bool) -> None:
    """A message that states a value and asks a question is the secret branch (review focus 5)."""
    message = "Mi clave es 1234, ¿cuál es mi dirección?"

    result = resolve_information_need(message, recall=recall, sensitive=True, secrets=True)

    assert result.need is InformationNeed.SECRET_VALUE
    assert result.rule_id == "secret.stated.v1"


@pytest.mark.unit
def test_the_security_question_is_a_read_not_a_secret() -> None:
    """«¿Quién conoce la clave de la alarma?» names no value: a sensitive read, not a secret."""
    result = resolve_information_need(_SECURITY_QUESTION, sensitive=True, secrets=True)

    assert result.need is InformationNeed.SENSITIVE_READ
    assert result.rule_id == "sensitive.secret_holder.v1"


@pytest.mark.unit
def test_the_security_question_is_ordinary_with_the_switch_off() -> None:
    """With the sensitive switch off the same question is ordinary conversation, as today."""
    result = resolve_information_need(_SECURITY_QUESTION, secrets=True)

    assert result == resolve_information_need(_SECURITY_QUESTION)
    assert result.need is InformationNeed.GENERIC_CONVERSATION


@pytest.mark.unit
@pytest.mark.parametrize("recall", [False, True])
def test_the_sensitive_rule_comes_before_the_household_protection(recall: bool) -> None:
    """The owner's own question is read before the protected-household rule can refuse it."""
    protected = resolve_information_need(_CHILD_BIRTHDAY_QUESTION, recall=recall)
    read = resolve_information_need(_CHILD_BIRTHDAY_QUESTION, recall=recall, sensitive=True)

    assert protected.need is InformationNeed.PROTECTED_HOUSEHOLD
    assert read.need is InformationNeed.SENSITIVE_READ
    assert read.rule_id == "sensitive.child_birthday.v1"
    address = resolve_information_need(_ADDRESS_QUESTION, recall=recall, sensitive=True)
    assert address.need is InformationNeed.SENSITIVE_READ


@pytest.mark.unit
@pytest.mark.parametrize("recall", [False, True])
def test_a_secret_wins_over_a_memory_answer(recall: bool) -> None:
    """«sí, guarda mi clave es 1234» is a memory answer today and a secret with the guard on."""
    message = "Sí, guarda mi clave es 1234"

    assert resolve_information_need(message).need is InformationNeed.MEMORY_ANSWER
    guarded = resolve_information_need(message, recall=recall, secrets=True)

    assert guarded.need is InformationNeed.SECRET_VALUE
    assert guarded.rule_id == "secret.stated.v1"


@pytest.mark.unit
def test_the_rule_order_is_stated_then_sensitive_then_asked() -> None:
    """D-1: the new rules come first, in this order, and only for the flags that are set."""
    names = [rule.__name__ for rule in resolver_module._rules_for(False, True, True)[:3]]

    assert names == ["_stated_secret_rule", "_sensitive_question_rule", "_asked_secret_rule"]
    assert resolver_module._rules_for(False, False, False) is resolver_module._RULES
    assert resolver_module._rules_for(True, False, False) is resolver_module._RECALL_RULES
    assert resolver_module._rules_for(True, True, True) is resolver_module._rules_for(
        True, True, True
    )


@pytest.mark.unit
def test_the_new_rule_ids_never_carry_the_words() -> None:
    """A rule id is closed operational metadata, never a value or a keyword."""
    for message in (_STATED_VALUE, _ASKED_VALUE, _ADDRESS_QUESTION, _SECURITY_QUESTION):
        result = resolve_information_need(message, sensitive=True, secrets=True)

        assert result.rule_id is not None
        assert "1234" not in result.rule_id
        assert "alarma" not in result.rule_id
        assert "banco" not in result.rule_id


@pytest.mark.unit
def test_resolution_rejects_unknown_fields() -> None:
    """The contract is closed — extra fields must be rejected, not silently dropped."""
    with pytest.raises(ValidationError):
        IntentResolution(
            need=InformationNeed.GENERIC_CONVERSATION,
            match=IntentMatch.NONE,
            rule_id=None,
            confidence=0.9,  # type: ignore[call-arg]  # deliberately unsupported field
        )


# --- Plan 0082 Task 6: the alta flag (D-2) ---

_ALTA_CORPUS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "fixtures" / "alta_questions.yaml").read_text(
        encoding="utf-8"
    )
)
_ALTA_PHRASES = [
    (phrase, key) for key, phrases in _ALTA_CORPUS["questions"].items() for phrase in phrases
]


@pytest.mark.parametrize("message, topic", _ALTA_PHRASES)
def test_an_alta_question_needs_both_flags(message: str, topic: str) -> None:
    on = resolve_information_need(message, recall=True, sensitive=True, secrets=True, alta=True)
    assert on.need is InformationNeed.SENSITIVE_READ
    assert on.rule_id == f"sensitive.{topic}.v1"
    without_alta = resolve_information_need(message, recall=True, sensitive=True, secrets=True)
    assert without_alta.rule_id != f"sensitive.{topic}.v1"
    alta_alone = resolve_information_need(message, recall=True, secrets=True, alta=True)
    assert alta_alone == resolve_information_need(message, recall=True, secrets=True)


_SENSITIVE_CORPUS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "fixtures" / "sensitive_questions.yaml").read_text(
        encoding="utf-8"
    )
)
_EVERY_PLAN_0079_PHRASE = [
    *(phrase for phrases in _SENSITIVE_CORPUS["questions"].values() for phrase in phrases),
    *(phrase for phrases in _SENSITIVE_CORPUS["slips"].values() for phrase in phrases),
    *_SENSITIVE_CORPUS["traps"],
    "hola",
]


@pytest.mark.parametrize("recall", [False, True])
def test_with_the_alta_flag_off_resolutions_are_unchanged(recall: bool) -> None:
    for message in _EVERY_PLAN_0079_PHRASE:
        assert resolve_information_need(
            message, recall=recall, sensitive=True, secrets=True, alta=False
        ) == resolve_information_need(message, recall=recall, sensitive=True, secrets=True)


def test_a_call_request_is_a_sensitive_read() -> None:
    result = resolve_information_need(
        "Llama a mi contacto 1", recall=True, sensitive=True, secrets=True, alta=True
    )
    assert result.need is InformationNeed.SENSITIVE_READ
    assert result.rule_id == "sensitive.contact_call.v1"
