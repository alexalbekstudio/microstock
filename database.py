# database.py
"""
Inicijalizacija baze. Radi i sa SQLite i sa PostgreSQL.
"""
from pathlib import Path
from db_adapter import connect, USE_POSTGRES, adapt_schema, get_conn

SCHEMA = Path(__file__).parent / "schema.sql"


def init_db():
    """Kreira tabele ako ne postoje."""
    conn = connect()
    with open(SCHEMA, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    if USE_POSTGRES:
        schema_sql = adapt_schema(schema_sql)
        # PostgreSQL ne podržava CREATE VIEW IF NOT EXISTS direktno
        schema_sql = schema_sql.replace("CREATE VIEW IF NOT EXISTS", "CREATE OR REPLACE VIEW")
        schema_sql = schema_sql.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE IF NOT EXISTS")
        # Ispravi trigger syntax koji PostgreSQL ne razume (SQLite specifičan)
        schema_sql = _strip_sqlite_only_triggers(schema_sql)
        # Izvrši svaki statement odvojeno
        for stmt in _split_sql(schema_sql):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                conn.execute(stmt)
            except Exception as e:
                # Preskoči "already exists" greške
                msg = str(e).lower()
                if "already exists" not in msg:
                    print(f"⚠️  Preskočeno: {stmt[:60]}... ({e})")
    else:
        conn.executescript(schema_sql)

    conn.commit()
    conn.close()

    backend = "PostgreSQL" if USE_POSTGRES else "SQLite"
    print(f"✅ Baza inicijalizovana ({backend})")


def _strip_sqlite_only_triggers(sql):
    """
    Ukloni SQLite-only trigere koji koriste RAISE() ili AFTER UPDATE
    sa subquery-jem (PostgreSQL zahteva funkciju + trigger syntax).
    Za potrebe naše aplikacije, možemo ih preskočiti jer isto radimo u Python kodu.
    """
    import re
    # Uklanja sve CREATE TRIGGER ... END; blokove
    pattern = re.compile(
        r"CREATE\s+TRIGGER\s+.*?END\s*;",
        re.IGNORECASE | re.DOTALL
    )
    return pattern.sub("", sql)


def _split_sql(sql):
    """Deljenje SQL skripte po ; koji nije unutar BEGIN...END."""
    result = []
    current = []
    in_trigger = False
    for line in sql.splitlines():
        upper = line.upper()
        if "CREATE TRIGGER" in upper:
            in_trigger = True
        if in_trigger:
            current.append(line)
            if line.strip().endswith("END;"):
                in_trigger = False
                result.append("\n".join(current))
                current = []
        else:
            current.append(line)
            if line.strip().endswith(";"):
                result.append("\n".join(current))
                current = []
    if current:
        result.append("\n".join(current))
    return result


if __name__ == "__main__":
    init_db()