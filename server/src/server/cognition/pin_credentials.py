"""Pure owner PIN hashing and verification — no persistence, no logging."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = ["EncodedPinCredential", "hash_pin", "verify_pin"]

_PIN_PATTERN = re.compile(r"^[0-9]{6,12}$")
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 3
_SCRYPT_DKLEN = 32
_SCRYPT_MAXMEM = 64 * 1024 * 1024
_SALT_LENGTH = 16


def _require_salt_length(value: bytes) -> bytes:
    """Reject any salt that is not exactly the expected length."""
    if len(value) != _SALT_LENGTH:
        raise ValueError(f"salt must be a {_SALT_LENGTH}-byte salt")
    return value


def _require_verifier_length(value: bytes) -> bytes:
    """Reject any verifier that is not exactly the expected dklen."""
    if len(value) != _SCRYPT_DKLEN:
        raise ValueError(f"verifier must be a {_SCRYPT_DKLEN}-byte verifier")
    return value


class EncodedPinCredential(BaseModel):
    """An owner PIN encoded as a salted scrypt verifier — never plaintext."""

    model_config = ConfigDict(frozen=True)

    algorithm: Literal["scrypt"]
    parameters_json: str
    salt: bytes
    verifier: bytes

    _validate_salt = field_validator("salt")(_require_salt_length)
    _validate_verifier = field_validator("verifier")(_require_verifier_length)


def _validate_pin(pin: str) -> None:
    """Raise ValueError if the candidate is not 6-12 ASCII digits.

    Never includes the candidate PIN in the exception text.
    """
    if not _PIN_PATTERN.fullmatch(pin):
        raise ValueError("PIN must be 6 to 12 ASCII digits")


def _derive(pin: str, salt: bytes) -> bytes:
    """Derive a scrypt verifier from a validated PIN and salt."""
    return hashlib.scrypt(
        pin.encode("ascii"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=_SCRYPT_DKLEN,
    )


def hash_pin(pin: str, *, salt: bytes | None = None) -> EncodedPinCredential:
    """Hash a PIN into a salted scrypt verifier.

    Args:
        pin: Candidate PIN — must be 6 to 12 ASCII digits.
        salt: Optional fixed salt for deterministic tests. Production callers
            must omit it so a fresh random salt is generated.

    Returns:
        The encoded credential: algorithm, parameters, salt, and verifier.
        Never contains the plaintext PIN.

    Raises:
        ValueError: If the PIN is not 6 to 12 ASCII digits.
    """
    _validate_pin(pin)
    used_salt = salt if salt is not None else secrets.token_bytes(_SALT_LENGTH)
    verifier = _derive(pin, used_salt)
    parameters_json = json.dumps(
        {"n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P, "dklen": _SCRYPT_DKLEN}
    )
    return EncodedPinCredential(
        algorithm="scrypt",
        parameters_json=parameters_json,
        salt=used_salt,
        verifier=verifier,
    )


def verify_pin(pin: str, credential: EncodedPinCredential) -> bool:
    """Verify a candidate PIN against a previously encoded credential.

    Args:
        pin: Candidate PIN — must be 6 to 12 ASCII digits.
        credential: A previously hashed credential to compare against.

    Returns:
        True only if the candidate PIN derives the stored verifier.

    Raises:
        ValueError: If the PIN is malformed, or the credential's salt,
            verifier, or parameters do not match the expected shape. Never
            includes the candidate PIN in the exception text.
    """
    _validate_pin(pin)
    if len(credential.salt) != _SALT_LENGTH:
        raise ValueError(f"credential salt must be a {_SALT_LENGTH}-byte salt")
    if len(credential.verifier) != _SCRYPT_DKLEN:
        raise ValueError(f"credential verifier must be a {_SCRYPT_DKLEN}-byte verifier")
    try:
        parameters = json.loads(credential.parameters_json)
    except json.JSONDecodeError as exc:
        raise ValueError("credential parameters_json is not valid JSON") from exc
    expected = {"n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P, "dklen": _SCRYPT_DKLEN}
    if parameters != expected:
        raise ValueError("credential parameters_json does not match the expected scrypt contract")

    candidate_verifier = _derive(pin, credential.salt)
    return hmac.compare_digest(candidate_verifier, credential.verifier)
