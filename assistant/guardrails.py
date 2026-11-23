"""Responsible-AI controls applied before anything is sent to the language model."""
from __future__ import annotations

import re

# Personal data is masked so it never leaves the bank's environment.
PII_PATTERNS = {
    "EMAIL": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "UK_NI_NUMBER": r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
    "PHONE": r"(?:\+44\s?|\b0)\d(?:[\s-]?\d){8,9}\b",
    "ES_ID_NUMBER": r"\b(?:\d{8}[A-Z]|[XYZ]\d{7}[A-Z])\b",       # Spanish DNI / NIE
    "ES_PHONE": r"(?:\+34\s?)\d{3}[\s-]?\d{3}[\s-]?\d{3}\b",
    "CARD_NUMBER": r"\b(?:\d[ -]?){13,16}\b",
}

# Topics where the assistant must hand over to a person instead of answering.
ESCALATION_KEYWORDS = {
    "grievance", "harassment", "bullying", "discrimination", "whistleblowing",
    "disciplinary", "dismissal", "redundancy", "tribunal", "lawyer",
    "acoso", "despido", "despidos", "discriminación", "discriminacion", "denuncia", "denunciar",
    "abogado", "mobbing", "expediente", "reclamación",
}

# Function words used only to tell English from Spanish, so the right policy set is searched.
_ES_WORDS = {"el", "la", "los", "las", "del", "que", "qué", "cuántos", "cuántas", "cuánto", "cómo",
             "puedo", "tengo", "mi", "mis", "para", "por", "con", "hay", "se", "quiero", "necesito",
             "cuál", "dónde", "cuándo", "una", "un", "es", "en", "de", "al", "cuantos", "como",
             "cual", "donde", "cuando", "tiene", "debo", "hacer"}
_EN_WORDS = {"the", "is", "are", "how", "what", "can", "do", "does", "i", "my", "to", "of", "and",
             "for", "if", "in", "when", "where", "which", "it", "get", "need", "with", "from"}


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Return the text with personal data masked, plus the types found."""
    found = []
    for label, pattern in PII_PATTERNS.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(label)
            text = re.sub(pattern, f"[{label}]", text, flags=re.IGNORECASE)
    return text, found


def needs_escalation(text: str) -> bool:
    words = set(re.findall(r"\w+", text.lower()))
    return bool(words & ESCALATION_KEYWORDS)


def detect_language(text: str) -> str:
    """'es' or 'en'. A simple function-word count: transparent and good enough for a
    two-language assistant; unclear text defaults to English."""
    if "¿" in text or "¡" in text:
        return "es"
    words = re.findall(r"\w+", text.lower())
    es = sum(w in _ES_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    return "es" if es > en else "en"
