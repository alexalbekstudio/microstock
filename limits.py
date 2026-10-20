# limits.py
from datetime import date
from db_adapter import connect

# Pravila i ograničenja paketa
PLANS = {
    "trial": {
        "max_products": 50,
        "max_orders_per_month": 100,
        "max_users": 1,
        "has_analytics": True,
        "has_projects": True,
        "has_suppliers": True,
        "has_recipes": True,
    },
    "starter": {
        "max_products": 50,
        "max_orders_per_month": 100,
        "max_users": 1,
        "has_analytics": False,      # Starter nema punu analitiku
        "has_projects": False,       # Nema praćenje projekata
        "has_suppliers": False,      # Nema nabavku i dobavljače
        "has_recipes": False,
    },
    "pro": {
        "max_products": float("inf"), # Neograničeno
        "max_orders_per_month": float("inf"),
        "max_users": 5,
        "has_analytics": True,
        "has_projects": True,
        "has_suppliers": True,
        "has_recipes": True,
    },
    "business": {
        "max_products": float("inf"),
        "max_orders_per_month": float("inf"),
        "max_users": float("inf"),
        "has_analytics": True,
        "has_projects": True,
        "has_suppliers": True,
        "has_recipes": True,
    }
}

def get_user_plan_context(user_id):
    """
    Vraća plan, status i dozvoljene limite za datog korisnika.
    """
    conn = connect()
    try:
        sub = conn.execute("""
            SELECT * FROM subscriptions 
            WHERE user_id = %s 
            ORDER BY id DESC LIMIT 1
        """, (user_id,)).fetchone()
    finally:
        conn.close()

    today = date.today()
    if not sub:
        return "expired", False, PLANS["starter"]

    plan_name = (sub.get("plan_name") or "starter").lower()
    end_date = sub.get("end_date")
    status = sub.get("status")

    # Provera validnosti datuma
    is_active = (status == "active") and (end_date is not None) and (end_date >= today)

    if not is_active:
        return plan_name, False, PLANS["starter"]

    return plan_name, True, PLANS.get(plan_name, PLANS["starter"])


def can_add_product(user_id):
    """Proverava da li korisnik sme da doda novi proizvod."""
    plan, is_active, rules = get_user_plan_context(user_id)
    if not is_active:
        return False, "Pretplata je istekla. Obnovite pretplatu na stranici Pretplata."

    conn = connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS total FROM products WHERE user_id = %s AND active = 1", (user_id,)).fetchone()
        current_count = row["total"] if row else 0
    finally:
        conn.close()

    if current_count >= rules["max_products"]:
        return False, f"Dostigli ste limit od {rules['max_products']} proizvoda za paket '{plan.upper()}'. Pređite na Pro paket za neograničeno."

    return True, None


def can_add_order(user_id):
    """Proverava mesečni limit porudžbina."""
    plan, is_active, rules = get_user_plan_context(user_id)
    if not is_active:
        return False, "Pretplata je istekla. Obnovite pretplatu na stranici Pretplata."

    # Broj porudžbina u tekućem mesecu
    conn = connect()
    try:
        row = conn.execute("""
            SELECT COUNT(*) AS total FROM orders 
            WHERE user_id = %s 
              AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
        """, (user_id,)).fetchone()
        current_orders = row["total"] if row else 0
    finally:
        conn.close()

    if current_orders >= rules["max_orders_per_month"]:
        return False, f"Dostigli ste mesečni limit od {rules['max_orders_per_month']} narudžbina za paket '{plan.upper()}'."

    return True, None