# test_rates.py
from currency_rates import fetch_nbs_latest, save_rates_to_db, get_cached_rate

print("=== 1) fetch_nbs_latest ===")
r = fetch_nbs_latest()
print("Datum:", r["rate_date"])
print("Broj valuta:", len(r["rates"]))
eur = [x for x in r["rates"] if x["source"] == "EUR"]
usd = [x for x in r["rates"] if x["source"] == "USD"]
print("EUR->RSD:", eur)
print("USD->RSD:", usd)

print()
print("=== 2) save_rates_to_db ===")
n = save_rates_to_db(r)
print(f"Upisano {n} kursva za {r['rate_date']}")

print()
print("=== 3) get_cached_rate ===")
print("EUR:", get_cached_rate("EUR", "RSD"))
print("USD:", get_cached_rate("USD", "RSD"))