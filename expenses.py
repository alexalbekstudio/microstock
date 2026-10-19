from db_adapter import connect


def list_expenses(user_id, days=30):
    """Vraća listu operativnih troškova za zadati broj dana."""
    conn = connect()
    sql = """
        SELECT id, title, category, amount, expense_date, note
        FROM business_expenses
        WHERE user_id = %s
    """
    params = [user_id]
    if days:
        sql += " AND expense_date >= CURRENT_DATE - (%s || ' days')::interval"
        params.append(str(days))

    sql += " ORDER BY expense_date DESC, id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_expense(user_id, title, category, amount, expense_date=None, note=""):
    """Upisuje novi režijski trošak."""
    conn = connect()
    conn.execute(
        """
        INSERT INTO business_expenses (user_id, title, category, amount, expense_date, note)
        VALUES (%s, %s, %s, %s, COALESCE(%s::date, CURRENT_DATE), %s)
    """,
        (user_id, title, category, float(amount), expense_date, note),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id, user_id):
    """Briše trošak."""
    conn = connect()
    conn.execute(
        "DELETE FROM business_expenses WHERE id = %s AND user_id = %s",
        (expense_id, user_id),
    )
    conn.commit()
    conn.close()


def total_expenses(user_id, days=30):
    """Vraća ukupan zbir režijskih troškova u zadatom periodu."""
    conn = connect()
    sql = """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM business_expenses
        WHERE user_id = %s
    """
    params = [user_id]
    if days:
        sql += " AND expense_date >= CURRENT_DATE - (%s || ' days')::interval"
        params.append(str(days))

    row = conn.execute(sql, params).fetchone()
    conn.close()
    return float(row["total"] or 0)