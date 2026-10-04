# database.py
"""
Inicijalizacija PostgreSQL baze.
"""
from pathlib import Path
from db_adapter import connect

SCHEMA = Path(__file__).parent / "schema.sql"


def init_db():
    """Kreira tabele ako ne postoje (idempotentno)."""
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

    conn.close()
    print("✅ Baza inicijalizovana (PostgreSQL)")


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

# Kompatibilnost: dashboard.py i drugi stari fajlovi očekuju get_conn() u database.py
from db_adapter import get_conn  # noqa: F401

if __name__ == "__main__":
    init_db()