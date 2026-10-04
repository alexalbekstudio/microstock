# migrate_pricing.py
"""
Dodaje tabele za kalkulator cena:
  - pricing_history    (istorija kalkulacija)
  - channel_presets    (šabloni provizija po kanalu)
"""
from db_adapter import connect


def migrate():
    conn = connect()
    cur = conn.cursor()

    # --- pricing_history ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pricing_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER,
            product_id      INTEGER,
            product_name    TEXT,
            mode            TEXT,        -- 'recommended' ili 'analyze'
            cost            REAL,
            shipping        REAL,
            fee_pct         REAL,
            tax_pct         REAL,
            margin_pct      REAL,        -- ciljna (režim A) ili stvarna (režim B)
            price           REAL,
            profit          REAL,
            markup_pct      REAL,
            applied         INTEGER DEFAULT 0,   -- 1 ako je cena upisana u proizvod
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pricing_history_created ON pricing_history(created_at DESC)")

    # --- channel_presets ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS channel_presets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL UNIQUE,
            fee_pct         REAL NOT NULL DEFAULT 0,
            tax_pct         REAL NOT NULL DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Seed podrazumevanih preseta (samo ako je tabela prazna)
    row = cur.execute("SELECT COUNT(*) FROM channel_presets").fetchone()
    count = row[0] if not isinstance(row, dict) else list(row.values())[0]
    if count == 0:
        defaults = [
            ("Etsy",        6.5, 0),
            ("Gumroad",    10.0, 0),
            ("Payhip",      5.0, 0),
            ("Shopify",     2.9, 0),
            ("TikTok",      5.0, 0),
            ("Instagram",   0.0, 0),
            ("PDV 20%",     0.0, 20),
        ]
        for name, fee, tax in defaults:
            cur.execute(
                "INSERT INTO channel_presets (name, fee_pct, tax_pct) VALUES (?,?,?)",
                (name, fee, tax)
            )
        conn.commit()
        print(f"→ Ubačeno {len(defaults)} podrazumevanih preseta.")

    conn.close()
    print("✅ Migracija za kalkulator cena završena.")


if __name__ == "__main__":
    migrate()