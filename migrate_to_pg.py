# migrate_to_pg.py
"""
Idempotentna migracija: TEXT datum kolone -> TIMESTAMP/DATE.
Bezbedno je pokrenuti više puta.

Pokretanje:
    python migrate_to_pg.py            # primeni migraciju
    python migrate_to_pg.py --dry-run  # samo prikaži šta bi uradio
"""

import sys
import logging

from db_adapter import connect, query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate")


# (tabela, kolona, ciljni_tip)
# ciljni_tip: 'timestamp' ili 'date'
MIGRATIONS = [
    ("orders",            "created_at",   "timestamp"),
    ("orders",            "updated_at",   "timestamp"),
    ("products",          "created_at",   "timestamp"),
    ("products",          "updated_at",   "timestamp"),
    ("sync_log",          "created_at",   "timestamp"),
    ("team_members",      "created_at",   "timestamp"),
    ("users",             "created_at",   "timestamp"),
    ("users",             "last_login",   "timestamp"),
    ("projects",          "created_at",   "timestamp"),
    ("projects",          "updated_at",   "timestamp"),
    ("projects",          "start_date",   "date"),
    ("projects",          "deadline",     "date"),
    ("projects",          "last_alert_sent_at", "timestamp"),
    ("time_entries",      "entry_date",   "date"),
    ("time_entries",      "created_at",   "timestamp"),
    ("project_expenses",  "expense_date", "date"),
    ("project_expenses",  "created_at",   "timestamp"),
    ("import_logs",       "created_at",   "timestamp"),
    ("exchange_rates",    "rate_date",    "date"),
    ("exchange_rates",    "fetched_at",   "timestamp"),
]


def column_type(table: str, column: str):
    """Vraća data_type iz information_schema, ili None ako kolona ne postoji."""
    rows = query("""
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
    """, (table, column))
    return rows[0]["data_type"] if rows else None


def column_has_bad_values(table: str, column: str) -> int:
    """
    Broj redova gde kolona nije NULL i nije parsabilna u timestamp.
    Koristi se da upozori pre ALTER-a.
    """
    rows = query(f"""
        SELECT COUNT(*) AS n
        FROM {table}
        WHERE {column} IS NOT NULL
          AND {column}::text <> ''
          AND {column}::text !~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
    """)
    return rows[0]["n"] if rows else 0


def normalize_nulls(table: str, column: str):
    """Pretvara prazne stringove u NULL da ALTER ne pukne."""
    conn = connect()
    try:
        cur = conn.execute(
            f"UPDATE {table} SET {column} = NULL "
            f"WHERE {column} IS NOT NULL AND {column}::text = ''"
        )
        conn.commit()
        if cur.rowcount:
            log.info("  očišćeno %s praznih stringova u %s.%s",
                     cur.rowcount, table, column)
    finally:
        conn.close()


def apply_migration(table: str, column: str, target: str, dry_run: bool) -> str:
    """
    Vraća: 'skipped' | 'applied' | 'failed' | 'missing'
    """
    current = column_type(table, column)
    if current is None:
        log.warning("  [%s.%s] kolona ne postoji — preskačem", table, column)
        return "missing"

    if current in ("timestamp without time zone", "timestamp with time zone"):
        log.info("  [%s.%s] već je %s — preskačem", table, column, current)
        return "skipped"

    if target == "date" and current == "date":
        log.info("  [%s.%s] već je date — preskačem", table, column)
        return "skipped"

    # Provera sumnjivih vrednosti
    try:
        bad = column_has_bad_values(table, column)
        if bad:
            log.warning("  [%s.%s] ima %s redova sa sumnjivim formatom — "
                        "prvo ih očistite ručno", table, column, bad)
            return "failed"
    except Exception as e:
        log.warning("  [%s.%s] ne mogu da proverim vrednosti: %s",
                    table, column, e)

    target_sql = "timestamp" if target == "timestamp" else "date"
    sql = (
        f"ALTER TABLE {table} "
        f"ALTER COLUMN {column} TYPE {target_sql} "
        f"USING NULLIF({column}::text, '')::{target_sql}"
    )

    if dry_run:
        log.info("  [%s.%s] DRY-RUN: %s", table, column, sql)
        return "applied"

    log.info("  [%s.%s] menjam %s -> %s", table, column, current, target_sql)
    normalize_nulls(table, column)

    conn = connect()
    try:
        conn.execute(sql)
        conn.commit()
        log.info("  [%s.%s] OK", table, column)
        return "applied"
    except Exception as e:
        conn.rollback()
        log.error("  [%s.%s] GREŠKA: %s", table, column, e)
        return "failed"
    finally:
        conn.close()


def refresh_views():
    """Osvežava view-ove koji zavise od promenjenih kolona."""
    log.info("Osvežavam view-ove...")
    conn = connect()
    try:
        conn.execute("DROP VIEW IF EXISTS v_order_profit")
        conn.execute("DROP VIEW IF EXISTS v_project_summary")
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.warning("Ne mogu da obrišem view-ove: %s", e)
    finally:
        conn.close()

    # Napomena: same view-ove kreirate iz schema.sql ili posebnom skriptom.
    log.info("View-ovi obrisani. Pokrenite schema.sql (ili CREATE VIEW deo) "
             "da ih ponovo napravite.")


def main():
    dry_run = "--dry-run" in sys.argv

    log.info("=== Migracija TEXT -> TIMESTAMP/DATE (dry_run=%s) ===", dry_run)

    # Brzi healthcheck
    try:
        rows = query("SELECT current_database() AS db, version() AS v")
        log.info("Baza: %s", rows[0]["db"])
        log.info("Verzija: %s", rows[0]["v"].split(",")[0])
    except Exception as e:
        log.error("Ne mogu da se povežem na bazu: %s", e)
        sys.exit(1)

    summary = {"applied": 0, "skipped": 0, "failed": 0, "missing": 0}

    for table, column, target in MIGRATIONS:
        log.info("-> %s.%s (cilj: %s)", table, column, target)
        try:
            result = apply_migration(table, column, target, dry_run)
        except Exception as e:
            log.error("  neočekivana greška: %s", e)
            result = "failed"
        summary[result] += 1

    log.info("=== Rezime ===")
    for k, v in summary.items():
        log.info("  %-8s %d", k, v)

    if not dry_run and summary["applied"] > 0:
        refresh_views()
        log.info("Sada pokrenite deo schema.sql koji kreira view-ove "
                 "(CREATE OR REPLACE VIEW ...).")

    if summary["failed"]:
        log.warning("Bilo je grešaka — pogledajte log iznad.")
        sys.exit(2)


if __name__ == "__main__":
    main()