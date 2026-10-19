# db_adapter.py
"""
Adapter za PostgreSQL (Render i lokalno).
- connect() vraća konekciju sa RealDictCursor (redovi se ponašaju kao dict).
- execute() prima SQL sa %s placeholderima (PostgreSQL stil).
- Postoji i helper query() koji odmah vraća listu dict-ova.

NAPOMENA: Ovaj adapter je namenjen ISKLJUČIVO PostgreSQL-u.
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

# Uvek PostgreSQL (nema više SQLite fallback-a)
USE_POSTGRES = True

DATABASE_URL = None  # postavlja se lenjo preko _database_url()


def _refresh_module_globals():
    """Popunjava module-level konstante nakon što se učita .env."""
    global DATABASE_URL
    DATABASE_URL = _database_url()


def get_conn():
    return connect()


def adapt_query(sql):
    return sql


def adapt_schema(schema_sql):
    return schema_sql

# ---------------------------------------------------------------------------
# Konfiguracija
# ---------------------------------------------------------------------------

def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "postgres")
    pwd  = os.environ.get("PGPASSWORD", "postgres")
    db   = os.environ.get("PGDATABASE", "microstock")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


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
    def __init__(self, raw_conn, pool):
        self._raw = raw_conn
        self._pool = pool
        self._closed = False

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
    """
    Vraća konekciju uvek sa čistim 'public' search_path-om,
    osim ako je u toku sesija u demo režimu (i to van login/logout ruta).
    """
    try:
        from flask import has_request_context, session, request
        if has_request_context():
            endpoint = request.endpoint or ""
            # Sve što ima veze sa loginom, odjavom, profilom ili resetom šifre MORA biti public
            if (
                "auth." in endpoint 
                or request.path in ("/login", "/logout", "/demo/exit", "/forgot-password")
                or request.path.startswith("/reset-password")
            ):
                return _connect_public()

            if session.get("demo_mode"):
                return connect_demo()
    except Exception:
        pass

    return _connect_public()


# ---------------------------------------------------------------------------
# Helperi
# ---------------------------------------------------------------------------

def query(sql: str, params=None):
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def query_one(sql: str, params=None):
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def execute(sql: str, params=None):
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
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def healthcheck():
    try:
        row = query_one("SELECT version() AS v, current_database() AS db")
        return True, {"version": row["v"], "database": row["db"]}
    except Exception as e:
        return False, str(e)


_refresh_module_globals()

# ---------------------------------------------------------------------------
# DEMO schema
# ---------------------------------------------------------------------------

def _connect_public():
    """Garantovano vraća konekciju čiji je search_path postavljen na public."""
    raw = _get_pool().getconn()
    cur = raw.cursor()
    try:
        cur.execute("SET search_path TO public;")
        raw.commit()
    except Exception:
        raw.rollback()
    finally:
        cur.close()
    return _ConnWrapper(raw, _get_pool())


def connect_demo():
    """Vraća konekciju u 'demo' schema (search_path: demo, public)."""
    raw = _get_pool().getconn()
    cur = raw.cursor()
    try:
        cur.execute("SET search_path TO demo, public;")
        raw.commit()
    except Exception as e:
        raw.rollback()
        log.error(f"Ne mogu da postavim search_path na demo: {e}")
    finally:
        cur.close()
    return _ConnWrapper(raw, _get_pool())