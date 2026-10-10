# currency_rates.py
"""
Dnevni kurs NBS (Narodna banka Srbije) preko AllRatesToday API-ja.

Cache strategija:
- PRVO proveri bazu (exchange_rates) za današnji datum
- Ako nema — pozovi API, sačuvaj u bazu
- Ako API padne — uzmi najnoviji kurs iz baze
- Ako ništa — vrati 1.0 (iznos ostaje u RSD)
"""

import os
import warnings
import requests
from datetime import date

from db_adapter import connect

# ============================================================
# IN-MEMORY CACHE (da ne udara NBS API za svaki display_money)
# ============================================================
_MEMORY_CACHE = {}          # {"EUR_RSD": {"rate": 117.2, "date": "2026-10-10"}}
_API_CALLED_TODAY = None    # Datum kad je API poslednji put uspešno pozvan

NBS_API_URL = "https://allratestoday.com/api/v1/central-bank/nbs/latest"

warnings.filterwarnings("ignore", message="Unable to find acceptable character detection dependency")


def fetch_nbs_latest():
    """Povlači najnoviju NBS kursnu listu."""
    api_key = os.getenv("NBS_API_KEY")
    if not api_key:
        raise RuntimeError("NBS_API_KEY nije postavljen u .env")

    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(NBS_API_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    rates = []
    for r in data.get("rates", []):
        base = r.get("base")
        quote = r.get("quote")
        value = r.get("value")
        if base and quote and value is not None:
            rates.append({
                "source": base.upper(),
                "target": quote.upper(),
                "rate": float(value),
            })

    return {
        "rate_date": data.get("rate_date"),
        "rates": rates,
    }


def get_rate(source, target):
    """
    Vraća kurs za par (npr. EUR -> RSD).
    Redosled: memorija → baza → API → fallback na najnoviji iz baze → 1.0
    """
    global _API_CALLED_TODAY
    from datetime import date as _date

    source = source.upper()
    target = target.upper()

    if source == target:
        return {"rate": 1.0, "rate_date": str(_date.today()),
                "source": source, "target": target}

    cache_key = f"{source}_{target}"
    today_str = str(_date.today())

    # 1) Memorija — ako je kurs od DANAS, vrati odmah
    mem = _MEMORY_CACHE.get(cache_key)
    if mem and mem.get("date") == today_str:
        return {
            "rate": mem["rate"],
            "rate_date": today_str,
            "source": source,
            "target": target,
            "from_memory": True,
        }

    # 2) Baza — današnji kurs?
    cached = get_cached_rate(source, target, today_only=True)
    if cached:
        # Sačuvaj u memoriju
        _MEMORY_CACHE[cache_key] = {"rate": cached["rate"], "date": today_str}
        return cached

    # 3) API — pozovi SAMO ako već nije pozvan danas (globalna zaštita)
    if _API_CALLED_TODAY != today_str:
        try:
            result = fetch_nbs_latest()
            _API_CALLED_TODAY = today_str   # markiraj da je API pozvan danas
            for r in result["rates"]:
                if r["source"] == source and r["target"] == target:
                    try:
                        save_rates_to_db(result)
                    except Exception as e:
                        print(f"[currency_rates] save greška: {e}")
                    # Sačuvaj u memoriju
                    _MEMORY_CACHE[cache_key] = {"rate": r["rate"], "date": today_str}
                    return {
                        "rate": r["rate"],
                        "rate_date": result["rate_date"],
                        "source": source,
                        "target": target,
                    }
        except Exception as e:
            print(f"[currency_rates] API greška: {e}")
            _API_CALLED_TODAY = today_str   # ne pokušavaj ponovo danas

    # 4) Fallback — najnoviji iz baze (iako je stariji)
    cached = get_cached_rate(source, target, today_only=False)
    if cached:
        _MEMORY_CACHE[cache_key] = {"rate": cached["rate"], "date": today_str}
        return cached

    # 5) Poslednja linija odbrane — 1.0
    print(f"[currency_rates] NEMA kursa za {source}->{target}, vraćam 1.0")
    _MEMORY_CACHE[cache_key] = {"rate": 1.0, "date": today_str}
    return {
        "rate": 1.0,
        "rate_date": today_str,
        "source": source,
        "target": target,
        "fallback": True,
    }


def save_rates_to_db(rates_data):
    """Upisuje kursnu listu u exchange_rates (UPSERT)."""
    rate_date = rates_data.get("rate_date")
    if not rate_date:
        raise ValueError("Nema rate_date u podacima")

    conn = connect()
    inserted = 0
    try:
        for r in rates_data["rates"]:
            conn.execute("""
                INSERT INTO exchange_rates (source_currency, target_currency, rate, rate_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(source_currency, target_currency, rate_date)
                DO UPDATE SET
                    rate = excluded.rate,
                    fetched_at = CURRENT_TIMESTAMP
            """, (r["source"], r["target"], r["rate"], rate_date))
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def get_cached_rate(source, target, today_only=False):
    """
    Čita kurs iz baze.
    today_only=True — samo današnji (rate_date = CURRENT_DATE)
    today_only=False — najnoviji dostupan
    """
    source = source.upper()
    target = target.upper()

    conn = connect()
    try:
        if today_only:
            row = conn.execute("""
                SELECT source_currency, target_currency, rate, rate_date
                FROM exchange_rates
                WHERE source_currency = %s AND target_currency = %s
                  AND rate_date::text = CURRENT_DATE::text
                ORDER BY rate_date DESC
                LIMIT 1
            """, (source, target)).fetchone()
        else:
            row = conn.execute("""
                SELECT source_currency, target_currency, rate, rate_date
                FROM exchange_rates
                WHERE source_currency = %s AND target_currency = %s
                ORDER BY rate_date DESC
                LIMIT 1
            """, (source, target)).fetchone()
    finally:
        conn.close()

    if row:
        return {
            "rate": float(row["rate"]),
            "rate_date": row["rate_date"],
            "source": row["source_currency"],
            "target": row["target_currency"],
            "cached": True,
        }
    return None

    # ============================================================
# ADMIN: kurs
# ============================================================

def list_all_rates():
    """
    Vraća sve trenutne kurseve iz exchange_rates (najnoviji po paru).
    Format: [{"source": "EUR", "target": "RSD", "rate": 117.2,
              "rate_date": "09.10.2026", "fetched_at": "09.10.2026 14:30"}, ...]
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

    result = []
    for r in rows:
        fetched = r["fetched_at"]
        if fetched and hasattr(fetched, "strftime"):
            fetched = fetched.strftime("%d.%m.%Y %H:%M")
        elif fetched:
            fetched = str(fetched)

        rate_date = r["rate_date"]
        if rate_date and hasattr(rate_date, "strftime"):
            rate_date = rate_date.strftime("%d.%m.%Y")
        elif rate_date:
            rate_date = str(rate_date)

        result.append({
            "source": r["source_currency"],
            "target": r["target_currency"],
            "rate": float(r["rate"]),
            "rate_date": rate_date,
            "fetched_at": fetched,
        })
    return result


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