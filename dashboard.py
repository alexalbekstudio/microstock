# dashboard.py
"""Agregira podatke iz sve tri alatke za Control Center."""
from database import get_conn
import analytics
import projects as proj
import models


def control_center(user_id, days=30):
    """Vraća kompletan snimak stanja poslovanja za jednog korisnika."""

    # === 1. KPI (poslednjih N dana) ===
    kpi = analytics.overview(user_id, days)

    # === 2. Alarmi ===
    low_stock = models.low_stock_products(user_id)
    loss_products = analytics.loss_makers(user_id, days)
    proj_overview = proj.projects_overview(user_id)

    # === 3. Šta treba danas ===
    conn = get_conn()
    pending_orders = conn.execute("""
        SELECT o.id, o.customer_name, o.status, c.name AS channel,
               (SELECT SUM(qty*unit_price) FROM order_items WHERE order_id=o.id) AS total
        FROM orders o JOIN channels c ON c.id=o.channel_id
        WHERE o.status IN ('new','paid') AND o.user_id = %s
        ORDER BY o.id ASC LIMIT 8
    """, (user_id,)).fetchall()

    stale_projects = conn.execute("""
        SELECT p.id, p.code, p.name, p.client
        FROM projects p
        WHERE p.status='active' AND p.user_id = %s
          AND NOT EXISTS (SELECT 1 FROM time_entries WHERE project_id=p.id)
        ORDER BY p.id DESC LIMIT 5
    """, (user_id,)).fetchall()

    soon_deadlines = conn.execute("""
        SELECT id, code, name, client, deadline
        FROM projects
        WHERE status='active' AND user_id = %s
          AND deadline IS NOT NULL
          AND deadline::date <= CURRENT_DATE + INTERVAL '14 days'
        ORDER BY deadline ASC LIMIT 5
    """, (user_id,)).fetchall()

    conn.close()

    # === 4. Ukupan alarm count ===
    total_alerts = (
        len(low_stock)
        + len(loss_products)
        + proj_overview["warnings"]
        + len(stale_projects)
        + len(soon_deadlines)
    )

    # === 5. Kapital (samo admin) ===
    import capital as capital_mod
    capital_summary = capital_mod.get_summary(user_id, days=days)

    # === 6. Nabavka (dug dobavljačima) ===
    import purchases as purch
    purchases_summary = purch.unpaid_total(user_id)

    return {
        "kpi": kpi,
        "trend": analytics.trend(user_id, days),
        "channels": analytics.by_channel(user_id, days),
        "low_stock": low_stock,
        "loss_products": loss_products,
        "projects": proj_overview,
        "pending_orders": pending_orders,
        "stale_projects": stale_projects,
        "soon_deadlines": soon_deadlines,
        "total_alerts": total_alerts,
        "days": days,
        "capital": capital_summary,
        "purchases": purchases_summary,
    }