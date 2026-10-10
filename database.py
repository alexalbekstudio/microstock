# database.py
"""
Inicijalizacija PostgreSQL baze + auto-migracije.
"""
from pathlib import Path
from db_adapter import connect

SCHEMA = Path(__file__).parent / "schema.sql"


def init_db():
    """Kreira tabele ako ne postoje (idempotentno) + auto-migracije."""
    conn = connect()
    with open(SCHEMA, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    for stmt in _split_sql(schema_sql):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception as e:
            conn.rollback()
            msg = str(e).lower()
            if "already exists" not in msg and "duplicate" not in msg:
                print(f"⚠️  Preskočeno: {stmt[:60]}... ({e})")

    # === AUTO-MIGRACIJE ===
    _run_migrations(conn)

    conn.close()
    print("✅ Baza inicijalizovana (PostgreSQL)")


def _run_migrations(conn):
    """
    Male izmene šeme koje se izvršavaju pri svakom startu.
    Sve koristi IF NOT EXISTS — bezbedno za ponovno pokretanje.
    """
    migrations = [
        # 1) users.capital (kapital vlasnika)
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS capital NUMERIC(12,2) NOT NULL DEFAULT 0",

        # 2) capital_transactions (istorija uplata/isplata)
        """
        CREATE TABLE IF NOT EXISTS capital_transactions (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            type        TEXT NOT NULL,
            amount      NUMERIC(12,2) NOT NULL,
            balance     NUMERIC(12,2) NOT NULL,
            note        TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 3) Index za capital_transactions
        """
        CREATE INDEX IF NOT EXISTS idx_capital_tx_user
        ON capital_transactions(user_id, created_at DESC)
        """,

        # 4) Novi kanali (Shopify, Gumroad, Payhip, TikTok)
        """
        INSERT INTO channels (name, fee_percent) VALUES
            ('Shopify', 0.0),
            ('Gumroad', 0.0),
            ('Payhip',  0.0),
            ('TikTok',  0.0)
        ON CONFLICT (name) DO NOTHING
        """,

                # 5) password_resets (zaboravljena šifra)
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token       TEXT NOT NULL UNIQUE,
            expires_at  TIMESTAMP NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 6) Index za password_resets
        """
        CREATE INDEX IF NOT EXISTS idx_password_resets_token
        ON password_resets(token)
        """,

                # 8) suppliers — dobavljači
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id                SERIAL PRIMARY KEY,
            name              TEXT NOT NULL,
            contact_person    TEXT,
            email             TEXT,
            phone             TEXT,
            address           TEXT,
            city              TEXT,
            tax_id            TEXT,
            iban              TEXT,
            swift             TEXT,
            product_categories TEXT,
            notes             TEXT,
            active            INTEGER NOT NULL DEFAULT 1,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

                # 10) purchase_invoices — računi nabavke
        """
        CREATE TABLE IF NOT EXISTS purchase_invoices (
            id              SERIAL PRIMARY KEY,
            supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
            invoice_number  TEXT,
            invoice_date    DATE,
            due_date        DATE,
            paid_date       DATE,
            amount          NUMERIC(12,2) NOT NULL DEFAULT 0,
            currency        TEXT NOT NULL DEFAULT 'RSD',
            status          TEXT NOT NULL DEFAULT 'pending',
            file_data       BYTEA,
            file_name       TEXT,
            file_mime       TEXT,
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 11) Index za pretragu računa
        """
        CREATE INDEX IF NOT EXISTS idx_purchase_invoices_supplier
        ON purchase_invoices(supplier_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_invoices_status
        ON purchase_invoices(status)
        """,

        # 12) purchase_items — stavke računa
        """
        CREATE TABLE IF NOT EXISTS purchase_items (
            id                  SERIAL PRIMARY KEY,
            purchase_invoice_id INTEGER NOT NULL REFERENCES purchase_invoices(id) ON DELETE CASCADE,
            product_id          INTEGER REFERENCES products(id) ON DELETE SET NULL,
            description         TEXT,
            qty                 NUMERIC(12,2) NOT NULL DEFAULT 0,
            unit_cost           NUMERIC(12,2) NOT NULL DEFAULT 0,
            total               NUMERIC(12,2) NOT NULL DEFAULT 0
        )
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_items_invoice
        ON purchase_items(purchase_invoice_id)
        """,

        # 9) Index za pretragu dobavljača
        """
        CREATE INDEX IF NOT EXISTS idx_suppliers_name
        ON suppliers(name)
        """,
    ]

    for sql in migrations:
        try:
            conn.execute(sql.strip())
            conn.commit()
        except Exception as e:
            conn.rollback()
            msg = str(e).lower()
            if "already exists" not in msg and "duplicate" not in msg:
                print(f"⚠️  Migracija preskočena: {sql[:60]}... ({e})")

    print("✅ Auto-migracije završene")


def _split_sql(sql):
    """Deli SQL po ; (prosto)."""
    parts = []
    current = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            parts.append("\n".join(current))
            current = []
    if current:
        parts.append("\n".join(current))
    return parts


# Kompatibilnost: dashboard.py i drugi stari fajlovi očekuju get_conn()
from db_adapter import get_conn  # noqa: F401

if __name__ == "__main__":
    init_db()