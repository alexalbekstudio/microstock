# refresh_views.py
"""Osvežava VIEW-ove da bi PostgreSQL pokupio nove tipove kolona."""
from pathlib import Path
from db_adapter import connect
import re
import traceback


def refresh_views():
    print("=== refresh_views START ===")
    try:
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")
        print(f"=== schema.sql pročitan ({len(schema_sql)} bajtova) ===")

        conn = connect()
        print("=== Konekcija otvorena ===")

        # 1. DROP
        try:
            conn.execute("DROP VIEW IF EXISTS v_order_profit")
            conn.execute("DROP VIEW IF EXISTS v_project_summary")
            conn.commit()
            print("✅ View-ovi obrisani")
        except Exception as e:
            conn.rollback()
            print(f"⚠️  Greška pri brisanju view-ova: {e}")
            traceback.print_exc()
            conn.close()
            return

        # 2. CREATE
        view_blocks = re.findall(
            r"CREATE\s+OR\s+REPLACE\s+VIEW\s+.*?;",
            schema_sql,
            re.IGNORECASE | re.DOTALL
        )
        print(f"=== Nađeno {len(view_blocks)} VIEW blokova u schema.sql ===")

        for i, block in enumerate(view_blocks, 1):
            name = block[:80].replace("\n", " ")
            print(f"=== Kreiram VIEW #{i}: {name}...")
            try:
                conn.execute(block)
                conn.commit()
                print(f"✅ VIEW #{i} kreiran")
            except Exception as e:
                conn.rollback()
                print(f"⚠️  VIEW #{i} preskočen: {str(e)[:200]}")
                traceback.print_exc()

        conn.close()
        print("=== refresh_views DONE ===")
    except Exception as e:
        print(f"⚠️  refresh_views FATAL: {e}")
        traceback.print_exc()