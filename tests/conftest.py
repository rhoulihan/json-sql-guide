"""Shared pytest fixtures.

Integration tests that need Oracle pull the ``oracle_conn`` session-scoped
fixture. The fixture reads connection details from environment variables:

* ``ORACLE_HOST``     (default ``localhost``)
* ``ORACLE_PORT``     (default ``1521``)
* ``ORACLE_SERVICE``  (default ``FREEPDB1``)
* ``ORACLE_USER``     (default ``validator``)
* ``ORACLE_PASSWORD`` (default ``validator``)

If Oracle isn't reachable, the fixture ``pytest.skip()``s so the whole
integration suite is skipped gracefully on a developer laptop without
the container running. In CI the service container brings Oracle up
before the suite runs.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@pytest.fixture(scope="session")
def oracle_conn() -> Iterator[object]:
    """Session-scoped Oracle connection.

    Returns a thin-mode ``oracledb.Connection``. Skipped cleanly when
    the DB is not reachable.
    """
    oracledb = pytest.importorskip("oracledb")

    host = _env("ORACLE_HOST", "localhost")
    port = int(_env("ORACLE_PORT", "1521"))
    service = _env("ORACLE_SERVICE", "FREEPDB1")
    user = _env("ORACLE_USER", "validator")
    password = _env("ORACLE_PASSWORD", "validator")

    dsn = f"{host}:{port}/{service}"
    try:
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
    except Exception as exc:
        pytest.skip(f"Oracle not reachable at {dsn}: {exc}")

    try:
        yield conn
    finally:
        with contextlib_suppress(Exception):
            conn.close()


# tiny helper so we don't need to import contextlib at module scope
def contextlib_suppress(*exc_types: type[BaseException]):  # type: ignore[no-untyped-def]
    import contextlib

    return contextlib.suppress(*exc_types)
