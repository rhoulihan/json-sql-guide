-- Canonical schema for the Oracle SQL/JSON Developer Guide validator.
-- Creates every table referenced in the guide plus the order_items
-- table needed by the JSON Relational Duality View example.
--
-- All objects live in the validator user's default schema. The loader
-- drops existing objects before applying this file, so DDL here is
-- plain CREATE — no OR REPLACE, no conditional drops.

-- ─────────── orders — primary table used throughout ───────────

CREATE TABLE orders (
    order_id   NUMBER PRIMARY KEY,
    order_doc  JSON
);

-- ─────────── entities — single-table design example ───────────

CREATE TABLE entities (
    pk    VARCHAR2(50)  NOT NULL,
    sk    VARCHAR2(100) NOT NULL,
    data  JSON,
    CONSTRAINT pk_entities PRIMARY KEY (pk, sk)
);

-- ─────────── validated_orders — JSON schema validation example ───────────

CREATE TABLE validated_orders (
    order_id   NUMBER PRIMARY KEY,
    order_doc  JSON
        CONSTRAINT order_doc_shape CHECK (
            order_doc IS JSON VALIDATE USING '{
              "type": "object",
              "properties": {
                "orderId":  { "type": "number" },
                "customer": { "type": "string" },
                "items":    { "type": "array" }
              },
              "required": ["orderId", "customer", "items"]
            }'
        )
);

-- ─────────── customers / products — relational tables for hybrid queries ───────────

CREATE TABLE customers (
    customer_id    VARCHAR2(50) PRIMARY KEY,
    customer_name  VARCHAR2(200),
    tier           VARCHAR2(20)
);

CREATE TABLE products (
    sku            VARCHAR2(50) PRIMARY KEY,
    product_name   VARCHAR2(200),
    category_id    NUMBER,
    list_price     NUMBER(12, 2)
);

-- ─────────── order_items — needed for the Duality View example in §12 ───────────

CREATE TABLE order_items (
    item_id     NUMBER PRIMARY KEY,
    order_id    NUMBER NOT NULL,
    sku         VARCHAR2(50) NOT NULL,
    quantity    NUMBER NOT NULL,
    unit_price  NUMBER(12, 2) NOT NULL,
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders (order_id)
);
