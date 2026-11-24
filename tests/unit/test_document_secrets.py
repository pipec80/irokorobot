"""The document secret detector (Plan 0088 Task B3, D-15): a deterministic guard, canaries only."""

from __future__ import annotations

import pytest
from server.memory.document_secrets import flags_secret

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text",
    [
        "La clave del wifi: zorro4821.",
        "contraseña = girasolazul",
        "Mi PIN es 7391.",
        "El código de acceso 55AZ9.",
        "La clave de la caja: 48213907.",
        "Tarjeta 4111 1111 1111 1111, vence pronto.",
        "Transferir a ES91 2100 0418 4502 0005 1332.",
    ],
)
def test_each_secret_shape_is_flagged(text: str) -> None:
    assert flags_secret(text)


@pytest.mark.parametrize(
    "text",
    [
        "El técnico revisa el pin 3 del conector de la bomba.",
        "El código de error 5 indica que el agua no entra.",
        "El error E21 indica que el agua no sale.",
        "La garantía empezó en 2024 y dura dos años.",
        "Lave a 40 grados y centrifugue a 1000 vueltas.",
        "La clave está en limpiar el filtro cada semana.",
        "Control el 12/03/2021 con el médico.",
        "Llame al 22 555 0101 si tiene dudas.",
        "",
    ],
)
def test_a_manual_s_numbers_and_words_are_not_flagged(text: str) -> None:
    assert not flags_secret(text)


def test_a_card_shape_that_fails_the_check_digit_is_not_flagged() -> None:
    assert not flags_secret("Pedido 4111 1111 1111 1112 del catálogo.")


@pytest.mark.parametrize(
    "text",
    [
        "La clave del router es: Gato2024!",
        "La clave de acceso del wifi: Gato2024!",
        "PIN de la tarjeta: 4821",
        "El pin de la tarjeta de debito es 4821",
        "1234 es mi clave del portón.",
        "Clave: abcd",
        "token: abcd1234",
        "El PUK es 12345678.",
    ],
)
def test_the_review_s_secret_phrasings_are_flagged(text: str) -> None:
    assert flags_secret(text)


@pytest.mark.parametrize(
    "text",
    [
        "Código de error E-21: el agua no sale.",
        "Código de producto ABC123.",
        "Llame al servicio técnico 800123456.",
        "Teléfono de la clínica: 912345678.",
    ],
)
def test_a_manual_s_codes_and_phones_are_not_flagged(text: str) -> None:
    assert not flags_secret(text)


@pytest.mark.parametrize(
    "text",
    [
        "Ficha 12345678, episodio 7654321.",
        "Folio clínico 123456789012345 del paciente.",
    ],
)
def test_a_record_s_long_numbers_are_not_flagged(text: str) -> None:
    """Measured on a real medical text (89 of 128 sections refused): an id is no secret."""
    assert not flags_secret(text)


def test_an_ungrouped_card_number_is_flagged_only_with_a_card_word() -> None:
    assert flags_secret("Tarjeta de crédito 4111111111111111.")
    assert not flags_secret("Número 4111111111111111 del registro.")
