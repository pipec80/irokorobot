"""Unit tests for pure owner PIN hashing and verification."""

import json

import pytest
from server.cognition.pin_credentials import EncodedPinCredential, hash_pin, verify_pin


@pytest.mark.unit
@pytest.mark.parametrize(
    "pin",
    ["", "12345", "1234567890123", "１２３４５６", "123 456", "abcdef"],  # noqa: RUF001
)
def test_hash_pin_rejects_non_six_to_twelve_ascii_digits(pin: str) -> None:
    """Only 6-12 ASCII digits are an acceptable PIN."""
    with pytest.raises(ValueError, match="6 to 12 ASCII digits"):
        hash_pin(pin)


@pytest.mark.unit
def test_hash_pin_uses_unique_salt_and_never_contains_plaintext() -> None:
    """Each hash call derives a fresh unpredictable salt and verifier."""
    first = hash_pin("482173")
    second = hash_pin("482173")
    assert len(first.salt) == 16
    assert first.salt != second.salt
    assert first.verifier != second.verifier
    assert b"482173" not in first.salt + first.verifier


@pytest.mark.unit
def test_verify_pin_accepts_only_the_matching_pin() -> None:
    """verify_pin distinguishes the exact PIN from any near miss."""
    credential = hash_pin("482173", salt=b"0" * 16)
    assert verify_pin("482173", credential) is True
    assert verify_pin("482174", credential) is False


@pytest.mark.unit
def test_hash_pin_records_exact_algorithm_and_parameters() -> None:
    """The stored parameter contract must match the plan's scrypt constants."""
    credential = hash_pin("482173")
    assert credential.algorithm == "scrypt"
    parameters = json.loads(credential.parameters_json)
    assert parameters == {"n": 2**15, "r": 8, "p": 3, "dklen": 32}


@pytest.mark.unit
def test_verify_pin_rejects_malformed_credential_fields() -> None:
    """A malformed salt, verifier, or parameters payload fails closed."""
    credential = hash_pin("482173")
    bad_salt = credential.model_copy(update={"salt": b"short"})
    with pytest.raises(ValueError, match="16-byte salt"):
        verify_pin("482173", bad_salt)

    bad_params = credential.model_copy(update={"parameters_json": "not json"})
    with pytest.raises(ValueError, match="parameters_json"):
        verify_pin("482173", bad_params)


@pytest.mark.unit
def test_verify_pin_error_never_leaks_candidate_pin() -> None:
    """Exception text from a malformed credential never echoes the candidate PIN."""
    credential = hash_pin("482173")
    bad_salt = credential.model_copy(update={"salt": b"short"})
    with pytest.raises(ValueError, match="16-byte salt") as exc_info:
        verify_pin("999999", bad_salt)
    assert "999999" not in str(exc_info.value)


@pytest.mark.unit
def test_encoded_pin_credential_rejects_wrong_length_salt_or_verifier() -> None:
    """EncodedPinCredential itself is a typed value, not a raw bytes bag."""
    with pytest.raises(ValueError, match="16-byte salt"):
        EncodedPinCredential(
            algorithm="scrypt",
            parameters_json=json.dumps({"n": 2**15, "r": 8, "p": 3, "dklen": 32}),
            salt=b"short",
            verifier=b"1" * 32,
        )
    with pytest.raises(ValueError, match="32-byte verifier"):
        EncodedPinCredential(
            algorithm="scrypt",
            parameters_json=json.dumps({"n": 2**15, "r": 8, "p": 3, "dklen": 32}),
            salt=b"0" * 16,
            verifier=b"short",
        )
