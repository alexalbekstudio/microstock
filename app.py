# app.py

from dotenv import load_dotenv
load_dotenv()   # ← MORA PRVO, pre svega što čita env

import csv
import io
import json
import os

from datetime import datetime

from flask import (Flask, render_template, request, redirect, url_for,
                   jsonify, abort, Response, flash, send_file)
from flask_login import login_required, current_user

import analytics
from database import init_db
import models
import pricing
import projects as proj
from auth import (auth_bp, login_manager, ensure_admin_exists,
                  role_required, is_admin)
from mailer import init_mail, send_test_email
from scheduler import init_scheduler
from backup import create_backup, list_backups, BACKUP_DIR
from users import (list_users, get_user, create_user, update_user,
                   change_password, toggle_active, delete_user, count_admins)
from i18n import t, get_locale, available_languages
from currency import get_display_currency, display_money, SUPPORTED_CURRENCIES

# ==================== APP INIT ====================

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "promeni-me-u-produkciji")
app.register_blueprint(auth_bp)
login_manager.init_app(app)

init_mail(app)
init_scheduler(app)

# ==================== JINJA GLOBALNE ====================

@app.context_processor
def inject_i18n_and_currency():
    """Ubacuje t(), display_money(), jezik i valutu u sve template-e."""
    return {
        "t": t,
        "display_money": display_money,
        "current_lang": get_locale(),
        "available_languages": available_languages(),
        "current_currency": get_display_currency(),
        "available_currencies": SUPPORTED_CURRENCIES,
    }


@app.context_processor
def inject_currency_rates():
    """
    Ubacuje kurs EUR/USD → RSD u sve template-e.
    Koristi se u JS-u za konverziju u Chart.js tooltip-ovima.
    Nikad ne puca — fallback vrednosti ako NBS API nije dostupan.
    """
    from currency_rates import get_rate
    try:
        eur = get_rate("EUR", "RSD")["rate"]
    except Exception:
        eur = 117.2
    try:
        usd = get_rate("USD", "RSD")["rate"]
    except Exception:
        usd = 108.5
    return {
        "eur_rate": eur,
        "usd_rate": usd,
    }

# ==================== JEZIK I VALUTA ====================

@app.route("/set-language/<lang>")
def set_language(lang):
    """Postavlja jezik (sesija + baza ako je ulogovan)."""
    from i18n import set_locale
    from flask import session

    if not set_locale(lang):
        abort(400)

    if current_user.is_authenticated:
        from db_adapter import connect
        conn = connect()
        conn.execute("UPDATE users SET language=%s WHERE id=%s",
                     (lang, current_user.id))
        conn.commit()
        conn.close()

    flash("Jezik promenjen." if lang == "sr" else "Language changed.", "ok")
    return redirect(request.referrer or url_for("index"))


@app.route("/set-currency/<cur>")
def set_currency(cur):
    """Postavlja valutu prikaza (sesija + baza ako je ulogovan)."""
    from flask import session

    cur = cur.upper()
    if cur not in SUPPORTED_CURRENCIES:
        abort(400)

    session["currency"] = cur

    if current_user.is_authenticated:
        from db_adapter import connect
        conn = connect()
        conn.execute("UPDATE users SET currency=%s WHERE id=%s",
                     (cur, current_user.id))
        conn.commit()
        conn.close()

    flash("Valuta promenjena.", "ok")
    return redirect(request.referrer or url_for("index"))

# ==================== ZABORAVLJENA ŠIFRA ====================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Forma za unos email-a → šalje link za reset."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        # Uvek ista poruka — ne otkrivamo da li email postoji
        generic_msg = "Ako nalog postoji, poslali smo link za reset šifre na tvoj email."

        if not email:
            flash(generic_msg, "ok")
            return redirect(url_for("auth.login"))

        from db_adapter import connect
        import secrets
        from datetime import datetime, timedelta

        conn = connect()
        try:
            user = conn.execute(
                "SELECT id, email FROM users WHERE email=%s AND active=1",
                (email,)
            ).fetchone()

            if user:
                token = secrets.token_urlsafe(32)
                expires = datetime.now() + timedelta(hours=1)

                conn.execute("""
                    INSERT INTO password_resets (user_id, token, expires_at)
                    VALUES (%s, %s, %s)
                """, (user["id"], token, expires))
                conn.commit()

                # Napravi URL
                reset_url = url_for("reset_password", token=token, _external=True)

                # Pošalji email
                from mailer import send_password_reset
                send_password_reset(user["email"], reset_url)
        finally:
            conn.close()

        flash(generic_msg, "ok")
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Forma za novu šifru."""
    from db_adapter import connect
    from werkzeug.security import generate_password_hash

    conn = connect()
    try:
        # Nađi validan token
        row = conn.execute("""
            SELECT pr.id AS reset_id, pr.user_id, pr.expires_at, pr.used,
                   u.email
            FROM password_resets pr
            JOIN users u ON u.id = pr.user_id
            WHERE pr.token = %s
        """, (token,)).fetchone()

        invalid = (
            not row
            or row["used"]
            or row["expires_at"] < datetime.now()
        )

        if invalid:
            flash("Link je istekao ili je već iskorišćen. Zatraži novi.", "err")
            return redirect(url_for("forgot_password"))

        if request.method == "POST":
            new_pw = request.form.get("password", "")
            new_pw2 = request.form.get("password2", "")

            if len(new_pw) < 6:
                flash("Šifra mora imati bar 6 znakova.", "err")
                return render_template("reset_password.html", token=token)

            if new_pw != new_pw2:
                flash("Šifre se ne poklapaju.", "err")
                return render_template("reset_password.html", token=token)

            pw_hash = generate_password_hash(new_pw)

            # Update šifre + markiraj token kao iskorišćen
            conn.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                         (pw_hash, row["user_id"]))
            conn.execute("UPDATE password_resets SET used=1 WHERE id=%s",
                         (row["reset_id"],))
            conn.commit()

            flash("Šifra je promenjena. Možeš se prijaviti.", "ok")
            return redirect(url_for("auth.login"))

    finally:
        conn.close()

    return render_template("reset_password.html", token=token)

# ==================== HELPER: role sets ====================

ALL_ROLES = ("admin", "manager", "viewer")
EDIT_ROLES = ("admin", "manager")
ADMIN_ONLY = ("admin",)


# ==================== DASHBOARD ====================

@app.route("/")
@login_required
@role_required(*ALL_ROLES)
def index():
    days = request.args.get("days", type=int) or 30
    import dashboard
    data = dashboard.control_center(days)

    # Kurs za JS konverziju u chart-ovima
    from currency_rates import get_rate
    try:
        eur_rate = get_rate("EUR", "RSD")["rate"]
    except Exception:
        eur_rate = 117.2
    try:
        usd_rate = get_rate("USD", "RSD")["rate"]
    except Exception:
        usd_rate = 108.5

    data["eur_rate"] = eur_rate
    data["usd_rate"] = usd_rate
    return render_template("index.html", **data)


# ==================== PROIZVODI ====================

@app.route("/products")
@login_required
@role_required(*ALL_ROLES)
def products():
    search   = request.args.get("q", "").strip()
    only_low = request.args.get("low") == "1"
    show_all = request.args.get("all") == "1"
    return render_template(
        "products.html",
        products=models.list_products(search, only_low, include_inactive=show_all),
        low=models.low_stock_products(),
        search=search, only_low=only_low, show_all=show_all
    )


@app.route("/products/add", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def add_product():
    try:
        models.add_product(
            sku=request.form["sku"].strip(),
            name=request.form["name"].strip(),
            price=float(request.form["price"]),
            cost=float(request.form.get("cost") or 0),
            stock=int(request.form.get("stock") or 0),
            low_stock_at=int(request.form.get("low_stock_at") or 3),
        )
        flash("Proizvod dodat.", "ok")
    except Exception as e:
        flash(f"Greška: {e}", "err")
    return redirect(url_for("products"))


@app.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@login_required
@role_required(*EDIT_ROLES)
def edit_product(pid):
    p = models.get_product(pid)
    if not p:
        abort(404)
    if request.method == "POST":
        models.update_product(
            pid,
            request.form["sku"].strip(),
            request.form["name"].strip(),
            float(request.form["price"]),
            float(request.form.get("cost") or 0),
            int(request.form.get("stock") or 0),
            int(request.form.get("low_stock_at") or 3),
        )
        flash("Proizvod sačuvan.", "ok")
        return redirect(url_for("products"))
    return render_template("product_edit.html", p=p)


@app.route("/products/<int:pid>/delete", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def delete_product(pid):
    models.archive_product(pid)
    flash("Proizvod arhiviran.", "ok")
    return redirect(url_for("products"))


# ==================== NARUDŽBINE ====================

@app.route("/orders")
@login_required
@role_required(*ALL_ROLES)
def orders():
    status     = request.args.get("status") or None
    channel_id = request.args.get("channel_id") or None
    search     = request.args.get("q") or None
    return render_template(
        "orders.html",
        orders=models.list_orders(status, int(channel_id) if channel_id else None, search),
        products=models.list_products(),
        channels=models.list_channels(),
        f_status=status, f_channel=channel_id, f_search=search or ""
    )


@app.route("/orders/new", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def new_order():
    product_ids = request.form.getlist("product_id[]")
    qtys        = request.form.getlist("qty[]")
    items = []
    for pid, q in zip(product_ids, qtys):
        if not pid or not q:
            continue
        items.append({"product_id": int(pid), "qty": int(q)})

    if not items:
        flash("Narudžbina mora imati bar jednu stavku.", "err")
        return redirect(url_for("orders"))

    order_id, dup = models.create_order(
        customer_name=request.form["customer_name"].strip(),
        channel_id=int(request.form["channel_id"]),
        items=items,
        note=request.form.get("note", ""),
        shipping_cost=float(request.form.get("shipping_cost") or 0),
        shipping_method=request.form.get("shipping_method", "").strip(),
    )
    if dup:
        flash("Narudžbina već postoji (duplikat).", "err")
    return redirect(url_for("invoice", order_id=order_id))


@app.route("/orders/<int:order_id>")
@login_required
@role_required(*ALL_ROLES)
def order_detail(order_id):
    order, items = models.get_order(order_id)
    if not order:
        abort(404)
    return render_template("order_edit.html",
                           order=order, items=items,
                           channels=models.list_channels())


@app.route("/orders/<int:order_id>/edit", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def edit_order(order_id):
    models.update_order(
        order_id,
        request.form["customer_name"].strip(),
        int(request.form["channel_id"]),
        request.form.get("note", ""),
        request.form["status"],
        shipping_cost=float(request.form.get("shipping_cost") or 0),
        shipping_method=request.form.get("shipping_method", "").strip(),
    )
    flash("Narudžbina sačuvana.", "ok")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<int:order_id>/delete", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def delete_order(order_id):
    models.delete_order(order_id)
    flash("Narudžbina obrisana (zalihe vraćene).", "ok")
    return redirect(url_for("orders"))


@app.route("/orders/<int:order_id>/status/<status>", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def change_status(order_id, status):
    if status not in ("new", "paid", "shipped", "done", "cancelled"):
        abort(400)
    models.set_order_status(order_id, status)
    return redirect(request.referrer or url_for("orders"))


# ==================== RAČUN ====================

@app.route("/invoice/<int:order_id>")
@login_required
@role_required(*ALL_ROLES)
def invoice(order_id):
    order, items = models.get_order(order_id)
    if not order:
        abort(404)
    subtotal = sum(float(i["qty"]) * float(i["unit_price"]) for i in items)
    fee = subtotal * (float(order["fee_percent"] or 0) / 100.0)
    total = subtotal + fee
    return render_template("invoice.html",
                           order=order, items=items,
                           subtotal=subtotal, fee=fee, total=total)


@app.route("/invoice/<int:order_id>.pdf")
@login_required
@role_required(*ALL_ROLES)
def invoice_pdf(order_id):
    order, items = models.get_order(order_id)
    if not order:
        abort(404)

    order = dict(order)
    items = [dict(i) for i in items]

    from currency import get_display_currency, convert, SUPPORTED_CURRENCIES
    currency = get_display_currency()
    symbol = SUPPORTED_CURRENCIES[currency]["symbol"]

    subtotal_rsd = sum(float(i["qty"]) * float(i["unit_price"]) for i in items)
    fee_rsd = subtotal_rsd * (float(order["fee_percent"] or 0) / 100.0)
    total_rsd = subtotal_rsd + fee_rsd

    if currency != "RSD":
        subtotal = convert(subtotal_rsd, "RSD", currency)
        fee = convert(fee_rsd, "RSD", currency)
        total = convert(total_rsd, "RSD", currency)
    else:
        subtotal, fee, total = subtotal_rsd, fee_rsd, total_rsd

    from pdf import generate_invoice_pdf
    pdf_bytes = generate_invoice_pdf(
        order, items, subtotal, fee, total,
        currency=currency, currency_symbol=symbol,
    )

    filename = f"racun-{order_id:05d}-{currency}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )

@app.route("/analytics.pdf")
@login_required
@role_required(*ALL_ROLES)
def analytics_pdf():
    """PDF izveštaj analitike."""
    days = request.args.get("days", type=int)

    from currency import get_display_currency, SUPPORTED_CURRENCIES
    currency = get_display_currency()
    symbol = SUPPORTED_CURRENCIES[currency]["symbol"]

    # Uzmi sve podatke iz analytics modula
    kpi = analytics.overview(days)
    channels = analytics.by_channel(days)
    products = analytics.by_product(days, limit=20)
    customers = analytics.top_customers(days, limit=20)

    from pdf import generate_analytics_pdf
    pdf_bytes = generate_analytics_pdf(
        kpi=kpi,
        channels=[dict(c) for c in channels] if channels else [],
        products=[dict(p) for p in products] if products else [],
        loss=[],
        customers=[dict(c) for c in customers] if customers else [],
        days=days,
        currency=currency,
        currency_symbol=symbol,
        title="Analitika prodaje" if get_locale() == "sr" else "Sales analytics",
    )

    filename = f"analitika-{days or 'all'}-{currency}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/projects/<int:pid>.pdf")
@login_required
@role_required(*ALL_ROLES)
def project_pdf(pid):
    """PDF izveštaj projekta."""
    p = proj.get_project(pid)
    if not p:
        abort(404)

    p = dict(p)
    time_entries = [dict(t) for t in proj.list_time(pid)]
    expenses = [dict(e) for e in proj.list_expenses(pid)]

    from currency import get_display_currency, SUPPORTED_CURRENCIES, convert
    currency = get_display_currency()
    symbol = SUPPORTED_CURRENCIES[currency]["symbol"]

    # Konvertuj KPI vrednosti ako nije RSD
    if currency != "RSD":
        try:
            for k in ("contract_value", "total_cost", "profit"):
                if p.get(k):
                    p[k] = convert(float(p[k]), "RSD", currency)
            for t in time_entries:
                if t.get("cost"):
                    t["cost"] = convert(float(t["cost"]), "RSD", currency)
            for e in expenses:
                if e.get("amount"):
                    e["amount"] = convert(float(e["amount"]), "RSD", currency)
        except Exception:
            pass  # fallback na RSD

    from pdf import generate_project_pdf
    pdf_bytes = generate_project_pdf(
        project=p,
        time_entries=time_entries,
        expenses=expenses,
        currency_symbol=symbol,
    )

    filename = f"projekat-{pid:05d}-{currency}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )

# ==================== CSV EXPORT ====================

@app.route("/export/products.csv")
@login_required
@role_required(*ALL_ROLES)
def export_products():
    rows = models.list_products(include_inactive=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "sku", "name", "price", "cost", "stock",
                "low_stock_at", "active", "created_at"])
    for r in rows:
        w.writerow([r["id"], r["sku"], r["name"], r["price"], r["cost"],
                    r["stock"], r["low_stock_at"], r["active"], r["created_at"]])
    return _csv_response(buf, "products.csv")


@app.route("/export/orders.csv")
@login_required
@role_required(*ALL_ROLES)
def export_orders():
    rows = models.list_orders()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "customer_name", "channel", "status", "total",
                "created_at", "source", "external_id"])
    for r in rows:
        w.writerow([r["id"], r["customer_name"], r["channel"], r["status"],
                    r["total"] or 0, r["created_at"], r["source"],
                    r["external_id"] or ""])
    return _csv_response(buf, "orders.csv")


def _csv_response(buf, filename):
    data = buf.getvalue().encode("utf-8-sig")   # BOM za Excel
    return Response(
        data, mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/admin/import-logs")
@login_required
@role_required(*ADMIN_ONLY)
def import_logs():
    """Istorija importa."""
    from db_adapter import connect
    conn = connect()
    try:
        rows = conn.execute("""
            SELECT l.*, u.name AS user_name, u.email AS user_email
            FROM import_logs l
            LEFT JOIN users u ON u.id = l.user_id
            ORDER BY l.created_at DESC
            LIMIT 200
        """).fetchall()
    except Exception as e:
        flash(f"Greška pri čitanju log-a: {e}", "err")
        rows = []
    finally:
        conn.close()

    # Normalizuj u dict (SQLite Row → dict)
    logs = []
    for r in rows:
        try:
            d = dict(r)
        except (TypeError, ValueError):
            d = r
        logs.append(d)

    return render_template("import_logs.html", logs=logs)

# ==================== WEBHOOK SINHRONIZACIJA ====================

@app.route("/webhook/orders", methods=["POST"])
def webhook_orders():
    """
    Očekivani JSON:
    {
      "source": "etsy",
      "external_id": "ETSY-12345",
      "customer_name": "Marko",
      "channel": "Etsy",              # ime kanala (ili channel_id)
      "items": [ {"sku": "TSHIRT-M", "qty": 2} ],
      "note": "opciono"
    }
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "invalid json"}), 400

    source = payload.get("source", "webhook")
    ext_id = payload.get("external_id")
    try:
        channel_id = _resolve_channel(payload)
        items = _resolve_items(payload.get("items", []))
        order_id, dup = models.create_order(
            customer_name=payload.get("customer_name", "Nepoznat kupac"),
            channel_id=channel_id,
            items=items,
            note=payload.get("note", ""),
            external_id=ext_id,
            source=source,
        )
        models.log_sync(source, ext_id, order_id, payload,
                        "duplicate" if dup else "ok")
        return jsonify({"order_id": order_id, "duplicate": dup}), (200 if dup else 201)
    except Exception as e:
        models.log_sync(source, ext_id, None, payload, "error", str(e))
        return jsonify({"error": str(e)}), 400


def _resolve_channel(payload):
    if "channel_id" in payload:
        return int(payload["channel_id"])
    name = payload.get("channel")
    if not name:
        raise ValueError("Nedostaje 'channel' ili 'channel_id'")
    from db_adapter import connect as db_connect
    conn = db_connect()
    row = conn.execute("SELECT id FROM channels WHERE name=%s", (name,)).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Nepoznat kanal: {name}")
    return row["id"]


def _resolve_items(items_in):
    """items_in može biti [{'sku':..., 'qty':...}] ili [{'product_id':..., 'qty':...}]"""
    from db_adapter import connect as db_connect
    conn = db_connect()
    out = []
    for it in items_in:
        qty = int(it.get("qty", 0))
        if qty <= 0:
            continue
        if "product_id" in it:
            out.append({"product_id": int(it["product_id"]), "qty": qty})
        elif "sku" in it:
            row = conn.execute("SELECT id FROM products WHERE sku=%s", (it["sku"],)).fetchone()
            if not row:
                raise ValueError(f"Nepoznat SKU: {it['sku']}")
            out.append({"product_id": row["id"], "qty": qty})
        else:
            raise ValueError("Stavka mora imati 'sku' ili 'product_id'")
    conn.close()
    if not out:
        raise ValueError("Nema validnih stavki")
    return out


# ==================== API ====================

@app.route("/api/low-stock")
def api_low_stock():
    return jsonify([dict(r) for r in models.low_stock_products()])


# ==================== ANALITIKA (ALAT #2) ====================

@app.route("/analytics")
@login_required
@role_required(*ALL_ROLES)
def analytics_view():
    days = request.args.get("days", type=int)

    # Kurs za JS konverziju
    from currency_rates import get_rate
    try:
        eur_rate = get_rate("EUR", "RSD")["rate"]
    except Exception:
        eur_rate = 117.2
    try:
        usd_rate = get_rate("USD", "RSD")["rate"]
    except Exception:
        usd_rate = 108.5

    return render_template(
        "analytics.html",
        days=days,
        kpi=analytics.overview(days),
        channels=analytics.by_channel(days),
        products=analytics.by_product(days, limit=15),
        trend=analytics.trend(days or 30),
        loss=analytics.loss_makers(days),
        customers=analytics.top_customers(days, limit=10),
        eur_rate=eur_rate,
        usd_rate=usd_rate,
    )

# ==================== KALKULATOR CENA ====================

@app.route("/pricing")
@login_required
@role_required(*ALL_ROLES)
def pricing_view():
    """Kalkulator cena — forma + live JS kalkulacija."""
    products = models.list_products(include_inactive=False)
    channels = models.list_channels()
    presets = pricing.list_presets()
    return render_template(
        "pricing.html",
        products=products,
        channels=channels,
        presets=presets,
        edit_roles=EDIT_ROLES,
    )


@app.route("/pricing/apply", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def pricing_apply():
    """Primeni izračunatu cenu na proizvod + upiši u istoriju."""
    product_id = request.form.get("product_id", type=int)
    new_price  = request.form.get("new_price", type=float)

    # Podaci iz kalkulatora za istoriju
    cost     = request.form.get("cost", type=float) or 0
    shipping = request.form.get("shipping", type=float) or 0
    fee_pct  = request.form.get("fee_pct", type=float) or 0
    tax_pct  = request.form.get("tax_pct", type=float) or 0
    margin_pct = request.form.get("margin_pct", type=float) or 0

    if not product_id or new_price is None or new_price <= 0:
        flash("Neispravan proizvod ili cena.", "err")
        return redirect(url_for("pricing_view"))

    p = models.get_product(product_id)
    if not p:
        flash("Proizvod nije nađen.", "err")
        return redirect(url_for("pricing_view"))

    models.update_product(
        product_id,
        p["sku"],
        p["name"],
        new_price,
        p["cost"] or 0,
        p["stock"] or 0,
        p["low_stock_at"] or 3,
    )

    # Upiši u istoriju
    try:
        analysis = pricing.analyze_price(cost, new_price, fee_pct, shipping, tax_pct)
        pricing.log_calculation(
            user_id=current_user.id,
            product_id=product_id,
            product_name=p["name"],
            mode="recommended",
            cost=cost, shipping=shipping,
            fee_pct=fee_pct, tax_pct=tax_pct, margin_pct=margin_pct,
            price=new_price,
            profit=analysis["profit"],
            markup_pct=analysis["markup_pct"],
            applied=True,
        )
    except Exception:
        pass  # istorija nije kritična

    flash(f"Cena proizvoda '{p['name']}' postavljena na {new_price:.2f} RSD.", "ok")
    return redirect(url_for("pricing_view"))


@app.route("/pricing/log", methods=["POST"])
@login_required
@role_required(*ALL_ROLES)
def pricing_log():
    """Ručno upiši kalkulaciju u istoriju (kad ne primenjuješ na proizvod)."""
    data = request.get_json(silent=True) or request.form
    mode = data.get("mode", "recommended")

    try:
        pricing.log_calculation(
            user_id=current_user.id,
            product_id=data.get("product_id") or None,
            product_name=data.get("product_name") or None,
            mode=mode,
            cost=data.get("cost") or 0,
            shipping=data.get("shipping") or 0,
            fee_pct=data.get("fee_pct") or 0,
            tax_pct=data.get("tax_pct") or 0,
            margin_pct=data.get("margin_pct") or 0,
            price=data.get("price") or 0,
            profit=data.get("profit") or 0,
            markup_pct=data.get("markup_pct") or 0,
            applied=False,
        )
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/pricing/history")
@login_required
@role_required(*ALL_ROLES)
def pricing_history():
    """Istorija kalkulacija."""
    # Viewer vidi samo svoje, admin/manager vide sve
    if current_user.role in ("admin", "manager"):
        logs = pricing.list_history(limit=200)
    else:
        logs = pricing.list_history(limit=200, user_id=current_user.id)

    return render_template("pricing_history.html", logs=logs)


# ==================== BULK KALKULACIJA ====================

@app.route("/pricing/bulk", methods=["GET", "POST"])
@login_required
@role_required(*EDIT_ROLES)
def pricing_bulk():
    """Bulk izračun preporučenih cena za sve proizvode."""
    presets = pricing.list_presets()

    if request.method == "POST":
        margin_pct = request.form.get("margin_pct", type=float) or 30
        fee_pct    = request.form.get("fee_pct", type=float) or 0
        tax_pct    = request.form.get("tax_pct", type=float) or 0
        shipping   = request.form.get("shipping", type=float) or 0
        only_low   = request.form.get("only_low") == "on"

        products = models.list_products(include_inactive=False)

        rows = []
        for p in products:
            if only_low and (p["stock"] or 0) > (p["low_stock_at"] or 3):
                continue
            cost = float(p["cost"] or 0)
            try:
                rec = pricing.recommended_price(
                    cost=cost, margin_pct=margin_pct,
                    fee_pct=fee_pct, shipping=shipping, tax_pct=tax_pct
                )
                rows.append({
                    "product": p,
                    "current_price": float(p["price"] or 0),
                    "recommended": rec["price"],
                    "profit": rec["profit"],
                    "margin_pct": rec["margin_pct"],
                    "diff": rec["price"] - float(p["price"] or 0),
                })
            except ValueError as e:
                rows.append({
                    "product": p,
                    "current_price": float(p["price"] or 0),
                    "recommended": None,
                    "error": str(e),
                    "diff": 0,
                })

        return render_template(
            "pricing_bulk.html",
            presets=presets,
            rows=rows,
            params={
                "margin_pct": margin_pct,
                "fee_pct": fee_pct,
                "tax_pct": tax_pct,
                "shipping": shipping,
                "only_low": only_low,
            }
        )

    return render_template(
        "pricing_bulk.html",
        presets=presets,
        rows=None,
        params={"margin_pct": 30, "fee_pct": 0, "tax_pct": 0, "shipping": 0, "only_low": False}
    )


@app.route("/pricing/bulk/apply", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def pricing_bulk_apply():
    """Primeni izabrane preporučene cene na proizvode."""
    product_ids = request.form.getlist("apply_product_id[]")
    new_prices  = request.form.getlist("apply_new_price[]")

    if not product_ids:
        flash("Nema izabranih proizvoda.", "err")
        return redirect(url_for("pricing_bulk"))

    updated = 0
    for pid_str, price_str in zip(product_ids, new_prices):
        try:
            pid = int(pid_str)
            new_price = float(price_str)
            if new_price <= 0:
                continue
            p = models.get_product(pid)
            if not p:
                continue
            models.update_product(
                pid, p["sku"], p["name"], new_price,
                p["cost"] or 0, p["stock"] or 0, p["low_stock_at"] or 3,
            )
            updated += 1
        except Exception:
            continue

    flash(f"Ažurirano {updated} proizvoda.", "ok")
    return redirect(url_for("pricing_bulk"))


# ==================== PRESETI KANALA (admin) ====================

@app.route("/pricing/presets")
@login_required
@role_required(*ADMIN_ONLY)
def pricing_presets():
    """Lista preseta kanala."""
    presets = pricing.list_presets()
    return render_template("pricing_presets.html", presets=presets)


@app.route("/pricing/presets/new", methods=["POST"])
@login_required
@role_required(*ADMIN_ONLY)
def pricing_preset_new():
    name = request.form.get("name", "").strip()
    fee  = request.form.get("fee_pct", type=float) or 0
    tax  = request.form.get("tax_pct", type=float) or 0

    if not name:
        flash("Naziv je obavezan.", "err")
        return redirect(url_for("pricing_presets"))

    try:
        pricing.add_preset(name, fee, tax)
        flash(f"Preset '{name}' dodat.", "ok")
    except Exception as e:
        flash(f"Greška: {e}", "err")

    return redirect(url_for("pricing_presets"))


@app.route("/pricing/presets/<int:preset_id>/edit", methods=["POST"])
@login_required
@role_required(*ADMIN_ONLY)
def pricing_preset_edit(preset_id):
    name = request.form.get("name", "").strip()
    fee  = request.form.get("fee_pct", type=float) or 0
    tax  = request.form.get("tax_pct", type=float) or 0

    try:
        pricing.update_preset(preset_id, name, fee, tax)
        flash("Preset sačuvan.", "ok")
    except Exception as e:
        flash(f"Greška: {e}", "err")

    return redirect(url_for("pricing_presets"))


@app.route("/pricing/presets/<int:preset_id>/delete", methods=["POST"])
@login_required
@role_required(*ADMIN_ONLY)
def pricing_preset_delete(preset_id):
    try:
        pricing.delete_preset(preset_id)
        flash("Preset obrisan.", "ok")
    except Exception as e:
        flash(f"Greška: {e}", "err")

    return redirect(url_for("pricing_presets"))

# ==================== PROJEKTI (ALAT #3) ====================

@app.route("/projects")
@login_required
@role_required(*ALL_ROLES)
def projects_view():
    status = request.args.get("status") or None
    return render_template(
        "projects.html",
        projects=proj.list_projects(status),
        overview=proj.projects_overview(),
        f_status=status,
    )


@app.route("/projects/new", methods=["GET", "POST"])
@login_required
@role_required(*EDIT_ROLES)
def project_new():
    if request.method == "POST":
        proj.add_project(
            code=request.form["code"].strip(),
            name=request.form["name"].strip(),
            client=request.form.get("client", "").strip(),
            contract_value=float(request.form.get("contract_value") or 0),
            start_date=request.form.get("start_date") or None,
            deadline=request.form.get("deadline") or None,
            notes=request.form.get("notes", ""),
        )
        flash("Projekat kreiran.", "ok")
        return redirect(url_for("projects_view"))
    return render_template("project_form.html", p=None)


@app.route("/projects/<int:pid>")
@login_required
@role_required(*ALL_ROLES)
def project_detail(pid):
    p = proj.get_project(pid)
    if not p:
        abort(404)
    return render_template(
        "project_detail.html",
        p=p,
        time_entries=proj.list_time(pid),
        expenses=proj.list_expenses(pid),
        members=proj.list_members(),
    )


@app.route("/projects/<int:pid>/edit", methods=["GET", "POST"])
@login_required
@role_required(*EDIT_ROLES)
def project_edit(pid):
    p = proj.get_project(pid)
    if not p:
        abort(404)
    if request.method == "POST":
        proj.update_project(
            pid,
            code=request.form["code"].strip(),
            name=request.form["name"].strip(),
            client=request.form.get("client", "").strip(),
            contract_value=float(request.form.get("contract_value") or 0),
            start_date=request.form.get("start_date") or None,
            deadline=request.form.get("deadline") or None,
            status=request.form["status"],
            notes=request.form.get("notes", ""),
        )
        flash("Projekat sačuvan.", "ok")
        return redirect(url_for("project_detail", pid=pid))
    return render_template("project_form.html", p=p)


@app.route("/projects/<int:pid>/delete", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def project_delete(pid):
    proj.delete_project(pid)
    flash("Projekat obrisan.", "ok")
    return redirect(url_for("projects_view"))


# --- Sati ---

@app.route("/projects/<int:pid>/time/add", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def time_add(pid):
    proj.add_time(
        pid,
        int(request.form["member_id"]),
        request.form["entry_date"],
        float(request.form["hours"]),
        request.form.get("description", ""),
    )
    return redirect(url_for("project_detail", pid=pid))


@app.route("/time/<int:entry_id>/delete", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def time_delete(entry_id):
    from db_adapter import connect as db_connect
    conn = db_connect()
    e = conn.execute("SELECT project_id FROM time_entries WHERE id=?", (entry_id,)).fetchone()
    conn.close()
    proj.delete_time(entry_id)
    return redirect(url_for("project_detail", pid=e["project_id"]))


# --- Troškovi ---

@app.route("/projects/<int:pid>/expense/add", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def expense_add(pid):
    proj.add_expense(
        pid,
        request.form["expense_date"],
        request.form.get("category", "").strip(),
        request.form.get("description", "").strip(),
        float(request.form["amount"]),
    )
    return redirect(url_for("project_detail", pid=pid))


@app.route("/expense/<int:eid>/delete", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def expense_delete(eid):
    from db_adapter import connect as db_connect
    conn = db_connect()
    e = conn.execute("SELECT project_id FROM project_expenses WHERE id=?", (eid,)).fetchone()
    conn.close()
    proj.delete_expense(eid)
    return redirect(url_for("project_detail", pid=e["project_id"]))


# --- Tim ---

@app.route("/team/add", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def team_add():
    proj.add_member(
        request.form["name"].strip(),
        request.form.get("role", "").strip(),
        float(request.form.get("hourly_rate") or 0),
    )
    flash("Član tima dodat.", "ok")
    return redirect(request.referrer or url_for("projects_view"))

# ==================== ADMIN: KURS ====================

@app.route("/admin/currency-rates")
@login_required
@role_required(*ADMIN_ONLY)
def admin_currency_rates():
    """Prikaz svih kurseva + forma za ručni unos."""
    import currency_rates

    rates = currency_rates.list_all_rates()
    # Uvek prikaži i EUR i USD, čak i ako nisu u bazi
    existing = {r["source"] for r in rates}
    for code in ("EUR", "USD"):
        if code not in existing:
            rates.append({
                "source": code,
                "target": "RSD",
                "rate": None,
                "rate_date": None,
                "fetched_at": None,
            })

    return render_template(
        "admin_currency_rates.html",
        rates=sorted(rates, key=lambda r: r["source"]),
    )


@app.route("/admin/currency-rates/set", methods=["POST"])
@login_required
@role_required(*ADMIN_ONLY)
def admin_currency_rates_set():
    """Ručno postavi kurs."""
    import currency_rates

    source = request.form.get("source", "").strip().upper()
    target = request.form.get("target", "RSD").strip().upper()
    rate_str = request.form.get("rate", "").strip()

    if not source or source == target:
        flash("Neispravan izvor valute.", "err")
        return redirect(url_for("admin_currency_rates"))

    try:
        rate = float(rate_str)
        if rate <= 0:
            raise ValueError
    except (ValueError, TypeError):
        flash("Kurs mora biti pozitivan broj.", "err")
        return redirect(url_for("admin_currency_rates"))

    try:
        currency_rates.set_manual_rate(source, target, rate)
        flash(f"Kurs {source}→{target} = {rate:.4f} sačuvan.", "success")
    except Exception as e:
        flash(f"Greška: {e}", "err")

    return redirect(url_for("admin_currency_rates"))


@app.route("/admin/currency-rates/refresh", methods=["POST"])
@login_required
@role_required(*ADMIN_ONLY)
def admin_currency_rates_refresh():
    """Osveži sve kurseve iz NBS API-ja."""
    import currency_rates

    ok, n, msg = currency_rates.refresh_from_nbs()
    flash(msg, "success" if ok else "err")
    return redirect(url_for("admin_currency_rates"))

# ==================== ADMIN: EMAIL TEST ====================

@app.route("/admin/test-email")
@login_required
@role_required(*ADMIN_ONLY)
def admin_test_email():
    ok = send_test_email()
    flash("Test email poslat ✅" if ok else "Greška — proveri log",
          "success" if ok else "danger")
    return redirect(url_for("auth.profile"))

@app.route("/admin/test-report/<period>")
@app.route("/admin/test-report/<period>/<lang>")
@login_required
@role_required(*ADMIN_ONLY)
def admin_test_report(period, lang=None):
    """
    Ručno pošalji izveštaj.
    - Bez `lang` u URL-u: uvek SR (za brzi test na srpskom)
    - Sa `lang` u URL-u: forsiraj taj jezik (npr. /en)
    """
    if period not in ("week", "month"):
        abort(400)

    # Ako lang NIJE prosleđen u URL-u — forsiraj SR
    if lang is None:
        lang = "sr"

    if lang not in ("sr", "en"):
        abort(400)

    # Valuta — koristi korisnikovu (RSD/EUR/USD)
    currency = getattr(current_user, "currency", None) or "RSD"

    from reports import send_report
    ok = send_report(period, lang=lang, currency=currency)

    if ok:
        flash(f"Test izveštaj ({period}/{lang}/{currency}) poslat ✅", "success")
    else:
        flash("Greška — proveri log", "danger")

    return redirect(url_for("auth.profile"))

# ==================== ADMIN: BACKUP ====================

@app.route("/admin/backup-db")
@login_required
@role_required(*ADMIN_ONLY)
def admin_backup_db():
    try:
        path = create_backup()
    except Exception as e:
        flash(f"Greška pri backup-u: {e}", "error")
        return redirect(url_for("auth.profile"))

    return send_file(
        path,
        as_attachment=True,
        download_name=path.name,
    )


@app.route("/admin/backups")
@login_required
@role_required(*ADMIN_ONLY)
def admin_backups():
    return render_template("backups.html", backups=list_backups())


# ==================== ADMIN: KORISNICI ====================

@app.route("/admin/users")
@login_required
@role_required(*ADMIN_ONLY)
def admin_users():
    users = list_users()
    return render_template("users.html", users=users)


@app.route("/admin/users/new", methods=["GET", "POST"])
@login_required
@role_required(*ADMIN_ONLY)
def admin_user_new():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "viewer")

        if not email or not password or not name:
            flash("Email, ime i lozinka su obavezni.", "error")
        elif len(password) < 6:
            flash("Lozinka mora imati bar 6 znakova.", "error")
        elif role not in ALL_ROLES:
            flash("Nepoznata rola.", "error")
        else:
            try:
                create_user(email, name, password, role)
                flash(f"Korisnik {email} kreiran.", "success")
                return redirect(url_for("admin_users"))
            except Exception as e:
                flash(f"Greška: {e}", "error")

    return render_template("user_form.html", user=None, roles=ALL_ROLES)


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required(*ADMIN_ONLY)
def admin_user_edit(user_id):
    user = get_user(user_id)
    if not user:
        flash("Korisnik nije nađen.", "error")
        return redirect(url_for("admin_users"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "viewer")
        active = request.form.get("active") == "on"
        new_password = request.form.get("new_password", "").strip()

        if role not in ALL_ROLES:
            flash("Nepoznata rola.", "error")
            return redirect(url_for("admin_user_edit", user_id=user_id))

        # Zaštita: ne smeš sebi skinuti admin rolu ako si poslednji admin
        if user_id == current_user.id and user["role"] == "admin" and role != "admin":
            if count_admins() <= 1:
                flash("Ne možeš skinuti admin rolu — ti si poslednji admin.", "error")
                return redirect(url_for("admin_user_edit", user_id=user_id))

        try:
            update_user(user_id, email, name, role, active)
            if new_password:
                if len(new_password) < 6:
                    flash("Nova lozinka mora imati bar 6 znakova.", "error")
                    return redirect(url_for("admin_user_edit", user_id=user_id))
                change_password(user_id, new_password)
            flash("Korisnik sačuvan.", "success")
            return redirect(url_for("admin_users"))
        except Exception as e:
            flash(f"Greška: {e}", "error")

    return render_template("user_form.html", user=user, roles=ALL_ROLES)


@app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@login_required
@role_required(*ADMIN_ONLY)
def admin_user_toggle(user_id):
    if user_id == current_user.id:
        flash("Ne možeš deaktivirati sam sebe.", "error")
        return redirect(url_for("admin_users"))

    user = get_user(user_id)
    if user and user["role"] == "admin" and user["active"] and count_admins() <= 1:
        flash("Ne možeš deaktivirati poslednjeg admina.", "error")
        return redirect(url_for("admin_users"))

    new_state = toggle_active(user_id)
    if new_state is None:
        flash("Korisnik nije nađen.", "error")
    else:
        flash("Korisnik aktiviran." if new_state else "Korisnik deaktiviran.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required(*ADMIN_ONLY)
def admin_user_delete(user_id):
    if user_id == current_user.id:
        flash("Ne možeš obrisati sam sebe.", "error")
        return redirect(url_for("admin_users"))

    user = get_user(user_id)
    if user and user["role"] == "admin" and count_admins() <= 1:
        flash("Ne možeš obrisati poslednjeg admina.", "error")
        return redirect(url_for("admin_users"))

    delete_user(user_id)
    flash("Korisnik obrisan.", "success")
    return redirect(url_for("admin_users"))


# ==================== TEMPLATE FILTER ====================

@app.template_filter("money")
def money_filter(value, decimals=0):
    try:
        n = float(value)
        if decimals == 0:
            return f"{n:,.0f}".replace(",", ".")
        return f"{n:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return value


# ==================== INIT DB ====================

if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    init_db()
    ensure_admin_exists()
    # Osveži VIEW-ove (DROP + CREATE) da bi PostgreSQL pokupio ispravne tipove kolona
    try:
        from refresh_views import refresh_views
        refresh_views()
    except Exception as e:
        print(f"⚠️  refresh_views preskočen: {e}")

# ==================== IMPORT IZ CSV ====================

from importers import (PRESETS, read_csv, build_mapping, validate_mapping,
                       import_rows)


@app.route("/import", methods=["GET", "POST"])
@login_required
@role_required(*EDIT_ROLES)
def import_view():
    """Forma za upload + mapiranje."""
    if request.method == "POST":
        # Korak 1: upload fajla → preview
        file = request.files.get("csv_file")
        preset_key = request.form.get("preset", "generic")

        if not file or not file.filename:
            flash("Izaberi CSV fajl.", "err")
            return redirect(url_for("import_view"))

        raw = file.read()
        try:
            fieldnames, rows = read_csv(raw)
        except Exception as e:
            flash(f"Greška pri čitanju CSV-a: {e}", "err")
            return redirect(url_for("import_view"))

        if not rows:
            flash("CSV je prazan.", "err")
            return redirect(url_for("import_view"))

        mapping = build_mapping(preset_key, fieldnames)
        errors = validate_mapping(mapping)

        # Sačuvaj privremeno u sesiji (za korak 2)
        from flask import session
        session["import_csv"] = raw.decode("utf-8-sig", errors="replace")
        session["import_filename"] = file.filename
        session["import_preset"] = preset_key

        return render_template(
            "import_preview.html",
            fieldnames=fieldnames,
            rows=rows[:10],
            total_rows=len(rows),
            mapping=mapping,
            errors=errors,
            preset_key=preset_key,
            presets=PRESETS,
            channels=models.list_channels(),
        )

    return render_template("import.html", presets=PRESETS)


@app.route("/import/confirm", methods=["POST"])
@login_required
@role_required(*EDIT_ROLES)
def import_confirm():
    """Korak 2: potvrda i sam import."""
    from flask import session

    raw = session.get("import_csv")
    filename = session.get("import_filename", "upload.csv")
    preset_key = request.form.get("preset", session.get("import_preset", "generic"))

    if not raw:
        flash("Sesija je istekla. Ponovi upload.", "err")
        return redirect(url_for("import_view"))

    try:
        fieldnames, rows = read_csv(raw.encode("utf-8"))
    except Exception as e:
        flash(f"Greška: {e}", "err")
        return redirect(url_for("import_view"))

    # Ručno mapiranje iz forme (override)
    overrides = {}
    for field in ("customer_name", "external_id", "order_date", "status", "note",
                  "items.sku", "items.name", "items.qty", "items.unit_price"):
        val = request.form.get(f"map_{field}", "").strip()
        if val:
            overrides[field] = val

    mapping = build_mapping(preset_key, fieldnames, overrides)
    errors = validate_mapping(mapping)
    if errors:
        for e in errors:
            flash(e, "err")
        return redirect(url_for("import_view"))

    # Kanal
    channel_id = request.form.get("channel_id", type=int)
    if not channel_id:
        # Ako preset ima fiksno ime kanala, nađi ga
        preset_channel = PRESETS.get(preset_key, {}).get("channel")
        if preset_channel:
            conn = connect()
            row = conn.execute("SELECT id FROM channels WHERE name=%s",
                               (preset_channel,)).fetchone()
            conn.close()
            if row:
                channel_id = row["id"]
        if not channel_id:
            flash("Izaberi kanal.", "err")
            return redirect(url_for("import_view"))

    auto_create = request.form.get("auto_create_products") == "on"
    source_name = preset_key

    results = import_rows(
        rows=rows,
        mapping=mapping,
        channel_id=channel_id,
        source_name=source_name,
        auto_create_products=auto_create,
        user_id=current_user.id,
        filename=filename,
    )

    # Očisti sesiju
    session.pop("import_csv", None)
    session.pop("import_filename", None)
    session.pop("import_preset", None)

    return render_template("import_result.html",
                           results=results,
                           filename=filename,
                           total=len(rows))

@app.route("/api/search")
@login_required
@role_required(*ALL_ROLES)
def api_search():
    """Globalna pretraga: proizvodi, narudžbine, projekti."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"products": [], "orders": [], "projects": []})

    from db_adapter import connect
    conn = connect()
    try:
        like = f"%{q}%"
        products = conn.execute("""
            SELECT id, sku, name, price FROM products
            WHERE active=1 AND (name ILIKE %s OR sku ILIKE %s)
            ORDER BY name LIMIT 5
        """, (like, like)).fetchall()

        orders = conn.execute("""
            SELECT id, customer_name, status, external_id FROM orders
            WHERE customer_name ILIKE %s OR external_id ILIKE %s
            ORDER BY id DESC LIMIT 5
        """, (like, like)).fetchall()

        projects = conn.execute("""
            SELECT id, code, name, client FROM projects
            WHERE name ILIKE %s OR code ILIKE %s OR client ILIKE %s
            ORDER BY id DESC LIMIT 5
        """, (like, like, like)).fetchall()
    finally:
        conn.close()

    return jsonify({
        "products": [dict(r) for r in products],
        "orders":   [dict(r) for r in orders],
        "projects": [dict(r) for r in projects],
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)