"""Local repository for the single active owner PIN credential."""

from dataclasses import dataclass

from server.cognition.identity import HouseholdRole
from server.cognition.pin_credentials import EncodedPinCredential
from server.db import get_conn
from server.memory.household_authorization import get_active_role

__all__ = [
    "OwnerPinCredential",
    "get_active_owner_pin_credential",
    "revoke_owner_pin_credential",
    "save_owner_pin_credential",
]


@dataclass(frozen=True)
class OwnerPinCredential:
    """One durable owner PIN credential row without the raw PIN."""

    id: int
    person_entity_id: int
    encoded: EncodedPinCredential


async def get_active_owner_pin_credential() -> OwnerPinCredential | None:
    """Return the sole active owner PIN credential.

    Returns:
        The active credential, or None if no owner has an active PIN yet.
    """
    cursor = await get_conn().execute(
        "SELECT id, person_entity_id, algorithm, parameters_json, salt, verifier "
        "FROM owner_pin_credentials WHERE revoked_at IS NULL"
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return None
    return OwnerPinCredential(
        id=int(row[0]),
        person_entity_id=int(row[1]),
        encoded=EncodedPinCredential(
            algorithm=row[2],
            parameters_json=row[3],
            salt=row[4],
            verifier=row[5],
        ),
    )


async def save_owner_pin_credential(
    *, person_entity_id: int, credential: EncodedPinCredential
) -> OwnerPinCredential:
    """Persist one owner PIN credential, creating or atomically rotating it.

    A caller that already verified the candidate PIN still matches the
    active credential must not call this function — it always performs a
    write, either the first credential or a genuine rotation.

    Args:
        person_entity_id: Existing person entity with an active owner role.
        credential: A freshly encoded credential to become the active one.

    Returns:
        The newly active credential.

    Raises:
        ValueError: If the entity does not hold an active owner role.
    """
    if await get_active_role(person_entity_id) is not HouseholdRole.OWNER:
        raise ValueError("owner PIN credential requires an active owner role")

    conn = get_conn()
    await conn.execute("BEGIN IMMEDIATE")
    try:
        await conn.execute(
            "UPDATE owner_pin_credentials SET revoked_at = datetime('now') "
            "WHERE person_entity_id = ? AND revoked_at IS NULL",
            (person_entity_id,),
        )
        cursor = await conn.execute(
            "INSERT INTO owner_pin_credentials "
            "(person_entity_id, algorithm, parameters_json, salt, verifier) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                person_entity_id,
                credential.algorithm,
                credential.parameters_json,
                credential.salt,
                credential.verifier,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("INSERT into owner_pin_credentials returned no lastrowid")
        credential_id = int(cursor.lastrowid)
        await cursor.close()
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    return OwnerPinCredential(
        id=credential_id, person_entity_id=person_entity_id, encoded=credential
    )


async def revoke_owner_pin_credential(*, person_entity_id: int) -> None:
    """Logically revoke the active credential for one owner.

    Args:
        person_entity_id: Existing person entity whose credential is revoked.

    Raises:
        ValueError: If no active credential exists for this person.
    """
    conn = get_conn()
    cursor = await conn.execute(
        "UPDATE owner_pin_credentials SET revoked_at = datetime('now') "
        "WHERE person_entity_id = ? AND revoked_at IS NULL",
        (person_entity_id,),
    )
    updated = cursor.rowcount
    await cursor.close()
    if updated != 1:
        await conn.rollback()
        raise ValueError("no active owner PIN credential exists for this person")
    await conn.commit()
