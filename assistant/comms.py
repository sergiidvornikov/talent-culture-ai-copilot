"""Communications Studio: drafts internal announcements, press releases and client posts,
checks them against brand, tone and compliance rules, and enforces human approval.

AI drafts and checks. People approve: one approver (Communications) for internal
messages, two different people (Communications and Compliance, "four eyes") for anything
external. Nothing is approved while a blocking finding or an unfilled placeholder remains,
and every draft and approval is audit-logged with a hash of the exact approved text.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import guardrails, llm, recruiting
from .mobility import DATA, ROOT

AUDIT_LOG = ROOT / "logs" / "comms_audit.jsonl"
BRAND = json.loads((DATA / "comms_brand.json").read_text(encoding="utf-8"))
KINDS = BRAND["kinds"]
LANGS = {"en": "English", "es": "Español"}
SENTENCE_LIMIT = 30   # average words per sentence above which text is hard to read


@dataclass
class Finding:
    term: str
    category: str
    severity: str        # "block" stops approval; "warn" is for the reviewer to judge
    suggestion: str


@dataclass
class Brief:
    kind: str                    # key of KINDS
    headline: str
    key_points: list[str]
    lang: str = "en"
    date: str = ""
    spokesperson: str = ""       # "Name, Title"
    quote: str = ""              # supplied by the spokesperson; the tool never invents quotes
    contact: str = ""
    link: str = ""


# ---- 1. Drafting ------------------------------------------------------------------------

_TEXT = {
    "en": {"today": "today announced", "what": "What this means for you", "hi": "Hi all,",
           "questions": "Questions? Contact", "said": "said", "about": "About Northbank CIB",
           "about_text": "Northbank CIB is a fictional corporate and investment bank.",
           "more": "Find out more", "internal": "Internal: please do not forward outside the bank.",
           "thanks": "Thank you,", "team": "Communications team"},
    "es": {"today": "ha anunciado hoy", "what": "Qué significa para ti", "hi": "Hola a todos:",
           "questions": "¿Preguntas? Contacta con", "said": "ha declarado", "about": "Acerca de Northbank CIB",
           "about_text": "Northbank CIB es un banco corporativo y de inversión ficticio.",
           "more": "Más información", "internal": "Interno: por favor, no reenviar fuera del banco.",
           "thanks": "Gracias,", "team": "Equipo de Comunicación"},
}


def disclaimer(kind: str, lang: str) -> str:
    return BRAND["disclaimers"].get(kind, {}).get(lang, "")


def draft(brief: Brief) -> tuple[str, str]:
    """Return (text, source). With an API key the LLM writes the prose under the brand
    rules; otherwise a template is used. Both go through the same checks."""
    if llm.is_enabled():
        try:
            return _llm_draft(brief), "llm"
        except Exception:
            pass
    return _template_draft(brief), "template"


def _template_draft(b: Brief) -> str:
    t = _TEXT[b.lang]
    bullets = "\n".join(f"- {p}" for p in b.key_points)
    legal = disclaimer(b.kind, b.lang)
    if b.kind == "internal_announcement":
        parts = [f"**{b.headline}**", "", t["hi"], "", f"{b.key_points[0]}" if b.key_points else "",
                 "", f"{t['what']}:", bullets, "",
                 f"{t['questions']} {b.contact or '[contact]'}.", "", t["thanks"], t["team"], "",
                 f"_{t['internal']}_"]
    elif b.kind == "press_release":
        parts = [f"# {b.headline}", "", f"**London, {b.date or '[date]'}**: Northbank CIB {t['today']} "
                 f"{b.key_points[0] if b.key_points else '[announcement]'}", ""]
        for p in b.key_points[1:]:
            parts += [p, ""]
        who = b.spokesperson or "[spokesperson]"
        quote = (b.quote or "[quote to be supplied by the spokesperson]").rstrip(".")
        parts += [f"\"{quote},\" {t['said']} {who}.",
                  "", f"## {t['about']}", t["about_text"], "", f"_{legal}_"]
    else:  # client_post
        parts = [f"**{b.headline}**", " ".join(b.key_points),
                 f"{t['more']}: {b.link or '[link]'}", "", f"_{legal}_"]
    return "\n".join(parts).strip()


def _llm_draft(b: Brief) -> str:
    rules = ("Write in the bank's plain, professional, warm voice. No hype, no superlatives, "
             "no guarantees or performance claims, no invented facts, no invented quotes. "
             "Use only the facts in the brief. Keep placeholders in [square brackets] for "
             "anything missing. End external texts with this disclaimer, unchanged: "
             f"{disclaimer(b.kind, b.lang)}")
    return llm.complete(
        system=f"You draft {KINDS[b.kind]['label'].lower()}s for Northbank CIB in {LANGS[b.lang]}. {rules}",
        user=json.dumps(b.__dict__, ensure_ascii=False), max_tokens=900, temperature=0.3)


# ---- 2. Brand, tone and compliance check ----------------------------------------------------

def _find(term: str, text: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE))


def review(text: str, kind: str, lang: str = "en") -> list[Finding]:
    spec, out = KINDS[kind], []
    low = text.lower()

    for e in BRAND["lexicon"]:
        if e["lang"] in (lang, "any") and _find(e["term"], text):
            out.append(Finding(e["term"], e["category"], e["severity"], e["suggestion"]))

    if spec["external"]:
        for phrase in BRAND["required_phrases"][kind][lang]:
            if phrase not in low:
                out.append(Finding(f"missing disclaimer: '{phrase}'", "required disclaimer", "block",
                                   f"add the approved disclaimer: {disclaimer(kind, lang)}"))
        fl = BRAND["forward_looking"]
        if any(_find(t, text) for t in fl["terms"]) and not any(c in low for c in fl["caveats"]):
            out.append(Finding("forward-looking statement", "forward-looking", "block",
                               "add the forward-looking statements caveat"))

    if re.search(r"\[[^\]]{2,}\]", text):
        out.append(Finding("unresolved placeholder", "incomplete", "block",
                           "fill every [placeholder] (quotes must come from the spokesperson)"))

    clean, pii = guardrails.redact_pii(text)
    if pii:
        out.append(Finding("personal data: " + ", ".join(pii), "personal data", "block",
                           "remove personal data from the draft"))

    for m in re.finditer(r"north\s*-?\s*bank(?![\w.])(?:\s+(?:bank|cib))?", text, flags=re.IGNORECASE):
        if m.group(0) not in (BRAND["bank_name"], BRAND["bank_name"].split()[0]):
            out.append(Finding(m.group(0), "brand name", "warn", f"write '{BRAND['bank_name']}'"))
            break

    if lang == "en":   # the inclusive-language lexicon is English only
        for f in recruiting.check_language(text):
            if f.category != "age-related" or f.term != "high years-of-experience requirement":
                out.append(Finding(f.term, f"inclusive language ({f.category})", "warn", f.suggestion))

    if text.count("!") > 1:
        out.append(Finding("exclamation marks", "tone", "warn", "keep the tone calm and factual"))
    caps = [w for w in re.findall(r"\b[A-Z]{4,}\b", text)]
    if len(caps) > 2:
        out.append(Finding("capitalised words", "tone", "warn", "avoid shouting"))
    words = len(re.findall(r"\w+", text))
    if words > spec["max_words"]:
        out.append(Finding(f"{words} words", "length", "warn", f"aim for {spec['max_words']} or fewer"))
    sentences = [s for s in re.split(r"[.!?]+\s", re.sub(r"[#*_\-]", "", text)) if s.strip()]
    if sentences and words / len(sentences) > SENTENCE_LIMIT:
        out.append(Finding("long sentences", "readability", "warn", f"average over {SENTENCE_LIMIT} words"))
    return out


def blockers(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "block"]


# ---- 3. Human approval gate and audit log ---------------------------------------------------

def _write(rec: dict, log_path: str | Path) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def log_draft(brief: Brief, text: str, source: str, log_path: str | Path = AUDIT_LOG) -> dict:
    found = review(text, brief.kind, brief.lang)
    rec = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": "comms_drafted",
           "kind": brief.kind, "lang": brief.lang, "headline": brief.headline, "source": source,
           "draft_hash": _hash(text), "blocking": len(blockers(found)),
           "warnings": len(found) - len(blockers(found)), "ai_role": "drafting and checks only"}
    _write(rec, log_path)
    return rec


def required_approvers(kind: str) -> list[str]:
    return KINDS[kind]["approvers"]


def approve(kind: str, lang: str, original_draft: str, final_text: str, approvals: dict[str, str],
            reviewed_warnings: bool = False, log_path: str | Path = AUDIT_LOG) -> dict:
    """approvals = {"Communications": "Name", "Compliance": "Name"}. Raises ValueError unless
    the final text has no blocking findings and every required approver is a named person.
    External content needs two different people."""
    found = review(final_text, kind, lang)
    if blockers(found):
        raise ValueError("Blocking issues remain: " + "; ".join(f.term for f in blockers(found)))
    names = {}
    for role in required_approvers(kind):
        who = approvals.get(role, "").strip()
        if not who:
            raise ValueError(f"Approval needed from {role}: a named person must sign off.")
        names[role] = who
    if len({n.lower() for n in names.values()}) < len(names):
        raise ValueError("External content needs two different approvers (four-eyes principle).")
    warns = [f for f in found if f.severity == "warn"]
    if warns and not reviewed_warnings:
        raise ValueError(f"{len(warns)} warning(s) must be reviewed and acknowledged before approval.")
    similarity = difflib.SequenceMatcher(None, original_draft, final_text).ratio()
    rec = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": "comms_approved",
           "kind": kind, "lang": lang, "approved_by": names, "final_hash": _hash(final_text),
           "draft_hash": _hash(original_draft), "edited_by_human": final_text != original_draft,
           "ai_text_retained": round(similarity, 2), "warnings_acknowledged": len(warns),
           "status": "approved for publication by a person", "ai_role": "drafting and checks only"}
    _write(rec, log_path)
    return rec


def read_log(log_path: str | Path = AUDIT_LOG) -> list[dict]:
    p = Path(log_path)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l] if p.exists() else []


# ---- Demo briefs (fictional) ----------------------------------------------------------------

DEMO_BRIEFS = {
    "AI Academy launch (internal, EN)": Brief(
        "internal_announcement", "AI Academy opens to all CIB employees",
        ["From 1 December every employee can enrol in the AI Academy, our new self-paced learning programme.",
         "Courses cover prompt engineering, responsible AI and simple automations.",
         "Completing 'Responsible Use of AI' is required before using generative AI with internal data.",
         "Your £1,000 learning budget can also be used for external AI courses."],
        "en", contact="Talent & Culture"),
    "Lanzamiento AI Academy (interno, ES)": Brief(
        "internal_announcement", "La AI Academy abre sus puertas a todos los empleados",
        ["Desde el 1 de diciembre, todos los empleados pueden inscribirse en la AI Academy, nuestro nuevo programa de formación a tu ritmo.",
         "Los cursos cubren ingeniería de prompts, IA responsable y automatizaciones sencillas.",
         "Es obligatorio completar «Uso responsable de la IA» antes de usar IA generativa con datos internos."],
        "es", contact="Talent & Culture"),
    "Graduate programme (press release, EN)": Brief(
        "press_release", "Northbank CIB opens applications for its 2027 Graduate Programme",
        ["it has opened applications for its 2027 Graduate Programme in London, with 40 places across markets, risk, technology and Talent & Culture.",
         "Applications close on 31 January. Selection uses structured interviews, and each hiring decision is made and recorded by a person.",
         "We expect to publish the first intake's learning plans in the spring."],
        "en", date="23 November 2026", spokesperson="Alex Morgan, Head of Talent & Culture (fictional)",
        quote="We want graduates to see how their skills fit the bank, and to start with a clear learning plan."),
    "Comunicado de prensa (ES)": Brief(
        "press_release", "Northbank CIB abre las candidaturas de su Programa de Graduados 2027",
        ["ha abierto las candidaturas de su Programa de Graduados 2027 en Londres, con 40 plazas en mercados, riesgos, tecnología y Talent & Culture.",
         "El plazo termina el 31 de enero. La selección utiliza entrevistas estructuradas y cada decisión la toma y registra una persona."],
        "es", date="23 de noviembre de 2026", spokesperson="Alex Morgan, directora de Talent & Culture (ficticia)",
        quote="Queremos que los graduados vean cómo encajan sus competencias en el banco."),
    "Client post (EN)": Brief(
        "client_post", "Webinar: AI in corporate treasury",
        ["Join our treasury specialists on 10 December for a practical look at how corporates are using AI in cash forecasting."],
        "en", link="northbank.example/webinars"),
}
