"""Declarative base for all ORM models.

Domain models land in Phase 2 per ``docs/database/DATABASE_SCHEMA.md``. Alembic
autogenerate compares against this metadata, so every model must be imported into
``app.models`` and that package imported from the migration environment.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for Rice Age ORM models."""
