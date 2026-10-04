# i18n.py
"""
Mali i18n sistem za MicroStock.

Podržava dva režima:
- set_locale() — iz HTTP request-a (koristi session)
- force_locale() — iz background thread-a (koristi thread-local)

t() automatski bira: ako postoji force_locale override → koristi njega,
inače padne na get_locale() (session/korisnik).
"""

import threading
from flask import session

from translations import LANGUAGES, DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


# Thread-local za background job-ove (scheduler)
_force = threading.local()


def get_locale():
    """Vraća trenutni jezik: force → session → korisnik → default."""
    # 1) Force override (scheduler, CLI, test)
    forced = getattr(_force, "lang", None)
    if forced and forced in SUPPORTED_LANGUAGES:
        return forced

    # 2) Sesija (HTTP request)
    try:
        if "lang" in session and session["lang"] in SUPPORTED_LANGUAGES:
            return session["lang"]
    except RuntimeError:
        # Nema request context-a (npr. scheduler) — preskoči
        pass

    # 3) Korisnik
    try:
        from flask_login import current_user
        if current_user and hasattr(current_user, "language") and current_user.language:
            if current_user.language in SUPPORTED_LANGUAGES:
                return current_user.language
    except Exception:
        pass

    # 4) Fallback
    return DEFAULT_LANGUAGE


def set_locale(lang):
    """Postavlja jezik u sesiju (HTTP request)."""
    if lang in SUPPORTED_LANGUAGES:
        session["lang"] = lang
        return True
    return False


def force_locale(lang):
    """
    Postavlja jezik za trenutni thread (za background job-ove).
    NE dira sesiju. Vraća prethodni jezik (za restore).
    """
    prev = getattr(_force, "lang", None)
    if lang in SUPPORTED_LANGUAGES:
        _force.lang = lang
    return prev


def clear_force_locale():
    """Briše force override za trenutni thread."""
    if hasattr(_force, "lang"):
        del _force.lang


def t(key, **kwargs):
    """Prevod ključa u trenutni jezik."""
    lang = get_locale()
    translations = LANGUAGES.get(lang, {})

    if key not in translations:
        translations = LANGUAGES.get(DEFAULT_LANGUAGE, {})

    text = translations.get(key, key)

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text

    return text


def available_languages():
    """Vraća listu dostupnih jezika."""
    return [
        {"code": "sr", "label": "Srpski"},
        {"code": "en", "label": "English"},
    ]