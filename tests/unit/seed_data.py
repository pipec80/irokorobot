"""Shared invented seed files for the Plan 0071 tests: a full household and a TOML writer.

Every name, phone and value is an invented canary.
"""

from __future__ import annotations

import copy
import json
from typing import Any

# A TOML document is heterogeneous by nature; the tests index into it freely.
type Toml = dict[str, Any]

_FULL: Toml = {
    "schema_version": 1,
    "pool_version": 1,
    "owner": {
        "name": "Canary Owner",
        "preferred_name": "Canary",
        "address_form": "tu",
        "birth_date": "1950-05-17",
        "health_coverage": "Canary Plan",
        "conditions": ["Canary condition"],
        "allergies": ["Canary allergy"],
        "medications": ["Canary pill, 10 mg, 8:00 y 20:00, con comida"],
        "takes_anticoagulant": "no",
        "rescue_medication": ["Canary inhaler, en el velador"],
        "devices": [],
        "blood_type": "O+",
        "mobility": "solo",
        "hearing": "normal",
        "vision": "lentes",
        "documents": ["el testamento está en el cajón del escritorio"],
        "emergency_facility": "Canary Clinic",
        "address": "Canary Street 100, Canary Town",
        "dwelling_type": "departamento",
        "floor": 20,
        "has_lift": "si",
        "access_note": "conserje en recepción",
        "lives_alone": "si",
        "likes": ["té verde"],
        "dislikes": [],
        "prefers": [],
        "private_topics": [],
        "secrets": ["la alarma la tiene Canary Friend"],
    },
    "status": {"devices": "none"},
    "partner": {"name": "Canary Partner"},
    "children": [
        {
            "name": "Canary Child",
            "guardianship": "minor",
            "birth_date": "2015-03-02",
            "likes": ["dibujar"],
        },
        {"name": "Canary Grown", "guardianship": "adult"},
    ],
    "pets": [{"name": "Canary Pet", "species": "gato", "stated_age": 3}],
    "parents": [{"name": "Canary Parent"}],
    "grandparents": [{"name": "Canary Grandparent"}],
    "siblings": [{"name": "Canary Sibling"}],
    "grandchildren": [{"name": "Canary Grandchild"}],
    "withhold": [{"name": "Canary Parent"}, {"name": "Canary Stranger"}],
    "contacts": [
        {
            "name": "Canary Grown",
            "role": "caregiver",
            "relationship": "hija",
            "may_view_activity": False,
            "phone": "+56900000001",
            "phone_alt": "+56200000002",
            "call_order": 1,
            "has_key": True,
            "may_receive_health_info": True,
        },
        {
            "name": "Canary Doctor",
            "role": "doctor",
            "phone": "+56900000003",
            "call_order": 2,
        },
    ],
}


def full_seed() -> Toml:
    """Return a fresh copy of the full invented household."""
    return copy.deepcopy(_FULL)


def minimal_seed() -> Toml:
    """Return the smallest valid file: the header and the owner's name."""
    return {"schema_version": 1, "pool_version": 1, "owner": {"name": "Canary Owner"}}


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def to_toml(data: Toml) -> str:
    """Write a seed dictionary as TOML: plain keys, tables and arrays of tables."""
    lines: list[str] = []
    tables: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append(f"\n[{key}]")
            tables.extend(f"{inner} = {_value(item)}" for inner, item in value.items())
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            for item in value:
                tables.append(f"\n[[{key}]]")
                tables.extend(f"{inner} = {_value(field)}" for inner, field in item.items())
        else:
            lines.append(f"{key} = {_value(value)}")
    return "\n".join([*lines, *tables]) + "\n"
