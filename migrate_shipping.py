# migrate_shipping.py
"""
Migracija: dodaje kolone za dostavu u tabelu orders.
Bezbedno se može pokrenuti više puta.
"""
from db_adapter import connect, USE_POSTGRES


def migrate():
    conn = connect()
    cur = conn.cursor()

    # Lista kolona koje dodajemo: (ime, SQL tip, default)
    columns = [
        ("shipping_cost",   "REAL",  "0"),
        ("shipping_method", "TEXT",  "''"),
    ]

    for col_name, col_type, default in columns:
        try:
            if USE_POSTGRES:
                sql = f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {col_name} {col_type} DEFAULT {default}"
            else:
                # SQLite nema IF NOT EXISTS za ADD COLUMN (starije verzije)
                sql = f"ALTER TABLE orders ADD COLUMN {col_name} {col_type} DEFAULT {default}"
            cur.execute(sql)
            conn.commit()
            print(f"✅ Dodata kolona: {col_name} ({col_type})")
        except Exception as e:
            # Ako kolona već postoji, preskoči
            msg = str(e).lower()
            if "duplicate" in msg or "already exists" in msg:
                print(f"⏭️  Kolona već postoji: {col_name}")
            else:
                print(f"❌ Greška pri dodavanju {col_name}: {e}")
                conn.close()
                return

    # Provera da li je sve OK
    print("\n📋 Trenutna šema tabele orders:")
    rows = cur.execute("PRAGMA table_info(orders)").fetchall()
    for r in rows:
        # r može biti tuple ili dict u zavisnosti od driver-a
        try:
            print(f"   {r['name']} ({r['type']})")
        except (TypeError, KeyError):
            print(f"   {r[1]} ({r[2]})")

    conn.close()
    print("\n🎉 Migracija završena!")


if __name__ == "__main__":
    migrate()