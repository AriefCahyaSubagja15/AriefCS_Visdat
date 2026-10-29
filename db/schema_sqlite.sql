-- =====================================================================
-- DBMS 2: SQLite (file lokal, ikut di repositori: olist_master.db)
-- Fungsi : data MASTER / REFERENSI (produk, kategori, penjual, ulasan)
-- Sumber : Brazilian E-Commerce Public Dataset by Olist (Kaggle)
--          https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
-- Catatan: order_id pada order_reviews merujuk ke orders di PostgreSQL
--          (tanpa FOREIGN KEY lintas DBMS). Join dilakukan di Pandas.
-- =====================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS order_reviews;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS product_category_translation;
DROP TABLE IF EXISTS sellers;

CREATE TABLE product_category_translation (
    product_category_name         TEXT PRIMARY KEY,   -- Portugis
    product_category_name_english TEXT NOT NULL
);

CREATE TABLE products (
    product_id                 TEXT PRIMARY KEY,
    product_category_name      TEXT REFERENCES product_category_translation (product_category_name),
    product_name_length        INTEGER,   -- di CSV tertulis "lenght" (typo asli)
    product_description_length INTEGER,
    product_photos_qty         INTEGER,
    product_weight_g           REAL,
    product_length_cm          REAL,
    product_height_cm          REAL,
    product_width_cm           REAL
);

CREATE TABLE sellers (
    seller_id              TEXT PRIMARY KEY,
    seller_zip_code_prefix TEXT,
    seller_city            TEXT,
    seller_state           TEXT
);

-- review_id di data mentah tidak unik, jadi dipakai kunci pengganti
CREATE TABLE order_reviews (
    review_pk               INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id               TEXT NOT NULL,
    order_id                TEXT NOT NULL,   -- -> orders (PostgreSQL)
    review_score            INTEGER CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title    TEXT,
    review_comment_message  TEXT,
    review_creation_date    TEXT,
    review_answer_timestamp TEXT
);

CREATE INDEX idx_products_category ON products (product_category_name);
CREATE INDEX idx_sellers_state     ON sellers (seller_state);
CREATE INDEX idx_reviews_order     ON order_reviews (order_id);
CREATE INDEX idx_reviews_score     ON order_reviews (review_score);
