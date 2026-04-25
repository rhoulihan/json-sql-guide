"""Fixture loader for the validator's integration tests.

The loader is strictly idempotent: every call to :meth:`FixtureLoader.load`
drops existing fixture tables, re-applies ``fixture/schema.sql``, and
then runs the ``load(conn)`` entry point of each requested seed profile
module in ``fixture.seeds``. Running a profile twice in a row yields the
same row counts — the second run re-creates a pristine schema before
re-seeding.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[2] / "fixture" / "schema.sql"

# Drop order matters: children first (FK: order_items → orders).
_DROP_ORDER: tuple[str, ...] = (
    "order_items",
    "products",
    "customers",
    "validated_orders",
    "entities",
    "events",
    "employees",
    "categories",
    "user_settings",
    "legacy_table",
    "orders",
)

_DROP_IF_EXISTS_TEMPLATE = """
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE {table} CASCADE CONSTRAINTS PURGE';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -942 THEN RAISE; END IF;
END;
"""


class UnknownSeedError(ValueError):
    """Raised when a requested seed profile can't be imported."""


@dataclass(frozen=True, slots=True)
class FixtureLoader:
    """Composable fixture loader.

    ``profiles`` names seed modules under ``fixture.seeds``. Each module
    must expose a ``load(conn)`` callable.
    """

    conn: Any
    profiles: list[str] = field(default_factory=list)

    def load(self) -> None:
        """Drop + recreate the schema, then run every seed profile."""
        self._drop_all()
        self._apply_schema()
        for name in self.profiles:
            module = self._import_profile(name)
            module.load(self.conn)

    def _drop_all(self) -> None:
        cur = self.conn.cursor()
        try:
            for table in _DROP_ORDER:
                cur.execute(_DROP_IF_EXISTS_TEMPLATE.format(table=table))
            self.conn.commit()
        finally:
            cur.close()

    def _apply_schema(self) -> None:
        statements = _split_ddl(_SCHEMA_SQL_PATH.read_text())
        cur = self.conn.cursor()
        try:
            for stmt in statements:
                cur.execute(stmt)
            self.conn.commit()
        finally:
            cur.close()

    @staticmethod
    def _import_profile(name: str) -> Any:
        try:
            return importlib.import_module(f"fixture.seeds.{name}")
        except ModuleNotFoundError as exc:
            raise UnknownSeedError(
                f"unknown seed profile: {name!r}. Available profiles live under fixture/seeds/"
            ) from exc


def _split_ddl(source: str) -> list[str]:
    """Strip ``--`` line comments and split on top-level semicolons.

    The schema is plain DDL with no PL/SQL blocks and no semicolons inside
    string literals, so a simple semicolon split is correct here.
    """
    lines = []
    for raw in source.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith("--"):
            continue
        lines.append(raw)
    joined = "\n".join(lines)
    parts = [chunk.strip() for chunk in joined.split(";")]
    return [chunk for chunk in parts if chunk]
