# users.py
"""
Upravljanje korisnicima — CRUD + role.
"""
from datetime import datetime
from werkzeug.security import generate_password_hash
from db_adapter import connect


VALID_ROLES = ("admin", "manager", "viewer")


def list_users():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, email, name, role, active, last_login
        FROM users
        ORDER BY role, name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Dict konverzija (SQLite row → dict)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


def get_user(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, email, name, role, active, last_login
        FROM users WHERE id = %s
    """, (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return dict(row) if not isinstance(row, dict) else row


def create_user(email, name, password, role="viewer"):
    if role not in VALID_ROLES:
        raise ValueError(f"Nepoznata rola: {role}")

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (email, name, password_hash, role, active)
            VALUES (%s, %s, %s, %s, 1)
        """, (email.lower().strip(), name.strip(),
              generate_password_hash(password), role))
        conn.commit()
        return cur.lastrowid
    finally:
        cur.close()
        conn.close()


def update_user(user_id, email, name, role, active):
    if role not in VALID_ROLES:
        raise ValueError(f"Nepoznata rola: {role}")

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users
            SET email = %s, name = %s, role = %s, active = %s
            WHERE id = %s
        """, (email.lower().strip(), name.strip(), role, 1 if active else 0, user_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def change_password(user_id, new_password):
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users SET password_hash = %s WHERE id = %s
        """, (generate_password_hash(new_password), user_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def toggle_active(user_id):
    """Vraća novi status (1/0)."""
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT active FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        current = row[0] if not isinstance(row, dict) else row["active"]
        new_val = 0 if current else 1
        cur.execute("UPDATE users SET active = %s WHERE id = %s", (new_val, user_id))
        conn.commit()
        return new_val
    finally:
        cur.close()
        conn.close()


def delete_user(user_id):
    """Zabranjeno brisanje samog sebe i poslednjeg admina."""
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def count_admins():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if not isinstance(row, dict) else list(row.values())[0]