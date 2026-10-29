"""
app.py - Dashboard Olist E-Commerce (Multi-DBMS)

Arsitektur:
  - PostgreSQL (Neon) : data transaksi (customers, orders, order_items, order_payments)
  - SQLite (lokal)    : data master (products, categories, sellers, reviews)
  - Integrasi         : Pandas merge() di tingkat aplikasi

Sumber data: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
Jalankan   : streamlit run app.py
"""
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
SQLITE_PATH = ROOT / "db" / "olist_master.db"

st.set_page_config(page_title="Olist Multi-DBMS Dashboard", page_icon="🛒", layout="wide")


# ---------------------------------------------------------------------
# Koneksi database
# ---------------------------------------------------------------------
def get_db_url():
    """Ambil DATABASE_URL dari environment (.env lokal) atau st.secrets (deploy)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            url = st.secrets["DATABASE_URL"]
        except Exception:
            url = None
    return url


@st.cache_resource
def get_pg_engine():
    url = get_db_url()
    if not url:
        raise RuntimeError("DATABASE_URL belum diatur (.env untuk lokal, Secrets untuk deploy).")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg2://" + url[len(prefix):]
            break
    return create_engine(url, pool_pre_ping=True)


@st.cache_resource
def get_sqlite_engine():
    if not SQLITE_PATH.exists():
        raise FileNotFoundError(f"File SQLite tidak ditemukan: {SQLITE_PATH}. "
                                "Jalankan python db/seed_data.py sqlite")
    return create_engine(f"sqlite:///{SQLITE_PATH.as_posix()}")


# ---------------------------------------------------------------------
# Pemuatan data (masing-masing DBMS dikueri terpisah)
# ---------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Mengambil data transaksi dari PostgreSQL ...")
def load_transactions():
    sql = """
        SELECT oi.order_id, oi.order_item_id, oi.product_id, oi.seller_id,
               oi.price, oi.freight_value,
               o.order_status,
               CAST(o.order_purchase_timestamp AS DATE) AS purchase_date,
               c.customer_state
        FROM order_items oi
        JOIN orders o    ON o.order_id = oi.order_id
        JOIN customers c ON c.customer_id = o.customer_id
    """
    df = pd.read_sql_query(sql, get_pg_engine())
    df["price"] = pd.to_numeric(df["price"])
    df["freight_value"] = pd.to_numeric(df["freight_value"])
    df["purchase_date"] = pd.to_datetime(df["purchase_date"])
    return df


@st.cache_data(ttl=3600, show_spinner="Mengambil data pembayaran dari PostgreSQL ...")
def load_payments():
    sql = """
        SELECT payment_type, COUNT(*) AS jumlah, SUM(payment_value) AS total
        FROM order_payments
        GROUP BY payment_type
    """
    df = pd.read_sql_query(sql, get_pg_engine())
    df["total"] = pd.to_numeric(df["total"])
    return df


@st.cache_data(ttl=3600, show_spinner="Mengambil data master dari SQLite ...")
def load_master():
    eng = get_sqlite_engine()
    products = pd.read_sql_query("""
        SELECT p.product_id,
               COALESCE(t.product_category_name_english, 'unknown') AS category
        FROM products p
        LEFT JOIN product_category_translation t
               ON t.product_category_name = p.product_category_name
    """, eng)
    sellers = pd.read_sql_query("SELECT seller_id, seller_state FROM sellers", eng)
    reviews = pd.read_sql_query("""
        SELECT order_id, AVG(review_score) AS review_score
        FROM order_reviews
        GROUP BY order_id
    """, eng)
    return products, sellers, reviews


@st.cache_data(ttl=3600, show_spinner="Menggabungkan data kedua DBMS dengan Pandas ...")
def build_dataset():
    """Integrasi: transaksi (PostgreSQL) + master/ulasan (SQLite) lewat merge()."""
    tx = load_transactions()
    products, sellers, reviews = load_master()
    df = (tx.merge(products, on="product_id", how="left")
            .merge(sellers, on="seller_id", how="left")
            .merge(reviews, on="order_id", how="left"))
    df["category"] = df["category"].fillna("unknown")
    df["purchase_month"] = df["purchase_date"].dt.to_period("M").dt.to_timestamp()
    return df


# ---------------------------------------------------------------------
# Muat data
# ---------------------------------------------------------------------
st.title("🛒 Olist E-Commerce Dashboard")
st.caption("Data transaksi dari PostgreSQL digabung dengan data master dari SQLite menggunakan Pandas.")

try:
    data = build_dataset()
    payments = load_payments()
except Exception as e:
    st.error("Gagal memuat data dari database.")
    st.code(str(e))
    st.stop()

# ---------------------------------------------------------------------
# Filter sidebar
# ---------------------------------------------------------------------
st.sidebar.header("Filter")

min_d, max_d = data["purchase_date"].min().date(), data["purchase_date"].max().date()
date_range = st.sidebar.date_input("Rentang tanggal pembelian", (min_d, max_d),
                                   min_value=min_d, max_value=max_d)
if len(date_range) != 2:
    st.info("Pilih tanggal akhir pada filter rentang tanggal.")
    st.stop()

all_status = sorted(data["order_status"].dropna().unique())
status_sel = st.sidebar.multiselect(
    "Status order", all_status,
    default=["delivered"] if "delivered" in all_status else all_status)

state_sel = st.sidebar.multiselect(
    "Negara bagian pembeli (kosong = semua)", sorted(data["customer_state"].dropna().unique()))

top_n = st.sidebar.slider("Jumlah kategori teratas", 5, 30, 10)

mask = (data["purchase_date"].dt.date >= date_range[0]) & (data["purchase_date"].dt.date <= date_range[1])
if status_sel:
    mask &= data["order_status"].isin(status_sel)
if state_sel:
    mask &= data["customer_state"].isin(state_sel)
f = data[mask]

if f.empty:
    st.warning("Tidak ada data untuk kombinasi filter ini.")
    st.stop()

# ---------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------
revenue = f["price"].sum()
n_orders = f["order_id"].nunique()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total omzet (harga barang)", f"R$ {revenue:,.0f}")
c2.metric("Jumlah order", f"{n_orders:,}")
c3.metric("Rata-rata nilai order", f"R$ {revenue / n_orders:,.2f}")
c4.metric("Rata-rata skor ulasan", f"{f['review_score'].mean():.2f} / 5")

tab1, tab2, tab3, tab4 = st.tabs(["📈 Tren", "🏷️ Kategori", "🗺️ Geografi", "🏗️ Arsitektur & Data"])

# ---------------------------------------------------------------------
# Tab 1: Tren
# ---------------------------------------------------------------------
with tab1:
    monthly = (f.groupby("purchase_month")
                 .agg(omzet=("price", "sum"), order=("order_id", "nunique"))
                 .reset_index())
    left, right = st.columns([2, 1])
    with left:
        fig = px.line(monthly, x="purchase_month", y="omzet", markers=True,
                      title="Omzet bulanan (R$)",
                      labels={"purchase_month": "Bulan", "omzet": "Omzet (R$)"})
        st.plotly_chart(fig)
        fig = px.bar(monthly, x="purchase_month", y="order", title="Jumlah order per bulan",
                     labels={"purchase_month": "Bulan", "order": "Jumlah order"})
        st.plotly_chart(fig)
    with right:
        fig = px.pie(payments, names="payment_type", values="total", hole=0.45,
                     title="Metode pembayaran (seluruh data, PostgreSQL)")
        st.plotly_chart(fig)

# ---------------------------------------------------------------------
# Tab 2: Kategori (join lintas DBMS: transaksi PG x kategori & ulasan SQLite)
# ---------------------------------------------------------------------
with tab2:
    cat = (f.groupby("category")
             .agg(omzet=("price", "sum"),
                  order=("order_id", "nunique"),
                  skor=("review_score", "mean"))
             .reset_index())

    fig = px.bar(cat.nlargest(top_n, "omzet"), x="omzet", y="category", orientation="h",
                 title=f"{top_n} kategori dengan omzet tertinggi",
                 labels={"omzet": "Omzet (R$)", "category": "Kategori"})
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig)

    scat = cat[(cat["order"] >= 30)].dropna(subset=["skor"])
    fig = px.scatter(scat, x="omzet", y="skor", size="order", hover_name="category",
                     log_x=True,
                     title="Omzet vs rata-rata skor ulasan per kategori (min. 30 order)",
                     labels={"omzet": "Omzet (R$, skala log)", "skor": "Rata-rata skor ulasan",
                             "order": "Jumlah order"})
    st.plotly_chart(fig)
    st.caption("Kategori dan skor ulasan berasal dari SQLite; omzet dari PostgreSQL.")

# ---------------------------------------------------------------------
# Tab 3: Geografi (state pembeli dari PG x state penjual dari SQLite)
# ---------------------------------------------------------------------
with tab3:
    buyers = (f.groupby("customer_state")["price"].sum().rename("omzet").reset_index()
                .rename(columns={"customer_state": "state"}))
    buyers["peran"] = "Pembeli (PostgreSQL)"
    sell = (f.groupby("seller_state")["price"].sum().rename("omzet").reset_index()
              .rename(columns={"seller_state": "state"}))
    sell["peran"] = "Penjual (SQLite)"
    geo = pd.concat([buyers, sell], ignore_index=True)
    top_states = geo.groupby("state")["omzet"].sum().nlargest(10).index
    fig = px.bar(geo[geo["state"].isin(top_states)], x="state", y="omzet", color="peran",
                 barmode="group", title="Omzet per negara bagian: sisi pembeli vs sisi penjual",
                 labels={"state": "Negara bagian", "omzet": "Omzet (R$)", "peran": ""})
    st.plotly_chart(fig)

    top_c = f.groupby("customer_state")["order_id"].nunique().nlargest(10).index
    top_s = f.groupby("seller_state")["order_id"].nunique().nlargest(10).index
    pivot = (f[f["customer_state"].isin(top_c) & f["seller_state"].isin(top_s)]
               .pivot_table(index="customer_state", columns="seller_state",
                            values="order_id", aggfunc="nunique", fill_value=0))
    fig = px.imshow(pivot, text_auto=True, aspect="auto", color_continuous_scale="Blues",
                    title="Jumlah order: negara bagian pembeli (baris) x penjual (kolom)",
                    labels={"x": "State penjual", "y": "State pembeli", "color": "Order"})
    st.plotly_chart(fig)

# ---------------------------------------------------------------------
# Tab 4: Arsitektur & data
# ---------------------------------------------------------------------
with tab4:
    st.subheader("Arsitektur")
    st.markdown("""
| DBMS | Engine | Fungsi | Tabel |
|---|---|---|---|
| DBMS 1 | PostgreSQL (Neon) | Data transaksi | customers, orders, order_items, order_payments |
| DBMS 2 | SQLite (file lokal) | Data master & referensi | products, product_category_translation, sellers, order_reviews |

**Alur integrasi:** tiap DBMS dikueri terpisah, lalu digabung di Pandas dengan
`merge()` memakai kunci `product_id`, `seller_id`, dan `order_id`.
Tidak ada foreign key lintas DBMS, sehingga integritas relasi dijaga di tingkat aplikasi.
""")
    st.subheader("Contoh data hasil gabungan (100 baris pertama setelah filter)")
    st.dataframe(f.head(100))
    st.caption(f"Total baris setelah filter: {len(f):,} dari {len(data):,}")

    st.subheader("Sumber data")
    st.markdown("""
Brazilian E-Commerce Public Dataset by Olist (Kaggle), lisensi CC BY-NC-SA 4.0:
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
""")
