# pricing.py
"""
Kalkulator cena za MicroStock.
Čista logika bez Flask zavisnosti — lako se testira.

Dva režima:
  - recommended_price(): kolika treba da bude cena za željenu maržu
  - analyze_price():     koliki je profit/marža za datu cenu

Terminologija:
  cost          — nabavna cena (trošak robe)
  shipping      — trošak dostave koji TI plaćaš (opciono)
  fee_pct       — provizija kanala u % (npr. Etsy 6.5%)
  tax_pct       — porez/PDV u % (opciono, npr. 20%)
  margin_pct    — ŽELJENA marža (profit / prodajna cena)
  markup_pct    — ŽELJENI markup (profit / cost)
"""


def recommended_price(cost, margin_pct, fee_pct=0, shipping=0, tax_pct=0):
    """
    Kolika treba da bude prodajna cena da bi ostvario datu maržu%s

    Formula:
        price = (cost + shipping) / (1 - fee_pct/100 - tax_pct/100 - margin_pct/100)

    Vraća dict sa breakdown-om. Ako je marža + provizija + porez >= 100%,
    baca ValueError.
    """
    cost = float(cost or 0)
    shipping = float(shipping or 0)
    fee_pct = float(fee_pct or 0)
    tax_pct = float(tax_pct or 0)
    margin_pct = float(margin_pct or 0)

    denom = 1 - (fee_pct + tax_pct + margin_pct) / 100.0
    if denom <= 0:
        raise ValueError(
            "Zbir marže, provizije i poreza mora biti manji od 100%."
        )

    price = (cost + shipping) / denom

    fee_amount = price * fee_pct / 100.0
    tax_amount = price * tax_pct / 100.0
    profit = price - cost - shipping - fee_amount - tax_amount
    real_margin = (profit / price * 100.0) if price > 0 else 0
    markup = (profit / (cost + shipping) * 100.0) if (cost + shipping) > 0 else 0

    return {
        "price": round(price, 2),
        "cost": round(cost, 2),
        "shipping": round(shipping, 2),
        "fee_pct": fee_pct,
        "fee_amount": round(fee_amount, 2),
        "tax_pct": tax_pct,
        "tax_amount": round(tax_amount, 2),
        "profit": round(profit, 2),
        "margin_pct": round(real_margin, 2),
        "markup_pct": round(markup, 2),
    }


def analyze_price(cost, price, fee_pct=0, shipping=0, tax_pct=0):
    """
    Koliki je profit/marža za datu prodajnu cenu%s
    Vraća isti dict format kao recommended_price().
    """
    cost = float(cost or 0)
    price = float(price or 0)
    shipping = float(shipping or 0)
    fee_pct = float(fee_pct or 0)
    tax_pct = float(tax_pct or 0)

    fee_amount = price * fee_pct / 100.0
    tax_amount = price * tax_pct / 100.0
    profit = price - cost - shipping - fee_amount - tax_amount
    real_margin = (profit / price * 100.0) if price > 0 else 0
    markup = (profit / (cost + shipping) * 100.0) if (cost + shipping) > 0 else 0

    return {
        "price": round(price, 2),
        "cost": round(cost, 2),
        "shipping": round(shipping, 2),
        "fee_pct": fee_pct,
        "fee_amount": round(fee_amount, 2),
        "tax_pct": tax_pct,
        "tax_amount": round(tax_amount, 2),
        "profit": round(profit, 2),
        "margin_pct": round(real_margin, 2),
        "markup_pct": round(markup, 2),
    }


def price_from_markup(cost, markup_pct, fee_pct=0, shipping=0, tax_pct=0):
    """
    Alternativa: kolika cena daje željeni MARKUP (a ne maržu)%s
    markup = profit / (cost + shipping)
    """
    cost = float(cost or 0)
    shipping = float(shipping or 0)
    fee_pct = float(fee_pct or 0)
    tax_pct = float(tax_pct or 0)
    markup_pct = float(markup_pct or 0)

    # profit = (cost+ship) * markup/100
    # price = (cost+ship+profit) / (1 - fee/100 - tax/100)
    target_profit = (cost + shipping) * markup_pct / 100.0
    denom = 1 - (fee_pct + tax_pct) / 100.0
    if denom <= 0:
        raise ValueError("Provizija + porez moraju biti < 100%.")

    price = (cost + shipping + target_profit) / denom
    return analyze_price(cost, price, fee_pct, shipping, tax_pct)

# ==================== ISTORIJA KALKULACIJA ====================

def log_calculation(user_id, product_id, product_name, mode,
                    cost, shipping, fee_pct, tax_pct, margin_pct,
                    price, profit, markup_pct, applied=False):
    """Upisuje jednu kalkulaciju u pricing_history. Vraća id."""
    from db_adapter import connect
    conn = connect()
    try:
        cur = conn.execute("""
            INSERT INTO pricing_history
            (user_id, product_id, product_name, mode,
             cost, shipping, fee_pct, tax_pct, margin_pct,
             price, profit, markup_pct, applied)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            user_id, product_id, product_name, mode,
            float(cost or 0), float(shipping or 0),
            float(fee_pct or 0), float(tax_pct or 0),
            float(margin_pct or 0),
            float(price or 0), float(profit or 0), float(markup_pct or 0),
            1 if applied else 0,
        ))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_history(limit=100, user_id=None, product_id=None):
    """Vraća poslednjih N kalkulacija, opciono filtrirano."""
    from db_adapter import connect
    conn = connect()
    try:
        sql = """
            SELECT h.*, u.name AS user_name, u.email AS user_email
            FROM pricing_history h
            LEFT JOIN users u ON u.id = h.user_id
            WHERE 1=1
        """
        params = []
        if user_id:
            sql += " AND h.user_id = %s"
            params.append(user_id)
        if product_id:
            sql += " AND h.product_id = %s"
            params.append(product_id)
        sql += " ORDER BY h.created_at DESC LIMIT %s"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            try:
                out.append(dict(r))
            except (TypeError, ValueError):
                out.append(r)
        return out
    finally:
        conn.close()


# ==================== PRESETI KANALA ====================

def list_presets():
    from db_adapter import connect
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM channel_presets ORDER BY name"
        ).fetchall()
        out = []
        for r in rows:
            try:
                out.append(dict(r))
            except (TypeError, ValueError):
                out.append(r)
        return out
    finally:
        conn.close()


def get_preset(preset_id):
    from db_adapter import connect
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM channel_presets WHERE id=%s", (preset_id,)
        ).fetchone()
        if not row:
            return None
        try:
            return dict(row)
        except (TypeError, ValueError):
            return row
    finally:
        conn.close()


def add_preset(name, fee_pct, tax_pct=0):
    from db_adapter import connect
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO channel_presets (name, fee_pct, tax_pct) VALUES (%s,%s,%s)",
            (name.strip(), float(fee_pct or 0), float(tax_pct or 0))
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_preset(preset_id, name, fee_pct, tax_pct=0):
    from db_adapter import connect
    conn = connect()
    try:
        conn.execute(
            "UPDATE channel_presets SET name=%s, fee_pct=%s, tax_pct=%s WHERE id=%s",
            (name.strip(), float(fee_pct or 0), float(tax_pct or 0), preset_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_preset(preset_id):
    from db_adapter import connect
    conn = connect()
    try:
        conn.execute("DELETE FROM channel_presets WHERE id=%s", (preset_id,))
        conn.commit()
    finally:
        conn.close()