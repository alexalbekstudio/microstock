# capital.py
"""
Praćenje kapitala vlasnika (admin).
- Jedan zajednički kapital za celu firmu.
- Sve transakcije se beleže u capital_transactions.
- users.capital čuva trenutno stanje (keš radi brzine).
"""
from db_adapter import connect


# Tipovi transakcija
TYPES = {
    "deposit":    "Uplata",       # uplata novca u firmu
    "withdrawal": "Isplata",      # izvlačenje novca iz firme
    "purchase":   "Kupovina",     # kupovina robe (smanjuje kapital)
    "sale":       "Prodaja",      # prihod od prodaje (povećava kapital)
    "adjustment": "Korekcija",    # ručna korekcija
}

# Znak po tipu: + povećava kapital, − smanjuje
SIGNS = {
    "deposit":    +1,
    "withdrawal": -1,
    "purchase":   -1,
    "sale":       +1,
    "adjustment": +1,   # adjustment može biti i + i − (koristi se sa predznakom)
}


def get_current_capital():
    """Vraća trenutno stanje kapitala (jedan broj)."""
    conn = connect()
    row = conn.execute(
        "SELECT COALESCE(MAX(capital), 0) AS c FROM users WHERE role='admin'"
    ).fetchone()
    conn.close()
    return float(row["c"]) if row else 0.0


def list_transactions(limit=50):
    """Vraća poslednjih N transakcija (sa formatiranim datumom)."""
    conn = connect()
    rows = conn.execute("""
        SELECT ct.*, u.email AS user_email, u.name AS user_name
        FROM capital_transactions ct
        LEFT JOIN users u ON u.id = ct.user_id
        ORDER BY ct.created_at DESC, ct.id DESC
        LIMIT %s
    """, (limit,)).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        created = d.get("created_at")
        if created and hasattr(created, "strftime"):
            d["created_at_formatted"] = created.strftime("%d.%m.%Y %H:%M")
        elif created:
            d["created_at_formatted"] = str(created)
        else:
            d["created_at_formatted"] = "—"
        result.append(d)
    return result


def add_transaction(user_id, tx_type, amount, note=""):
    """
    Dodaje transakciju i ažurira stanje u users.capital.
    amount: pozitivan broj (znak se primenjuje po tipu).
    Vraća (ok, nova_balanca, poruka).
    """
    if tx_type not in TYPES:
        return False, None, f"Nepoznat tip: {tx_type}"
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return False, None, "Iznos nije broj."
    if amount <= 0:
        return False, None, "Iznos mora biti veći od 0."

    sign = SIGNS[tx_type]
    signed = amount * sign

    conn = connect()
    try:
        # Provera trenutnog stanja (da ne ode u minus, osim za deposit/adjustment)
        row = conn.execute(
            "SELECT COALESCE(capital, 0) AS c FROM users WHERE id=%s",
            (user_id,)
        ).fetchone()
        current = float(row["c"]) if row else 0.0

        new_balance = current + signed
        if new_balance < 0:
            conn.close()
            return False, None, f"Nedovoljno sredstava. Trenutno: {current:.2f}, pokušaj: {signed:+.2f}"

        # Upis transakcije
        conn.execute("""
            INSERT INTO capital_transactions (user_id, type, amount, balance, note)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, tx_type, amount, new_balance, note))

        # Update stanja
        conn.execute(
            "UPDATE users SET capital=%s WHERE id=%s",
            (new_balance, user_id)
        )
        conn.commit()
        return True, new_balance, "Transakcija sačuvana."
    except Exception as e:
        conn.rollback()
        return False, None, f"Greška: {e}"
    finally:
        conn.close()


def get_summary(days=30):
    """
    Vraća sumu po tipu za poslednjih N dana + trenutno stanje.
    Za dashboard KPI.
    """
    conn = connect()
    current = get_current_capital()

    rows = conn.execute("""
        SELECT type, COALESCE(SUM(amount), 0) AS total
        FROM capital_transactions
        WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
        GROUP BY type
    """, (days,)).fetchall()
    conn.close()

    by_type = {r["type"]: float(r["total"]) for r in rows}
    return {
        "current": current,
        "deposits":   by_type.get("deposit", 0.0),
        "withdrawals": by_type.get("withdrawal", 0.0),
        "purchases":  by_type.get("purchase", 0.0),
        "sales":      by_type.get("sale", 0.0),
        "adjustments": by_type.get("adjustment", 0.0),
    }