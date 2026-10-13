# purchases.py
"""
Računi nabavke — CRUD operacije (multi-tenant).
"""
from db_adapter import connect


# ==================== LISTE ====================

def list_invoices(user_id=None, search=None, status=None, supplier_id=None):
    """Vraća listu računa sa imenom dobavljača."""
    sql = """
        SELECT pi.*, s.name AS supplier_name
        FROM purchase_invoices pi
        LEFT JOIN suppliers s ON s.id = pi.supplier_id
        WHERE 1=1
    """
    params = []

    if user_id is not None:
        sql += " AND pi.user_id = %s"
        params.append(user_id)

    if search:
        sql += " AND (pi.invoice_number ILIKE %s OR s.name ILIKE %s OR pi.notes ILIKE %s)"
        like = f"%{search}%"
        params += [like, like, like]

    if status:
        sql += " AND pi.status = %s"
        params.append(status)

    if supplier_id:
        sql += " AND pi.supplier_id = %s"
        params.append(supplier_id)

    sql += " ORDER BY pi.invoice_date DESC NULLS LAST, pi.id DESC"

    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return rows


def get_invoice(iid, user_id=None):
    """Vraća jedan račun sa dobavljačem."""
    conn = connect()
    try:
        if user_id is not None:
            row = conn.execute("""
                SELECT pi.*, s.name AS supplier_name
                FROM purchase_invoices pi
                LEFT JOIN suppliers s ON s.id = pi.supplier_id
                WHERE pi.id = %s AND pi.user_id = %s
            """, (iid, user_id)).fetchone()
        else:
            row = conn.execute("""
                SELECT pi.*, s.name AS supplier_name
                FROM purchase_invoices pi
                LEFT JOIN suppliers s ON s.id = pi.supplier_id
                WHERE pi.id = %s
            """, (iid,)).fetchone()
    finally:
        conn.close()
    return row


def list_items(iid):
    """Vraća stavke računa."""
    conn = connect()
    try:
        rows = conn.execute("""
            SELECT pii.*, p.sku, p.name AS product_name
            FROM purchase_items pii
            LEFT JOIN products p ON p.id = pii.product_id
            WHERE pii.purchase_invoice_id = %s
            ORDER BY pii.id
        """, (iid,)).fetchall()
    finally:
        conn.close()
    return rows


# ==================== CRUD ====================

def add_invoice(user_id, supplier_id, invoice_number, invoice_date, due_date,
                amount, currency="RSD", status="pending",
                file_data=None, file_name=None, file_mime=None, notes=""):
    """Dodaje novi račun. Vraća ID."""
    conn = connect()
    try:
        cur = conn.execute("""
            INSERT INTO purchase_invoices
                (user_id, supplier_id, invoice_number, invoice_date, due_date,
                 amount, currency, status,
                 file_data, file_name, file_mime, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, supplier_id, invoice_number, invoice_date, due_date,
              amount, currency, status,
              file_data, file_name, file_mime, notes))
        row = cur.fetchone()
        conn.commit()
        return row["id"] if row else None
    finally:
        conn.close()


def update_invoice(iid, supplier_id, invoice_number, invoice_date, due_date,
                   amount, currency, status, notes="", user_id=None):
    """Menja račun (osim fajla)."""
    conn = connect()
    try:
        if user_id is not None:
            conn.execute("""
                UPDATE purchase_invoices SET
                    supplier_id=%s, invoice_number=%s, invoice_date=%s, due_date=%s,
                    amount=%s, currency=%s, status=%s, notes=%s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s AND user_id=%s
            """, (supplier_id, invoice_number, invoice_date, due_date,
                  amount, currency, status, notes, iid, user_id))
        else:
            conn.execute("""
                UPDATE purchase_invoices SET
                    supplier_id=%s, invoice_number=%s, invoice_date=%s, due_date=%s,
                    amount=%s, currency=%s, status=%s, notes=%s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """, (supplier_id, invoice_number, invoice_date, due_date,
                  amount, currency, status, notes, iid))
        conn.commit()
    finally:
        conn.close()


def set_status(iid, status, paid_date=None, user_id=None):
    """Menja status računa. Ako je 'paid', postavlja paid_date."""
    conn = connect()
    try:
        if user_id is not None:
            if status == "paid" and paid_date:
                conn.execute("""
                    UPDATE purchase_invoices SET
                        status=%s, paid_date=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s AND user_id=%s
                """, (status, paid_date, iid, user_id))
            else:
                conn.execute("""
                    UPDATE purchase_invoices SET
                        status=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s AND user_id=%s
                """, (status, iid, user_id))
        else:
            if status == "paid" and paid_date:
                conn.execute("""
                    UPDATE purchase_invoices SET
                        status=%s, paid_date=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (status, paid_date, iid))
            else:
                conn.execute("""
                    UPDATE purchase_invoices SET
                        status=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (status, iid))
        conn.commit()
    finally:
        conn.close()


def delete_invoice(iid, user_id=None):
    """Briše račun (i stavke kroz CASCADE)."""
    conn = connect()
    try:
        if user_id is not None:
            conn.execute("DELETE FROM purchase_invoices WHERE id=%s AND user_id=%s",
                         (iid, user_id))
        else:
            conn.execute("DELETE FROM purchase_invoices WHERE id=%s", (iid,))
        conn.commit()
    finally:
        conn.close()


# ==================== STAVKE ====================

def add_item(iid, product_id, description, qty, unit_cost):
    """Dodaje stavku računa. Vraća ID."""
    total = float(qty) * float(unit_cost)
    conn = connect()
    try:
        cur = conn.execute("""
            INSERT INTO purchase_items
                (purchase_invoice_id, product_id, description, qty, unit_cost, total)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (iid, product_id, description, qty, unit_cost, total))
        row = cur.fetchone()
        conn.commit()
        return row["id"] if row else None
    finally:
        conn.close()


def delete_item(item_id):
    """Briše stavku."""
    conn = connect()
    try:
        conn.execute("DELETE FROM purchase_items WHERE id=%s", (item_id,))
        conn.commit()
    finally:
        conn.close()


def recalc_amount(iid):
    """Preračuna ukupan iznos računa iz stavki."""
    conn = connect()
    try:
        row = conn.execute("""
            SELECT COALESCE(SUM(total), 0) AS s
            FROM purchase_items
            WHERE purchase_invoice_id = %s
        """, (iid,)).fetchone()
        total = float(row["s"]) if row else 0.0

        conn.execute("""
            UPDATE purchase_invoices SET
                amount=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (total, iid))
        conn.commit()
        return total
    finally:
        conn.close()


# ==================== HELPERS ====================

def get_file(iid, user_id=None):
    """Vraća (file_data, file_name, file_mime) ili None."""
    conn = connect()
    try:
        if user_id is not None:
            row = conn.execute("""
                SELECT file_data, file_name, file_mime
                FROM purchase_invoices WHERE id=%s AND user_id=%s
            """, (iid, user_id)).fetchone()
        else:
            row = conn.execute("""
                SELECT file_data, file_name, file_mime
                FROM purchase_invoices WHERE id=%s
            """, (iid,)).fetchone()
    finally:
        conn.close()
    return row


def statuses_count(user_id=None):
    """Brojevi po statusu — za KPI."""
    conn = connect()
    try:
        if user_id is not None:
            rows = conn.execute("""
                SELECT status, COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total
                FROM purchase_invoices
                WHERE user_id = %s
                GROUP BY status
            """, (user_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT status, COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total
                FROM purchase_invoices
                GROUP BY status
            """).fetchall()
    finally:
        conn.close()

    result = {"pending": {"n": 0, "total": 0.0},
              "paid": {"n": 0, "total": 0.0},
              "overdue": {"n": 0, "total": 0.0},
              "cancelled": {"n": 0, "total": 0.0},
              "partial": {"n": 0, "total": 0.0}}
    for r in rows:
        s = r["status"]
        if s in result:
            result[s]["n"] = int(r["n"])
            result[s]["total"] = float(r["total"])
    return result


def recalc_product_costs(product_ids=None, user_id=None):
    """
    Preračuna prosečnu nabavnu cenu za proizvode iz plaćenih računa.
    """
    conn = connect()
    try:
        where = "WHERE pi.status IN ('paid', 'partial') AND pii.product_id IS NOT NULL"
        params = []

        if user_id is not None:
            where += " AND pi.user_id = %s"
            params.append(user_id)

        if product_ids:
            placeholders = ",".join(["%s"] * len(product_ids))
            where += f" AND pii.product_id IN ({placeholders})"
            params.extend(product_ids)

        rows = conn.execute(f"""
            SELECT
                pii.product_id,
                SUM(pii.qty * pii.unit_cost) / NULLIF(SUM(pii.qty), 0) AS avg_cost
            FROM purchase_items pii
            JOIN purchase_invoices pi ON pi.id = pii.purchase_invoice_id
            {where}
            GROUP BY pii.product_id
        """, tuple(params)).fetchall()

        updated = 0
        for r in rows:
            if r["avg_cost"] is None:
                continue
            conn.execute(
                "UPDATE products SET cost=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (float(r["avg_cost"]), r["product_id"])
            )
            updated += 1

        conn.commit()
        return updated
    finally:
        conn.close()


def report_by_supplier(user_id=None, date_from=None, date_to=None):
    """Ukupno plaćeno po dobavljaču."""
    sql = """
        SELECT
            s.id AS supplier_id,
            s.name AS supplier_name,
            COUNT(pi.id) AS invoice_count,
            COALESCE(SUM(pi.amount), 0) AS total_amount,
            COALESCE(SUM(CASE WHEN pi.status = 'paid' THEN pi.amount ELSE 0 END), 0) AS paid_amount,
            COALESCE(SUM(CASE WHEN pi.status IN ('pending', 'overdue', 'partial') THEN pi.amount ELSE 0 END), 0) AS unpaid_amount
        FROM suppliers s
        LEFT JOIN purchase_invoices pi ON pi.supplier_id = s.id
        WHERE 1=1
    """
    params = []
    if user_id is not None:
        sql += " AND s.user_id = %s"
        params.append(user_id)
    if date_from:
        sql += " AND (pi.invoice_date IS NULL OR pi.invoice_date >= %s)"
        params.append(date_from)
    if date_to:
        sql += " AND (pi.invoice_date IS NULL OR pi.invoice_date <= %s)"
        params.append(date_to)

    sql += " GROUP BY s.id, s.name ORDER BY total_amount DESC"

    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return rows


def report_by_month(months=12, user_id=None):
    """Ukupno plaćeno po mesecu (poslednjih N meseci)."""
    conn = connect()
    try:
        if user_id is not None:
            rows = conn.execute("""
                SELECT
                    TO_CHAR(invoice_date, 'YYYY-MM') AS month,
                    COUNT(*) AS invoice_count,
                    COALESCE(SUM(amount), 0) AS total_amount,
                    COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS paid_amount
                FROM purchase_invoices
                WHERE invoice_date IS NOT NULL
                  AND invoice_date >= CURRENT_DATE - (%s || ' months')::interval
                  AND user_id = %s
                GROUP BY TO_CHAR(invoice_date, 'YYYY-MM')
                ORDER BY month DESC
            """, (str(months), user_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT
                    TO_CHAR(invoice_date, 'YYYY-MM') AS month,
                    COUNT(*) AS invoice_count,
                    COALESCE(SUM(amount), 0) AS total_amount,
                    COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS paid_amount
                FROM purchase_invoices
                WHERE invoice_date IS NOT NULL
                  AND invoice_date >= CURRENT_DATE - (%s || ' months')::interval
                GROUP BY TO_CHAR(invoice_date, 'YYYY-MM')
                ORDER BY month DESC
            """, (str(months),)).fetchall()
    finally:
        conn.close()
    return rows


def unpaid_total(user_id=None):
    """Ukupan dug (neplaćeni + u kašnjenju + delimično)."""
    conn = connect()
    try:
        if user_id is not None:
            row = conn.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) AS pending,
                    COALESCE(SUM(CASE WHEN status = 'overdue' THEN amount ELSE 0 END), 0) AS overdue,
                    COALESCE(SUM(CASE WHEN status = 'partial' THEN amount ELSE 0 END), 0) AS partial
                FROM purchase_invoices
                WHERE user_id = %s
            """, (user_id,)).fetchone()
        else:
            row = conn.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) AS pending,
                    COALESCE(SUM(CASE WHEN status = 'overdue' THEN amount ELSE 0 END), 0) AS overdue,
                    COALESCE(SUM(CASE WHEN status = 'partial' THEN amount ELSE 0 END), 0) AS partial
                FROM purchase_invoices
            """).fetchone()
    finally:
        conn.close()

    return {
        "pending": float(row["pending"]) if row else 0.0,
        "overdue": float(row["overdue"]) if row else 0.0,
        "partial": float(row["partial"]) if row else 0.0,
        "total": (float(row["pending"]) + float(row["overdue"]) + float(row["partial"])) if row else 0.0,
    }