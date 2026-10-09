# migrate_capital.py
"""
Migracija: dodaje tabelu capital_transactions i kolonu users.capital.
Pokreni jednom: python migrate_capital.py
"""
from db_adapter import connect


def migrate():
    conn = connect()

    # 1) Kolona users.capital (trenutno stanje, keširano radi brzine)
    conn.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS capital NUMERIC(12,2) NOT NULL DEFAULT 0
    """)

    # 2) Tabela capital_transactions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS capital_transactions (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            type        TEXT NOT NULL,           -- 'deposit' | 'withdrawal' | 'purchase' | 'sale' | 'adjustment'
            amount      NUMERIC(12,2) NOT NULL,  -- uvek pozitivan broj
            balance     NUMERIC(12,2) NOT NULL,  -- stanje POSLE transakcije
            note        TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_capital_tx_user
        ON capital_transactions(user_id, created_at DESC)
    """)

    conn.commit()
    conn.close()
    print("✅ Migracija završena: capital_transactions + users.capital")


if __name__ == "__main__":
    migrate()