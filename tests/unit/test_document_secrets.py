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
        "Anote el número 48213907 en la caja.",
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
