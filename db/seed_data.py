"""
seed_data.py
Mengisi dua database dari CSV Olist (Kaggle):
  - PostgreSQL (Neon)  -> data transaksi  (customers, orders, order_items, order_payments)
  - SQLite (lokal)     -> data master     (products, categories, sellers, reviews)

Sumber data: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

Cara pakai (dari folder root proyek):
    python db/seed_data.py             # isi kedua database
    python db/seed_data.py postgres    # hanya PostgreSQL
    python db/seed_data.py sqlite      # hanya SQLite

Kredensial dibaca dari environment variable DATABASE_URL (file .env),
tidak ada password yang ditulis di dalam kode.
"""
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

DB_DIR = Path(__file__).resolve().parent
ROOT = DB_DIR.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("OLIST_DATA_DIR", ROOT / "data"))
SQLITE_PATH = DB_DIR / "olist_master.db"


def read_csv(name, **kwargs):
    path = DATA_DIR / name
    if not path.exists():
        sys.exit(f"[ERROR] File tidak ditemukan: {path}\n"
                 f"Letakkan semua CSV Olist di folder: {DATA_DIR}")
    # utf-8-sig menangani BOM yang ada di beberapa CSV Kaggle
    return pd.read_csv(path, encoding="utf-8-sig", **kwargs)


def pad_zip(series):
    """Zip prefix Olist 5 digit, tetapi nol di depan hilang pada CSV."""
    return series.astype(str).str.zfill(5)


# ---------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------
def seed_postgres():
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("[ERROR] DATABASE_URL belum diatur. Salin .env.example menjadi .env "
                 "lalu isi connection string dari Neon.")
    # SQLAlchemy 2.1 memakai driver psycopg (v3) secara default; kita pakai psycopg2
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg2://" + url[len(prefix):]
            break

    engine = create_engine(url)
    print("[PostgreSQL] Membuat tabel dari schema_postgres.sql ...")
    schema = (DB_DIR / "schema_postgres.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(schema)

    def load(df, table):
        print(f"[PostgreSQL] Memuat {table}: {len(df):,} baris ...")
        df.to_sql(table, engine, if_exists="append", index=False,
                  method="multi", chunksize=2000)

    customers = read_csv("olist_customers_dataset.csv", dtype=str)
    customers["customer_zip_code_prefix"] = pad_zip(customers["customer_zip_code_prefix"])
    load(customers, "customers")

    orders = read_csv("olist_orders_dataset.csv")
    for col in ["order_purchase_timestamp", "order_approved_at",
                "order_delivered_carrier_date", "order_delivered_customer_date",
                "order_estimated_delivery_date"]:
        orders[col] = pd.to_datetime(orders[col])
    load(orders, "orders")

    items = read_csv("olist_order_items_dataset.csv")
    items["shipping_limit_date"] = pd.to_datetime(items["shipping_limit_date"])
    load(items, "order_items")

    payments = read_csv("olist_order_payments_dataset.csv")
    load(payments, "order_payments")

    with engine.connect() as conn:
        for t in ["customers", "orders", "order_items", "order_payments"]:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"[PostgreSQL] OK  {t}: {n:,} baris")


# ---------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------
def seed_sqlite():
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()
    conn = sqlite3.connect(SQLITE_PATH)
    print("[SQLite] Membuat tabel dari schema_sqlite.sql ...")
    conn.executescript((DB_DIR / "schema_sqlite.sql").read_text(encoding="utf-8"))

    def load(df, table):
        print(f"[SQLite] Memuat {table}: {len(df):,} baris ...")
        df.to_sql(table, conn, if_exists="append", index=False)

    translation = read_csv("product_category_name_translation.csv")

    products = read_csv("olist_products_dataset.csv").rename(columns={
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    })
    for col in ["product_name_length", "product_description_length", "product_photos_qty"]:
        products[col] = products[col].astype("Int64")

    # Beberapa kategori produk tidak ada di tabel terjemahan -> tambahkan fallback
    missing = sorted(set(products["product_category_name"].dropna())
                     - set(translation["product_category_name"]))
    if missing:
        extra = pd.DataFrame({
            "product_category_name": missing,
            "product_category_name_english": [m.replace("_", " ") for m in missing],
        })
        translation = pd.concat([translation, extra], ignore_index=True)
        print(f"[SQLite] Kategori tanpa terjemahan (diberi fallback): {missing}")

    sellers = read_csv("olist_sellers_dataset.csv", dtype=str)
    sellers["seller_zip_code_prefix"] = pad_zip(sellers["seller_zip_code_prefix"])

    reviews = read_csv("olist_order_reviews_dataset.csv")

    load(translation, "product_category_translation")
    load(products, "products")
    load(sellers, "sellers")
    load(reviews, "order_reviews")
    conn.commit()

    cur = conn.cursor()
    for t in ["product_category_translation", "products", "sellers", "order_reviews"]:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"[SQLite] OK  {t}: {n:,} baris")
    conn.close()


if __name__ == "__main__":
    target = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if target in ("all", "sqlite"):
        seed_sqlite()
    if target in ("all", "postgres"):
        seed_postgres()
    print("Selesai.")
