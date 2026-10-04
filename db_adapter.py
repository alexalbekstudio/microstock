# db_adapter.py
"""
Apstrakcija između SQLite (lokalno) i PostgreSQL (produkcija).

Detekcija:
- Ako postoji env varijabla DATABASE_URL -> koristi PostgreSQL
- Inače -> koristi SQLite (inventory.db u istom folderu)

Obezbeđuje isti interfejs (get_conn(), Row kao dict, upitnik ? -> %s).
"""
import os
import sqlite3
from pathlib import Path

# Učitaj .env ako postoji (lokalno)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = Path(__file__).parent / "inventory.db"

USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras


# ==================== KONEKCIJA ====================

def get_conn():
    if USE_POSTGRES:
        # Render ponekad daje URL sa prefiksom "postgres://" (staro),
        # psycopg2 zahteva "postgresql://"
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


# ==================== PREVODILAC UPITA ====================

def adapt_query(sql):
    """SQLite koristi ? za parametre, PostgreSQL %s."""
    if USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def adapt_schema(schema_sql):
    """
    Prilagodi SQL šemu za PostgreSQL:
    - AUTOINCREMENT -> SERIAL (preko INTEGER PRIMARY KEY)
    - datetime('now') -> CURRENT_TIMESTAMP
    - RAISE() trigeri se preskaču (SQLite-only)
    """
    if not USE_POSTGRES:
        return schema_sql

    # AUTOINCREMENT ne postoji u PostgreSQL - koristi SERIAL
    schema_sql = schema_sql.replace(
        "INTEGER PRIMARY KEY AUTOINCREMENT",
        "SERIAL PRIMARY KEY"
    )
    # datetime('now') -> CURRENT_TIMESTAMP
    schema_sql = schema_sql.replace("datetime('now')", "CURRENT_TIMESTAMP")

    return schema_sql


# ==================== WRAPPER KONEKCIJE ====================

class ConnectionWrapper:
    """
    Omotava konekciju tako da `conn.execute(sql, params)` radi
    isto za SQLite i PostgreSQL.
    """
    def __init__(self, conn):
        self._conn = conn
        self._pg = USE_POSTGRES

    def execute(self, sql, params=None):
        sql = adapt_query(sql)
        if params is None:
            params = ()
        if self._pg:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur
        else:
            return self._conn.execute(sql, params)

    def executescript(self, sql):
        """Za šemu - u PostgreSQL-u se izvršava red po red."""
        if self._pg:
            cur = self._conn.cursor()
            cur.execute(sql)
            return cur
        else:
            return self._conn.executescript(sql)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()


def connect():
    """Vraća omotanu konekciju."""
    return ConnectionWrapper(get_conn())