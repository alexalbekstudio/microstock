# test_currency.py
from currency import format_money, convert, display_money

print("=== 1) Formatiranje ===")
print("RSD 1234.5  ->", format_money(1234.5, "RSD"))
print("RSD 1234567 ->", format_money(1234567, "RSD"))
print("EUR 1234.5  ->", format_money(1234.5, "EUR"))
print("USD 1234.5  ->", format_money(1234.5, "USD"))

print()
print("=== 2) Konverzija (RSD -> EUR/USD) ===")
print("1000 RSD -> EUR:", convert(1000, "RSD", "EUR"))
print("1000 RSD -> USD:", convert(1000, "RSD", "USD"))

print()
print("=== 3) Konverzija nazad ===")
print("10 EUR -> RSD:", convert(10, "EUR", "RSD"))
print("10 USD -> RSD:", convert(10, "USD", "RSD"))

print()
print("=== 4) Cross (EUR -> USD) ===")
print("10 EUR -> USD:", convert(10, "EUR", "USD"))