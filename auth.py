# auth.py
"""
Autentifikacija - login, logout, zaštita ruta.
Inicijalni admin nalog se kreira automatski pri prvom pokretanju.

Podrazumevani kredencijali (PROMENI ODMAH posle prvog logina!):
  Email:  admin@microstock.local
  Šifra:  admin123
"""
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort)
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash

from db_adapter import connect

import capital as capital_mod

# ==================== USER MODEL ====================

class User(UserMixin):
    def __init__(self, id, email, name, role, language="sr", currency="RSD"):
        self.id = id
        self.email = email
        self.name = name
        self.role = role
        self.language = language
        self.currency = currency


# ==================== INICIJALIZACIJA ====================

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Moraš biti ulogovan da pristupiš ovoj stranici."
login_manager.login_message_category = "err"


@login_manager.user_loader
def load_user(user_id):
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
    conn.close()
    if not row or not row["active"]:
        return None
    return User(
        row["id"], row["email"], row["name"], row["role"],
        language=row["language"] if "language" in row.keys() else "sr",
        currency=row["currency"] if "currency" in row.keys() else "RSD",
    )


# ==================== POMOĆNE ====================

def get_user_by_email(email):
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE email=%s", (email,)).fetchone()
    conn.close()
    return row


def create_user(email, password, name="", role="admin"):
    """Napravi novog korisnika. Vraća id."""
    pw_hash = generate_password_hash(password)
    conn = connect()
    conn.execute(
        "INSERT INTO users (email, password_hash, name, role) VALUES (%s,%s,%s,%s)",
        (email.lower().strip(), pw_hash, name, role)
    )
    conn.commit()
    row = conn.execute("SELECT id FROM users WHERE email=%s", (email.lower().strip(),)).fetchone()
    conn.close()
    return row["id"]


def ensure_admin_exists():
    """Ako nema ni jednog korisnika, napravi podrazumevani admin nalog."""
    conn = connect()
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    conn.close()
    if row["n"] == 0:
        create_user(
            email="admin@microstock.local",
            password="admin123",
            name="Administrator",
            role="admin"
        )
        print("=" * 60)
        print("⚠️  KREIRAN PODRAZUMEVANI ADMIN NALOG:")
        print("    Email: admin@microstock.local")
        print("    Šifra: admin123")
        print("    ⚠️  PROMENI ŠIFRU ODMAH POSLE PRVOG LOGINA!")
        print("=" * 60)


# ==================== ROLE HELPERS ====================

def role_required(*roles):
    """
    Dekorator: dozvoli pristup samo korisnicima sa datim rolama.
    Primer: @role_required("admin")
            @role_required("admin", "manager")
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                flash("Nemaš dozvolu za ovu akciju.", "err")
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def is_admin():
    return current_user.is_authenticated and current_user.role == "admin"


def is_manager_or_admin():
    return current_user.is_authenticated and current_user.role in ("admin", "manager")


def can_edit():
    """Viewer ne može ništa da menja."""
    return current_user.is_authenticated and current_user.role in ("admin", "manager")


# ==================== RUTE ====================

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user_row = get_user_by_email(email)
        if user_row and check_password_hash(user_row["password_hash"], password):
            # Provera da li je nalog aktivan
            if not user_row["active"]:
                flash("Nalog je deaktiviran.", "err")
                return render_template("login.html")

            # Napravi User objekat
            user = User(
                user_row["id"],
                user_row["email"],
                user_row["name"],
                user_row["role"],
                language=user_row["language"] if "language" in user_row.keys() else "sr",
                currency=user_row["currency"] if "currency" in user_row.keys() else "RSD",
            )
            login_user(user, remember=True)

            # Postavi jezik i valutu u sesiju
            from flask import session
            session["lang"] = user.language
            session["currency"] = user.currency

            # Ažuriraj last_login
            conn = connect()
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id=%s",
                         (user.id,))
            conn.commit()
            conn.close()

            flash(f"Dobrodošao, {user.name or user.email}!", "ok")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        else:
            flash("Pogrešan email ili šifra.", "err")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Uspešno si se odjavio.", "ok")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        new_name = request.form.get("name", "").strip()
        new_email = request.form.get("email", "").strip().lower()

        conn = connect()
        row = conn.execute("SELECT password_hash FROM users WHERE id=%s",
                           (current_user.id,)).fetchone()

        if not check_password_hash(row["password_hash"], current_pw):
            conn.close()
            flash("Trenutna šifra nije tačna.", "err")
            return redirect(url_for("auth.profile"))

        # Promena email-a (ako je zadat i drugačiji)
        if new_email and new_email != current_user.email:
            existing = conn.execute(
                "SELECT id FROM users WHERE email=%s AND id!=%s",
                (new_email, current_user.id)
            ).fetchone()
            if existing:
                conn.close()
                flash("Taj email je već u upotrebi.", "err")
                return redirect(url_for("auth.profile"))
            conn.execute("UPDATE users SET email=%s WHERE id=%s",
                         (new_email, current_user.id))

        if new_pw:
            if len(new_pw) < 6:
                conn.close()
                flash("Nova šifra mora imati bar 6 znakova.", "err")
                return redirect(url_for("auth.profile"))
            new_hash = generate_password_hash(new_pw)
            conn.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                         (new_hash, current_user.id))

        if new_name:
            conn.execute("UPDATE users SET name=%s WHERE id=%s",
                         (new_name, current_user.id))

        conn.commit()
        conn.close()
        flash("Profil sačuvan.", "ok")
        return redirect(url_for("auth.profile"))
    
    capital_current = capital_mod.get_current_capital()
    capital_transactions = capital_mod.list_transactions(limit=50)

    return render_template(
        "profile.html",
        capital_current=capital_current,
        capital_transactions=capital_transactions,
    )

# ==================== CAPITAL RUTE (samo admin) ====================

@auth_bp.route("/capital/add", methods=["POST"])
@login_required
def capital_add():
    if current_user.role != "admin":
        flash("Samo admin može da menja kapital.", "err")
        return redirect(url_for("auth.profile"))

    tx_type = request.form.get("type", "").strip()
    amount  = request.form.get("amount", "").strip()
    note    = request.form.get("note", "").strip()

    import capital as capital_mod
    ok, new_balance, msg = capital_mod.add_transaction(
        user_id=current_user.id,
        tx_type=tx_type,
        amount=amount,
        note=note,
    )

    if ok:
        flash(f"{msg} Novo stanje: {new_balance:,.2f} RSD", "ok")
    else:
        flash(msg, "err")

    return redirect(url_for("auth.profile"))