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

_PRODUCTS: list[tuple[str, str, int, float, float, str]] = [
    # (sku, product_name, category_id, list_price, weight_kg, supplier)
    ("LAPTOP-001",   "Widget Pro",   3, 1299.00,  2.10, "Acme Manufacturing"),
    ("MOUSE-042",    "Gadget Plus",  3,   18.50,  0.10, "Beta Devices"),
    ("CABLE-USB",    "Cable Kit",    6,    7.00,  0.05, "Beta Devices"),
    ("MONITOR-27",   "Monitor 27",   4,  499.00,  6.40, "Acme Manufacturing"),
    ("SERVER-RACK",  "Server Rack",  8, 2499.99, 38.00, "Heavy Iron Co"),
    ("LAPTOP-STAND", "Laptop Stand", 8,   63.00,  1.30, "Beta Devices"),
    ("SENSOR-900",   "Sensor 900",   1,   65.15,  0.30, "Acme Manufacturing"),
    ("GADGET-PLUS",  "Gadget Plus",  3,   49.99,  0.40, "Beta Devices"),
    ("WIDGET-PRO",   "Widget Pro",   3,   29.99,  0.50, "Acme Manufacturing"),
]

_ORDER_ITEMS: list[tuple[int, int, str, int, float]] = [
    # (item_id, order_id, sku, quantity, unit_price) — order_id matches the
    # IDENTITY values 1..10 produced by the base seed.
    (10001, 1, "LAPTOP-001", 1, 1299.00),
    (10002, 2, "MOUSE-042", 2, 18.50),
    (10003, 2, "CABLE-USB", 3, 7.17),
    (10004, 3, "MONITOR-27", 1, 499.00),
    (10005, 3, "WIDGET-PRO", 4, 100.00),
    (10006, 7, "CABLE-USB", 6, 7.00),
    (10007, 10, "LAPTOP-STAND", 3, 63.00),
]

_CATEGORIES: list[tuple[int, int | None, str]] = [
    # (id, parent_id, name) — a small tree for the recursive CTE example
    (1, None, "Electronics"),
    (2, 1, "Computers"),
    (3, 2, "Laptops"),
    (4, 2, "Monitors"),
    (5, 1, "Networking"),
    (6, 5, "Cables"),
    (7, None, "Hardware"),
    (8, 7, "Storage"),
]

_EMPLOYEES: list[tuple[int, str, str, str, int, str, float]] = [
    # (employee_id, first_name, last_name, email, dept_id, hire_date_iso, salary)
    (100, "Steven",  "King",     "SKING",     10, "2020-01-15", 245000),
    (101, "Ada",     "Lovelace", "ALOVELACE", 10, "2023-01-15", 145000),
    (102, "Alan",    "Turing",   "ATURING",   10, "2022-06-01", 165000),
    (103, "Grace",   "Hopper",   "GHOPPER",   20, "2021-03-12", 175000),
    (104, "Edsger",  "Dijkstra", "EDIJKSTRA", 20, "2024-08-22", 155000),
    (105, "Donald",  "Knuth",    "DKNUTH",    30, "2020-11-04", 185000),
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
            "INSERT INTO products "
            "(sku, product_name, category_id, list_price, weight_kg, supplier) "
            "VALUES (:1, :2, :3, :4, :5, :6)",
            _PRODUCTS,
        )
        cur.executemany(
            "INSERT INTO order_items (item_id, order_id, sku, quantity, unit_price) "
            "VALUES (:1, :2, :3, :4, :5)",
            _ORDER_ITEMS,
        )
        cur.executemany(
            "INSERT INTO categories (id, parent_id, name) VALUES (:1, :2, :3)",
            _CATEGORIES,
        )
        cur.executemany(
            "INSERT INTO employees "
            "(employee_id, first_name, last_name, email, dept_id, hire_date, salary) "
            "VALUES (:1, :2, :3, :4, :5, TO_DATE(:6, 'YYYY-MM-DD'), :7)",
            _EMPLOYEES,
        )
        conn.commit()
    finally:
        cur.close()
