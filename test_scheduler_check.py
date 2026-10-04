# test_scheduler_check.py
from currency_rates import get_cached_rate

eur = get_cached_rate("EUR", "RSD")
usd = get_cached_rate("USD", "RSD")

print("EUR->RSD:", eur)
print("USD->RSD:", usd)

if eur and usd:
    print()
    print("✅ Scheduler je uspešno upisao NBS kurs u bazu.")
else:
    print()
    print("❌ Nema kursa u bazi — scheduler nije upisao.")