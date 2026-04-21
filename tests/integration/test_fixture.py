"""Integration tests for the FixtureLoader.

These tests require a live Oracle AI Database 26ai instance. They skip
cleanly when one isn't reachable — see ``tests/conftest.py::oracle_conn``.
Mark every test ``@pytest.mark.requires_oracle`` so the integration job
in CI picks them up.
"""

from __future__ import annotations

from typing import Any

import pytest

from validator.fixture import FixtureLoader, UnknownSeedError

pytestmark = pytest.mark.requires_oracle


def _scalar(conn: Any, sql: str) -> Any:
    cur = conn.cursor()
    try:
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


# ───────── 1 — idempotent drop/recreate ─────────


def test_fixture_drops_and_recreates_schema_idempotently(oracle_conn: Any) -> None:
    loader = FixtureLoader(oracle_conn, profiles=["base"])
    loader.load()
    first_count = _scalar(oracle_conn, "SELECT COUNT(*) FROM orders")

    loader.load()  # second run should succeed without error
    second_count = _scalar(oracle_conn, "SELECT COUNT(*) FROM orders")

    assert first_count == second_count


# ───────── 2 — base seed loads orders and asserts count ─────────


def test_fixture_loads_base_seed_and_asserts_row_counts(oracle_conn: Any) -> None:
    FixtureLoader(oracle_conn, profiles=["base"]).load()
    count = _scalar(oracle_conn, "SELECT COUNT(*) FROM orders")
    # Base profile creates exactly 10 orders per the plan.
    assert count == 10


# ───────── 3 — tags-with-nums seed ─────────


def test_fixture_loads_tags_with_nums_seed_and_inspects_array_shape(
    oracle_conn: Any,
) -> None:
    FixtureLoader(oracle_conn, profiles=["base", "tags_with_nums"]).load()
    # At least one order should have a numeric value inside its tags array.
    exists = _scalar(
        oracle_conn,
        """
        SELECT COUNT(*) FROM orders o
        WHERE JSON_EXISTS(o.order_doc, '$.tags[*]?(@.number() >= 0)')
        """,
    )
    assert exists >= 1


# ───────── 4 — deep-nest seed has 4-level paths ─────────


def test_fixture_loads_deep_nest_seed_with_four_level_paths(oracle_conn: Any) -> None:
    FixtureLoader(oracle_conn, profiles=["base", "deep_nest"]).load()
    exists = _scalar(
        oracle_conn,
        """
        SELECT COUNT(*) FROM orders o
        WHERE JSON_EXISTS(o.order_doc, '$.shipping.address.geo.coords[0]')
        """,
    )
    assert exists >= 1


# ───────── 5 — dates-and-intervals seed ─────────


def test_fixture_loads_dates_and_intervals_seed(oracle_conn: Any) -> None:
    FixtureLoader(oracle_conn, profiles=["base", "dates_and_intervals"]).load()
    date_exists = _scalar(
        oracle_conn,
        """
        SELECT COUNT(*) FROM orders o
        WHERE JSON_VALUE(o.order_doc, '$.orderDate' RETURNING DATE) IS NOT NULL
        """,
    )
    assert date_exists >= 1


# ───────── 6 — hybrid seed (customers + products populated) ─────────


def test_fixture_loads_hybrid_seed_with_customers_and_products(oracle_conn: Any) -> None:
    FixtureLoader(oracle_conn, profiles=["base", "hybrid"]).load()
    customers = _scalar(oracle_conn, "SELECT COUNT(*) FROM customers")
    products = _scalar(oracle_conn, "SELECT COUNT(*) FROM products")
    assert customers >= 3
    assert products >= 3


# ───────── 7 — multiple profiles compose ─────────


def test_fixture_loader_accepts_multiple_seed_profiles_in_one_run(
    oracle_conn: Any,
) -> None:
    loader = FixtureLoader(
        oracle_conn,
        profiles=["base", "tags_with_nums", "deep_nest"],
    )
    loader.load()
    count = _scalar(oracle_conn, "SELECT COUNT(*) FROM orders")
    assert count >= 10  # base + extras


# ───────── 8 — unknown profile raises ─────────


def test_fixture_loader_raises_on_unknown_seed_profile(oracle_conn: Any) -> None:
    loader = FixtureLoader(oracle_conn, profiles=["not_a_real_profile"])
    with pytest.raises(UnknownSeedError, match="not_a_real_profile"):
        loader.load()


# ───────── 9 — re-run without error ─────────


def test_fixture_loader_can_rerun_against_already_loaded_db_without_error(
    oracle_conn: Any,
) -> None:
    loader = FixtureLoader(oracle_conn, profiles=["base"])
    loader.load()
    loader.load()  # must not raise
    loader.load()


# ───────── 10 — order_items table for duality view ─────────


def test_fixture_loader_creates_order_items_table_for_duality_view_example(
    oracle_conn: Any,
) -> None:
    FixtureLoader(oracle_conn, profiles=["base", "hybrid"]).load()
    # Must be queryable; an empty result is fine — the table's existence is what matters.
    cur = oracle_conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM order_items")
        (count,) = cur.fetchone()
        assert isinstance(count, int)
    finally:
        cur.close()
