"""Seed: relational rows for the hybrid / Duality View examples.

Populates ``customers``, ``products``, and ``order_items`` — the tables
that the guide's hybrid modeling and JSON Relational Duality View
sections join against. Base ``orders`` must already be loaded because
``order_items.order_id`` has a foreign-key reference to ``orders``.
"""

from __future__ import annotations

from typing import Any

_CUSTOMERS: list[tuple[str, str, str]] = [
    ("CUST-001", "Acme Corp", "platinum"),
    ("CUST-002", "Beta LLC", "gold"),
    ("CUST-003", "Gamma Inc", "gold"),
    ("CUST-004", "Delta Co", "silver"),
    ("CUST-005", "Epsilon Labs", "silver"),
]

_PRODUCTS: list[tuple[str, str, int, float]] = [
    ("LAPTOP-001", "Developer Laptop 16", 10, 1299.00),
    ("MOUSE-042", "Wireless Mouse", 10, 18.50),
    ("CABLE-USB", "USB-C Cable 2m", 10, 7.00),
    ("MONITOR-27", "27-inch 4K Monitor", 10, 499.00),
    ("WIDGET-PRO", "Widget Pro", 20, 100.00),
    ("SERVER-RACK", "Server Rack 42U", 30, 2499.99),
    ("LAPTOP-STAND", "Laptop Stand", 40, 63.00),
]

_ORDER_ITEMS: list[tuple[int, int, str, int, float]] = [
    # (item_id, order_id, sku, quantity, unit_price)
    (10001, 1001, "LAPTOP-001", 1, 1299.00),
    (10002, 1002, "MOUSE-042", 2, 18.50),
    (10003, 1002, "CABLE-USB", 3, 7.17),
    (10004, 1003, "MONITOR-27", 1, 499.00),
    (10005, 1003, "WIDGET-PRO", 4, 100.00),
    (10006, 1007, "CABLE-USB", 6, 7.00),
    (10007, 1010, "LAPTOP-STAND", 3, 63.00),
]


def load(conn: Any) -> None:
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO customers (customer_id, customer_name, tier) "
            "VALUES (:1, :2, :3)",
            _CUSTOMERS,
        )
        cur.executemany(
            "INSERT INTO products (sku, product_name, category_id, list_price) "
            "VALUES (:1, :2, :3, :4)",
            _PRODUCTS,
        )
        cur.executemany(
            "INSERT INTO order_items (item_id, order_id, sku, quantity, unit_price) "
            "VALUES (:1, :2, :3, :4, :5)",
            _ORDER_ITEMS,
        )
        conn.commit()
    finally:
        cur.close()
