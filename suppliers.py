# suppliers.py
"""
Dobavljači — CRUD operacije (multi-tenant).
"""
from db_adapter import connect


def list_suppliers(user_id=None, search=None, only_active=False):
    """Vraća listu dobavljača."""
    sql = "SELECT * FROM suppliers WHERE 1=1"
    params = []

    if user_id is not None:
        sql += " AND user_id = %s"
        params.append(user_id)
    if only_active:
        sql += " AND active = 1"
    if search:
        sql += " AND (name ILIKE %s OR contact_person ILIKE %s OR email ILIKE %s OR city ILIKE %s)"
        like = f"%{search}%"
        params += [like, like, like, like]

    sql += " ORDER BY name"
    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return rows


def get_supplier(sid, user_id=None):
    """Vraća jednog dobavljača ili None."""
    conn = connect()
    try:
        if user_id is not None:
            row = conn.execute(
                "SELECT * FROM suppliers WHERE id=%s AND user_id=%s",
                (sid, user_id)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM suppliers WHERE id=%s", (sid,)
            ).fetchone()
    finally:
        conn.close()
    return row


def add_supplier(user_id, name, contact_person="", email="", phone="",
                 address="", city="", tax_id="", iban="", swift="",
                 product_categories="", notes=""):
    """Dodaje novog dobavljača. Vraća ID."""
    conn = connect()
    try:
        cur = conn.execute("""
            INSERT INTO suppliers
                (user_id, name, contact_person, email, phone, address, city,
                 tax_id, iban, swift, product_categories, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, name, contact_person, email, phone, address, city,
              tax_id, iban, swift, product_categories, notes))
        row = cur.fetchone()
        conn.commit()
        return row["id"] if row else None
    finally:
        conn.close()


def update_supplier(sid, name, contact_person="", email="", phone="",
                    address="", city="", tax_id="", iban="", swift="",
                    product_categories="", notes="", active=1, user_id=None):
    """Menja dobavljača."""
    conn = connect()
    try:
        if user_id is not None:
            conn.execute("""
                UPDATE suppliers SET
                    name=%s, contact_person=%s, email=%s, phone=%s,
                    address=%s, city=%s, tax_id=%s, iban=%s, swift=%s,
                    product_categories=%s, notes=%s, active=%s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s AND user_id=%s
            """, (name, contact_person, email, phone, address, city,
                  tax_id, iban, swift, product_categories, notes, active,
                  sid, user_id))
        else:
            conn.execute("""
                UPDATE suppliers SET
                    name=%s, contact_person=%s, email=%s, phone=%s,
                    address=%s, city=%s, tax_id=%s, iban=%s, swift=%s,
                    product_categories=%s, notes=%s, active=%s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """, (name, contact_person, email, phone, address, city,
                  tax_id, iban, swift, product_categories, notes, active, sid))
        conn.commit()
    finally:
        conn.close()


def archive_supplier(sid, user_id=None):
    """Soft delete — postavlja active=0."""
    conn = connect()
    try:
        if user_id is not None:
            conn.execute(
                "UPDATE suppliers SET active=0, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=%s AND user_id=%s",
                (sid, user_id)
            )
        else:
            conn.execute(
                "UPDATE suppliers SET active=0, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (sid,)
            )
        conn.commit()
    finally:
        conn.close()


def delete_supplier(sid, user_id=None):
    """Hard delete — briše dobavljača (samo ako nema računa)."""
    conn = connect()
    try:
        # Provera da li ima računa
        if user_id is not None:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM purchase_invoices "
                "WHERE supplier_id=%s AND user_id=%s",
                (sid, user_id)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM purchase_invoices WHERE supplier_id=%s",
                (sid,)
            ).fetchone()
        if row and row["n"] > 0:
            raise ValueError("Dobavljač ima račune — ne može se obrisati. Arhiviraj ga.")

        if user_id is not None:
            conn.execute("DELETE FROM suppliers WHERE id=%s AND user_id=%s", (sid, user_id))
        else:
            conn.execute("DELETE FROM suppliers WHERE id=%s", (sid,))
        conn.commit()
    finally:
        conn.close()