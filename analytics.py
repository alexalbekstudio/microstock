# analytics.py
"""
Analitika za Alat #2 - višekanalna prodaja i profit.
Svi upiti se oslanjaju na VIEW v_order_profit.
Verzija: sa shipping_cost (2026-10-03)
"""
from db_adapter import connect


# ==================== PREGLED (KPI) ====================

def overview(days=None):
    """Ukupni KPI: prihod, trošak, provizije, dostava, profit, marža."""
    sql = """
        SELECT
            COALESCE(SUM(revenue), 0)       AS revenue,
            COALESCE(SUM(channel_fee), 0)   AS fees,
            COALESCE(SUM(product_cost), 0)  AS cost,
            COALESCE(SUM(shipping_cost), 0) AS shipping,
            COALESCE(SUM(profit), 0)        AS profit,
            COUNT(DISTINCT order_id)        AS orders,
            COALESCE(SUM(qty), 0)           AS units
        FROM v_order_profit
    """
    params = []
    if days:
        sql += " WHERE order_date >= date('now', ?)"
        params.append(f"-{days} days")

    conn = connect()
    row = conn.execute(sql, params).fetchone()
    conn.close()

    revenue = row["revenue"] or 0
    margin = (row["profit"] / revenue * 100) if revenue > 0 else 0

    return {
        "revenue":  round(revenue, 2),
        "fees":     round(row["fees"], 2),
        "cost":     round(row["cost"], 2),
        "shipping": round(row["shipping"], 2),
        "profit":   round(row["profit"], 2),
        "margin":   round(margin, 1),
        "orders":   row["orders"],
        "units":    row["units"],
    }


# ==================== PO KANALU ====================

def by_channel(days=None):
    """Prihod, provizija, trošak, dostava i profit po kanalu prodaje."""
    sql = """
        SELECT
            channel_id,
            channel_name,
            fee_percent,
            SUM(revenue)       AS revenue,
            SUM(channel_fee)   AS fees,
            SUM(product_cost)  AS cost,
            SUM(shipping_cost) AS shipping,
            SUM(profit)        AS profit,
            SUM(qty)           AS units,
            COUNT(DISTINCT order_id) AS orders
        FROM v_order_profit
    """
    params = []
    if days:
        sql += " WHERE order_date >= date('now', ?)"
        params.append(f"-{days} days")
    sql += " GROUP BY channel_id ORDER BY profit DESC"

    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        rev = r["revenue"] or 0
        margin = (r["profit"] / rev * 100) if rev > 0 else 0
        result.append({
            "channel_id":   r["channel_id"],
            "channel_name": r["channel_name"],
            "fee_percent":  r["fee_percent"],
            "revenue":      round(rev, 2),
            "fees":         round(r["fees"] or 0, 2),
            "cost":         round(r["cost"] or 0, 2),
            "shipping":     round(r["shipping"] or 0, 2),
            "profit":       round(r["profit"] or 0, 2),
            "margin":       round(margin, 1),
            "units":        r["units"],
            "orders":       r["orders"],
        })
    return result


# ==================== PO PROIZVODU ====================

def by_product(days=None, limit=20):
    """Profit po proizvodu - koji se najviše isplati, a koji gubi novac."""
    sql = """
        SELECT
            product_id,
            sku,
            product_name,
            SUM(qty)           AS units,
            SUM(revenue)       AS revenue,
            SUM(channel_fee)   AS fees,
            SUM(product_cost)  AS cost,
            SUM(shipping_cost) AS shipping,
            SUM(profit)        AS profit
        FROM v_order_profit
    """
    params = []
    if days:
        sql += " WHERE order_date >= date('now', ?)"
        params.append(f"-{days} days")
    sql += " GROUP BY product_id ORDER BY profit DESC LIMIT ?"
    params.append(limit)

    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        rev = r["revenue"] or 0
        margin = (r["profit"] / rev * 100) if rev > 0 else 0
        result.append({
            "product_id":   r["product_id"],
            "sku":          r["sku"],
            "product_name": r["product_name"],
            "units":        r["units"],
            "revenue":      round(rev, 2),
            "fees":         round(r["fees"] or 0, 2),
            "cost":         round(r["cost"] or 0, 2),
            "shipping":     round(r["shipping"] or 0, 2),
            "profit":       round(r["profit"] or 0, 2),
            "margin":       round(margin, 1),
        })
    return result


# ==================== TREND KROZ VREME ====================

def trend(days=30):
    """Dnevni prihod i profit za poslednjih N dana."""
    conn = connect()
    rows = conn.execute("""
        SELECT
            date(order_date) AS day,
            SUM(revenue)     AS revenue,
            SUM(profit)      AS profit
        FROM v_order_profit
        WHERE order_date >= date('now', ?)
        GROUP BY day
        ORDER BY day
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return [{
        "day":     r["day"],
        "revenue": round(r["revenue"] or 0, 2),
        "profit":  round(r["profit"] or 0, 2),
    } for r in rows]


# ==================== GUBITAŠI ====================

def loss_makers(days=None):
    """Proizvodi koji imaju negativan profit (prodaju se ispod cene koštanja)."""
    sql = """
        SELECT
            product_id, sku, product_name,
            SUM(qty)     AS units,
            SUM(revenue) AS revenue,
            SUM(profit)  AS profit
        FROM v_order_profit
    """
    params = []
    if days:
        sql += " WHERE order_date >= date('now', ?)"
        params.append(f"-{days} days")
    sql += " GROUP BY product_id HAVING SUM(profit) < 0 ORDER BY profit ASC"

    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{
        "product_id":   r["product_id"],
        "sku":          r["sku"],
        "product_name": r["product_name"],
        "units":        r["units"],
        "revenue":      round(r["revenue"] or 0, 2),
        "profit":       round(r["profit"] or 0, 2),
    } for r in rows]


# ==================== TOP KUPCI ====================

def top_customers(days=None, limit=10):
    """Kupci sa najvećim prihodom."""
    sql = """
        SELECT
            o.customer_name,
            COUNT(DISTINCT o.id) AS orders,
            SUM(oi.qty * oi.unit_price) AS revenue
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE o.status != 'cancelled'
    """
    params = []
    if days:
        sql += " AND o.created_at >= date('now', ?)"
        params.append(f"-{days} days")
    sql += " GROUP BY o.customer_name ORDER BY revenue DESC LIMIT ?"
    params.append(limit)

    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{
        "customer_name": r["customer_name"],
        "orders":        r["orders"],
        "revenue":       round(r["revenue"] or 0, 2),
    } for r in rows]