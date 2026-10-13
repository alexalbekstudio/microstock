# subscriptions.py
"""
Upravljanje pretplatama — CRUD + pregled.
Ručni unos (pre Stripe integracije).
"""
from datetime import date, datetime
from db_adapter import connect


# ==================== DEFINICIJE PAKETA ====================

PLANS = {
    "starter": {
        "label": "Starter",
        "price_eur": 5,
        "max_products": 100,
        "max_orders_month": 50,
        "support_hours": 48,
    },
    "pro": {
        "label": "Pro",
        "price_eur": 10,
        "max_products": 500,
        "max_orders_month": 300,
        "support_hours": 24,
    },
    "business": {
        "label": "Business",
        "price_eur": 20,
        "max_products": 2000,
        "max_orders_month": 2000,
        "support_hours": 12,
    },
    "enterprise": {
        "label": "Enterprise",
        "price_eur": None,   # na upit
        "max_products": None,  # neograničeno
        "max_orders_month": None,
        "support_hours": None,
    },
}

VALID_STATUSES = ("active", "expired", "canceled", "trial")


def plan_label(plan_name):
    """Vraća labelu paketa ili sam naziv ako nepoznat."""
    if plan_name in PLANS:
        return PLANS[plan_name]["label"]
    return plan_name


# ==================== LISTE I PREGLED ====================

def list_subscriptions(status=None, plan=None, search=None):
    """
    Lista pretplata (najnovija po korisniku).
    Vraća sve redove, sortirane po end_date.
    """
    sql = """
        SELECT
            s.id,
            s.user_id,
            s.plan_name,
            s.status,
            s.start_date,
            s.end_date,
            s.renewal_date,
            s.is_self_hosted,
            s.license_key,
            s.sla_level,
            s.notes,
            s.created_at,
            s.updated_at,
            u.email AS user_email,
            u.name AS user_name
        FROM subscriptions s
        JOIN users u ON u.id = s.user_id
        WHERE 1=1
    """
    params = []

    if status:
        sql += " AND s.status = %s"
        params.append(status)

    if plan:
        sql += " AND s.plan_name = %s"
        params.append(plan)

    if search:
        sql += " AND (u.email ILIKE %s OR u.name ILIKE %s)"
        like = f"%{search}%"
        params.extend([like, like])

    sql += " ORDER BY s.end_date NULLS LAST, s.id DESC"

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return [dict(r) if not isinstance(r, dict) else r for r in rows]


def get_subscription(sub_id):
    """Vraća jednu pretplatu po ID-ju."""
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT s.*, u.email AS user_email, u.name AS user_name
            FROM subscriptions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = %s
        """, (sub_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        return None
    return dict(row) if not isinstance(row, dict) else row


def active_subscription_for_user(user_id):
    """Vraća aktivnu pretplatu korisnika ili None."""
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT * FROM subscriptions
            WHERE user_id = %s AND status = 'active'
            ORDER BY end_date NULLS LAST, id DESC
            LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        return None
    return dict(row) if not isinstance(row, dict) else row


def user_subscription_history(user_id):
    """Sve pretplate korisnika, najnovije prvo."""
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT * FROM subscriptions
            WHERE user_id = %s
            ORDER BY id DESC
        """, (user_id,))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return [dict(r) if not isinstance(r, dict) else r for r in rows]


def subscriptions_summary():
    """
    KPI: broj pretplata po paketu i statusu.
    Vraća dict sa brojevima.
    """
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT plan_name, COUNT(*) AS n
            FROM subscriptions
            WHERE status = 'active'
            GROUP BY plan_name
        """)
        by_plan_rows = cur.fetchall()

        cur.execute("""
            SELECT status, COUNT(*) AS n
            FROM subscriptions
            GROUP BY status
        """)
        by_status_rows = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*) AS n
            FROM subscriptions
            WHERE status = 'active'
              AND end_date IS NOT NULL
              AND end_date <= CURRENT_DATE + INTERVAL '7 days'
        """)
        expiring_soon = cur.fetchone()
        expiring_soon = expiring_soon[0] if not isinstance(expiring_soon, dict) else list(expiring_soon.values())[0]

    finally:
        cur.close()
        conn.close()

    by_plan = {}
    for r in by_plan_rows:
        d = dict(r) if not isinstance(r, dict) else r
        by_plan[d["plan_name"]] = int(d["n"])

    by_status = {}
    for r in by_status_rows:
        d = dict(r) if not isinstance(r, dict) else r
        by_status[d["status"]] = int(d["n"])

    return {
        "by_plan": by_plan,
        "by_status": by_status,
        "expiring_soon": int(expiring_soon),
        "total_active": sum(by_plan.values()),
    }


# ==================== CRUD ====================

def add_subscription(user_id, plan_name, status="active",
                     start_date=None, end_date=None, renewal_date=None,
                     is_self_hosted=False, license_key=None,
                     sla_level=None, notes=None):
    """Dodaje novu pretplatu. Vraća ID."""
    if plan_name not in PLANS:
        raise ValueError(f"Nepoznat paket: {plan_name}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Nepoznat status: {status}")

    if start_date is None:
        start_date = date.today()

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO subscriptions
              (user_id, plan_name, status, start_date, end_date, renewal_date,
               is_self_hosted, license_key, sla_level, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id, plan_name, status, start_date, end_date, renewal_date,
            bool(is_self_hosted), license_key, sla_level, notes
        ))
        row = cur.fetchone()
        new_id = row[0] if not isinstance(row, dict) else list(row.values())[0]
        conn.commit()
        return new_id
    finally:
        cur.close()
        conn.close()


def update_subscription(sub_id, **fields):
    """
    Ažurira pretplatu. Dozvoljena polja:
    plan_name, status, start_date, end_date, renewal_date,
    is_self_hosted, license_key, sla_level, notes
    """
    allowed = ("plan_name", "status", "start_date", "end_date", "renewal_date",
               "is_self_hosted", "license_key", "sla_level", "notes")

    updates = []
    params = []

    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "plan_name" and v not in PLANS:
            raise ValueError(f"Nepoznat paket: {v}")
        if k == "status" and v not in VALID_STATUSES:
            raise ValueError(f"Nepoznat status: {v}")
        if k == "is_self_hosted":
            v = bool(v)
        updates.append(f"{k} = %s")
        params.append(v)

    if not updates:
        return False

    updates.append("updated_at = NOW()")
    params.append(sub_id)

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE subscriptions SET {', '.join(updates)} WHERE id = %s",
            params
        )
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()


def cancel_subscription(sub_id):
    """Postavlja status na 'canceled'."""
    return update_subscription(sub_id, status="canceled")


def delete_subscription(sub_id):
    """Briše pretplatu (samo admin)."""
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM subscriptions WHERE id = %s", (sub_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

# ==================== LIMITI PAKETA ====================

def user_usage(user_id, period=None):
    """
    Vraća trenutnu potrošnju korisnika za tekući mesec (ili zadati period).
    Koristi usage_logs kao proxy za aktivnost.

    Vraća dict:
        {
            'products_added': int,   # add_product ovog meseca
            'orders_created': int,   # create_order ovog meseca
            'period': str,           # 'YYYY-MM'
        }
    """
    from datetime import datetime
    if period is None:
        period = datetime.now().strftime("%Y-%m")

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT feature_code, SUM(count) AS total
            FROM usage_logs
            WHERE user_id = %s AND period = %s
            GROUP BY feature_code
        """, (user_id, period))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    by_feature = {}
    for r in rows:
        d = dict(r) if not isinstance(r, dict) else r
        by_feature[d["feature_code"]] = int(d["total"])

    return {
        "products_added": by_feature.get("add_product", 0),
        "orders_created": by_feature.get("create_order", 0),
        "period": period,
    }


def user_limit_status(user_id):
    """
    Vraća status limita za korisnika:
    - plan (aktivna pretplata)
    - trenutna potrošnja
    - limiti paketa
    - procenat iskorišćenosti
    - da li prelazi 80% ili 100%

    Vraća None ako korisnik nema aktivnu pretplatu.
    """
    sub = active_subscription_for_user(user_id)
    if not sub:
        return None

    plan_name = sub["plan_name"]
    plan = PLANS.get(plan_name)
    if not plan:
        return None

    usage = user_usage(user_id)

    # Izračunaj procente
    max_products = plan["max_products"]
    max_orders = plan["max_orders_month"]

    products_pct = (
        (usage["products_added"] / max_products * 100)
        if max_products else 0
    )
    orders_pct = (
        (usage["orders_created"] / max_orders * 100)
        if max_orders else 0
    )

    return {
        "plan_name": plan_name,
        "plan_label": plan["label"],
        "subscription_id": sub["id"],
        "end_date": sub["end_date"],
        "usage": usage,
        "limits": {
            "max_products": max_products,
            "max_orders_month": max_orders,
        },
        "pct": {
            "products": round(products_pct, 1),
            "orders": round(orders_pct, 1),
        },
        "warn_products": max_products is not None and products_pct >= 80,
        "warn_orders": max_orders is not None and orders_pct >= 80,
        "over_products": max_products is not None and products_pct >= 100,
        "over_orders": max_orders is not None and orders_pct >= 100,
    }


def all_limit_statuses():
    """
    Vraća listu svih aktivnih pretplata sa statusom limita.
    Koristi se za scheduler.
    """
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT s.user_id, u.email AS user_email, u.name AS user_name
            FROM subscriptions s
            JOIN users u ON u.id = s.user_id
            WHERE s.status = 'active'
        """)
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    result = []
    for r in rows:
        d = dict(r) if not isinstance(r, dict) else r
        status = user_limit_status(d["user_id"])
        if not status:
            continue
        status["user_email"] = d["user_email"]
        status["user_name"] = d["user_name"]
        result.append(status)

    return result