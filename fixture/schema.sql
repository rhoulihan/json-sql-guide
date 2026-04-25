-- Canonical schema for the Oracle SQL/JSON Developer Guide validator.
-- Creates every table referenced in the guide plus the order_items
-- table needed by the JSON Relational Duality View example.
--
-- All objects live in the validator user's default schema. The loader
-- drops existing objects before applying this file, so DDL here is
-- plain CREATE — no OR REPLACE, no conditional drops.

-- ─────────── orders — primary table used throughout ───────────

CREATE TABLE orders (
    id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_doc  JSON
);

-- ─────────── entities — polymorphic-document table for §11 examples ───────────

CREATE TABLE entities (
    id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc  JSON
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
    list_price     NUMBER(12, 2),
    weight_kg      NUMBER(8, 3),
    supplier       VARCHAR2(100)
);

-- ─────────── order_items — needed for the Duality View example in §12 ───────────

CREATE TABLE order_items (
    item_id     NUMBER PRIMARY KEY,
    order_id    NUMBER NOT NULL,
    sku         VARCHAR2(50) NOT NULL,
    quantity    NUMBER NOT NULL,
    unit_price  NUMBER(12, 2) NOT NULL,
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders (id)
);

-- ─────────── events — append-only event log used in §3, §4 examples ───────────

CREATE TABLE events (
    event_id    NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_doc   JSON
);

-- ─────────── employees — relational table for §6, §8 join examples ───────────

CREATE TABLE employees (
    employee_id  NUMBER PRIMARY KEY,
    first_name   VARCHAR2(100),
    last_name    VARCHAR2(100),
    email        VARCHAR2(200),
    dept_id      NUMBER,
    hire_date    DATE,
    salary       NUMBER(12, 2)
);

-- ─────────── categories — relational lookup for §6 join examples ───────────

CREATE TABLE categories (
    id         NUMBER PRIMARY KEY,
    parent_id  NUMBER REFERENCES categories(id),
    name       VARCHAR2(100) NOT NULL
);

-- ─────────── user_settings — JSON-only config table for §8 examples ───────────

CREATE TABLE user_settings (
    user_id        NUMBER NOT NULL,
    setting_name   VARCHAR2(100) NOT NULL,
    setting_value  VARCHAR2(4000),
    CONSTRAINT pk_user_settings PRIMARY KEY (user_id, setting_name)
);

-- ─────────── legacy_table — illustrates migration in §9 ───────────

CREATE TABLE legacy_table (
    id                  NUMBER PRIMARY KEY,
    legacy_text_column  CLOB CHECK (legacy_text_column IS JSON)
);
