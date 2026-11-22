"""Small reusable model column helpers."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import Enum


def pg_enum[E: enum.Enum](enum_cls: type[E], name: str, **kwargs: Any) -> Enum:
    """PostgreSQL native enum storing the member *values*, not member names.

    The type is created explicitly by the migration (and by ``create_all`` in tests)
    before any table that uses it, which keeps downgrade ordering deterministic.
    """

    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        create_constraint=False,
        validate_strings=True,
        values_callable=lambda members: [str(member.value) for member in members],
        **kwargs,
    )
