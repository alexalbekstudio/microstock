# migrate_alerts.py — pokreni JEDNOM
from db_adapter import connect

conn = connect()
cur = conn.cursor()

for stmt in [
    "ALTER TABLE projects ADD COLUMN last_alert_level TEXT DEFAULT NULL",
    "ALTER TABLE projects ADD COLUMN last_alert_sent_at TEXT DEFAULT NULL",
]:
    try:
        cur.execute(stmt)
        print(f"OK: {stmt}")
    except Exception as e:
        print(f"SKIP: {e}")

conn.commit()
conn.close()
print("Migracija završena.")