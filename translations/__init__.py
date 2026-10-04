# translations/__init__.py
"""Paket za prevode."""

from . import sr, en

LANGUAGES = {
    "sr": sr.TRANSLATIONS,
    "en": en.TRANSLATIONS,
}

DEFAULT_LANGUAGE = "sr"
SUPPORTED_LANGUAGES = list(LANGUAGES.keys())