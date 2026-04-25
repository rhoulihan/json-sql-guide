"""Seed: orders with 4-level-deep paths.

Exercises ``$.shipping.address.geo.coords[0]`` style paths that the
extended-types section uses to show deep nesting.
"""

from __future__ import annotations

import json
from typing import Any

_ORDERS: list[dict[str, Any]] = [
    {
        "orderId": 3001,
        "customer": {
            "name": "Nu Dynamics",
            "tier": "gold",
            "address": {"city": "Somewhere", "state": "CA", "zip": "90001"},
        },
        "status": "shipped",
        "priority": "normal",
        "orderDate": "2025-04-10",
        "items": [{"product": "Deep Nest 1", "quantity": 1, "unitPrice": 75.0, "category": "hardware"}],
        "shipping": {
            "method": "ground",
            "address": {
                "city": "Somewhere",
                "state": "CA",
                "zip": "90001",
                "geo": {
                    "coords": [-118.2437, 34.0522],
                    "accuracy_m": 5,
                    "source": "gps",
                },
            },
        },
        "tags": ["geocoded"],
    },
    {
        "orderId": 3002,
        "customer": {
            "name": "Xi Research",
            "tier": "silver",
            "address": {"city": "Nowhere", "state": "NM", "zip": "87001"},
        },
        "status": "pending",
        "priority": "normal",
        "orderDate": "2025-04-11",
        "items": [{"product": "Deep Nest 2", "quantity": 1, "unitPrice": 125.0, "category": "hardware"}],
        "shipping": {
            "method": "express",
            "address": {
                "city": "Nowhere",
                "state": "NM",
                "zip": "87001",
                "geo": {
                    "coords": [-106.6504, 35.0844],
                    "accuracy_m": 3,
                    "source": "gps",
                },
            },
        },
        "tags": ["geocoded"],
    },
]


def load(conn: Any) -> None:
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO orders (order_doc) VALUES (:1)",
            [(json.dumps(o),) for o in _ORDERS],
        )
        conn.commit()
    finally:
        cur.close()
