"""Versioned prompt for post translation."""

# v2 — simpler instruction; the verbose multi-line v1 degraded smaller models badly.
TRANSLATE_SYSTEM_V1 = """Translate the user's post into {language}. Keep stock cashtags \
(like $GP, $BEXIMCO) and every number and percentage EXACTLY as written — do not translate or \
alter them. Preserve the meaning and tone. Output ONLY the translation, nothing else."""
