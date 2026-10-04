# refresh_views.py
"""
Osvežava VIEW-ove da bi PostgreSQL pokupio nove tipove kolona.
Pokreni pri startu aplikacije — bezbedno je za višestruko izvršavanje.
"""
from pathlib import Path
from db_adapter import connect
import re


def refresh_views():
    """DROP + CREATE view-ove iznova iz schema.sql."""
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = connect()
    try:
        # 1. Obriši postojeće VIEW-ove
        conn.execute("DROP VIEW IF EXISTS v_order_profit")
        conn.execute("DROP VIEW IF EXISTS v_project_summary")
        conn.commit()
        print("✅ View-ovi obrisani")
    except Exception as e:
        conn.rollback()
        print(f"⚠️  Greška pri brisanju view-ova: {e}")
        conn.close()
        return
    finally:
        pass

    # 2. Izvuci i ponovo kreiraj VIEW-ove iz schema.sql
    view_blocks = re.findall(
        r"CREATE\s+OR\s+REPLACE\s+VIEW\s+.*?;",
        schema_sql,
        re.IGNORECASE | re.DOTALL
    )

    created = 0
    for block in view_blocks:
        try:
            conn.execute(block)
            conn.commit()
            created += 1
        except Exception as e:
            conn.rollback()
            print(f"⚠️  View preskočen: {str(e)[:120]}")

    conn.close()
    print(f"✅ Kreirano {created} view-ova")