# scheduler.py
"""
Dnevni poslovi:
- 08:00 — email digest (low stock, pending orders, deadlines)
- 08:05 — NBS kurs (Narodna banka Srbije)
Koristi APScheduler — radi u istom procesu kao Flask.
"""
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

_scheduler = None


def init_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return
    # Ne pokrećuj u Flask reloader-u (duplo bi se izvršavalo)
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and app.debug:
        return

    _scheduler = BackgroundScheduler(daemon=True)

    # 08:00 — dnevni email digest
    _scheduler.add_job(
        func=lambda: _run_daily_digest(app),
        trigger="cron",
        hour=8, minute=0,
        id="daily_digest",
        replace_existing=True,
    )

    # 08:05 — NBS kurs (pon-pet)
    _scheduler.add_job(
        func=lambda: _run_nbs_rates(app),
        trigger="cron",
        day_of_week="mon-fri",
        hour=8, minute=5,
        id="nbs_rates",
        replace_existing=True,
    )

    # Nedeljni izveštaj — ponedeljak u 08:15
    _scheduler.add_job(
        func=lambda: _run_report(app, "week"),
        trigger="cron",
        day_of_week="mon", hour=8, minute=25,
        id="weekly_report",
        replace_existing=True,
    )

    # Mesečni izveštaj — 1. u mesecu u 08:20
    _scheduler.add_job(
        func=lambda: _run_report(app, "month"),
        trigger="cron",
        day=1, hour=8, minute=30,
        id="monthly_report",
        replace_existing=True,
    )

    # Svakih sat vremena — reset demo baze
    _scheduler.add_job(
        func=lambda: _reset_demo(app),
        trigger="interval",
        hours=1,
        id="demo_reset",
        replace_existing=True,
    )

    # 08:12 — upozorenja o limitu paketa (80%)
    _scheduler.add_job(
        func=lambda: _run_package_limit_alerts(app),
        trigger="cron",
        hour=8, minute=12,
        id="package_limit_alerts",
        replace_existing=True,
    )

    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    app.logger.info("Scheduler: digest 08:00, NBS kurs 08:05 (pon-pet)")


# ==================== EMAIL DIGEST ====================

def _run_daily_digest(app):
    """Pokreće se u background thread-u — mora app context."""
    with app.app_context():
        try:
            _digest_low_stock()
            _digest_pending_orders()
            _digest_deadlines()
        except Exception as e:
            app.logger.error(f"Digest greška: {e}")


def _digest_low_stock():
    from db_adapter import connect
    from mailer import send_low_stock_digest
    conn = connect()
    cur = conn.execute("""
        SELECT id, sku, name, stock, low_stock_at
        FROM products
        WHERE active = 1 AND stock <= low_stock_at
        ORDER BY stock ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    if rows:
        send_low_stock_digest(rows)


def _digest_pending_orders():
    from db_adapter import connect
    from mailer import send_pending_orders_digest
    days = int(os.getenv("PENDING_ORDER_DAYS", "3"))
    conn = connect()
    cur = conn.execute("""
        SELECT id, customer_name, status, created_at
        FROM orders
        WHERE status IN ('new', 'paid')
          AND created_at <= CURRENT_TIMESTAMP - (%s || ' days')::interval
        ORDER BY created_at ASC
    """, (str(days),))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    if rows:
        send_pending_orders_digest(rows, days)


def _digest_deadlines():
    from db_adapter import connect
    from mailer import send_deadlines_digest
    conn = connect()
    cur = conn.execute("""
        SELECT id, name, client, deadline
        FROM projects
        WHERE status = 'active'
          AND deadline IS NOT NULL
          AND deadline BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '14 days'
        ORDER BY deadline ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    if rows:
        send_deadlines_digest(rows)


# ==================== NBS KURS ====================

def _run_nbs_rates(app):
    """Povlači NBS kurs i upisuje u exchange_rates."""
    with app.app_context():
        try:
            from currency_rates import fetch_nbs_latest, save_rates_to_db
            data = fetch_nbs_latest()
            n = save_rates_to_db(data)
            app.logger.info(
                f"NBS kurs: upisano {n} valuta za {data['rate_date']}"
            )
        except Exception as e:
            app.logger.error(f"NBS kurs greška: {e}")


# ==================== PERIODIČNI IZVEŠTAJI ====================

def _run_report(app, period):
    """Šalje nedeljni ili mesečni izveštaj."""
    with app.app_context():
        try:
            from reports import send_report
            ok = send_report(period)
            app.logger.info(f"Report {period}: {'poslato' if ok else 'NIJE poslato'}")
        except Exception as e:
            app.logger.error(f"Report {period} greška: {e}")

# ============================================================
# ADMIN: kurs
# ============================================================

def list_all_rates():
    """
    Vraća sve trenutne kurseve iz exchange_rates (najnoviji po paru).
    """
    conn = connect()
    try:
        rows = conn.execute("""
            SELECT DISTINCT ON (source_currency, target_currency)
                source_currency, target_currency, rate, rate_date, fetched_at
            FROM exchange_rates
            ORDER BY source_currency, target_currency, rate_date DESC
        """).fetchall()
    finally:
        conn.close()

    return [
        {
            "source": r["source_currency"],
            "target": r["target_currency"],
            "rate": float(r["rate"]),
            "rate_date": r["rate_date"],
            "fetched_at": r["fetched_at"],
        }
        for r in rows
    ]


def set_manual_rate(source, target, rate, rate_date=None):
    """
    Ručno postavi kurs (UPSERT).
    Ako rate_date nije zadat — koristi današnji datum.
    """
    from datetime import date as _date
    source = source.upper().strip()
    target = target.upper().strip()
    if rate_date is None:
        rate_date = _date.today()

    conn = connect()
    try:
        conn.execute("""
            INSERT INTO exchange_rates
                (source_currency, target_currency, rate, rate_date)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_currency, target_currency, rate_date)
            DO UPDATE SET
                rate = excluded.rate,
                fetched_at = CURRENT_TIMESTAMP
        """, (source, target, float(rate), rate_date))
        conn.commit()
    finally:
        conn.close()


def refresh_from_nbs():
    """
    Ručno osveži sve kurseve iz NBS API-ja.
    Vraća (ok, broj_upisanih, poruka).
    """
    try:
        data = fetch_nbs_latest()
        n = save_rates_to_db(data)
        return True, n, f"Uspešno povučeno {n} kurseva za {data['rate_date']}."
    except Exception as e:
        return False, 0, f"Greška: {e}"

def _reset_demo(app):
    """Resetuje demo bazu svakih sat vremena."""
    with app.app_context():
        try:
            from demo import reset_demo_data
            ok = reset_demo_data()
            app.logger.info(f"Demo reset: {'OK' if ok else 'FAILED'}")
        except Exception as e:
            app.logger.error(f"Demo reset greška: {e}")

# ==================== PRETPLATE — PODSETNIK ====================

def _run_subscription_alerts(app):
    """
    Šalje podsetnike:
    - korisniku 7 dana pre isteka
    - adminu (ALERT_EMAIL) listu svih koji ističu
    """
    with app.app_context():
        try:
            from db_adapter import connect
            from mailer import (send_subscription_expiring,
                                send_subscription_expiring_admin)
            from subscriptions import plan_label

            conn = connect()
            try:
                # Pretplate koje ističu u narednih 7 dana
                rows = conn.execute("""
                    SELECT
                        s.id, s.plan_name, s.end_date,
                        u.email AS user_email,
                        u.name AS user_name,
                        (s.end_date - CURRENT_DATE) AS days_left
                    FROM subscriptions s
                    JOIN users u ON u.id = s.user_id
                    WHERE s.status = 'active'
                      AND s.end_date IS NOT NULL
                      AND s.end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
                    ORDER BY s.end_date ASC
                """).fetchall()
            finally:
                conn.close()

            expiring = []
            for r in rows:
                d = dict(r) if not isinstance(r, dict) else r
                days_left = int(d["days_left"])
                label = plan_label(d["plan_name"])

                # Korisniku
                send_subscription_expiring(
                    to_email=d["user_email"],
                    user_name=d["user_name"],
                    plan_label=label,
                    end_date=str(d["end_date"]),
                    days_left=days_left,
                )

                expiring.append({
                    "email": d["user_email"],
                    "plan_label": label,
                    "end_date": str(d["end_date"]),
                    "days_left": days_left,
                })

            # Adminu — samo ako ima nešto
            if expiring:
                # Šalji jedan email adminu sa listom
                for e in expiring:
                    send_subscription_expiring_admin(
                        user_email=e["email"],
                        user_name="",
                        plan_label=e["plan_label"],
                        end_date=e["end_date"],
                        days_left=e["days_left"],
                    )

            app.logger.info(f"Subscription alerts: {len(expiring)} pretplata ističe")
        except Exception as e:
            app.logger.error(f"Subscription alerts greška: {e}")

# ==================== LIMIT PAKETA ====================

def _run_package_limit_alerts(app):
    """
    Prolazi kroz sve aktivne pretplate i šalje upozorenje
    korisnicima koji su prešli 80% limita paketa.
    """
    with app.app_context():
        try:
            from subscriptions import all_limit_statuses
            from mailer import send_package_limit_warning

            statuses = all_limit_statuses()
            sent = 0

            for s in statuses:
                # Proizvodi
                if s["warn_products"] and s["limits"]["max_products"]:
                    send_package_limit_warning(
                        to_email=s["user_email"],
                        user_name=s["user_name"],
                        plan_label=s["plan_label"],
                        resource="proizvoda",
                        current=s["usage"]["products_added"],
                        max_value=s["limits"]["max_products"],
                        pct=s["pct"]["products"],
                    )
                    sent += 1

                # Narudžbine
                if s["warn_orders"] and s["limits"]["max_orders_month"]:
                    send_package_limit_warning(
                        to_email=s["user_email"],
                        user_name=s["user_name"],
                        plan_label=s["plan_label"],
                        resource="narudžbina",
                        current=s["usage"]["orders_created"],
                        max_value=s["limits"]["max_orders_month"],
                        pct=s["pct"]["orders"],
                    )
                    sent += 1

            app.logger.info(f"Package limit alerts: {sent} upozorenja poslato")
        except Exception as e:
            app.logger.error(f"Package limit alerts greška: {e}")

# ==================== ADMIN DNEVNI REPORT ====================

def _run_admin_daily(app):
    """Šalje dnevni admin report sa aktivnošću + pretplatama koje ističu."""
    with app.app_context():
        try:
            from admin_analytics import kpi_overview, top_features
            from mailer import send_admin_daily_report
            from db_adapter import connect

            kpi = kpi_overview(30)
            features = top_features(30, limit=10)

            # Pretplate koje ističu u narednih 7 dana
            conn = connect()
            try:
                rows = conn.execute("""
                    SELECT
                        s.plan_name, s.end_date,
                        u.email,
                        (s.end_date - CURRENT_DATE) AS days_left
                    FROM subscriptions s
                    JOIN users u ON u.id = s.user_id
                    WHERE s.status = 'active'
                      AND s.end_date IS NOT NULL
                      AND s.end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
                    ORDER BY s.end_date ASC
                """).fetchall()
            finally:
                conn.close()

            from subscriptions import plan_label
            expiring = []
            for r in rows:
                d = dict(r) if not isinstance(r, dict) else r
                expiring.append({
                    "email": d["email"],
                    "plan_label": plan_label(d["plan_name"]),
                    "end_date": str(d["end_date"]),
                    "days_left": int(d["days_left"]),
                })

            send_admin_daily_report(kpi, logins=None, features=features, expiring=expiring)
            app.logger.info(f"Admin daily report: poslat")
        except Exception as e:
            app.logger.error(f"Admin daily greška: {e}")