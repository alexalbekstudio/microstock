# reports.py
"""
Periodični izveštaji — nedeljni i mesečni.
Podržava jezik primaoca (sr/en).
"""
import os
from datetime import date, timedelta

import analytics
from db_adapter import connect
from i18n import t, force_locale, clear_force_locale
from currency import format_money


# ==================== PERIOD ====================

def get_period_range(period="week"):
    """Vraća (start_date, end_date, label) za period."""
    today = date.today()

    if period == "week":
        monday_this_week = today - timedelta(days=today.weekday())
        monday_last_week = monday_this_week - timedelta(days=7)
        sunday_last_week = monday_last_week + timedelta(days=6)
        label = f"{monday_last_week.strftime('%d.%m.%Y')} — {sunday_last_week.strftime('%d.%m.%Y')}"
        return monday_last_week, sunday_last_week, label

    elif period == "month":
        first_this_month = today.replace(day=1)
        last_day_prev = first_this_month - timedelta(days=1)
        first_prev = last_day_prev.replace(day=1)
        label = first_prev.strftime("%B %Y")
        return first_prev, last_day_prev, label

    raise ValueError(f"Nepoznat period: {period}")


# ==================== JEZIK PRIMAOCA ====================

def _get_recipient_lang(email):
    """Vraća jezik korisnika po emailu. Fallback: sr."""
    if not email:
        return "sr"
    try:
        conn = connect()
        row = conn.execute(
            "SELECT language FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()
        if row:
            try:
                return row["language"] or "sr"
            except (TypeError, KeyError):
                return row[0] or "sr"
    except Exception:
        pass
    return "sr"

def _get_recipient_currency(email):
    """Vraća valutu korisnika po emailu. Fallback: RSD."""
    if not email:
        return "RSD"
    try:
        conn = connect()
        row = conn.execute(
            "SELECT currency FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()
        if row:
            try:
                return row["currency"] or "RSD"
            except (TypeError, KeyError):
                return row[0] or "RSD"
    except Exception:
        pass
    return "RSD"

# ==================== PRIKUPLJANJE PODATAKA ====================

def _days_between(start, end):
    today = date.today()
    return (today - start).days + 1


def collect_report_data(period="week"):
    """Prikuplja sve podatke za izveštaj."""
    start, end, label = get_period_range(period)
    days = _days_between(start, end)

    kpi       = analytics.overview(days)
    channels  = analytics.by_channel(days)
    products  = analytics.by_product(days, limit=5)
    customers = analytics.top_customers(days, limit=5)
    loss      = analytics.loss_makers(days)

    return {
        "period":    period,
        "label":     label,
        "start":     start.isoformat(),
        "end":       end.isoformat(),
        "kpi":       kpi,
        "channels":  channels,
        "products":  products,
        "customers": customers,
        "loss":      loss,
    }


# ==================== HTML ====================

def render_report_html(data, currency="RSD"):
    """Pravi HTML email za izveštaj. Jezik čita iz t(), valutu iz parametra."""
    from mailer import _wrap

    k = data["kpi"]

    def m(v):
        return format_money(v or 0, currency)

    kpi_html = f"""
      <table style="border-collapse:collapse;width:100%;margin:12px 0">
        <tr><td style="padding:6px 12px 6px 0"><b>{t('report_revenue')}:</b></td><td style="text-align:right">{m(k['revenue'])}</td></tr>
        <tr><td style="padding:6px 12px 6px 0">{t('report_fees')}:</td><td style="text-align:right">{m(k['fees'])}</td></tr>
        <tr><td style="padding:6px 12px 6px 0">{t('report_cost')}:</td><td style="text-align:right">{m(k['cost'])}</td></tr>
        <tr><td style="padding:6px 12px 6px 0">{t('report_shipping')}:</td><td style="text-align:right">{m(k['shipping'])}</td></tr>
        <tr style="border-top:2px solid #6366f1"><td style="padding:6px 12px 6px 0"><b>{t('report_profit')}:</b></td>
            <td style="text-align:right;color:{'#10b981' if k['profit'] >= 0 else '#dc2626'}"><b>{m(k['profit'])}</b></td></tr>
        <tr><td style="padding:6px 12px 6px 0">{t('report_margin')}:</td><td style="text-align:right">{k['margin']}%</td></tr>
        <tr><td style="padding:6px 12px 6px 0">{t('report_orders')}:</td><td style="text-align:right">{k['orders']}</td></tr>
        <tr><td style="padding:6px 12px 6px 0">{t('report_units')}:</td><td style="text-align:right">{k['units']}</td></tr>
      </table>
    """

    prod_rows = ""
    for p in data["products"]:
        prod_rows += (
            f"<tr><td style='padding:4px 12px 4px 0'>{p['product_name']}</td>"
            f"<td style='padding:4px 12px 4px 0;text-align:right'>{p['units']}</td>"
            f"<td style='padding:4px 12px 4px 0;text-align:right'>{m(p['revenue'])}</td>"
            f"<td style='padding:4px 12px 4px 0;text-align:right'><b>{m(p['profit'])}</b></td></tr>"
        )
    prod_html = f"""
      <h3 style="margin-top:20px">{t('report_top_products')}</h3>
      <table style="border-collapse:collapse;width:100%">
        <tr style="background:#f3f4f6">
          <th style="padding:6px;text-align:left">{t('report_col_product')}</th>
          <th style="padding:6px;text-align:right">{t('report_col_units')}</th>
          <th style="padding:6px;text-align:right">{t('report_col_revenue')}</th>
          <th style="padding:6px;text-align:right">{t('report_col_profit')}</th>
        </tr>
        {prod_rows or f'<tr><td colspan="4" style="padding:8px;color:#6b7280">{t("report_no_data")}</td></tr>'}
      </table>
    """

    ch_rows = ""
    for c in data["channels"]:
        ch_rows += (
            f"<tr><td style='padding:4px 12px 4px 0'>{c['channel_name']}</td>"
            f"<td style='padding:4px 12px 4px 0;text-align:right'>{c['orders']}</td>"
            f"<td style='padding:4px 12px 4px 0;text-align:right'>{m(c['revenue'])}</td>"
            f"<td style='padding:4px 12px 4px 0;text-align:right'><b>{m(c['profit'])}</b></td>"
            f"<td style='padding:4px 12px 4px 0;text-align:right'>{c['margin']}%</td></tr>"
        )
    ch_html = f"""
      <h3 style="margin-top:20px">{t('report_by_channel')}</h3>
      <table style="border-collapse:collapse;width:100%">
        <tr style="background:#f3f4f6">
          <th style="padding:6px;text-align:left">{t('report_col_channel')}</th>
          <th style="padding:6px;text-align:right">{t('report_col_orders')}</th>
          <th style="padding:6px;text-align:right">{t('report_col_revenue')}</th>
          <th style="padding:6px;text-align:right">{t('report_col_profit')}</th>
          <th style="padding:6px;text-align:right">{t('report_col_margin')}</th>
        </tr>
        {ch_rows or f'<tr><td colspan="5" style="padding:8px;color:#6b7280">{t("report_no_data")}</td></tr>'}
      </table>
    """

    loss_html = ""
    if data["loss"]:
        loss_items = "".join(
            f"<li>{l['product_name']} ({l['sku']}) — {t('report_loss_word')} {m(l['profit'])}</li>"
            for l in data["loss"]
        )
        loss_html = f"""
          <h3 style="margin-top:20px;color:#dc2626">{t('report_losses')}</h3>
          <ul style="color:#dc2626">{loss_items}</ul>
        """

    body = f"""
      <p>{t('report_for_period')} <b>{data['label']}</b></p>
      {kpi_html}
      {prod_html}
      {ch_html}
      {loss_html}
    """

    period_label = t("report_period_week") if data["period"] == "week" else t("report_period_month")
    title = f"{period_label} — {data['label']}"
    return _wrap(title, "#6366f1", body)


# ==================== PDF ====================

def render_report_pdf(data, currency="RSD"):
    """Pravi PDF izveštaj koristeći FPDF."""
    try:
        from fpdf import FPDF
        from pathlib import Path
    except ImportError:
        return None

    PDF = FPDF(orientation="P", unit="mm", format="A4")
    PDF.add_page()

    fonts_dir = Path(__file__).parent / "fonts"
    regular = str(fonts_dir / "DejaVuSans.ttf")
    bold    = str(fonts_dir / "DejaVuSans-Bold.ttf")
    if Path(regular).exists() and Path(bold).exists():
        PDF.add_font("DejaVu", "", regular)
        PDF.add_font("DejaVu", "B", bold)
        FONT = "DejaVu"
    else:
        FONT = "Helvetica"

    def m(v):
        return format_money(v or 0, currency)

    period_label = t("report_period_week") if data["period"] == "week" else t("report_period_month")

    PDF.set_font(FONT, "B", 18)
    PDF.cell(0, 12, f"{period_label} — {data['label']}", ln=1)

    PDF.set_font(FONT, "", 11)
    PDF.set_text_color(100)
    PDF.cell(0, 8, f"{t('report_period')}: {data['start']} → {data['end']}", ln=1)
    PDF.set_text_color(0)
    PDF.ln(4)

    k = data["kpi"]
    PDF.set_font(FONT, "B", 13)
    PDF.cell(0, 8, t("report_kpi_title"), ln=1)
    PDF.set_font(FONT, "", 11)

    kpi_rows = [
        (t("report_revenue"),   m(k["revenue"])),
        (t("report_fees"),      m(k["fees"])),
        (t("report_cost"),      m(k["cost"])),
        (t("report_shipping"),  m(k["shipping"])),
        (t("report_profit"),    m(k["profit"])),
        (t("report_margin"),    f"{k['margin']}%"),
        (t("report_orders"),    str(k["orders"])),
        (t("report_units"),     str(k["units"])),
    ]
    for label, val in kpi_rows:
        is_profit = label == t("report_profit")
        PDF.set_font(FONT, "B" if is_profit else "", 11)
        PDF.cell(80, 7, label, border=0)
        PDF.cell(0, 7, val, border=0, ln=1)
    PDF.ln(4)

    PDF.set_font(FONT, "B", 13)
    PDF.cell(0, 8, t("report_top_products"), ln=1)
    PDF.set_font(FONT, "B", 10)
    PDF.cell(80, 7, t("report_col_product"), border="B")
    PDF.cell(25, 7, t("report_col_units"), border="B", align="R")
    PDF.cell(40, 7, t("report_col_revenue"), border="B", align="R")
    PDF.cell(0, 7, t("report_col_profit"), border="B", align="R", ln=1)
    PDF.set_font(FONT, "", 10)
    for p in data["products"]:
        PDF.cell(80, 6, p["product_name"][:40], border=0)
        PDF.cell(25, 6, str(p["units"]), border=0, align="R")
        PDF.cell(40, 6, m(p["revenue"]), border=0, align="R")
        PDF.cell(0, 6, m(p["profit"]), border=0, align="R", ln=1)
    PDF.ln(4)

    PDF.set_font(FONT, "B", 13)
    PDF.cell(0, 8, t("report_by_channel"), ln=1)
    PDF.set_font(FONT, "B", 10)
    PDF.cell(60, 7, t("report_col_channel"), border="B")
    PDF.cell(25, 7, t("report_col_orders"), border="B", align="R")
    PDF.cell(40, 7, t("report_col_revenue"), border="B", align="R")
    PDF.cell(40, 7, t("report_col_profit"), border="B", align="R")
    PDF.cell(0, 7, t("report_col_margin"), border="B", align="R", ln=1)
    PDF.set_font(FONT, "", 10)
    for c in data["channels"]:
        PDF.cell(60, 6, c["channel_name"], border=0)
        PDF.cell(25, 6, str(c["orders"]), border=0, align="R")
        PDF.cell(40, 6, m(c["revenue"]), border=0, align="R")
        PDF.cell(40, 6, m(c["profit"]), border=0, align="R")
        PDF.cell(0, 6, f"{c['margin']}%", border=0, align="R", ln=1)

    return bytes(PDF.output())


# ==================== SLANJE ====================

def send_report(period="week", to_email=None, lang=None, currency=None):
    """
    Šalje izveštaj.
    - lang=None → čita iz baze po emailu primaoca
    - currency=None → čita iz baze po emailu primaoca
    """
    try:
        to_email = to_email or os.getenv("REPORT_EMAIL") or os.getenv("ALERT_EMAIL")

        # Odredi jezik
        if not lang:
            lang = _get_recipient_lang(to_email)

        # Odredi valutu
        if not currency:
            currency = _get_recipient_currency(to_email)

        # Postavi force_locale za ovaj thread
        prev = force_locale(lang)
        try:
            data = collect_report_data(period)
            html = render_report_html(data, currency=currency)

            pdf_bytes = None
            pdf_filename = None
            if os.getenv("REPORT_INCLUDE_PDF", "true").lower() == "true":
                pdf_bytes = render_report_pdf(data, currency=currency)
                if pdf_bytes:
                    pdf_filename = f"report-{period}-{data['end']}.pdf"

            period_key = "report_subject_week" if period == "week" else "report_subject_month"
            subject = t(period_key, label=data["label"])

            from mailer import send_report_email
            return send_report_email(to_email, subject, html, pdf_bytes, pdf_filename)
        finally:
            if prev:
                force_locale(prev)
            else:
                clear_force_locale()

    except Exception as e:
    
        try:
            from flask import current_app
            current_app.logger.error(f"Report greška: {e}")
        except Exception:
            print(f"Report greška: {e}")
        return False