"""Base seed — 10 orders with realistic shapes.

Required by every profile. Populates ``orders`` with documents that
exercise every path expression cited in the guide's narrative:

* ``$.customer`` scalar
* ``$.status`` scalar
* ``$.amount`` number
* ``$.orderDate`` string (the extended-types seed adds DATE variants)
* ``$.items[*]`` array with ``sku``, ``quantity``, ``unitPrice``
* ``$.shipping`` nested object with ``method`` and ``address``
* ``$.tags[*]`` string array (tags-with-nums seed adds numeric variants)
"""

from __future__ import annotations

import json
from typing import Any

_ORDERS: list[dict[str, Any]] = [
    {
        "orderId": 1001,
        "customer": "Acme Corp",
        "status": "shipped",
        "amount": 1299.00,
        "orderDate": "2026-01-15",
        "items": [
            {"sku": "LAPTOP-001", "quantity": 1, "unitPrice": 1299.00, "category": "electronics"},
        ],
        "shipping": {
            "method": "ground",
            "address": {"city": "Belmont", "state": "CA", "zip": "94002"},
        },
        "tags": ["priority", "b2b"],
    },
    {
        "orderId": 1002,
        "customer": "Beta LLC",
        "status": "pending",
        "amount": 58.50,
        "orderDate": "2026-01-16",
        "items": [
            {"sku": "MOUSE-042", "quantity": 2, "unitPrice": 18.50, "category": "electronics"},
            {"sku": "CABLE-USB", "quantity": 3, "unitPrice": 7.17, "category": "electronics"},
        ],
        "shipping": {
            "method": "ground",
            "address": {"city": "Austin", "state": "TX", "zip": "78701"},
        },
        "tags": ["standard"],
    },
    {
        "orderId": 1003,
        "customer": "Gamma Inc",
        "status": "shipped",
        "amount": 899.00,
        "orderDate": "2026-01-17",
        "items": [
            {"sku": "MONITOR-27", "quantity": 1, "unitPrice": 499.00, "category": "electronics"},
            {"sku": "WIDGET-PRO", "quantity": 4, "unitPrice": 100.00, "category": "hardware"},
        ],
        "shipping": {
            "method": "express",
            "address": {"city": "Denver", "state": "CO", "zip": "80202"},
            "tracking": "1Z999AA10123456784",
        },
        "tags": ["wholesale", "priority"],
    },
    {
        "orderId": 1004,
        "customer": "Delta Co",
        "status": "cancelled",
        "amount": 150.00,
        "orderDate": "2026-01-18",
        "items": [
            {"sku": "GADGET-PLUS", "quantity": 3, "unitPrice": 50.00, "category": "hardware"},
        ],
        "shipping": {
            "method": "ground",
            "address": {"city": "Boston", "state": "MA", "zip": "02101"},
        },
        "tags": ["cancelled"],
    },
    {
        "orderId": 1005,
        "customer": "Epsilon Labs",
        "status": "shipped",
        "amount": 325.75,
        "orderDate": "2026-01-19",
        "items": [
            {"sku": "SENSOR-900", "quantity": 5, "unitPrice": 65.15, "category": "hardware"},
        ],
        "shipping": {
            "method": "ground",
            "address": {"city": "Seattle", "state": "WA", "zip": "98101"},
        },
        "tags": ["research", "standard"],
    },
    {
        "orderId": 1006,
        "customer": "Zeta Systems",
        "status": "shipped",
        "amount": 2499.99,
        "orderDate": "2026-01-20",
        "items": [
            {"sku": "SERVER-RACK", "quantity": 1, "unitPrice": 2499.99, "category": "hardware"},
        ],
        "shipping": {
            "method": "freight",
            "address": {"city": "Portland", "state": "OR", "zip": "97201"},
        },
        "tags": ["wholesale", "b2b"],
    },
    {
        "orderId": 1007,
        "customer": "Acme Corp",
        "status": "pending",
        "amount": 42.00,
        "orderDate": "2026-01-21",
        "items": [
            {"sku": "CABLE-USB", "quantity": 6, "unitPrice": 7.00, "category": "electronics"},
        ],
        "shipping": {
            "method": "ground",
            "address": {"city": "Belmont", "state": "CA", "zip": "94002"},
        },
        "tags": ["standard", "b2b"],
    },
    {
        "orderId": 1008,
        "customer": "Theta Group",
        "status": "shipped",
        "amount": 78.00,
        "orderDate": "2026-01-22",
        "items": [
            {"sku": "WIDGET-PRO", "quantity": 1, "unitPrice": 78.00, "category": "hardware"},
        ],
        "shipping": {
            "method": "ground",
            "address": {"city": "Chicago", "state": "IL", "zip": "60601"},
        },
        "tags": ["standard"],
    },
    {
        "orderId": 1009,
        "customer": "Iota Partners",
        "status": "shipped",
        "amount": 450.00,
        "orderDate": "2026-01-23",
        "items": [
            {"sku": "MONITOR-27", "quantity": 1, "unitPrice": 450.00, "category": "electronics"},
        ],
        "shipping": {
            "method": "express",
            "address": {"city": "Miami", "state": "FL", "zip": "33101"},
        },
        "tags": ["priority"],
    },
    {
        "orderId": 1010,
        "customer": "Kappa Industries",
        "status": "shipped",
        "amount": 189.00,
        "orderDate": "2026-01-24",
        "items": [
            {"sku": "LAPTOP-STAND", "quantity": 3, "unitPrice": 63.00, "category": "accessories"},
        ],
        "shipping": {
            "method": "ground",
            "address": {"city": "Phoenix", "state": "AZ", "zip": "85001"},
        },
        "tags": ["wholesale"],
    },
]


def load(conn: Any) -> None:
    """Insert the 10 base orders. Assumes ``orders`` is empty."""
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO orders (order_id, order_doc) VALUES (:1, :2)",
            [(o["orderId"], json.dumps(o)) for o in _ORDERS],
        )
        conn.commit()
    finally:
        cur.close()
