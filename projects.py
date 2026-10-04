# projects.py
"""Model za Alat #3 - projekti, sati, troškovi, profitabilnost."""
from mailer import send_project_warn, send_project_danger
from db_adapter import connect


# ==================== TIM ====================

def list_members(only_active=True):
    conn = connect()
    sql = "SELECT * FROM team_members"
    if only_active:
        sql += " WHERE active = 1"
    sql += " ORDER BY name"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows

def add_member(name, role, hourly_rate):
    conn = connect()
    conn.execute(
        "INSERT INTO team_members (name, role, hourly_rate) VALUES (?,?,?)",
        (name, role, hourly_rate)
    )
    conn.commit(); conn.close()


# ==================== PROJEKTI ====================

def list_projects(status=None):
    sql = "SELECT * FROM v_project_summary WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY (status='active') DESC, start_date DESC"
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_enrich(r) for r in rows]

def get_project(pid):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM v_project_summary WHERE project_id=?", (pid,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _enrich(row)

def add_project(code, name, client, contract_value, start_date, deadline, notes=""):
    conn = connect()
    conn.execute("""
        INSERT INTO projects (code, name, client, contract_value, start_date, deadline, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (code, name, client, contract_value, start_date, deadline, notes))
    conn.commit(); conn.close()

def update_project(pid, code, name, client, contract_value, start_date, deadline, status, notes):
    conn = connect()
    conn.execute("""
        UPDATE projects
           SET code=?, name=?, client=?, contract_value=?,
               start_date=?, deadline=?, status=?, notes=?
         WHERE id=?
    """, (code, name, client, contract_value, start_date, deadline, status, notes, pid))
    conn.commit(); conn.close()

def delete_project(pid):
    conn = connect()
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit(); conn.close()


# ==================== RADNI SATI ====================

def list_time(project_id):
    conn = connect()
    rows = conn.execute("""
        SELECT te.*, tm.name AS member_name, tm.hourly_rate,
               (te.hours * tm.hourly_rate) AS cost
        FROM time_entries te JOIN team_members tm ON tm.id = te.member_id
        WHERE te.project_id = ?
        ORDER BY te.entry_date DESC, te.id DESC
    """, (project_id,)).fetchall()
    conn.close()
    return rows

def add_time(project_id, member_id, entry_date, hours, description=""):
    conn = connect()
    conn.execute("""
        INSERT INTO time_entries (project_id, member_id, entry_date, hours, description)
        VALUES (?,?,?,?,?)
    """, (project_id, member_id, entry_date, hours, description))
    conn.commit(); conn.close()

def delete_time(entry_id):
    conn = connect()
    conn.execute("DELETE FROM time_entries WHERE id=?", (entry_id,))
    conn.commit(); conn.close()


# ==================== TROŠKOVI ====================

def list_expenses(project_id):
    conn = connect()
    rows = conn.execute("""
        SELECT * FROM project_expenses WHERE project_id=? ORDER BY expense_date DESC, id DESC
    """, (project_id,)).fetchall()
    conn.close()
    return rows

def add_expense(project_id, expense_date, category, description, amount):
    conn = connect()
    conn.execute("""
        INSERT INTO project_expenses (project_id, expense_date, category, description, amount)
        VALUES (?,?,?,?,?)
    """, (project_id, expense_date, category, description, amount))
    conn.commit(); conn.close()

def delete_expense(expense_id):
    conn = connect()
    conn.execute("DELETE FROM project_expenses WHERE id=?", (expense_id,))
    conn.commit(); conn.close()


# ==================== POMOĆNE ====================

def _enrich(row):
    if not row:
        return None
    p = dict(row)

    # STVARNA ŠEMA: contract_value (ne budget), expense_cost (ne material_cost)
    revenue  = p.get("contract_value") or 0
    labor    = p.get("labor_cost") or 0
    material = p.get("expense_cost") or 0
    spent    = labor + material

    p["spent"]      = spent
    p["total_cost"] = spent
    p["profit"]     = revenue - spent
    p["budget_pct"] = (spent / revenue * 100) if revenue else 0
    p["margin"]     = ((revenue - spent) / revenue * 100) if revenue else 0

    pct = p["budget_pct"]
    if revenue <= 0:
        level = "none"
    elif pct >= 100:
        level = "danger"
    elif pct >= 80:
        level = "warn"
    else:
        level = "ok"

    p["alert_level"] = level

    # ---- ALIASI za template (da ne moraš da menjaš HTML) ----
    p["budget_usage"] = p["budget_pct"]      # template koristi ovo ime
    p["alert"]        = level                # template koristi ovo ime
    p["budget"]       = revenue              # template možda prikazuje "budget"
    p["material_cost"] = material            # ako template traži ovo ime
    # ---------------------------------------------------------

    return p

# ==================== PREGLED ZA DASHBOARD ====================

def projects_overview():
    """Broj projekata, koliko ih je u opasnosti (>80%), ukupan profit."""
    conn = connect()
    rows = conn.execute("SELECT * FROM v_project_summary WHERE status='active'").fetchall()
    conn.close()

    active = [_enrich(r) for r in rows]
    warn_count = sum(1 for p in active if p["alert_level"] in ("warn", "danger"))
    total_revenue = sum(p["contract_value"] for p in active)
    total_cost    = sum(p["total_cost"] for p in active)
    total_profit  = sum(p["profit"] for p in active)

    return {
        "active":        len(active),
        "warnings":      warn_count,
        "total_revenue": round(total_revenue, 2),
        "total_cost":    round(total_cost, 2),
        "total_profit":  round(total_profit, 2),
        "at_risk": [p for p in active if p["alert_level"] != "ok"],
    }

def _check_budget_alert(project_id):
    proj = get_project(project_id)
    if not proj or proj.get("status") != "active":
        return

    budget = proj.get("contract_value") or 0   # ← contract_value!
    if budget <= 0:
        return

    spent = proj.get("spent") or 0
    pct   = proj.get("budget_pct") or 0

    current_level = proj.get("last_alert_level")
    new_level = None
    if pct >= 100:
        new_level = "danger"
    elif pct >= 80:
        new_level = "warn"

    if new_level is None or new_level == current_level:
        return
    if current_level == "danger":
        return

    ok = False
    if new_level == "danger":
        ok = send_project_danger(proj, pct, spent, budget)
    elif new_level == "warn":
        ok = send_project_warn(proj, pct, spent, budget)

    if ok:
        _update_alert_state(project_id, new_level)


def _update_alert_state(project_id, level):
    from db_adapter import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE projects SET last_alert_level = ?, "
        "last_alert_sent_at = CURRENT_TIMESTAMP WHERE id = ?",
        (level, project_id),
    )
    conn.commit()
    conn.close()

def add_expense(project_id, expense_date, category, description, amount):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO project_expenses (project_id, expense_date, category, description, amount)
        VALUES (?,?,?,?,?)
    """, (project_id, expense_date, category, description, amount))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()

    _check_budget_alert(project_id)   # ← pokreće email ako treba
    return new_id


def add_time(project_id, member_id, entry_date, hours, description=""):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO time_entries (project_id, member_id, entry_date, hours, description)
        VALUES (?,?,?,?,?)
    """, (project_id, member_id, entry_date, hours, description))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()

    _check_budget_alert(project_id)   # ← pokreće email ako treba
    return new_id