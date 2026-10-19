# models.py
from db_adapter import connect
import json

# ==================== PROIZVODI ====================

def list_products(user_id=None, search=None, only_low=False, include_inactive=False, filter_type=None):
    sql = "SELECT * FROM products WHERE 1=1"
    params = []
    if user_id is not None:
        sql += " AND user_id = %s"
        params.append(user_id)
    if not include_inactive:
        sql += " AND active = 1"
    if filter_type == "materials":
        sql += " AND is_material = 1"
    elif filter_type == "finished":
        sql += " AND (is_material = 0 OR is_material IS NULL)"
    if search:
        sql += " AND (name ILIKE %s OR sku ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    if only_low:
        sql += " AND stock <= low_stock_at"
    sql += " ORDER BY name"
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows

def add_product(user_id, sku, name, price, cost, stock, low_stock_at=3, is_material=0, unit='kom'):
    conn = connect()
    conn.execute(
        """
        INSERT INTO products (user_id, sku, name, price, cost, stock, low_stock_at, is_material, unit)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, sku, name, price, cost, stock, low_stock_at, int(is_material), unit)
    )
    conn.commit()
    conn.close()

def update_product(pid, sku, name, price, cost, stock, low_stock_at, user_id=None):
    """Ako je user_id zadat, menja samo ako proizvod pripada tom korisniku."""
    conn = connect()
    if user_id is not None:
        conn.execute("""
            UPDATE products
               SET sku=%s, name=%s, price=%s, cost=%s, stock=%s, low_stock_at=%s
             WHERE id=%s AND user_id=%s
        """, (sku, name, price, cost, stock, low_stock_at, pid, user_id))
    else:
        conn.execute("""
            UPDATE products
               SET sku=%s, name=%s, price=%s, cost=%s, stock=%s, low_stock_at=%s
             WHERE id=%s
        """, (sku, name, price, cost, stock, low_stock_at, pid))
    conn.commit(); conn.close()

def archive_product(pid, user_id=None):
    """Soft delete - proizvod ostaje u bazi zbog istorije narudžbina."""
    conn = connect()
    if user_id is not None:
        conn.execute("UPDATE products SET active = 0 WHERE id = %s AND user_id = %s",
                     (pid, user_id))
    else:
        conn.execute("UPDATE products SET active = 0 WHERE id = %s", (pid,))
    conn.commit(); conn.close()

def get_product(pid, user_id=None):
    conn = connect()
    if user_id is not None:
        row = conn.execute("SELECT * FROM products WHERE id=%s AND user_id=%s",
                           (pid, user_id)).fetchone()
    else:
        row = conn.execute("SELECT * FROM products WHERE id=%s", (pid,)).fetchone()
    conn.close()
    return row

def low_stock_products(user_id=None):
    conn = connect()
    if user_id is not None:
        rows = conn.execute(
            "SELECT * FROM products WHERE active=1 AND user_id=%s AND stock <= low_stock_at ORDER BY stock",
            (user_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM products WHERE active=1 AND stock <= low_stock_at ORDER BY stock"
        ).fetchall()
    conn.close()
    return rows

# ==================== KANALI ====================

def list_channels():
    """Kanali su globalni (dele se preko svih korisnika)."""
    conn = connect()
    rows = conn.execute("SELECT * FROM channels ORDER BY name").fetchall()
    conn.close()
    return rows

# ==================== NARUDŽBINE ====================

def create_order_tx(conn, user_id, customer_name, channel_id, items, note="",
                    external_id=None, source="manual",
                    shipping_cost=0, shipping_method="",
                    customer_phone=""):
    """
    Isto kao create_order, ali prima POSTOJEĆU konekciju.
    Ne otvara novu, ne zatvara je. Pozivalac kontroliše transakciju.
    Koristi isključivo conn.execute() (vraća RealDictCursor).
    """

    # Duplikat (po user_id + external_id + source)
    if external_id:
        dup = conn.execute(
            "SELECT id FROM orders WHERE external_id=%s AND source=%s AND user_id=%s",
            (external_id, source, user_id)
        ).fetchone()
        if dup:
            return dup["id"], True

    cur = conn.execute("""
        INSERT INTO orders (user_id, customer_name, channel_id, note, external_id, source,
                            shipping_cost, shipping_method, customer_phone)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (user_id, customer_name, channel_id, note, external_id, source,
          float(shipping_cost or 0), (shipping_method or "").strip(),
          (customer_phone or "").strip() or None))
    row_new = cur.fetchone()
    order_id = row_new["id"] if row_new else None
    if not order_id:
        raise RuntimeError("Nisam dobio ID nove narudžbine.")

    for it in items:
        prod = conn.execute(
            "SELECT price FROM products WHERE id=%s",
            (it["product_id"],)
        ).fetchone()
        if prod is None:
            raise ValueError(f"Proizvod {it['product_id']} ne postoji")

        conn.execute("""
            INSERT INTO order_items (order_id, product_id, qty, unit_price)
            VALUES (%s,%s,%s,%s)
        """, (order_id, it["product_id"], it["qty"], prod["price"]))

        # 1. Skidanje zaliha samog gotovog proizvoda
        conn.execute(
            "UPDATE products SET stock = stock - %s WHERE id = %s",
            (it["qty"], it["product_id"])
        )

        # 2. Automatsko skidanje vezanih sirovina iz sastavnice (BOM)
        conn.execute("""
            UPDATE products p
            SET stock = p.stock - (r.qty_needed * %s)
            FROM product_recipes r
            WHERE r.parent_product_id = %s
              AND p.id = r.material_product_id
        """, (it["qty"], it["product_id"]))

    return order_id, False

def create_order(user_id, customer_name, channel_id, items, note="",
                 external_id=None, source="manual",
                 shipping_cost=0, shipping_method="",
                 customer_phone=""):
    conn = connect()
    try:
        order_id, dup = create_order_tx(
            conn, user_id, customer_name, channel_id, items, note,
            external_id, source, shipping_cost, shipping_method,
            customer_phone
        )
        conn.commit()
        return order_id, dup
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def update_order(order_id, customer_name, channel_id, note, status,
                 shipping_cost=0, shipping_method="", customer_phone="",
                 user_id=None):
    conn = connect()
    if user_id is not None:
        conn.execute("""
            UPDATE orders
               SET customer_name=%s, channel_id=%s, note=%s, status=%s,
                   shipping_cost=%s, shipping_method=%s, customer_phone=%s
             WHERE id=%s AND user_id=%s
        """, (customer_name, channel_id, note, status,
              float(shipping_cost or 0), (shipping_method or "").strip(),
              (customer_phone or "").strip() or None,
              order_id, user_id))
    else:
        conn.execute("""
            UPDATE orders
               SET customer_name=%s, channel_id=%s, note=%s, status=%s,
                   shipping_cost=%s, shipping_method=%s, customer_phone=%s
             WHERE id=%s
        """, (customer_name, channel_id, note, status,
              float(shipping_cost or 0), (shipping_method or "").strip(),
              (customer_phone or "").strip() or None,
              order_id))
    conn.commit(); conn.close()

def delete_order(order_id, user_id=None):
    """Briše narudžbinu - ručno vraća zalihe (umesto triggera)."""
    conn = connect()
    cur = conn.cursor()

    # Ako je user_id zadat — proveri da narudžbina pripada korisniku
    if user_id is not None:
        check = cur.execute("SELECT id FROM orders WHERE id=%s AND user_id=%s",
                            (order_id, user_id)).fetchone()
        if not check:
            cur.close(); conn.close()
            return False

    # Vrati zalihe za sve stavke pre brisanja
    items = cur.execute(
        "SELECT product_id, qty FROM order_items WHERE order_id=%s",
        (order_id,)
    ).fetchall()
    for it in items:
        cur.execute(
            "UPDATE products SET stock = stock + %s WHERE id = %s",
            (it["qty"], it["product_id"])
        )

    # Obriši narudžbinu (ON DELETE CASCADE briše i stavke)
    cur.execute("DELETE FROM orders WHERE id=%s", (order_id,))
    conn.commit(); conn.close()
    return True

def list_orders(user_id=None, status=None, channel_id=None, search=None):
    sql = """
        SELECT o.id, o.customer_name, o.customer_phone, o.status, o.created_at, o.source,
               o.external_id, o.shipping_cost, o.shipping_method, o.user_id,
               c.name AS channel,
               (SELECT SUM(qty*unit_price) FROM order_items WHERE order_id=o.id) AS total
        FROM orders o
        JOIN channels c ON c.id = o.channel_id
        WHERE 1=1
    """
    params = []
    if user_id is not None:
        sql += " AND o.user_id = %s"; params.append(user_id)
    if status:
        sql += " AND o.status = %s"; params.append(status)
    if channel_id:
        sql += " AND o.channel_id = %s"; params.append(channel_id)
    if search:
        sql += " AND (o.customer_name ILIKE %s OR o.external_id ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY o.id DESC"
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows

def get_order(order_id, user_id=None):
    conn = connect()
    if user_id is not None:
        order = conn.execute("""
            SELECT o.*, c.name AS channel, c.fee_percent
            FROM orders o JOIN channels c ON c.id=o.channel_id
            WHERE o.id=%s AND o.user_id=%s
        """, (order_id, user_id)).fetchone()
    else:
        order = conn.execute("""
            SELECT o.*, c.name AS channel, c.fee_percent
            FROM orders o JOIN channels c ON c.id=o.channel_id
            WHERE o.id=%s
        """, (order_id,)).fetchone()
    items = conn.execute("""
        SELECT oi.*, p.name AS product_name, p.sku
        FROM order_items oi JOIN products p ON p.id=oi.product_id
        WHERE oi.order_id=%s
    """, (order_id,)).fetchall()
    conn.close()
    return (dict(order) if order else None, items)

def set_order_status(order_id, status, user_id=None):
    conn = connect()
    if user_id is not None:
        conn.execute("UPDATE orders SET status=%s WHERE id=%s AND user_id=%s",
                     (status, order_id, user_id))
    else:
        conn.execute("UPDATE orders SET status=%s WHERE id=%s", (status, order_id))
    conn.commit(); conn.close()

def get_order_by_external_id(external_id, source=None, user_id=None):
    """
    Provera da li narudžbina već postoji (za deduplikaciju pri importu).
    Ako je `source` zadat, traži i po source-u.
    Ako je `user_id` zadat, traži samo u okviru tog korisnika.
    """
    if not external_id:
        return None

    conn = connect()
    try:
        sql = "SELECT * FROM orders WHERE external_id = %s"
        params = [str(external_id)]

        if source:
            sql += " AND source = %s"
            params.append(str(source))
        if user_id is not None:
            sql += " AND user_id = %s"
            params.append(user_id)

        row = conn.execute(sql, params).fetchone()
        return row
    finally:
        conn.close()

# ==================== SYNC LOG ====================

def log_sync(source, external_id, order_id, payload, status, message=""):
    conn = connect()
    conn.execute("""
        INSERT INTO sync_log (source, external_id, order_id, payload, status, message)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (source, external_id, order_id, json.dumps(payload, ensure_ascii=False),
          status, message))
    conn.commit(); conn.close()


def add_recipe_item(parent_product_id, material_product_id, qty_needed):
    """Dodaje ili ažurira sirovinu u recepturi gotovog proizvoda."""
    conn = connect()
    conn.execute(
        """
        INSERT INTO product_recipes (parent_product_id, material_product_id, qty_needed)
        VALUES (%s, %s, %s)
        ON CONFLICT (parent_product_id, material_product_id)
        DO UPDATE SET qty_needed = EXCLUDED.qty_needed
    """,
        (parent_product_id, material_product_id, float(qty_needed)),
    )
    conn.commit()

    # Automatski ažuriramo nabavnu cenu (cost) gotovog proizvoda na osnovu zbira sirovina
    _recalc_parent_cost(conn, parent_product_id)
    conn.close()


def remove_recipe_item(recipe_item_id, parent_product_id):
    """Uklanja sirovinu iz recepture."""
    conn = connect()
    conn.execute("DELETE FROM product_recipes WHERE id = %s", (recipe_item_id,))
    conn.commit()
    _recalc_parent_cost(conn, parent_product_id)
    conn.close()


def _recalc_parent_cost(conn, parent_product_id):
    """Pomoćna funkcija: sabira troškove sirovina i postavlja cost gotovog artikla."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(r.qty_needed * p.cost), 0) AS calculated_cost
        FROM product_recipes r
        JOIN products p ON p.id = r.material_product_id
        WHERE r.parent_product_id = %s
    """,
        (parent_product_id,),
    ).fetchone()

    new_cost = float(row["calculated_cost"] or 0)
    conn.execute(
        "UPDATE products SET cost = %s WHERE id = %s",
        (new_cost, parent_product_id),
    )
    conn.commit()


def get_recipe(parent_product_id, user_id=None):
    """Vraća listu sirovina koje čine gotov proizvod."""
    conn = connect()
    try:
        sql = """
            SELECT r.id AS recipe_item_id,
                   r.qty_needed,
                   p.id AS material_id,
                   p.sku,
                   p.name AS material_name,
                   COALESCE(p.cost, 0) AS unit_cost,
                   COALESCE(p.stock, 0) AS current_stock,
                   COALESCE(p.unit, 'kom') AS unit,
                   (r.qty_needed * COALESCE(p.cost, 0)) AS total_material_cost
            FROM product_recipes r
            JOIN products p ON p.id = r.material_product_id
            WHERE r.parent_product_id = %s
            ORDER BY p.name ASC
        """
        rows = conn.execute(sql, (parent_product_id,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["total_material_cost"] = round(float(d.get("total_material_cost") or 0), 2)
            d["unit"] = "kom"
            result.append(d)
        return result
    except Exception as e:
        print(f"Greška u get_recipe: {e}")
        return []
    finally:
        conn.close()


def list_raw_materials(user_id):
    """Vraća samo artikle koji su definisani kao repromaterijal/sirovina."""
    conn = connect()
    try:
        sql = """
            SELECT id, sku, name, COALESCE(cost, 0) AS cost, 
                   COALESCE(stock, 0) AS stock, COALESCE(unit, 'kom') AS unit
            FROM products
            WHERE user_id = %s AND active = 1 AND is_material = 1
            ORDER BY name ASC
        """
        rows = conn.execute(sql, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Greška u list_raw_materials: {e}")
        return []
    finally:
        conn.close()