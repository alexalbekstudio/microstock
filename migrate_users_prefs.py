# migrate_users_prefs.py
"""
Dodaje kolone `language` i `currency` u tabelu users.
Bezbedno za ponovno pokretanje (proverava da li kolone postoje).
"""
from db_adapter import connect, USE_POSTGRES


def column_exists(cur, table, column):
    """Proverava da li kolona postoji (SQLite i PostgreSQL)."""
    if USE_POSTGRES:
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """ if False else """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = ? AND column_name = ?
        """, (table, column))
    else:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [row["name"] for row in cur.fetchall()]
        return column in cols

    return cur.fetchone() is not None


def main():
    conn = connect()
    cur = conn.cursor()

    # language
    if not column_exists(cur, "users", "language"):
        print("Dodajem kolonu users.language ...")
        cur.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'sr'")
        conn.commit()
        print("  ✅ users.language dodata")
    else:
        print("  ⏭  users.language već postoji")

    # currency
    if not column_exists(cur, "users", "currency"):
        print("Dodajem kolonu users.currency ...")
        cur.execute("ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'RSD'")
        conn.commit()
        print("  ✅ users.currency dodata")
    else:
        print("  ⏭  users.currency već postoji")

    conn.close()
    print()
    print("Migracija završena.")


if __name__ == "__main__":
    main()