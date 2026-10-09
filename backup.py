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
    return _backup_postgres()

def _backup_postgres() -> Path:
    """
    Export PostgreSQL baze u JSON (tabele + redovi).
    Koristi jednu konekciju kroz celu operaciju.
    """
    dst = BACKUP_DIR / f"pg_backup_{_timestamp()}.json"
    data = {"exported_at": datetime.now().isoformat(), "tables": {}}

    conn = connect()
    try:
        # Lista tabela — preko _ConnWrapper (RealDictCursor)
        tables = conn.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """).fetchall()

        for t in tables:
            table = t["table_name"]
            rows_raw = conn.execute(f'SELECT * FROM "{table}"').fetchall()
            rows = []
            for r in rows_raw:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if hasattr(v, "isoformat"):
                        row_dict[k] = v.isoformat()
                    elif isinstance(v, bytes):
                        row_dict[k] = v.decode("utf-8", errors="replace")
                rows.append(row_dict)
            data["tables"][table] = rows

    finally:
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