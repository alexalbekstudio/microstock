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


# --- Boje ---
CRNA = (17, 17, 17)
SIVA = (120, 120, 120)
SVETLO_SIVA = (240, 240, 240)
ZELENA = (39, 174, 96)
CRVENA = (217, 83, 79)


class InvoicePDF(FPDF):
    """Podklasa FPDF za fakturu."""

    def header(self):
        # Logo / naziv
        self.set_font("DejaVu", "B", 20)
        self.set_text_color(*CRNA)
        self.cell(0, 10, "MicroStock", ln=True, align="L")
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
    pdf.cell(90, 5, f"Datum: {order['created_at'][:10]}", align="R", ln=True)
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