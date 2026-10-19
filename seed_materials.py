from db_adapter import connect

MATERIALS = [
    ("RAW-VOX-01", "Sojin vosak pahulje", 0.0, 450.00, 25.5, 5.0, 1, "kg"),
    ("RAW-FIT-02", "Pamučni fitilj sa držačem 15cm", 0.0, 12.00, 150.0, 30.0, 1, "kom"),
    ("RAW-ULJ-03", "Mirisno ulje - Francuska vanila", 0.0, 620.00, 8.0, 2.0, 1, "ml"),
    ("RAW-TEG-04", "Staklena tegla za sveću 200ml", 0.0, 65.00, 80.0, 20.0, 1, "kom"),
    ("RAW-GLI-05", "Keramička glina bela", 0.0, 180.00, 40.0, 10.0, 1, "kg"),
    ("RAW-GLA-06", "Glazura za keramiku - Sjajna bela", 0.0, 890.00, 5.0, 1.5, 1, "l"),
    ("RAW-PIN-07", "Metalna osnova za bedž 38mm", 0.0, 8.50, 500.0, 100.0, 1, "kom"),
    ("RAW-BOJ-08", "Tekstilna boja za sito štampu - Crna", 0.0, 1250.00, 4.0, 1.0, 1, "kg"),
    ("RAW-KUT-09", "Kraft transportna kutija 15x15x10cm", 0.0, 32.00, 200.0, 50.0, 1, "kom"),
]

def seed():
    conn = connect()
    # Preuzimamo prvog korisnika (admina)
    user = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
    if not user:
        print("❌ Nema registrovanih korisnika u bazi.")
        conn.close()
        return

    user_id = user["id"]
    print(f"Uvozim sirovine za korisnika ID: {user_id}...")

    for sku, name, price, cost, stock, low_stock, is_mat, unit in MATERIALS:
        conn.execute("""
            INSERT INTO products (user_id, sku, name, price, cost, stock, low_stock_at, is_material, unit, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            ON CONFLICT (sku) DO UPDATE 
            SET name = EXCLUDED.name,
                cost = EXCLUDED.cost,
                stock = EXCLUDED.stock,
                is_material = EXCLUDED.is_material,
                unit = EXCLUDED.unit
        """, (user_id, sku, name, price, cost, stock, low_stock, is_mat, unit))

    conn.commit()
    conn.close()
    print("✅ Uspješno uvezeno 9 sirovina u bazu!")

if __name__ == "__main__":
    seed()