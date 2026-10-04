# currency_rates.py
"""
Dnevni kurs NBS (Narodna banka Srbije) preko AllRatesToday API-ja.

Struktura odgovora (potvrđeno):
{
  "bank": "nbs",
  "rate_date": "2026-10-02",
  "rates": [
      {"base": "EUR", "quote": "RSD", "type": "middle", "value": 117.4948},
      ...
  ]
}
"""

import os
import requests

from db_adapter import connect

NBS_API_URL = "https://allratestoday.com/api/v1/central-bank/nbs/latest"

import warnings
warnings.filterwarnings("ignore", message="Unable to find acceptable character detection dependency")

def fetch_nbs_latest():
    """
    Povlači najnoviju NBS kursnu listu.
    Vraća dict: {"rate_date": "...", "rates": [{source, target, rate}, ...]}
    """
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
    Prvo pokušava API, pa fallback na bazu.
    """
    source = source.upper()
    target = target.upper()

    # 1) Pokušaj API
    try:
        result = fetch_nbs_latest()
        for r in result["rates"]:
            if r["source"] == source and r["target"] == target:
                return {
                    "rate": r["rate"],
                    "rate_date": result["rate_date"],
                    "source": source,
                    "target": target,
                }
    except Exception as e:
        print(f"[currency_rates] API greška: {e}")

    # 2) Fallback — baza
    cached = get_cached_rate(source, target)
    if cached:
        return cached

    raise RuntimeError(f"Nema kursa za {source}->{target}")


def save_rates_to_db(rates_data):
    """
    Upisuje kursnu listu u exchange_rates (UPSERT).
    Vraća broj upisanih redova.
    """
    rate_date = rates_data.get("rate_date")
    if not rate_date:
        raise ValueError("Nema rate_date u podacima")

    conn = connect()
    cur = conn.cursor()

    inserted = 0
    for r in rates_data["rates"]:
        src = r["source"]
        tgt = r["target"]
        rate = r["rate"]

        cur.execute("""
            INSERT INTO exchange_rates (source_currency, target_currency, rate, rate_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_currency, target_currency, rate_date)
            DO UPDATE SET
                rate = excluded.rate,
                fetched_at = CURRENT_TIMESTAMP
        """, (src, tgt, rate, rate_date))
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def get_cached_rate(source, target):
    """
    Čita najnoviji kurs iz baze za dati par.
    Vraća dict ili None.
    """
    source = source.upper()
    target = target.upper()

    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT rate, rate_date, source_currency, target_currency
        FROM exchange_rates
        WHERE source_currency = ? AND target_currency = ?
        ORDER BY rate_date DESC
        LIMIT 1
    """, (source, target))
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "rate": row["rate"],
            "rate_date": row["rate_date"],
            "source": row["source_currency"],
            "target": row["target_currency"],
            "cached": True,
        }
    return None