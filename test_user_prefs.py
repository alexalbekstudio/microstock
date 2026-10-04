# test_user_prefs.py
from auth import load_user

u = load_user(1)
if u:
    print(f"Email:    {u.email}")
    print(f"Role:     {u.role}")
    print(f"Language: {u.language}")
    print(f"Currency: {u.currency}")
else:
    print("Korisnik nije nađen.")