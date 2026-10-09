# db_adapter.py
"""
Adapter za PostgreSQL (Render i lokalno).
- connect() vraća konekciju sa RealDictCursor (redovi se ponašaju kao dict).
- execute() prima SQL sa %s placeholderima (PostgreSQL stil).
- Postoji i helper query() koji odmah vraća listu dict-ova.

NAPOMENA: Ovaj adapter je namenjen ISKLJUČIVO PostgreSQL-u.
Ako želite da podržite i SQLite, javite — ali preporuka je
da svuda koristite PostgreSQL da izbegnete dijalekt razlike.
"""

import os
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.extensions

# Konvertuj Decimal u float automatski
DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    'DEC2FLOAT',
    lambda value, curs: float(value) if value is not None else None
)
psycopg2.extensions.register_type(DEC2FLOAT)
from psycopg2 import pool as pg_pool


log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kompatibilnost sa starim API-jem (SQLite + PostgreSQL)
# ---------------------------------------------------------------------------
# Ostali moduli u projektu (auth.py, models.py, backup.py, itd.) očekuju
# ove simbole iz starog db_adapter-a. Pošto smo prešli na PostgreSQL-only,
# ostavljamo ih kao stubove.

# Uvek PostgreSQL (nema više SQLite fallback-a)
USE_POSTGRES = True

# Za backup.py — puna URL adresa baze
DATABASE_URL = None  # postavlja se lenjo preko _database_url()


def _refresh_module_globals():
    """Popunjava module-level konstante nakon što se učita .env."""
    global DATABASE_URL
    DATABASE_URL = _database_url()


# Ove funkcije su stubovi — u PostgreSQL-only režimu nisu potrebne,
# ali ih ostali moduli mogu pozivati.
def get_conn():
    """
    Vraća _ConnWrapper (isto kao connect()) — kompatibilnost sa starim kodom.
    """
    return connect()


def adapt_query(sql):
    """U PostgreSQL-only režimu, samo vrati SQL nepromenjen (očekuje %s)."""
    return sql


def adapt_schema(schema_sql):
    """U PostgreSQL-only režimu, šema je već PostgreSQL sintaksa."""
    return schema_sql

# ---------------------------------------------------------------------------
# Konfiguracija
# ---------------------------------------------------------------------------

def _database_url() -> str:
    """
    Redosled traženja:
      1) DATABASE_URL  (Render ga automatski postavlja)
      2) DB_URL        (alternativa)
      3) sastavljanje iz PG* varijabli
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if url:
        # Render ponekad daje "postgres://", psycopg2 zahteva "postgresql://"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    # Fallback za lokalni razvoj
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "postgres")
    pwd  = os.environ.get("PGPASSWORD", "postgres")
    db   = os.environ.get("PGDATABASE", "microstock")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


# Jednostavan pool — dovoljno za Flask na Render-u (1 worker).
# Ako imate više worker-a, povećajte maxconn.
_POOL = None


def _get_pool() -> pg_pool.SimpleConnectionPool:
    global _POOL
    if _POOL is None:
        dsn = _database_url()
        log.info("Kreiram PostgreSQL connection pool")
        _POOL = pg_pool.SimpleConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=dsn,
            cursor_factory=psycopg2.extras.RealDictCursor,
            options="-c extra_float_digits=3",
        )
    return _POOL


# ---------------------------------------------------------------------------
# Konekcija
# ---------------------------------------------------------------------------

class _ConnWrapper:
    """
    Tanki omotač oko psycopg2 konekcije koji imitira sqlite3 API
    (execute/fetchone/fetchall/close) da ostatak koda ne mora da se menja.
    """

    def __init__(self, raw_conn, pool):
        self._raw = raw_conn
        self._pool = pool
        self._closed = False

    # --- izvršavanje ---

    def execute(self, sql: str, params=None):
        sql = sql.replace("?", "%s")
        cur = self._raw.cursor()
        try:
            cur.execute(sql, params or ())
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur
    def executemany(self, sql: str, seq_of_params):
        sql = sql.replace("?", "%s")
        cur = self._raw.cursor()
        try:
            cur.executemany(sql, seq_of_params)
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur

    def executescript(self, script: str):
        """Izvršava više SQL naredbi odjednom (kao sqlite3.executescript)."""
        cur = self._raw.cursor()
        try:
            cur.execute(script)
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._raw.rollback()
        except Exception:
            pass
        try:
            self._pool.putconn(self._raw)
        except Exception:
            try:
                self._raw.close()
            except Exception:
                pass

    # --- convenience ---

    def cursor(self, *args, **kwargs):
        return self._raw.cursor(*args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            try:
                self.commit()
            except Exception:
                self.rollback()
                raise
        else:
            self.rollback()
        self.close()


def connect():
    raw = _get_pool().getconn()
    return _ConnWrapper(raw, _get_pool())


# ---------------------------------------------------------------------------
# Helperi (opciono — mogu da zamene direktne connect() pozive)
# ---------------------------------------------------------------------------

def query(sql: str, params=None):
    """Vraća listu dict-ova."""
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def query_one(sql: str, params=None):
    """Vraća jedan dict ili None."""
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def execute(sql: str, params=None):
    """Izvršava INSERT/UPDATE/DELETE i commit-uje. Vraća rowcount."""
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_returning(sql: str, params=None):
    """Za INSERT ... RETURNING id — vraća fetchone() rezultat."""
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction():
    """with transaction() as conn: ... — automatski commit/rollback."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dijagnostika
# ---------------------------------------------------------------------------

def healthcheck():
    """Vraća (True, info) ili (False, greška). Korisno za /health rutu."""
    try:
        row = query_one("SELECT version() AS v, current_database() AS db")
        return True, {"version": row["v"], "database": row["db"]}
    except Exception as e:
        return False, str(e)

# Inicijalizuj module-level konstante
_refresh_module_globals()