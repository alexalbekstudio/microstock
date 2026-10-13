# admin_analytics.py
"""
Agregira podatke za Admin Dashboard iz:
- user_activity (login, posete stranicama)
- usage_logs (koliko puta koja funkcija)
- subscriptions (paketi)
- users (ime, email, last_login)
"""
from db_adapter import connect


def kpi_overview(days=30):
    """Glavni KPI brojevi za Admin Dashboard."""
    conn = connect()
    try:
        # Aktivni korisnici u zadnjih 7 dana (unikatni user_id)
        active_7 = conn.execute("""
            SELECT COUNT(DISTINCT user_id) AS n
            FROM user_activity
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """).fetchone()["n"]

        # Logini danas
        logins_today = conn.execute("""
            SELECT COUNT(*) AS n
            FROM user_activity
            WHERE endpoint = 'login'
              AND created_at::date = CURRENT_DATE
        """).fetchone()["n"]

        # Akcije u zadnjih N dana (isti filter kao tabela)
        actions_period = conn.execute("""
            SELECT COALESCE(SUM(count), 0) AS n
            FROM usage_logs
            WHERE period >= TO_CHAR(CURRENT_DATE - (%s || ' days')::interval, 'YYYY-MM')
        """, (str(days),)).fetchone()["n"]

        # Broj korisnika
        total_users = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE active = 1"
        ).fetchone()["n"]

        # Pretplate (aktivne)
        active_subs = conn.execute("""
            SELECT COUNT(*) AS n FROM subscriptions WHERE status = 'active'
        """).fetchone()["n"]

    finally:
        conn.close()

    return {
        "active_7": active_7,
        "logins_today": logins_today,
        "actions_period": actions_period,
        "total_users": total_users,
        "active_subs": active_subs,
    }


def logins_by_day(days=30):
    """Lista login-a po danu za Chart.js line chart."""
    conn = connect()
    try:
        rows = conn.execute("""
            SELECT
                created_at::date AS day,
                COUNT(*) AS logins,
                COUNT(DISTINCT user_id) AS unique_users
            FROM user_activity
            WHERE endpoint = 'login'
              AND created_at >= NOW() - (%s || ' days')::interval
            GROUP BY created_at::date
            ORDER BY day
        """, (str(days),)).fetchall()
    finally:
        conn.close()

    return [{
        "day": str(r["day"]),
        "logins": int(r["logins"]),
        "unique_users": int(r["unique_users"]),
    } for r in rows]


def top_features(days=30, limit=10):
    """Top funkcije po broju poziva u zadnjih N dana."""
    conn = connect()
    try:
        rows = conn.execute("""
            SELECT
                feature_code,
                SUM(count) AS total,
                COUNT(DISTINCT user_id) AS users
            FROM usage_logs
            WHERE period >= TO_CHAR(CURRENT_DATE - (%s || ' days')::interval, 'YYYY-MM')
            GROUP BY feature_code
            ORDER BY total DESC
            LIMIT %s
        """, (str(days), limit)).fetchall()
    finally:
        conn.close()

    return [{
        "feature_code": r["feature_code"],
        "total": int(r["total"]),
        "users": int(r["users"]),
    } for r in rows]


def activity_by_user(days=30, limit=20):
    """Koliko akcija je svaki korisnik napravio u zadnjih N dana."""
    conn = connect()
    try:
        rows = conn.execute("""
            SELECT
                u.id, u.email, u.name,
                COALESCE((
                    SELECT SUM(count)
                    FROM usage_logs
                    WHERE user_id = u.id
                      AND period >= TO_CHAR(CURRENT_DATE - (%s || ' days')::interval, 'YYYY-MM')
                ), 0) AS actions,
                (
                    SELECT MAX(created_at)
                    FROM user_activity
                    WHERE user_id = u.id
                ) AS last_seen
            FROM users u
            WHERE u.active = 1
            ORDER BY actions DESC, u.id ASC
            LIMIT %s
        """, (str(days), limit)).fetchall()
    finally:
        conn.close()

    return [{
        "id": r["id"],
        "email": r["email"],
        "name": r["name"] or r["email"],
        "actions": int(r["actions"]),
        "last_seen": str(r["last_seen"]) if r["last_seen"] else "—",
    } for r in rows]

def package_limits_overview():
    """
    Vraća listu korisnika sa aktivnom pretplatom i statusom limita.
    Za prikaz progress bar-ova u Admin Dashboard-u.
    """
    from subscriptions import all_limit_statuses

    statuses = all_limit_statuses()

    # Sortiraj: prvo oni koji prelaze 100%, pa 80%, pa ostali
    def sort_key(s):
        if s["over_products"] or s["over_orders"]:
            return 0
        if s["warn_products"] or s["warn_orders"]:
            return 1
        return 2

    statuses.sort(key=sort_key)
    return statuses