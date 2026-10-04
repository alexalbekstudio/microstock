# analytics.py (PostgreSQL verzija - 2026-10-04)
from db_adapter import connect


def overview(days=None):
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
        sql += " WHERE order_date >= now() - (%s || ' days')::interval"
        params.append(str(days))

    conn = connect()
    row = conn.execute(sql, params).fetchone()
    conn.close()

    revenue = row["revenue"] or 0
    margin = (row["profit"] / revenue * 100) if revenue > 0 else 0
    return {
        "revenue":  round(float(revenue), 2),
        "fees":     round(float(row["fees"]), 2),
        "cost":     round(float(row["cost"]), 2),
        "shipping": round(float(row["shipping"]), 2),
        "profit":   round(float(row["profit"]), 2),
        "margin":   round(margin, 1),
        "orders":   row["orders"],
        "units":    row["units"],
    }


def by_channel(days=None):
    sql = """
        SELECT
            channel_id, channel_name, fee_percent,
            SUM(revenue) AS revenue, SUM(channel_fee) AS fees,
            SUM(product_cost) AS cost, SUM(shipping_cost) AS shipping,
            SUM(profit) AS profit, SUM(qty) AS units,
            COUNT(DISTINCT order_id) AS orders
        FROM v_order_profit
    """
    params = []
    if days:
        sql += " WHERE order_date >= now() - (%s || ' days')::interval"
        params.append(str(days))
    sql += " GROUP BY channel_id, channel_name, fee_percent ORDER BY profit DESC"

    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        rev = float(r["revenue"] or 0)
        margin = (float(r["profit"] or 0) / rev * 100) if rev > 0 else 0
        result.append({
            "channel_id":   r["channel_id"],
            "channel_name": r["channel_name"],
            "fee_percent":  float(r["fee_percent"] or 0),
            "revenue":      round(rev, 2),
            "fees":         round(float(r["fees"] or 0), 2),
            "cost":         round(float(r["cost"] or 0), 2),
            "shipping":     round(float(r["shipping"] or 0), 2),
            "profit":       round(float(r["profit"] or 0), 2),
            "margin":       round(margin, 1),
            "units":        r["units"],
            "orders":       r["orders"],
        })
    return result


def by_product(days=None, limit=20):
    sql = """
        SELECT product_id, sku, product_name,
            SUM(qty) AS units, SUM(revenue) AS revenue,
            SUM(channel_fee) AS fees, SUM(product_cost) AS cost,
            SUM(shipping_cost) AS shipping, SUM(profit) AS profit
        FROM v_order_profit
    """
    params = []
    if days:
        sql += " WHERE order_date >= now() - (%s || ' days')::interval"
        params.append(str(days))
    sql += " GROUP BY product_id, sku, product_name ORDER BY profit DESC LIMIT %s"
    params.append(limit)

    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        rev = float(r["revenue"] or 0)
        margin = (float(r["profit"] or 0) / rev * 100) if rev > 0 else 0
        result.append({
            "product_id":   r["product_id"],
            "sku":          r["sku"],
            "product_name": r["product_name"],
            "units":        r["units"],
            "revenue":      round(rev, 2),
            "fees":         round(float(r["fees"] or 0), 2),
            "cost":         round(float(r["cost"] or 0), 2),
            "shipping":     round(float(r["shipping"] or 0), 2),
            "profit":       round(float(r["profit"] or 0), 2),
            "margin":       round(margin, 1),
        })
    return result


def trend(days=30):
    conn = connect()
    rows = conn.execute("""
        SELECT
            order_date::date AS day,
            SUM(revenue) AS revenue,
            SUM(profit)  AS profit
        FROM v_order_profit
        WHERE order_date >= now() - (%s || ' days')::interval
        GROUP BY order_date::date
        ORDER BY day
    """, (str(days),)).fetchall()
    conn.close()
    return [{
        "day":     str(r["day"]),
        "revenue": round(float(r["revenue"] or 0), 2),
        "profit":  round(float(r["profit"] or 0), 2),
    } for r in rows]


def loss_makers(days=None):
    sql = """
        SELECT product_id, sku, product_name,
            SUM(qty) AS units, SUM(revenue) AS revenue, SUM(profit) AS profit
        FROM v_order_profit
    """
    params = []
    if days:
        sql += " WHERE order_date >= now() - (%s || ' days')::interval"
        params.append(str(days))
    sql += " GROUP BY product_id, sku, product_name HAVING SUM(profit) < 0 ORDER BY profit ASC"

    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{
        "product_id":   r["product_id"],
        "sku":          r["sku"],
        "product_name": r["product_name"],
        "units":        r["units"],
        "revenue":      round(float(r["revenue"] or 0), 2),
        "profit":       round(float(r["profit"] or 0), 2),
    } for r in rows]


def top_customers(days=None, limit=10):
    sql = """
        SELECT o.customer_name,
            COUNT(DISTINCT o.id) AS orders,
            SUM(oi.qty * oi.unit_price) AS revenue
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE o.status != 'cancelled'
    """
    params = []
    if days:
        sql += " AND o.created_at >= now() - (%s || ' days')::interval"
        params.append(str(days))
    sql += " GROUP BY o.customer_name ORDER BY revenue DESC LIMIT %s"
    params.append(limit)

    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{
        "customer_name": r["customer_name"],
        "orders":        r["orders"],
        "revenue":       round(float(r["revenue"] or 0), 2),
    } for r in rows]