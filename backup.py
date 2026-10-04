# backup.py
"""
Backup baze podataka — SQLite i PostgreSQL.
"""
import os
import shutil
import sqlite3
import json
from datetime import datetime
from pathlib import Path

from db_adapter import connect, USE_POSTGRES, DATABASE_URL

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "backups"))
BACKUP_DIR.mkdir(exist_ok=True)


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def create_backup() -> Path:
    """
    Pravi backup baze.
    - SQLite: kopira inventory.db u backups/inventory_YYYYMMDD_HHMMSS.db
    - PostgreSQL: export u JSON backups/pg_backup_YYYYMMDD_HHMMSS.json
    Vraća putanju do backup fajla.
    """
    if USE_POSTGRES:
        return _backup_postgres()
    return _backup_sqlite()


def _backup_sqlite() -> Path:
    """Kopira SQLite fajl (sigurno i dok je baza otvorena)."""
    src = Path(os.getenv("SQLITE_PATH", "inventory.db"))
    if not src.exists():
        raise FileNotFoundError(f"SQLite baza nije nađena: {src}")

    dst = BACKUP_DIR / f"inventory_{_timestamp()}.db"

    # Sigurno kopiranje preko SQLite backup API-ja (radi i sa aktivnim konekcijama)
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    with dst_conn:
        src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    return dst


def _backup_postgres() -> Path:
    """
    Export PostgreSQL baze u JSON (tabele + redovi).
    Za pravi pg_dump backup koristiti eksterni alat.
    """
    dst = BACKUP_DIR / f"pg_backup_{_timestamp()}.json"
    data = {"exported_at": datetime.now().isoformat(), "tables": {}}

    conn = connect()
    cur = conn.cursor()

    # Lista tabela
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]

    for table in tables:
        cur.execute(f'SELECT * FROM "{table}"')
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        # datetime → string
        for r in rows:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
        data["tables"][table] = rows

    cur.close()
    conn.close()

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return dst


def list_backups():
    """Vraća listu backup fajlova (najnoviji prvi)."""
    files = sorted(BACKUP_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "name": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d.%m.%Y %H:%M"),
        }
        for f in files
        if f.is_file()
    ]