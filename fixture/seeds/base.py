"""Base seed — 10 orders with the canonical shape declared in the guide.

Required by every profile. Populates ``orders`` with documents that
exercise every path expression cited in the guide's narrative:

* ``$.customer.name`` — string inside a nested customer object
* ``$.customer.tier`` — categorical, used by tier-routed examples
* ``$.customer.address.city`` — deep-nested string for filter examples
* ``$.status`` / ``$.priority`` — categoricals
* ``$.orderDate`` — ISO date string (extended-types seed adds DATE variants)
* ``$.shipping`` — nested object with ``method`` + ``address``
* ``$.items[*]`` — array of objects with ``product``, ``quantity``,
  ``unitPrice``, ``category``
* ``$.tags[*]`` — string array (tags-with-nums seed adds numeric variants)
"""

from __future__ import annotations

import json
from typing import Any

_ORDERS: list[dict[str, Any]] = [
    {
        "orderId": 1001,
        "customer": {
            "name": "Acme Corp",
            "tier": "platinum",
            "address": {"city": "Belmont", "state": "CA", "zip": "94002"},
        },
        "status": "shipped",
        "priority": "high",
        "orderDate": "2025-03-15",
        "shipping": {
            "method": "express",
            "address": {"city": "Austin", "state": "TX", "zip": "78701"},
        },
        "items": [
            {"product": "Widget Pro", "quantity": 10, "unitPrice": 29.99, "category": "hardware"},
            {"product": "Gadget Plus", "quantity": 5, "unitPrice": 49.99, "category": "electronics"},
            {"product": "Cable Kit", "quantity": 50, "unitPrice": 4.99, "category": "accessories"},
        ],
        "tags": ["wholesale", "priority", "Q1-promo"],
    },
    {
        "orderId": 1002,
        "customer": {
            "name": "Beta LLC",
            "tier": "gold",
            "address": {"city": "Austin", "state": "TX", "zip": "78701"},
        },
        "status": "pending",
        "priority": "normal",
        "orderDate": "2025-03-16",
        "shipping": {
            "method": "ground",
            "address": {"city": "Austin", "state": "TX", "zip": "78701"},
        },
        "items": [
            {"product": "Widget Pro", "quantity": 2, "unitPrice": 29.99, "category": "hardware"},
            {"product": "Cable Kit", "quantity": 3, "unitPrice": 7.17, "category": "accessories"},
        ],
        "tags": ["standard"],
    },
    {
        "orderId": 1003,
        "customer": {
            "name": "Gamma Inc",
            "tier": "gold",
            "address": {"city": "Denver", "state": "CO", "zip": "80202"},
        },
        "status": "shipped",
        "priority": "high",
        "orderDate": "2025-03-17",
        "shipping": {
            "method": "express",
            "address": {"city": "Denver", "state": "CO", "zip": "80202"},
            "tracking": "1Z999AA10123456784",
        },
        "items": [
            {"product": "Monitor 27", "quantity": 1, "unitPrice": 499.00, "category": "electronics"},
            {"product": "Widget Pro", "quantity": 4, "unitPrice": 100.00, "category": "hardware"},
        ],
        "tags": ["wholesale", "priority"],
    },
    {
        "orderId": 1004,
        "customer": {
            "name": "Delta Co",
            "tier": "silver",
            "address": {"city": "Boston", "state": "MA", "zip": "02101"},
        },
        "status": "cancelled",
        "priority": "normal",
        "orderDate": "2025-03-18",
        "shipping": {
            "method": "ground",
            "address": {"city": "Boston", "state": "MA", "zip": "02101"},
        },
        "items": [
            {"product": "Gadget Plus", "quantity": 3, "unitPrice": 50.00, "category": "hardware"},
        ],
        "tags": ["cancelled"],
    },
    {
        "orderId": 1005,
        "customer": {
            "name": "Epsilon Labs",
            "tier": "silver",
            "address": {"city": "Seattle", "state": "WA", "zip": "98101"},
        },
        "status": "shipped",
        "priority": "normal",
        "orderDate": "2025-03-19",
        "shipping": {
            "method": "ground",
            "address": {"city": "Seattle", "state": "WA", "zip": "98101"},
        },
        "items": [
            {"product": "Sensor 900", "quantity": 5, "unitPrice": 65.15, "category": "hardware"},
        ],
        "tags": ["research", "standard"],
    },
    {
        "orderId": 1006,
        "customer": {
            "name": "Zeta Systems",
            "tier": "platinum",
            "address": {"city": "Portland", "state": "OR", "zip": "97201"},
        },
        "status": "shipped",
        "priority": "high",
        "orderDate": "2025-03-20",
        "shipping": {
            "method": "freight",
            "address": {"city": "Portland", "state": "OR", "zip": "97201"},
        },
        "items": [
            {"product": "Server Rack", "quantity": 1, "unitPrice": 2499.99, "category": "hardware"},
        ],
        "tags": ["wholesale", "b2b"],
    },
    {
        "orderId": 1007,
        "customer": {
            "name": "Acme Corp",
            "tier": "platinum",
            "address": {"city": "Belmont", "state": "CA", "zip": "94002"},
        },
        "status": "pending",
        "priority": "normal",
        "orderDate": "2025-03-21",
        "shipping": {
            "method": "ground",
            "address": {"city": "Belmont", "state": "CA", "zip": "94002"},
        },
        "items": [
            {"product": "Cable Kit", "quantity": 6, "unitPrice": 7.00, "category": "accessories"},
        ],
        "tags": ["standard", "b2b"],
    },
    {
        "orderId": 1008,
        "customer": {
            "name": "Theta Group",
            "tier": "silver",
            "address": {"city": "Chicago", "state": "IL", "zip": "60601"},
        },
        "status": "shipped",
        "priority": "normal",
        "orderDate": "2025-03-22",
        "shipping": {
            "method": "ground",
            "address": {"city": "Chicago", "state": "IL", "zip": "60601"},
        },
        "items": [
            {"product": "Widget Pro", "quantity": 1, "unitPrice": 78.00, "category": "hardware"},
        ],
        "tags": ["standard"],
    },
    {
        "orderId": 1009,
        "customer": {
            "name": "Iota Partners",
            "tier": "gold",
            "address": {"city": "Miami", "state": "FL", "zip": "33101"},
        },
        "status": "shipped",
        "priority": "high",
        "orderDate": "2025-03-23",
        "shipping": {
            "method": "express",
            "address": {"city": "Miami", "state": "FL", "zip": "33101"},
        },
        "items": [
            {"product": "Monitor 27", "quantity": 1, "unitPrice": 450.00, "category": "electronics"},
        ],
        "tags": ["priority"],
    },
    {
        "orderId": 1010,
        "customer": {
            "name": "Kappa Industries",
            "tier": "silver",
            "address": {"city": "Phoenix", "state": "AZ", "zip": "85001"},
        },
        "status": "shipped",
        "priority": "normal",
        "orderDate": "2025-03-24",
        "shipping": {
            "method": "ground",
            "address": {"city": "Phoenix", "state": "AZ", "zip": "85001"},
        },
        "items": [
            {"product": "Laptop Stand", "quantity": 3, "unitPrice": 63.00, "category": "accessories"},
        ],
        "tags": ["wholesale"],
    },
]


def load(conn: Any) -> None:
    """Insert the 10 base orders. Assumes ``orders`` is empty."""
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO orders (order_doc) VALUES (:1)",
            [(json.dumps(o),) for o in _ORDERS],
        )
        conn.commit()
    finally:
        cur.close()
