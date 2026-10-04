# seed_data.py
"""
Test podaci za Alat #2.
Pokreni JEDNOM: python seed_data.py
Obriše postojeće narudžbine i ubaci 25 novih kroz zadnjih 45 dana.
"""
import random
from datetime import datetime, timedelta
from database import get_conn
import models

# ===== 1) Obriši sve narudžbine i resetuj zalihe =====
conn = get_conn()
conn.execute("DELETE FROM order_items")
conn.execute("DELETE FROM orders")
conn.execute("UPDATE products SET stock = 100")
conn.commit()
conn.close()
print("🧹 Očišćeno.")

# ===== 2) Dodaj proizvode =====
proizvodi = [
    ("MAJICA-M",   "Majica M",       1500,  700),
    ("MAJICA-L",   "Majica L",       1500,  700),
    ("DUKS-CRN",   "Duks crni",      3500, 1800),
    ("SOLJA-BELA", "Šolja bela",      900,  350),
    ("TORBA-PLAT", "Torba platnena", 2200, 1100),
    ("KAPA-CRNA",  "Kapa crna",      1200,  450),
]
for sku, name, price, cost in proizvodi:
    try:
        models.add_product(sku, name, price, cost, stock=100, low_stock_at=10)
    except Exception:
        pass  # već postoji
print("📦 Proizvodi dodati.")

products = models.list_products()
channels = models.list_channels()

# ===== 3) Generiši 25 narudžbina kroz 45 dana =====
imena = ["Petar Petrović", "Ana Anić", "Marko Marković", "Jovana Jović",
         "Nikola Nikolić", "Milica Milić", "Stefan Stefanović", "Ivana Ivanović"]

conn = get_conn()
for i in range(25):
    p = random.choice(products)
    c = random.choice(channels)
    qty = random.randint(1, 3)
    days_ago = random.randint(0, 45)
    date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (customer_name, channel_id, status, created_at)
        VALUES (?, ?, 'paid', ?)
    """, (random.choice(imena), c["id"], date))
    oid = cur.lastrowid

    # 1-2 stavke po narudžbini
    for _ in range(random.randint(1, 2)):
        p2 = random.choice(products)
        q = random.randint(1, 2)
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, qty, unit_price)
            VALUES (?, ?, ?, ?)
        """, (oid, p2["id"], q, p2["price"]))

conn.commit()
conn.close()
print("✅ Generisano 25 narudžbina kroz zadnjih 45 dana.")
print("👉 Idi na http://localhost:5000/analytics")