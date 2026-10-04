# models.py
from db_adapter import connect
import json

# ==================== PROIZVODI ====================

def list_products(search=None, only_low=False, include_inactive=False):
    sql = "SELECT * FROM products WHERE 1=1"
    params = []
    if not include_inactive:
        sql += " AND active = 1"
    if search:
        sql += " AND (name LIKE %s OR sku LIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    if only_low:
        sql += " AND stock <= low_stock_at"
    sql += " ORDER BY name"
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows

def add_product(sku, name, price, cost, stock, low_stock_at=3):
    conn = connect()
    conn.execute(
        "INSERT INTO products (sku,name,price,cost,stock,low_stock_at) VALUES (%s,%s,%s,%s,%s,%s)",
        (sku, name, price, cost, stock, low_stock_at)
    )
    conn.commit(); conn.close()

def update_product(pid, sku, name, price, cost, stock, low_stock_at):
    conn = connect()
    conn.execute("""
        UPDATE products
           SET sku=%s, name=%s, price=%s, cost=%s, stock=%s, low_stock_at=%s
         WHERE id=%s
    """, (sku, name, price, cost, stock, low_stock_at, pid))
    conn.commit(); conn.close()

def archive_product(pid):
    """Soft delete - proizvod ostaje u bazi zbog istorije narudžbina."""
    conn = connect()
    conn.execute("UPDATE products SET active = 0 WHERE id = %s", (pid,))
    conn.commit(); conn.close()

def get_product(pid):
    conn = connect()
    row = conn.execute("SELECT * FROM products WHERE id=%s", (pid,)).fetchone()
    conn.close()
    return row

def low_stock_products():
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM products WHERE active=1 AND stock <= low_stock_at ORDER BY stock"
    ).fetchall()
    conn.close()
    return rows

# ==================== KANALI ====================

def list_channels():
    conn = connect()
    rows = conn.execute("SELECT * FROM channels ORDER BY name").fetchall()
    conn.close()
    return rows

# ==================== NARUDŽBINE ====================

def create_order(customer_name, channel_id, items, note="",
                 external_id=None, source="manual",
                 shipping_cost=0, shipping_method=""):
    conn = connect()
    cur = conn.cursor()

    # Duplikat%s
    if external_id:
        dup = cur.execute(
            "SELECT id FROM orders WHERE external_id=%s AND source=%s",
            (external_id, source)
        ).fetchone()
        if dup:
            conn.close()
            return dup["id"], True

    cur.execute("""
        INSERT INTO orders (customer_name, channel_id, note, external_id, source,
                            shipping_cost, shipping_method)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (customer_name, channel_id, note, external_id, source,
          float(shipping_cost or 0), (shipping_method or "").strip()))

    # Uzmi ID novo-kreirane narudžbine (radi i za SQLite i PostgreSQL)
    last = cur.execute("SELECT lastval() AS id").fetchone() \
        if False else None   # placeholder

    # Zapravo - koristi RETURNING (PostgreSQL) ili lastrowid (SQLite)
    # Rešavamo univerzalno:
    if hasattr(cur, "lastrowid") and cur.lastrowid:
        order_id = cur.lastrowid
    else:
        # PostgreSQL - uzmi poslednji ID iz orders
        order_id = cur.execute(
            "SELECT id FROM orders ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]

    for it in items:
        prod = cur.execute("SELECT price FROM products WHERE id=%s", (it["product_id"],)).fetchone()
        if prod is None:
            raise ValueError(f"Proizvod {it['product_id']} ne postoji")
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, qty, unit_price)
            VALUES (%s,%s,%s,%s)
        """, (order_id, it["product_id"], it["qty"], prod["price"]))

        # Umesto triggera - ručno smanji zalihu
        cur.execute("""
            UPDATE products SET stock = stock - %s WHERE id = %s
        """, (it["qty"], it["product_id"]))

    conn.commit(); conn.close()
    return order_id, False

def update_order(order_id, customer_name, channel_id, note, status,
                 shipping_cost=0, shipping_method=""):
    conn = connect()
    conn.execute("""
        UPDATE orders
           SET customer_name=%s, channel_id=%s, note=%s, status=%s,
               shipping_cost=%s, shipping_method=%s
         WHERE id=%s
    """, (customer_name, channel_id, note, status,
          float(shipping_cost or 0), (shipping_method or "").strip(),
          order_id))
    conn.commit(); conn.close()

def delete_order(order_id):
    """Briše narudžbinu - ručno vraća zalihe (umesto triggera)."""
    conn = connect()
    cur = conn.cursor()

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

def list_orders(status=None, channel_id=None, search=None):
    sql = """
        SELECT o.id, o.customer_name, o.status, o.created_at, o.source,
               o.external_id, o.shipping_cost, o.shipping_method,
               c.name AS channel,
               (SELECT SUM(qty*unit_price) FROM order_items WHERE order_id=o.id) AS total
        FROM orders o
        JOIN channels c ON c.id = o.channel_id
        WHERE 1=1
    """
    params = []
    if status:
        sql += " AND o.status = %s"; params.append(status)
    if channel_id:
        sql += " AND o.channel_id = %s"; params.append(channel_id)
    if search:
        sql += " AND (o.customer_name LIKE %s OR o.external_id LIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY o.id DESC"
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows

def get_order(order_id):
    conn = connect()
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

def set_order_status(order_id, status):
    conn = connect()
    conn.execute("UPDATE orders SET status=%s WHERE id=%s", (status, order_id))
    conn.commit(); conn.close()

def get_order_by_external_id(external_id, source=None):
    """
    Provera da li narudžbina već postoji (za deduplikaciju pri importu).
    Ako je `source` zadat, traži i po source-u.
    """
    if not external_id:
        return None

    conn = connect()
    try:
        if source:
            row = conn.execute(
                "SELECT * FROM orders WHERE external_id = %s AND source = %s",
                (str(external_id), str(source))
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM orders WHERE external_id = %s",
                (str(external_id),)
            ).fetchone()
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

    # importers.py
"""
CSV import iz raznih platformi.
Podržava: Etsy, Gumroad, Payhip, Shopify, TikTok Shop, Instagram, generički CSV.
"""
import csv
import io
import json
from datetime import datetime

from db_adapter import connect


# ==================== PRESETI ====================

# Svaki preset: mapiranje naših polja → moguća imena kolona u CSV-u
# (prvo nađeno se koristi)
PRESETS = {
    "etsy": {
        "label": "Etsy (Orders.csv)",
        "customer_name": ["Buyer Name", "Buyer", "Ship Name"],
        "external_id":   ["Order ID", "Order Number"],
        "order_date":    ["Order Date", "Sale Date", "Date"],
        "status":        ["Status", "Order Status"],
        "channel":       "Etsy",
        "items": {
            "sku":        ["SKU", "Product SKU"],
            "name":       ["Item Name", "Product Name", "Title"],
            "qty":        ["Quantity", "Qty"],
            "unit_price": ["Price", "Item Price", "Unit Price"],
        },
        "note":          ["Note from Buyer", "Notes", "Message"],
    },
    "gumroad": {
        "label": "Gumroad (Sales.csv)",
        "customer_name": ["Buyer Email", "Email", "Customer"],
        "external_id":   ["Order Number", "ID", "Sale ID"],
        "order_date":    ["Created", "Date", "Purchase Date"],
        "status":        ["Status", "State"],
        "channel":       "Gumroad",
        "items": {
            "sku":        ["Product ID", "SKU", "Permalink"],
            "name":       ["Product Name", "Product"],
            "qty":        ["Quantity", "Qty"],
            "unit_price": ["Price", "Amount", "Total"],
        },
        "note":          ["Notes", "Note"],
    },
    "payhip": {
        "label": "Payhip (Sales.csv)",
        "customer_name": ["Customer Email", "Buyer Email", "Name"],
        "external_id":   ["Order ID", "Transaction ID", "ID"],
        "order_date":    ["Date", "Created"],
        "status":        ["Status", "Payment Status"],
        "channel":       "Payhip",
        "items": {
            "sku":        ["Product ID", "SKU"],
            "name":       ["Product Name", "Item"],
            "qty":        ["Quantity", "Qty"],
            "unit_price": ["Price", "Amount"],
        },
        "note":          ["Notes"],
    },
    "shopify": {
        "label": "Shopify (orders_export.csv)",
        "customer_name": ["Billing Name", "Customer", "Shipping Name"],
        "external_id":   ["Name", "Order ID", "Id"],
        "order_date":    ["Created at", "Paid at", "Date"],
        "status":        ["Financial Status", "Fulfillment Status"],
        "channel":       "Shopify",
        "items": {
            "sku":        ["Lineitem sku", "SKU"],
            "name":       ["Lineitem name", "Product"],
            "qty":        ["Lineitem quantity", "Qty"],
            "unit_price": ["Lineitem price", "Price"],
        },
        "note":          ["Notes", "Note"],
    },
    "tiktok": {
        "label": "TikTok Shop (OrderSKUList.csv)",
        "customer_name": ["Buyer Username", "Customer Name", "Recipient"],
        "external_id":   ["Order ID", "Order Number"],
        "order_date":    ["Created Time", "Order Time", "Paid Time"],
        "status":        ["Order Status", "Status"],
        "channel":       "TikTok",
        "items": {
            "sku":        ["Seller SKU", "SKU"],
            "name":       ["Product Name", "Item Name"],
            "qty":        ["Quantity", "Qty"],
            "unit_price": ["SKU Unit Original Price", "Unit Price", "Price"],
        },
        "note":          ["Buyer Message", "Notes"],
    },
    "instagram": {
        "label": "Instagram / Meta (generic)",
        "customer_name": ["Customer", "Buyer", "Name", "Full Name"],
        "external_id":   ["Order ID", "ID", "Reference"],
        "order_date":    ["Date", "Created", "Order Date"],
        "status":        ["Status"],
        "channel":       "Instagram",
        "items": {
            "sku":        ["SKU"],
            "name":       ["Product", "Item", "Product Name"],
            "qty":        ["Qty", "Quantity"],
            "unit_price": ["Price", "Unit Price"],
        },
        "note":          ["Note", "Notes"],
    },
    "generic": {
        "label": "Generički CSV (ručno mapiranje)",
        "customer_name": ["customer", "customer_name", "buyer", "name"],
        "external_id":   ["external_id", "order_id", "id"],
        "order_date":    ["date", "order_date", "created_at"],
        "status":        ["status"],
        "channel":       None,   # korisnik unosi
        "items": {
            "sku":        ["sku"],
            "name":       ["product", "product_name", "item", "name"],
            "qty":        ["qty", "quantity"],
            "unit_price": ["price", "unit_price", "amount"],
        },
        "note":          ["note", "notes"],
    },
}


# ==================== PARSIRANJE ====================

def detect_delimiter(sample: str) -> str:
    """Detektuje , ili ; ili \\t."""
    for d in [",", ";", "\t"]:
        if sample.count(d) > sample.count(","):
            return d
    return ","


def read_csv(file_bytes: bytes, delimiter=None):
    """
    Vraća (fieldnames, rows) — lista dict-ova.
    Probava utf-8, pa utf-8-sig, pa cp1250 (Windows).
    """
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Ne mogu da dekodiram CSV ni u jednoj poznatoj enkodaciji.")

    if delimiter is None:
        delimiter = detect_delimiter(text[:1000])

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return reader.fieldnames or [], list(reader)


def find_column(fieldnames, candidates):
    """Vraća prvo ime kolone iz `candidates` koje postoji u fieldnames (case-insensitive)."""
    if not candidates:
        return None
    if isinstance(candidates, str):
        candidates = [candidates]
    lower_map = {f.lower().strip(): f for f in fieldnames}
    for c in candidates:
        key = c.lower().strip()
        if key in lower_map:
            return lower_map[key]
    return None


def build_mapping(preset_key, fieldnames, overrides=None):
    """
    Vraća dict sa tačnim imenima kolona iz CSV-a za dati preset.
    overrides: dict {nase_polje: ime_kolone_u_csv} — ručno mapiranje
    """
    preset = PRESETS.get(preset_key, PRESETS["generic"])
    mapping = {}

    def pick(field):
        if overrides and field in overrides and overrides[field]:
            return overrides[field]
        return find_column(fieldnames, preset.get(field))

    # Top-level polja
    mapping["customer_name"] = pick("customer_name")
    mapping["external_id"]   = pick("external_id")
    mapping["order_date"]    = pick("order_date")
    mapping["status"]        = pick("status")
    mapping["note"]          = pick("note")

    # Items (podkolone)
    items_map = {}
    for sub in ("sku", "name", "qty", "unit_price"):
        items_map[sub] = pick(f"items.{sub}") if overrides and f"items.{sub}" in overrides \
                         else find_column(fieldnames, preset["items"].get(sub))
    mapping["items"] = items_map

    mapping["channel"] = preset.get("channel")
    return mapping


# ==================== VALIDACIJA ====================

def validate_mapping(mapping):
    """Vraća listu grešaka."""
    errors = []
    if not mapping.get("customer_name"):
        errors.append("Nedostaje mapiranje za: customer_name")
    if not mapping["items"].get("qty"):
        errors.append("Nedostaje mapiranje za: items.qty (količina)")
    if not mapping["items"].get("unit_price"):
        errors.append("Nedostaje mapiranje za: items.unit_price (cena)")
    if not (mapping["items"].get("sku") or mapping["items"].get("name")):
        errors.append("Treba bar jedno: items.sku ili items.name")
    return errors


# ==================== IMPORT ====================

def import_rows(rows, mapping, channel_id, source_name,
                auto_create_products=True, user_id=None,
                filename=""):
    """
    Uvozi redove. Vraća dict sa rezultatima.
    Svaki red = jedna narudžbina sa jednom stavkom.
    (Ako platforma ima multi-item CSV, grupišemo po external_id.)
    """
    from models import create_order, get_order_by_external_id

    # Grupisanje po external_id (jer CSV može imati 1 red = 1 stavka)
    grouped = {}
    ungrouped = []
    for i, row in enumerate(rows):
        ext = _get(row, mapping.get("external_id"))
        if ext:
            grouped.setdefault(str(ext).strip(), []).append((i, row))
        else:
            ungrouped.append((i, row))

    results = {
        "imported": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "created_orders": [],
        "created_products": [],
    }

    conn = connect()

    # 1) Grupisane
    for ext_id, group in grouped.items():
        try:
            _import_group(conn, ext_id, group, mapping, channel_id, source_name,
                          auto_create_products, results)
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"external_id={ext_id}: {e}")

    # 2) Negrupisane (bez external_id) — svaki red zasebno
    for i, row in ungrouped:
        try:
            _import_group(conn, None, [(i, row)], mapping, channel_id, source_name,
                          auto_create_products, results)
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"red {i+2}: {e}")

    # Log
    conn.execute("""
        INSERT INTO import_logs
        (user_id, source, filename, rows_total, rows_imported,
         rows_skipped, rows_failed, errors)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (user_id, source_name, filename, len(rows),
          results["imported"], results["skipped"], results["failed"],
          json.dumps(results["errors"][:50], ensure_ascii=False)))
    conn.commit()
    conn.close()

    return results


def _import_group(conn, ext_id, group, mapping, channel_id, source_name,
                  auto_create_products, results):
    """Uvozi jednu narudžbinu (može imati više stavki)."""
    from models import create_order, get_order_by_external_id

    # Duplikat%s
    if ext_id:
        existing = get_order_by_external_id(ext_id, source_name)
        if existing:
            results["skipped"] += 1
            return

    first_row = group[0][1]
    customer = _get(first_row, mapping.get("customer_name")) or "Nepoznat kupac"
    note = _get(first_row, mapping.get("note")) or ""

    items = []
    for _, row in group:
        item = _build_item(conn, row, mapping, auto_create_products, results)
        if item:
            items.append(item)

    if not items:
        results["skipped"] += 1
        return

    order_id, dup = create_order(
        customer_name=str(customer).strip(),
        channel_id=channel_id,
        items=items,
        note=str(note).strip(),
        external_id=ext_id,
        source=source_name,
    )
    if dup:
        results["skipped"] += 1
    else:
        results["imported"] += 1
        results["created_orders"].append(order_id)


def _build_item(conn, row, mapping, auto_create_products, results):
    """Vraća {product_id, qty} ili None."""
    sku = _get(row, mapping["items"].get("sku"))
    name = _get(row, mapping["items"].get("name"))
    qty_raw = _get(row, mapping["items"].get("qty"))
    price_raw = _get(row, mapping["items"].get("unit_price"))

    if not qty_raw:
        return None
    try:
        qty = int(float(str(qty_raw).replace(",", ".")))
    except (ValueError, TypeError):
        return None
    if qty <= 0:
        return None

    price = None
    if price_raw not in (None, ""):
        try:
            price = float(str(price_raw).replace(",", ".").replace("€", "").replace("$", "").strip())
        except (ValueError, TypeError):
            price = None

    # Nađi proizvod po SKU, pa po imenu
    product_id = None
    if sku:
        row_db = conn.execute("SELECT id FROM products WHERE sku=%s", (str(sku).strip(),)).fetchone()
        if row_db:
            product_id = row_db["id"]
    if not product_id and name:
        row_db = conn.execute("SELECT id FROM products WHERE name=%s", (str(name).strip(),)).fetchone()
        if row_db:
            product_id = row_db["id"]

    # Ako nema — kreiraj
    if not product_id and auto_create_products:
        new_sku = str(sku).strip() if sku else f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        new_name = str(name).strip() if name else f"Proizvod {new_sku}"
        cur = conn.execute("""
            INSERT INTO products (sku, name, price, cost, stock, low_stock_at)
            VALUES (%s, %s, %s, 0, 0, 3)
        """, (new_sku, new_name, price or 0))
        conn.commit()
        product_id = cur.lastrowid
        results["created_products"].append(new_sku)

    if not product_id:
        return None

    return {"product_id": product_id, "qty": qty}


def _get(row, key):
    """Bezbedno čitanje iz dict-a, case-insensitive fallback."""
    if not key:
        return None
    if key in row:
        return row[key]
    key_l = key.lower().strip()
    for k, v in row.items():
        if k and k.lower().strip() == key_l:
            return v
    return None