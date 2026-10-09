# currency.py
"""
Formatiranje i konverzija valuta.

Sve cene u bazi su u RSD (bazna valuta).
Korisnik može da izabere prikaz u RSD, EUR ili USD.
Konverzija ide preko NBS kursa (currency_rates.py).
"""

from currency_rates import get_rate, get_cached_rate

# Bazna valuta — sve u bazi je u ovoj valuti
BASE_CURRENCY = "RSD"

# Podržane valute za prikaz
SUPPORTED_CURRENCIES = {
    "RSD": {
        "symbol": "din",
        "decimals": 0,
        "thousands": ".",
        "decimal_sep": ",",
        "position": "suffix",
        "label": "Srpski dinar",
    },
    "EUR": {
        "symbol": "€",
        "decimals": 2,
        "thousands": ".",
        "decimal_sep": ",",
        "position": "prefix",
        "label": "Euro",
    },
    "USD": {
        "symbol": "$",
        "decimals": 2,
        "thousands": ",",
        "decimal_sep": ".",
        "position": "prefix",
        "label": "US Dollar",
    },
}


def format_money(amount, currency="RSD"):
    """
    Formatira broj po pravilima valute.

    format_money(1234.5, "RSD")  -> "1.234 din"
    format_money(1234.5, "EUR")  -> "€1.234,50"
    format_money(1234.5, "USD")  -> "$1,234.50"
    """
    if amount is None:
        return "—"

    currency = currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        currency = BASE_CURRENCY

    cfg = SUPPORTED_CURRENCIES[currency]
    decimals = cfg["decimals"]

    rounded = round(float(amount), decimals)

    if decimals == 0:
        num_str = f"{int(rounded):,}"
    else:
        num_str = f"{rounded:,.{decimals}f}"

    num_str = num_str.replace(",", "§")
    num_str = num_str.replace(".", cfg["decimal_sep"])
    num_str = num_str.replace("§", cfg["thousands"])

    if cfg["position"] == "prefix":
        return f"{cfg['symbol']}{num_str}"
    else:
        return f"{num_str} {cfg['symbol']}"


def convert(amount, from_currency, to_currency):
    """
    Konvertuje iz jedne valute u drugu preko NBS kursa.

    NBS objavljuje samo strane valute -> RSD.
    Za RSD -> strana valuta koristimo inverzni kurs.

    convert(1000, "RSD", "EUR") -> 8.51 (ako je EUR=117.4948)
    convert(10, "EUR", "RSD")   -> 1174.948
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return float(amount)

    if amount is None:
        return None

    # RSD -> strana valuta: podeli kursom (inverzno)
    if from_currency == BASE_CURRENCY:
        rate = get_rate(to_currency, BASE_CURRENCY)
        return float(amount) / rate["rate"]

    # strana valuta -> RSD: pomnoži kursom
    if to_currency == BASE_CURRENCY:
        rate = get_rate(from_currency, BASE_CURRENCY)
        return float(amount) * rate["rate"]

    # Cross: EUR -> USD = EUR -> RSD -> USD
    rate_from = get_rate(from_currency, BASE_CURRENCY)
    rate_to = get_rate(to_currency, BASE_CURRENCY)
    return float(amount) * rate_from["rate"] / rate_to["rate"]


def get_display_currency():
    """
    Vraća valutu za prikaz iz sesije/trenutnog korisnika.
    Fallback: RSD.
    """
    try:
        from flask import session
        from flask_login import current_user

        if "currency" in session:
            return session["currency"]

        if current_user and hasattr(current_user, "currency") and current_user.currency:
            return current_user.currency
    except Exception:
        pass

    return BASE_CURRENCY


def display_money(amount_rsd, force_currency=None):
    """
    Prikazuje iznos konvertovan u izabranu valutu.
    Ako kurs nije dostupan — prikazuje iznos u RSD (fallback).
    NIKAD ne puca.
    """
    try:
        from currency import get_display_currency
        currency = force_currency or get_display_currency()
    except Exception:
        currency = "RSD"

    if amount_rsd is None:
        amount_rsd = 0

    try:
        amount_rsd = float(amount_rsd)
    except (ValueError, TypeError):
        return str(amount_rsd)

    # Ako je već RSD — samo formatiraj
    if currency == "RSD" or currency == BASE_CURRENCY:
        return format_money(amount_rsd, "RSD")

    # Pokušaj konverziju, ali ne pucaj ako nema kursa
    try:
        converted = convert(amount_rsd, BASE_CURRENCY, currency)
    except Exception as e:
        # Fallback: prikaži u RSD
        return format_money(amount_rsd, "RSD")

    return format_money(converted, currency)