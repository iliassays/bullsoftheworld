"""Map a tenant locale code to a language name for AI prompts."""

from __future__ import annotations

_LANGUAGES = {
    "bn": "Bengali (Bangla)",
    "en": "English",
    "hi": "Hindi",
    "ur": "Urdu",
}


def language_for(locale: str) -> str:
    return _LANGUAGES.get(locale, "English")
