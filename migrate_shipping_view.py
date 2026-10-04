# migrate_shipping_view.py
"""
Zamenjuje VIEW v_order_profit novom verzijom koja uračunava shipping_cost.
SQLite ne podržava ALTER VIEW, pa radimo DROP + CREATE.
"""
from db_adapter import connect, USE_POSTGRES


def migrate():
    conn = connect()
    cur = conn.cursor()

    # 1) Obriši stari VIEW
    try:
        cur.execute("DROP VIEW IF EXISTS v_order_profit")
        conn.commit()
        print("🗑️  Stari VIEW v_order_profit obrisan")
    except Exception as e:
        print(f"⚠️  Greška pri brisanju VIEW-a: {e}")
        conn.close()
        return

    # 2) Napravi novi VIEW (sa shipping_cost raspoređenim po itemu)
    new_view = """
    CREATE VIEW v_order_profit AS
    SELECT
        o.id                AS order_id,
        o.created_at        AS order_date,
        o.status            AS status,
        c.id                AS channel_id,
        c.name              AS channel_name,
        c.fee_percent       AS fee_percent,
        p.id                AS product_id,
        p.sku               AS sku,
        p.name              AS product_name,
        p.cost              AS unit_cost,
        oi.qty              AS qty,
        oi.unit_price       AS unit_price,
        (oi.qty * oi.unit_price)                                    AS revenue,
        (oi.qty * oi.unit_price * c.fee_percent / 100.0)            AS channel_fee,
        (oi.qty * p.cost)                                           AS product_cost,
        -- Deo shipping_cost-a koji pripada ovom itemu:
        COALESCE(o.shipping_cost, 0) *
          (oi.qty * oi.unit_price) /
          NULLIF((SELECT SUM(oi2.qty * oi2.unit_price)
                  FROM order_items oi2
                  WHERE oi2.order_id = o.id), 0)                    AS shipping_cost,
        -- Profit = prihod - provizija - trošak proizvoda - dostava
        (oi.qty * oi.unit_price)
          - (oi.qty * oi.unit_price * c.fee_percent / 100.0)
          - (oi.qty * p.cost)
          - COALESCE(o.shipping_cost, 0) *
            (oi.qty * oi.unit_price) /
            NULLIF((SELECT SUM(oi2.qty * oi2.unit_price)
                    FROM order_items oi2
                    WHERE oi2.order_id = o.id), 0)                  AS profit
    FROM order_items oi
    JOIN orders   o ON o.id = oi.order_id
    JOIN products p ON p.id = oi.product_id
    JOIN channels c ON c.id = o.channel_id
    WHERE o.status != 'cancelled';
    """

    try:
        cur.execute(new_view)
        conn.commit()
        print("✅ Novi VIEW v_order_profit kreiran (sa shipping_cost)")
    except Exception as e:
        print(f"❌ Greška pri kreiranju VIEW-a: {e}")
        conn.close()
        return

    # 3) Brzi test — da vidimo da VIEW radi
    print("\n🧪 Test VIEW-a (prvih 5 redova):")
    try:
        rows = cur.execute("""
            SELECT order_id, product_name, revenue, shipping_cost, profit
            FROM v_order_profit
            LIMIT 5
        """).fetchall()
        if not rows:
            print("   (nema podataka u narudžbinama — to je OK ako baza nema test narudžbine)")
        for r in rows:
            try:
                print(f"   #{r['order_id']} {r['product_name']}: "
                      f"rev={r['revenue']:.0f} ship={r['shipping_cost']:.0f} profit={r['profit']:.0f}")
            except (TypeError, KeyError):
                print(f"   {r}")
    except Exception as e:
        print(f"   ⚠️  Test nije prošao: {e}")

    conn.close()
    print("\n🎉 VIEW migracija završena!")


if __name__ == "__main__":
    migrate()