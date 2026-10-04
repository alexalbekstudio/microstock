# seed_projects.py
"""Ubacuje 4 test projekta + tim + sate + troškove."""
from datetime import datetime, timedelta
from database import get_conn

conn = get_conn()

# Očisti
conn.execute("DELETE FROM time_entries")
conn.execute("DELETE FROM project_expenses")
conn.execute("DELETE FROM projects")
conn.execute("DELETE FROM team_members")
conn.commit()

# Tim
members = [
    ("Milan Milošević", "Senior consultant", 3500),
    ("Jelena Jelić",    "Designer",          2500),
    ("Nikola Nikolić",  "Developer",         3000),
    ("Ivana Ivanović",  "Junior",            1200),
]
for m in members:
    conn.execute("INSERT INTO team_members (name, role, hourly_rate) VALUES (?,?,?)", m)
conn.commit()
member_ids = [r["id"] for r in conn.execute("SELECT id FROM team_members").fetchall()]

# Projekti: (code, name, client, contract_value, days_start, days_deadline, status, notes)
projects_data = [
    ("PROJ-2026-001", "Website redizajn",   "Firma A",  350000, -30, 30,  "active", "Kompletna izrada sajta."),
    ("PROJ-2026-002", "Brand identitet",    "Firma B",  180000, -20, 20,  "active", "Logo + vizuali."),
    ("PROJ-2026-003", "Marketing kampanja", "Firma C",  120000, -45, -5,  "done",   "Završeno."),
    ("PROJ-2026-004", "CRM integracija",    "Firma D",  600000, -10, 60,  "active", "Veliki projekat."),
]
for code, name, client, val, ds, dd, status, notes in projects_data:
    start = (datetime.now() + timedelta(days=ds)).strftime("%Y-%m-%d")
    deadl = (datetime.now() + timedelta(days=dd)).strftime("%Y-%m-%d")
    conn.execute("""
        INSERT INTO projects (code,name,client,contract_value,start_date,deadline,status,notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, (code, name, client, val, start, deadl, status, notes))
conn.commit()
project_ids = [r["id"] for r in conn.execute("SELECT id FROM projects").fetchall()]

# Sati i troškovi - namerno različita iskorišćenost
import random
scenarios = [
    (project_ids[0], 40),   # ~40% budžeta -> ok
    (project_ids[1], 85),   # ~85% budžeta -> WARN
    (project_ids[2], 60),   # gotov, ok
    (project_ids[3], 105),  # >100% -> DANGER
]

for pid, target_usage in scenarios:
    proj = conn.execute("SELECT contract_value FROM projects WHERE id=?", (pid,)).fetchone()
    target_cost = proj["contract_value"] * target_usage / 100.0
    spent = 0.0
    while spent < target_cost:
        mid = random.choice(member_ids)
        rate = conn.execute("SELECT hourly_rate FROM team_members WHERE id=?", (mid,)).fetchone()["hourly_rate"]
        max_hours = min(8, (target_cost - spent) / rate)
        if max_hours <= 0.5:
            break
        hours = round(random.uniform(2, max_hours), 2)
        days_ago = random.randint(1, 30)
        d = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO time_entries (project_id, member_id, entry_date, hours, description)
            VALUES (?,?,?,?,?)
        """, (pid, mid, d, hours, "Rad na projektu"))
        spent += hours * rate

    # Dodaj i nekoliko materijalnih troškova (10% budžeta)
    for cat in ["materijal", "podizvodjac"]:
        d = (datetime.now() - timedelta(days=random.randint(5, 25))).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO project_expenses (project_id, expense_date, category, description, amount)
            VALUES (?,?,?,?,?)
        """, (pid, d, cat, f"Trošak - {cat}", round(target_cost * 0.05, 2)))

conn.commit()
conn.close()

print("✅ Test projekti ubačeni.")
print("👉 Idi na http://localhost:5000/projects")