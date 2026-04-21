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
        "customer": "Nu Dynamics",
        "status": "shipped",
        "amount": 75.0,
        "items": [{"sku": "DEEPNEST-1", "quantity": 1, "unitPrice": 75.0}],
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
        "customer": "Xi Research",
        "status": "pending",
        "amount": 125.0,
        "items": [{"sku": "DEEPNEST-2", "quantity": 1, "unitPrice": 125.0}],
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
            "INSERT INTO orders (order_id, order_doc) VALUES (:1, :2)",
            [(o["orderId"], json.dumps(o)) for o in _ORDERS],
        )
        conn.commit()
    finally:
        cur.close()
