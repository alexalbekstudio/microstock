# refresh_views.py
"""Osvežava VIEW-ove u public i demo šemi."""
from db_adapter import connect
import traceback

def refresh_views():
    print("=== refresh_views START ===")
    conn = connect()
    try:
        schemas = ["public", "demo"]
        
        for sch in schemas:
            print(f"--- Osvežavam šemu: {sch} ---")
            
            row = conn.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
                (sch,)
            ).fetchone()
            if not row:
                continue

            # 1. DROP
            conn.execute(f"DROP VIEW IF EXISTS {sch}.v_order_profit CASCADE;")
            conn.execute(f"DROP VIEW IF EXISTS {sch}.v_project_summary CASCADE;")
            conn.commit()

            # 2. CREATE v_order_profit
            sql_order_profit = f"""
            CREATE VIEW {sch}.v_order_profit AS
            SELECT
                o.id                    AS order_id,
                o.user_id               AS user_id,
                o.created_at::timestamp AS order_date,
                o.status                AS status,
                c.id                    AS channel_id,
                c.name                  AS channel_name,
                c.fee_percent           AS fee_percent,
                p.id                    AS product_id,
                p.sku                   AS sku,
                p.name                  AS product_name,
                p.cost                  AS unit_cost,
                oi.qty                  AS qty,
                oi.unit_price           AS unit_price,
                (oi.qty * oi.unit_price)                                 AS revenue,
                (oi.qty * oi.unit_price * c.fee_percent / 100.0)         AS channel_fee,
                (oi.qty * p.cost)                                        AS product_cost,
                COALESCE(o.shipping_cost, 0) *
                  (oi.qty * oi.unit_price) /
                  NULLIF((SELECT SUM(oi2.qty * oi2.unit_price)
                          FROM {sch}.order_items oi2
                          WHERE oi2.order_id = o.id), 0)                 AS shipping_cost,
                (oi.qty * oi.unit_price)
                  - (oi.qty * oi.unit_price * c.fee_percent / 100.0)
                  - (oi.qty * p.cost)
                  - COALESCE(o.shipping_cost, 0) *
                    (oi.qty * oi.unit_price) /
                    NULLIF((SELECT SUM(oi2.qty * oi2.unit_price)
                            FROM {sch}.order_items oi2
                            WHERE oi2.order_id = o.id), 0)               AS profit
            FROM {sch}.order_items oi
            JOIN {sch}.orders   o ON o.id = oi.order_id
            JOIN {sch}.products p ON p.id = oi.product_id
            JOIN {sch}.channels c ON c.id = o.channel_id
            WHERE o.status != 'cancelled';
            """
            conn.execute(sql_order_profit)
            conn.commit()

            # 3. CREATE v_project_summary
            sql_project_summary = f"""
            CREATE VIEW {sch}.v_project_summary AS
            SELECT
                p.id                                    AS project_id,
                p.user_id                               AS user_id,
                p.code                                  AS code,
                p.name                                  AS name,
                p.client                                AS client,
                p.status                                AS status,
                p.contract_value                        AS contract_value,
                p.start_date                            AS start_date,
                p.deadline                              AS deadline,
                p.last_alert_level,
                p.last_alert_sent_at,
                COALESCE((SELECT SUM(hours) FROM {sch}.time_entries WHERE project_id = p.id), 0) AS total_hours,
                COALESCE((
                    SELECT SUM(te.hours * tm.hourly_rate)
                    FROM {sch}.time_entries te JOIN {sch}.team_members tm ON tm.id = te.member_id
                    WHERE te.project_id = p.id
                ), 0) AS labor_cost,
                COALESCE((SELECT SUM(amount) FROM {sch}.project_expenses WHERE project_id = p.id), 0) AS expense_cost
            FROM {sch}.projects p;
            """
            conn.execute(sql_project_summary)
            conn.commit()

            print(f"✅ {sch}.v_order_profit i {sch}.v_project_summary uspešno kreirani!")

        print("=== refresh_views DONE ===")
    except Exception as e:
        conn.rollback()
        print(f"⚠️  refresh_views greška: {e}")
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    refresh_views()