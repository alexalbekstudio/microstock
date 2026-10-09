# mailer.py
"""
Email notifikacije za MicroStock.
- Sends via Flask-Mail (Gmail SMTP)
- Templates su inline (HTML + plain text fallback)
- Sve funkcije vraćaju True/False (ne dižu exception da ne sruše request)
"""
import os
from flask import current_app
from flask_mail import Mail, Message
import base64
from pathlib import Path
mail = Mail()


def init_mail(app):
    """Pozovi iz app.py: init_mail(app)"""
    app.config.update(
        MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
        MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "true").lower() == "true",
        MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME")),
        MAIL_SUPPRESS_SEND=not os.getenv("MAIL_USERNAME"),  # ako nema creds, samo loguj
    )
    mail.init_app(app)


def _alert_recipient():
    return os.getenv("ALERT_EMAIL") or os.getenv("MAIL_USERNAME")


def _send(subject, html, text=None):
    """Wrap za slanje — nikad ne ruši request."""
    try:
        to = _alert_recipient()
        if not to:
            current_app.logger.warning("MAIL: nema ALERT_EMAIL, preskačem.")
            return False
        msg = Message(subject=subject, recipients=[to])
        msg.html = html
        msg.body = text or _html_to_text(html)
        mail.send(msg)
        current_app.logger.info(f"MAIL: poslato → {to} | {subject}")
        return True
    except Exception as e:
        current_app.logger.error(f"MAIL greška: {e}")
        return False


def _html_to_text(html):
    """Grubi fallback ako nema plain text-a."""
    import re
    return re.sub(r"<[^>]+>", "", html).strip()


# ============================================================
# ŠABLONI
# ============================================================

def _wrap(title, color, body_html):
    """Email šablon sa logom u header-u (URL do javne slike)."""
    import os
    base_url = os.getenv("PUBLIC_URL", "https://microstock.onrender.com")
    logo_url = f"{base_url}/static/img/logo-wordmark.png"

    DARK = "#0f172a"   # tamna boja iz sidebar-a

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;
                border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">

      <div style="background:{DARK};padding:24px 20px;text-align:center">
        <img src="{logo_url}" alt="MicroStock"
             style="max-width:180px;height:auto;display:block;margin:0 auto">
      </div>

      <div style="background:{color};color:#fff;padding:12px 20px 16px;
                  text-align:center;font-size:16px;font-weight:700">
        MicroStock — {title}
      </div>

      <div style="padding:20px;color:#111827;font-size:14px;line-height:1.6">
        {body_html}
      </div>

      <div style="background:#f9fafb;color:#6b7280;padding:12px 20px;
                  font-size:12px;border-top:1px solid #e5e7eb;text-align:center">
        Automatska poruka iz MicroStock. Ne odgovaraj na ovaj email.<br>
        <a href="mailto:alexalbekstudio.design@gmail.com"
           style="color:#6366f1;text-decoration:none">
          alexalbekstudio.design@gmail.com
        </a>
      </div>
    </div>
    """


# ============================================================
# 1) PROJEKAT — 80% budžeta (warn)
# ============================================================
def send_project_warn(project, pct, spent, budget):
    subject = f"⚠️ Projekat '{project['name']}' je na {pct:.0f}% budžeta"
    body = f"""
      <p>Projekat <b>{project['name']}</b>
         ({project.get('client') or 'bez klijenta'}) je prešao <b>80% budžeta</b>.</p>
      <table style="border-collapse:collapse;margin:12px 0">
        <tr><td style="padding:4px 12px 4px 0"><b>Budžet:</b></td>
            <td>{budget:.2f} €</td></tr>
        <tr><td style="padding:4px 12px 4px 0"><b>Potrošeno:</b></td>
            <td>{spent:.2f} €</td></tr>
        <tr><td style="padding:4px 12px 4px 0"><b>Iskorišćeno:</b></td>
            <td><b>{pct:.1f}%</b></td></tr>
      </table>
      <p>Preporuka: proveri troškove i preostale sate tima.</p>
    """
    return _send(subject, _wrap("Alarm budžeta", "#f59e0b", body))


# ============================================================
# 2) PROJEKAT — 100% budžeta (danger)
# ============================================================
def send_project_danger(project, pct, spent, budget):
    subject = f"🚨 KREŠENJE: Projekat '{project['name']}' je prekoračio budžet"
    body = f"""
      <p>Projekat <b>{project['name']}</b>
         ({project.get('client') or 'bez klijenta'}) je prekoračio <b>100% budžeta</b>!</p>
      <table style="border-collapse:collapse;margin:12px 0">
        <tr><td style="padding:4px 12px 4px 0"><b>Budžet:</b></td>
            <td>{budget:.2f} €</td></tr>
        <tr><td style="padding:4px 12px 4px 0"><b>Potrošeno:</b></td>
            <td>{spent:.2f} €</td></tr>
        <tr><td style="padding:4px 12px 4px 0"><b>Prekoračenje:</b></td>
            <td><b style="color:#dc2626">{spent - budget:.2f} €</b></td></tr>
      </table>
      <p>Hitno: zaustavi dodatne troškove ili dogovori dodatni budžet sa klijentom.</p>
    """
    return _send(subject, _wrap("Kritično prekoračenje", "#dc2626", body))


# ============================================================
# 3) NISKE ZALIHE (dnevni digest)
# ============================================================
def send_low_stock_digest(products):
    if not products:
        return False
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'>{p['sku']}</td>"
        f"<td style='padding:4px 12px 4px 0'>{p['name']}</td>"
        f"<td style='padding:4px 12px 4px 0;color:#dc2626'><b>{p['stock']}</b></td>"
        f"<td style='padding:4px 12px 4px 0'>{p.get('low_stock_threshold', 5)}</td></tr>"
        for p in products
    )
    subject = f"📦 Niske zalihe: {len(products)} proizvod(a)"
    body = f"""
      <p>Sledeći proizvodi imaju niske zalihe:</p>
      <table style="border-collapse:collapse">
        <tr style="background:#f3f4f6">
          <th style="padding:6px 12px 6px 0;text-align:left">SKU</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Naziv</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Stanje</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Prag</th>
        </tr>
        {rows}
      </table>
    """
    return _send(subject, _wrap("Niske zalihe", "#2563eb", body))


# ============================================================
# 4) NARUDŽBINE KOJE ČEKAJU
# ============================================================
def send_pending_orders_digest(orders, days):
    if not orders:
        return False
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'>#{o['id']}</td>"
        f"<td style='padding:4px 12px 4px 0'>{o.get('customer') or '—'}</td>"
        f"<td style='padding:4px 12px 4px 0'>{o.get('status')}</td>"
        f"<td style='padding:4px 12px 4px 0'>{o.get('created_at', '')[:10]}</td></tr>"
        for o in orders
    )
    subject = f"⏳ {len(orders)} narudžbina čeka duže od {days} dana"
    body = f"""
      <p>Sledeće narudžbine nisu promenile status duže od <b>{days} dana</b>:</p>
      <table style="border-collapse:collapse">
        <tr style="background:#f3f4f6">
          <th style="padding:6px 12px 6px 0;text-align:left">#</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Kupac</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Status</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Datum</th>
        </tr>
        {rows}
      </table>
    """
    return _send(subject, _wrap("Narudžbine koje čekaju", "#f59e0b", body))


# ============================================================
# 5) ROKOVI PROJEKATA (14 dana)
# ============================================================
def send_deadlines_digest(projects):
    if not projects:
        return False
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'>{p['name']}</td>"
        f"<td style='padding:4px 12px 4px 0'>{p.get('client') or '—'}</td>"
        f"<td style='padding:4px 12px 4px 0'>{p.get('deadline', '')[:10]}</td></tr>"
        for p in projects
    )
    subject = f"📅 {len(projects)} projekat(a) sa rokom u narednih 14 dana"
    body = f"""
      <p>Sledeći projekti imaju rok u narednih <b>14 dana</b>:</p>
      <table style="border-collapse:collapse">
        <tr style="background:#f3f4f6">
          <th style="padding:6px 12px 6px 0;text-align:left">Projekat</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Klijent</th>
          <th style="padding:6px 12px 6px 0;text-align:left">Rok</th>
        </tr>
        {rows}
      </table>
    """
    return _send(subject, _wrap("Rokovi projekata", "#7c3aed", body))


# ============================================================
# TEST
# ============================================================
def send_test_email():
    return _send(
        "✅ MicroStock test email",
        _wrap("Test", "#10b981",
              "<p>Ako vidiš ovu poruku — email alarmi rade ispravno. 🎉</p>")
    )

def send_report_email(to_email, subject, html_body, pdf_bytes=None, pdf_filename=None):
    """
    Šalje izveštaj sa opcionim PDF attachment-om.
    Ne koristi _send() jer _send() uvek šalje na ALERT_EMAIL.
    """
    try:
        if not to_email:
            current_app.logger.warning("REPORT: nema REPORT_EMAIL, preskačem.")
            return False

        msg = Message(subject=subject, recipients=[to_email])
        msg.html = html_body
        msg.body = _html_to_text(html_body)

        if pdf_bytes and pdf_filename:
            msg.attach(
                filename=pdf_filename,
                content_type="application/pdf",
                data=pdf_bytes,
            )

        mail.send(msg)
        current_app.logger.info(f"REPORT: poslato → {to_email} | {subject}")
        return True
    except Exception as e:
        current_app.logger.error(f"REPORT greška: {e}")
        return False

def send_password_reset(to_email, reset_url):
    """
    Šalje email sa linkom za reset šifre.
    Vraća True/False.
    """
    subject = "🔐 MicroStock — Reset šifre"
    body = f"""
      <p>Zdravo,</p>
      <p>Neko je zatražio reset šifre za tvoj MicroStock nalog.</p>
      <p style="margin:24px 0">
        <a href="{reset_url}"
           style="background:#6366f1;color:#fff;padding:12px 24px;
                  border-radius:6px;text-decoration:none;font-weight:600">
          Postavi novu šifru
        </a>
      </p>
      <p>Ili kopiraj ovaj link u browser:</p>
      <p style="background:#f3f4f6;padding:8px 12px;border-radius:4px;
                font-family:monospace;font-size:12px;word-break:break-all">
        {reset_url}
      </p>
      <p><b>Link važi 1 sat.</b> Ako nisi ti zatražio reset — ignoriši ovaj email.</p>
    """
    return _send_to(to_email, subject, _wrap("Reset šifre", "#6366f1", body))


def _send_to(to_email, subject, html):
    """Kao _send, ali na proizvoljan email (ne ALERT_EMAIL)."""
    try:
        if not to_email:
            return False
        msg = Message(subject=subject, recipients=[to_email])
        msg.html = html
        msg.body = _html_to_text(html)
        mail.send(msg)
        current_app.logger.info(f"MAIL: poslato → {to_email} | {subject}")
        return True
    except Exception as e:
        current_app.logger.error(f"MAIL greška: {e}")
        return False