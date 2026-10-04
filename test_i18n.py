# test_i18n.py
from flask import Flask
from i18n import t, get_locale, set_locale

app = Flask(__name__)
app.secret_key = "test"

with app.test_request_context("/"):
    print("=== Default jezik ===")
    print("get_locale():", get_locale())
    print("t('dashboard'):", t("dashboard"))
    print("t('kpi_orders'):", t("kpi_orders"))
    print()

    print("=== Prebacivanje na EN ===")
    set_locale("en")
    print("get_locale():", get_locale())
    print("t('dashboard'):", t("dashboard"))
    print("t('kpi_orders'):", t("kpi_orders"))
    print()

    print("=== Nepostojeći ključ ===")
    print("t('nepostojeci_kljuc'):", t("nepostojeci_kljuc"))