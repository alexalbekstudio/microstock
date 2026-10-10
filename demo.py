# demo.py
"""
Demo mod — seed podataka u 'demo' schema.
Koristi se kad posetilac klikne 'Pogledaj demo' na login stranici.
"""
import os
from datetime import datetime, timedelta
import random


def is_demo_enabled():
    """Da li je demo mod dostupan (env varijabla postavljena)."""
    return True  # uvek dostupan, jer koristimo demo schema


def seed_demo_data():
    """
    Puni 'demo' schema realističnim SR podacima.
    Briše postojeće i ponovo seeduje.
    """
    from db_adapter import connect_demo
    from werkzeug.security import generate_password_hash

    conn = connect_demo()
    try:
        # ===== 1. Obriši postojeće =====
        tables = [
            "order_items", "orders", "purchase_items", "purchase_invoices",
            "capital_transactions", "time_entries", "project_expenses",
            "projects", "team_members", "suppliers",
            "pricing_history", "products", "channels",
            "password_resets",
        ]
        for t in tables:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.commit()

        # ===== 2. Demo korisnik =====
        pw_hash = generate_password_hash("demo123")
        conn.execute("""
            INSERT INTO users (email, password_hash, name, role, language, currency)
            VALUES ('demo@microstock.local', %s, 'Demo korisnik', 'admin', 'sr', 'RSD')
            ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash
        """, (pw_hash,))
        conn.commit()

        # Uzmi ID demo korisnika
        user_row = conn.execute(
            "SELECT id FROM users WHERE email='demo@microstock.local'"
        ).fetchone()
        user_id = user_row["id"] if user_row else 1

        # ===== 3. Kanali =====
        channels = [
            ("Instagram", 0.0), ("WhatsApp", 0.0), ("Etsy", 6.5),
            ("Shopify", 2.9), ("Faire", 15.0), ("Lično", 0.0),
        ]
        for name, fee in channels:
            conn.execute(
                "INSERT INTO channels (name, fee_percent) VALUES (%s, %s) "
                "ON CONFLICT (name) DO NOTHING",
                (name, fee)
            )

        # ===== 4. Proizvodi =====
        products = [
            ("SOLJA-001", "Ručno rađena keramička šolja", 2200, 800, 25),
            ("SOLJA-002", "Keramička šolja — plava glazura", 2400, 900, 18),
            ("SVECA-001", "Sveća lavanda (ručno livena)", 1200, 400, 40),
            ("SVECA-002", "Sveća vanila i cimet", 1200, 400, 35),
            ("SVECA-003", "Sveća eukaliptus", 1300, 450, 22),
            ("NOVCANIK-001", "Kožni novčanik ručno šiven", 4500, 1800, 12),
            ("NOVCANIK-002", "Kožna futrola za kartice", 2800, 1100, 20),
            ("TORBA-001", "Platnena torba sa printom", 1800, 650, 30),
            ("TORBA-002", "Platnena torba — minimalist", 1900, 700, 15),
            ("NARUKVICA-001", "Narukvica od prirodnog kamena", 1500, 500, 28),
            ("NARUKVICA-002", "Narukvica sa imenom", 1800, 600, 8),
            ("PRIVEZAK-001", "Privezak za ključeve — koža", 900, 300, 45),
            ("BEDZ-001", "Email bedž set (3 kom)", 1200, 400, 33),
            ("BEDZ-002", "Email bedž — cvetni motiv", 500, 150, 50),
            ("CESALJ-001", "Drveni češalj", 1400, 450, 17),
            ("OGLEDALO-001", "Ručno ogledalo, drveni ram", 3200, 1200, 9),
            ("SAL-001", "Vuneni šal — ručno pleten", 3800, 1500, 11),
            ("KAPA-001", "Pletena kapa", 2200, 800, 21),
            ("PODMETAC-001", "Podmetač za čašu (set od 4)", 1600, 550, 26),
            ("SVEZA-001", "Sušeni cvetni aranžman", 2800, 1000, 7),
        ]
        for sku, name, price, cost, stock in products:
            conn.execute("""
                INSERT INTO products (sku, name, price, cost, stock, low_stock_at)
                VALUES (%s, %s, %s, %s, %s, 5)
                ON CONFLICT (sku) DO NOTHING
            """, (sku, name, price, cost, stock))

        conn.commit()

        # ===== 5. Narudžbine =====
        kupci = [
            "Ana Petrović", "Marko Jovanović", "Jelena Nikolić", "Stefan Ilić",
            "Milica Stojanović", "Lazar Đorđević", "Ivana Marković",
            "Nikola Pavlović", "Teodora Kostić", "Vuk Radović",
            "Petar Nikolić", "Jovana Đukić", "Andrej Popović",
            "Katarina Simić", "Đorđe Vasić", "Marija Stanković",
            "Filip Milošević", "Sofija Todorović", "Luka Janković",
            "Nina Živković",
        ]

        ch_rows = conn.execute("SELECT id, name FROM channels").fetchall()
        ch_map = {r["name"]: r["id"] for r in ch_rows}

        prod_rows = conn.execute("SELECT id, price FROM products").fetchall()
        prods = [(r["id"], float(r["price"])) for r in prod_rows]

        for i in range(30):
            days_ago = random.randint(0, 60)
            created = datetime.now() - timedelta(days=days_ago)
            customer = random.choice(kupci)
            channel_name = random.choice(["Instagram", "WhatsApp", "Etsy", "Shopify", "Lično"])
            channel_id = ch_map.get(channel_name, ch_map.get("Lično"))
            status = random.choice(["new", "paid", "shipped", "done", "done", "done"])
            phone = f"+3816{random.randint(10000000, 99999999)}"

            cur = conn.execute("""
                INSERT INTO orders
                    (customer_name, customer_phone, channel_id, status, created_at, source)
                VALUES (%s, %s, %s, %s, %s, 'demo')
                RETURNING id
            """, (customer, phone, channel_id, status, created))
            order_id = cur.fetchone()["id"]

            for _ in range(random.randint(1, 3)):
                prod_id, price = random.choice(prods)
                qty = random.randint(1, 3)
                conn.execute("""
                    INSERT INTO order_items (order_id, product_id, qty, unit_price)
                    VALUES (%s, %s, %s, %s)
                """, (order_id, prod_id, qty, price))

        conn.commit()

        # ===== 6. Tim =====
        members = [
            ("Aleksandar N.", "Dizajner", 1500),
            ("Jovana M.", "Programer", 2000),
            ("Marko P.", "Marketing", 1200),
        ]
        for name, role, rate in members:
            conn.execute("""
                INSERT INTO team_members (name, role, hourly_rate)
                VALUES (%s, %s, %s)
            """, (name, role, rate))

        # ===== 7. Projekti =====
        projekti = [
            ("PRJ-2026-01", "Rebrending kafića", "Kafić Dva lava", 180000, "done"),
            ("PRJ-2026-02", "Web sajt za restoran", "Restoran Stara vodenica", 350000, "active"),
            ("PRJ-2026-03", "Logo i identitet", "Cvetna radnja Lala", 120000, "active"),
            ("PRJ-2026-04", "Instagram kampanja", "Butik Elegance", 80000, "active"),
        ]
        for code, name, client, value, status in projekti:
            conn.execute("""
                INSERT INTO projects
                    (code, name, client, contract_value, status, start_date, deadline)
                VALUES (%s, %s, %s, %s, %s,
                        CURRENT_DATE - INTERVAL '30 days',
                        CURRENT_DATE + INTERVAL '30 days')
            """, (code, name, client, value, status))

        conn.commit()

        # ===== 8. Kapital =====
        conn.execute("""
            INSERT INTO capital_transactions
                (user_id, type, amount, balance, note)
            VALUES (%s, 'deposit', 200000, 200000, 'Početni kapital (demo)')
        """, (user_id,))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[demo] seed greška: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


def reset_demo_data():
    """Reset — poziva seed ponovo."""
    return seed_demo_data()