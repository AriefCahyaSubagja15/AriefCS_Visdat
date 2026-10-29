-- =====================================================================
-- DBMS 1: PostgreSQL (Neon / Supabase)
-- Fungsi : data TRANSAKSIONAL utama (pelanggan, order, item, pembayaran)
-- Sumber : Brazilian E-Commerce Public Dataset by Olist (Kaggle)
--          https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
-- Catatan: product_id dan seller_id di order_items merujuk ke tabel di
--          SQLite, sehingga TIDAK diberi FOREIGN KEY (lintas DBMS tidak
--          didukung). Penggabungan dilakukan di Pandas (aplikasi).
-- =====================================================================

DROP TABLE IF EXISTS order_payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id              VARCHAR(32) PRIMARY KEY,
    customer_unique_id       VARCHAR(32) NOT NULL,
    customer_zip_code_prefix VARCHAR(5),
    customer_city            VARCHAR(100),
    customer_state           CHAR(2)
);

CREATE TABLE orders (
    order_id                       VARCHAR(32) PRIMARY KEY,
    customer_id                    VARCHAR(32) NOT NULL REFERENCES customers (customer_id),
    order_status                   VARCHAR(20) NOT NULL,
    order_purchase_timestamp       TIMESTAMP,
    order_approved_at              TIMESTAMP,
    order_delivered_carrier_date   TIMESTAMP,
    order_delivered_customer_date  TIMESTAMP,
    order_estimated_delivery_date  TIMESTAMP
);

CREATE TABLE order_items (
    order_id            VARCHAR(32) NOT NULL REFERENCES orders (order_id),
    order_item_id       INTEGER     NOT NULL,
    product_id          VARCHAR(32) NOT NULL,   -- -> products (SQLite)
    seller_id           VARCHAR(32) NOT NULL,   -- -> sellers  (SQLite)
    shipping_limit_date TIMESTAMP,
    price               NUMERIC(10, 2),
    freight_value       NUMERIC(10, 2),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE order_payments (
    order_id             VARCHAR(32) NOT NULL REFERENCES orders (order_id),
    payment_sequential   INTEGER     NOT NULL,
    payment_type         VARCHAR(20),
    payment_installments INTEGER,
    payment_value        NUMERIC(10, 2),
    PRIMARY KEY (order_id, payment_sequential)
);

-- Indeks untuk mempercepat filter dan join di dashboard
CREATE INDEX idx_orders_customer   ON orders (customer_id);
CREATE INDEX idx_orders_purchase   ON orders (order_purchase_timestamp);
CREATE INDEX idx_orders_status     ON orders (order_status);
CREATE INDEX idx_items_product     ON order_items (product_id);
CREATE INDEX idx_items_seller      ON order_items (seller_id);
CREATE INDEX idx_customers_state   ON customers (customer_state);
