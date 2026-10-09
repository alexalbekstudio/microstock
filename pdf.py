# pdf.py
"""
Generator PDF faktura koristeći fpdf2 sa Unicode fontom (DejaVuSans).
Podržava naša slova: č, ć, š, ž, đ.
"""
from pathlib import Path
from datetime import datetime
from fpdf import FPDF


# --- Putanje do fontova ---
FONT_DIR = Path(__file__).parent / "fonts"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"

# --- Logo ---
LOGO_PATH = Path(__file__).parent / "static" / "img" / "logo-wordmark.png"

# --- Boje ---
CRNA = (17, 17, 17)
SIVA = (120, 120, 120)
SVETLO_SIVA = (240, 240, 240)
ZELENA = (39, 174, 96)
CRVENA = (217, 83, 79)


class InvoicePDF(FPDF):
    """Podklasa FPDF za fakturu."""

    def header(self):
        # Logo levo (ako postoji)
        if LOGO_PATH.exists():
            try:
                self.image(str(LOGO_PATH), x=10, y=8, w=40)
            except Exception:
                pass
        # Naziv aplikacije
        self.set_xy(55, 10)
        self.set_font("DejaVu", "B", 16)
        self.set_text_color(*CRNA)
        self.cell(0, 8, "MicroStock", ln=True, align="L")

        self.set_x(55)
        self.set_font("DejaVu", "", 9)
        self.set_text_color(*SIVA)
        self.cell(0, 5, "Tvoja online prodavnica", ln=True, align="L")

        # Linija ispod headera
        self.ln(4)
        self.set_draw_color(*CRNA)
        self.set_line_width(0.8)
        y = self.get_y()
        self.line(10, y, 200, y)
        self.ln(6)

    def footer(self):
        self.set_y(-20)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(*SIVA)
        self.cell(0, 5,
                  f"MicroStock · generisano {datetime.now().strftime('%d.%m.%Y %H:%M')} · Hvala na poverenju!",
                  align="C")


def generate_invoice_pdf(order, items, subtotal, fee, total,
                          currency="RSD", currency_symbol="din"):
    """Vraća bytes PDF fajla za datu narudžbinu u izabranoj valuti."""

    pdf = InvoicePDF(orientation="P", unit="mm", format="A4")

    pdf.add_font("DejaVu", "", str(FONT_REGULAR))
    pdf.add_font("DejaVu", "B", str(FONT_BOLD))
    pdf.add_font("DejaVu", "I", str(FONT_REGULAR))

    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ===== Zaglavlje desno =====
    pdf.set_xy(110, 12)
    pdf.set_font("DejaVu", "B", 16)
    pdf.set_text_color(*CRNA)
    pdf.cell(90, 8, f"RAČUN #{order['id']:05d}", align="R", ln=True)
    pdf.set_x(110)
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(*SIVA)
    # Konvertuj created_at u string (radi i za datetime i za string)
    created = order.get("created_at")
    if hasattr(created, "strftime"):
        created_str = created.strftime("%d.%m.%Y")
    elif created:
        created_str = str(created)[:10]
    else:
        created_str = "—"

    pdf.cell(90, 5, f"Datum: {created_str}", align="R", ln=True)
    pdf.set_x(110)
    pdf.cell(90, 5, f"Kanal: {order['channel']}", align="R", ln=True)
    pdf.set_x(110)
    pdf.cell(90, 5, f"Status: {order['status']}", align="R", ln=True)
    pdf.set_x(110)
    pdf.cell(90, 5, f"Valuta: {currency}", align="R", ln=True)
    pdf.set_text_color(0, 0, 0)

    pdf.set_y(45)

    # ===== Info box =====
    pdf.set_fill_color(*SVETLO_SIVA)
    pdf.set_font("DejaVu", "B", 9)
    pdf.set_text_color(*SIVA)
    pdf.cell(90, 6, "  KUPAC", ln=False, fill=True)
    pdf.cell(10, 6, "", ln=False)
    pdf.cell(90, 6, "  PODACI O RAČUNU", ln=True, fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(90, 7, "  " + order["customer_name"], ln=False)
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(10, 7, "", ln=False)
    pdf.cell(90, 7, f"  Broj: #{order['id']:05d}", ln=True)

    pdf.set_font("DejaVu", "", 10)
    if order.get("note"):
        pdf.cell(90, 6, "  " + str(order["note"])[:50], ln=False)
    else:
        pdf.cell(90, 6, "", ln=False)
    pdf.cell(10, 6, "", ln=False)
    pdf.cell(90, 6, f"  Izvor: {order.get('source') or 'manual'}", ln=True)

    pdf.cell(90, 6, "", ln=False)
    pdf.cell(10, 6, "", ln=False)
    if order.get("external_id"):
        pdf.cell(90, 6, f"  Ref: {order['external_id']}", ln=True)

    pdf.ln(6)

    # ===== Tabela stavki =====
    pdf.set_fill_color(*CRNA)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 9)
    pdf.cell(110, 8, "  PROIZVOD", fill=True)
    pdf.cell(20, 8, "KOL.", fill=True, align="C")
    pdf.cell(30, 8, f"CENA ({currency_symbol})", fill=True, align="R")
    pdf.cell(30, 8, "UKUPNO  ", fill=True, align="R", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("DejaVu", "", 10)
    fill = False
    for it in items:
        if fill:
            pdf.set_fill_color(250, 250, 250)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.cell(110, 8, "  " + str(it["product_name"])[:45], fill=True)
        pdf.cell(20, 8, str(it["qty"]), fill=True, align="C")
        pdf.cell(30, 8, f"{float(it['unit_price']):.2f}", fill=True, align="R")
        pdf.cell(30, 8, f"{float(it['qty']) * float(it['unit_price']):.2f}  ", fill=True, align="R", ln=True)
        fill = not fill

        pdf.set_font("DejaVu", "I", 8)
        pdf.set_text_color(*SIVA)
        pdf.cell(110, 4, "  " + str(it["sku"]), ln=True)
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(0, 0, 0)

    pdf.ln(4)

    # ===== Suma =====
    pdf.set_x(120)
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(*SIVA)
    pdf.cell(45, 6, "Osnova:", align="R")
    pdf.set_text_color(0, 0, 0)
    pdf.cell(35, 6, f"{float(subtotal):.2f} {currency_symbol}", align="R", ln=True)

    if float(fee) > 0:
        pdf.set_x(120)
        pdf.set_text_color(*SIVA)
        pdf.cell(45, 6, f"Provizija ({order['fee_percent']}%):", align="R")
        pdf.set_text_color(0, 0, 0)
        pdf.cell(35, 6, f"{float(fee):.2f} {currency_symbol}", align="R", ln=True)

    pdf.set_x(120)
    pdf.set_draw_color(*CRNA)
    pdf.set_line_width(0.5)
    y = pdf.get_y() + 1
    pdf.line(120, y, 200, y)
    pdf.ln(2)

    pdf.set_x(120)
    pdf.set_font("DejaVu", "B", 13)
    pdf.set_text_color(*CRNA)
    pdf.cell(45, 8, "UKUPNO:", align="R")
    pdf.cell(35, 8, f"{float(total):.2f} {currency_symbol}", align="R", ln=True)

    pdf.ln(10)
    pdf.set_x(120)
    pdf.set_text_color(*ZELENA)
    pdf.set_draw_color(*ZELENA)
    pdf.set_line_width(0.5)
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(40, 10, "PLAĆENO", border=1, align="C", ln=True)

    return bytes(pdf.output())

# ============================================================
# ANALYTICS PDF
# ============================================================

def generate_analytics_pdf(kpi, channels, products, loss, customers,
                            days=None, lang="sr", currency="RSD",
                            currency_symbol="din",
                            title="Analytics"):
    """Vraća bytes PDF izveštaja analitike."""
    from datetime import datetime as _dt

    pdf = InvoicePDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(FONT_REGULAR))
    pdf.add_font("DejaVu", "B", str(FONT_BOLD))
    pdf.add_font("DejaVu", "I", str(FONT_REGULAR))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Naslov + period
    pdf.set_xy(10, 12)
    pdf.set_font("DejaVu", "B", 18)
    pdf.set_text_color(*CRNA)
    pdf.cell(0, 10, title, ln=True, align="L")

    pdf.set_x(10)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(*SIVA)
    period_label = f"Period: {days} dana" if days else "Period: sve vreme"
    pdf.cell(0, 5, period_label, ln=True, align="L")

    pdf.set_x(10)
    pdf.cell(0, 5, f"Generisano: {_dt.now().strftime('%d.%m.%Y %H:%M')}", ln=True, align="L")

    pdf.ln(4)

    # === KPI ===
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*CRNA)
    pdf.cell(0, 8, "KPI", ln=True)

    pdf.set_font("DejaVu", "", 10)
    kpi_rows = [
        ("Prihod:",       f"{float(kpi.get('revenue', 0)):.2f} {currency_symbol}"),
        ("Provizije:",    f"{float(kpi.get('fees', 0)):.2f} {currency_symbol}"),
        ("Trošak robe:",  f"{float(kpi.get('cost', 0)):.2f} {currency_symbol}"),
        ("Dostava:",      f"{float(kpi.get('shipping', 0)):.2f} {currency_symbol}"),
        ("Profit:",       f"{float(kpi.get('profit', 0)):.2f} {currency_symbol}"),
        ("Marža:",        f"{kpi.get('margin', 0)}%"),
        ("Narudžbina:",   f"{kpi.get('orders', 0)}"),
    ]
    for label, value in kpi_rows:
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(60, 6, label)
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(0, 6, value, ln=True)

    # === Kanali ===
    if channels:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(*CRNA)
        pdf.cell(0, 8, "Prodaja po kanalima", ln=True)
        pdf.ln(2)

        # Header tabele
        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        headers = [("Kanal", 35), ("Prihod", 30), ("Proviz.", 25),
                   ("Trošak", 25), ("Dostava", 25), ("Profit", 30), ("Nar.", 15)]
        for h, w in headers:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for c in channels:
            pdf.cell(35, 6, str(c.get("channel_name", ""))[:20])
            pdf.cell(30, 6, f"{float(c.get('revenue', 0)):.2f}", align="R")
            pdf.cell(25, 6, f"{float(c.get('fees', 0)):.2f}", align="R")
            pdf.cell(25, 6, f"{float(c.get('cost', 0)):.2f}", align="R")
            pdf.cell(25, 6, f"{float(c.get('shipping', 0)):.2f}", align="R")
            pdf.cell(30, 6, f"{float(c.get('profit', 0)):.2f}", align="R")
            pdf.cell(15, 6, str(c.get("orders", 0)), align="C")
            pdf.ln()

    # === Top proizvodi ===
    if products:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(0, 8, "Top proizvodi", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        for h, w in [("SKU", 30), ("Naziv", 70), ("Kom", 20), ("Prihod", 30), ("Profit", 30)]:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for p in products[:20]:
            pdf.cell(30, 6, str(p.get("sku", ""))[:15])
            pdf.cell(70, 6, str(p.get("product_name", ""))[:35])
            pdf.cell(20, 6, str(p.get("units", 0)), align="C")
            pdf.cell(30, 6, f"{float(p.get('revenue', 0)):.2f}", align="R")
            pdf.cell(30, 6, f"{float(p.get('profit', 0)):.2f}", align="R")
            pdf.ln()

    # === Top kupci ===
    if customers:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(0, 8, "Top kupci", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        for h, w in [("Kupac", 120), ("Narudžbina", 30), ("Ukupno", 30)]:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for c in customers[:20]:
            pdf.cell(120, 6, str(c.get("customer_name", ""))[:50])
            pdf.cell(30, 6, str(c.get("orders", 0)), align="C")
            pdf.cell(30, 6, f"{float(c.get('revenue', 0)):.2f}", align="R")
            pdf.ln()

    return bytes(pdf.output())

# ============================================================
# PROJECT PDF
# ============================================================

def generate_project_pdf(project, time_entries, expenses,
                          currency_symbol="din", lang="sr"):
    """Vraća bytes PDF izveštaja projekta."""
    from datetime import datetime as _dt

    pdf = InvoicePDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(FONT_REGULAR))
    pdf.add_font("DejaVu", "B", str(FONT_BOLD))
    pdf.add_font("DejaVu", "I", str(FONT_REGULAR))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Naslov
    pdf.set_xy(10, 12)
    pdf.set_font("DejaVu", "B", 18)
    pdf.set_text_color(*CRNA)
    pdf.cell(0, 10, f"Projekat: {project.get('name', '')}", ln=True, align="L")

    pdf.set_x(10)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(*SIVA)
    pdf.cell(0, 5, f"Kod: {project.get('code', '—')}  ·  Klijent: {project.get('client', '—')}", ln=True, align="L")
    pdf.set_x(10)
    pdf.cell(0, 5, f"Rok: {project.get('deadline', '—')}  ·  Status: {project.get('status', '—')}", ln=True, align="L")
    pdf.set_x(10)
    pdf.cell(0, 5, f"Generisano: {_dt.now().strftime('%d.%m.%Y %H:%M')}", ln=True, align="L")

    pdf.ln(4)

    # KPI
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*CRNA)
    pdf.cell(0, 8, "KPI", ln=True)

    pdf.set_font("DejaVu", "", 10)
    kpi_rows = [
        ("Ugovorena vrednost:",  f"{float(project.get('contract_value', 0)):.2f} {currency_symbol}"),
        ("Ukupan trošak:",       f"{float(project.get('total_cost', 0)):.2f} {currency_symbol}"),
        ("Profit:",              f"{float(project.get('profit', 0)):.2f} {currency_symbol}"),
        ("Marža:",               f"{project.get('margin', 0)}%"),
        ("Radni sati:",          f"{float(project.get('total_hours', 0)):.1f} h"),
    ]
    for label, value in kpi_rows:
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(70, 6, label)
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(0, 6, value, ln=True)

    # Sati
    if time_entries:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(*CRNA)
        pdf.cell(0, 8, "Radni sati", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        for h, w in [("Datum", 30), ("Član", 60), ("Sati", 20), ("Opis", 80)]:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for t in time_entries:
            pdf.cell(30, 6, str(t.get("entry_date", ""))[:10])
            pdf.cell(60, 6, str(t.get("member_name", ""))[:30])
            pdf.cell(20, 6, f"{float(t.get('hours', 0)):.2f}", align="C")
            pdf.cell(80, 6, str(t.get("description", ""))[:50])
            pdf.ln()

    # Troškovi
    if expenses:
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(*CRNA)
        pdf.cell(0, 8, "Troškovi", ln=True)
        pdf.ln(2)

        pdf.set_fill_color(*CRNA)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 8)
        for h, w in [("Datum", 30), ("Kategorija", 40), ("Opis", 80), ("Iznos", 40)]:
            pdf.cell(w, 7, h, fill=True, align="C")
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 9)
        for e in expenses:
            pdf.cell(30, 6, str(e.get("expense_date", ""))[:10])
            pdf.cell(40, 6, str(e.get("category", ""))[:20])
            pdf.cell(80, 6, str(e.get("description", ""))[:50])
            pdf.cell(40, 6, f"{float(e.get('amount', 0)):.2f} {currency_symbol}", align="R")
            pdf.ln()

    return bytes(pdf.output())