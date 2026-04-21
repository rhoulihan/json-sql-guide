"""Seed: orders with DATE / TIMESTAMP / INTERVAL values.

Exercises the extended-types section of the guide — ``RETURNING DATE``,
``RETURNING TIMESTAMP WITH TIME ZONE``, and ``RETURNING INTERVAL DAY TO
SECOND`` variants of ``JSON_VALUE``.

The ``orderDate`` field is written as an ISO-8601 date string so Oracle
can parse it via ``JSON_VALUE(... RETURNING DATE)`` without a format
mask. ``orderPlacedAt`` uses an ISO-8601 timestamp with offset.
``shippingWindow`` uses an ISO-8601 duration.
"""

from __future__ import annotations

import json
from typing import Any

_ORDERS: list[dict[str, Any]] = [
    {
        "orderId": 4001,
        "customer": "Omicron Systems",
        "status": "shipped",
        "amount": 540.00,
        "orderDate": "2026-02-03",
        "orderPlacedAt": "2026-02-03T09:15:00-08:00",
        "shippingWindow": "P2DT4H",
        "items": [{"sku": "DATETIME-1", "quantity": 1, "unitPrice": 540.00}],
        "shipping": {"method": "ground", "address": {"city": "San Jose", "state": "CA"}},
        "tags": ["dated"],
    },
    {
        "orderId": 4002,
        "customer": "Pi Networks",
        "status": "pending",
        "amount": 1280.00,
        "orderDate": "2026-02-10",
        "orderPlacedAt": "2026-02-10T14:42:00+00:00",
        "shippingWindow": "P5D",
        "items": [{"sku": "DATETIME-2", "quantity": 2, "unitPrice": 640.00}],
        "shipping": {"method": "express", "address": {"city": "New York", "state": "NY"}},
        "tags": ["dated", "priority"],
    },
    {
        "orderId": 4003,
        "customer": "Rho Analytics",
        "status": "shipped",
        "amount": 99.00,
        "orderDate": "2026-02-14",
        "orderPlacedAt": "2026-02-14T22:01:00-05:00",
        "shippingWindow": "PT36H",
        "items": [{"sku": "DATETIME-3", "quantity": 3, "unitPrice": 33.00}],
        "shipping": {"method": "ground", "address": {"city": "Atlanta", "state": "GA"}},
        "tags": ["dated"],
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
