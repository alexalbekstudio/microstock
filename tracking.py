# tracking.py
"""
Admin tracking — beleženje aktivnosti korisnika za Admin Dashboard.
NE mešati sa analytics.py (to je Alat #2 — analitika prodaje).
"""
from db_adapter import connect


def record_activity(user_id, endpoint=None, method=None, path=None,
                    response_code=None):
    """
    Generička funkcija: upiši jedan red u user_activity.
    Ne baca grešku ako nešto pukne — tracking ne sme da obori aplikaciju.
    """
    if not user_id:
        return
    try:
        conn = connect()
        conn.execute(
            """INSERT INTO user_activity
               (user_id, endpoint, method, path, response_code)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, endpoint, method, path, response_code)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[tracking] record_activity failed: {e}")


def record_login(user_id):
    """Specijalni slučaj: uspešan login."""
    record_activity(
        user_id=user_id,
        endpoint="login",
        method="POST",
        path="/login",
        response_code=302
    )


def record_logout(user_id):
    """Specijalni slučaj: logout."""
    record_activity(
        user_id=user_id,
        endpoint="logout",
        method="GET",
        path="/logout",
        response_code=302
    )

def record_usage(user_id, feature_code, amount=1):
    """
    Poveća brojač za korisnika/funkciju/mesec u usage_logs.
    Ako red ne postoji — kreira ga.
    Ne baca grešku ako nešto pukne.

    Primer:
        record_usage(user.id, "add_product")
        record_usage(user.id, "create_order", amount=1)
    """
    if not user_id or not feature_code:
        return

    from datetime import datetime
    period = datetime.now().strftime("%Y-%m")   # npr. '2026-10'

    try:
        conn = connect()
        conn.execute("""
            INSERT INTO usage_logs (user_id, feature_code, period, count)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, feature_code, period)
            DO UPDATE SET
                count = usage_logs.count + EXCLUDED.count,
                updated_at = NOW()
        """, (user_id, feature_code, period, amount))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[tracking] record_usage failed: {e}")