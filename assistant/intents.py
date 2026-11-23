"""Questions the assistant answers without searching policies: "what can you do?"
and "which jobs are open?". Rules are simple and visible, so they are easy to audit."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_HELP = {
    "en": re.compile(r"^\s*(help|hi|hello|hey)\s*[?!.]*\s*$|what (do|can) you (know|do|help)|what can i ask|"
                     r"what (topics|questions)|how (do|does) (this|it) work", re.I),
    "es": re.compile(r"^\s*¿?\s*(ayuda|hola)\s*[?!.]*\s*$|qu[eé] sabes|qu[eé] puedes hacer|qu[eé] puedo preguntar|"
                     r"c[oó]mo funciona", re.I),
}
_VACANCIES = {
    "en": re.compile(r"\b(jobs?|roles?|vacanc\w*|openings?|positions?)\b.*\b(available|open|hiring|"
                     r"advertised|are there)\b|\b(open|available|current|internal)\s+(jobs?|roles?|"
                     r"vacanc\w*|positions?|openings?)\b|^\s*what (jobs|roles|vacancies|positions)\b", re.I),
    "es": re.compile(r"\bvacantes?\b|puestos? (abiertos|disponibles|libres)|ofertas de (empleo|trabajo)|"
                     r"qu[eé] (trabajos|puestos) hay", re.I),
}

EXAMPLES = {
    "en": ["How many days of annual leave do I get?", "Can I work from abroad?",
           "How do I get promoted?", "Will the bank pay for my CFA?", "What jobs are open?"],
    "es": ["¿Cuántos días de vacaciones tengo?", "¿Puedo trabajar desde el extranjero?",
           "¿Cómo puedo conseguir un ascenso?", "¿El banco paga mi CFA?", "¿Qué vacantes hay?"],
}


def is_help(text: str, lang: str) -> bool:
    return bool(_HELP[lang].search(text))


def is_vacancies(text: str, lang: str) -> bool:
    return bool(_VACANCIES[lang].search(text))


def topics(chunks) -> dict[str, list[str]]:
    """Policy title -> section headings, in document order."""
    out: dict[str, list[str]] = {}
    for c in chunks:
        title = re.split(r"\s+[–-]\s+Northbank", c.title)[0]
        out.setdefault(title, []).append(c.section)
    return out


def help_text(chunks, lang: str) -> str:
    head = ("Puedo responder preguntas sobre estas políticas, siempre citando la fuente:"
            if lang == "es" else "I can answer questions on these policies, always with a source:")
    lines = [head, ""] + [f"- **{t}**: {', '.join(s)}" for t, s in topics(chunks).items()]
    lines += ["", "Por ejemplo:" if lang == "es" else "For example:"]
    lines += [f"- {q}" for q in EXAMPLES[lang]]
    lines += ["", ("Los asuntos delicados (acoso, despidos, reclamaciones) se derivan a una persona."
                   if lang == "es" else
                   "Sensitive matters (harassment, redundancy, grievances) are passed to a person.")]
    return "\n".join(lines)


def not_found_suffix(chunks, lang: str) -> str:
    names = ", ".join(t.lower() if lang == "en" else t for t in topics(chunks))
    if lang == "es":
        return f"\n\nPuedo ayudarte con: {names}. Prueba, por ejemplo: «{EXAMPLES['es'][2]}»"
    return f"\n\nI can help with: {names}. Try, for example: \"{EXAMPLES['en'][2]}\""


def vacancies_text(lang: str) -> tuple[str, list[str]]:
    roles = json.loads((ROOT / "data" / "roles.json").read_text(encoding="utf-8"))
    rows = [f"- **{r['title']}** · {r['location']} · {r.get('work_pattern', '')}".rstrip(" ·")
            for r in roles]
    if lang == "es":
        text = "\n".join(["Estas son las vacantes internas abiertas ahora mismo [1]:", "", *rows, "",
                          "Si cumples los requisitos esenciales tienes garantizada una entrevista, y "
                          "puedes presentarte tras 12 meses en tu puesto o antes con el acuerdo de tu "
                          "responsable [2]. Abre el módulo **Internal Mobility** para ver cuánto encajan "
                          "tus competencias con cada puesto y qué cursos te ayudarían."])
        return text, ["careers-mobility.md § Vacantes internas", "careers-mobility.md § Solicitar un puesto interno"]
    text = "\n".join(["These internal roles are open right now [1]:", "", *rows, "",
                      "If you meet the essential criteria you are guaranteed an interview, and you can "
                      "apply after 12 months in your current role, or earlier with your line manager's "
                      "agreement [2]. Open the **Internal Mobility** module to see how well your skills "
                      "match each role and which courses would close the gaps."])
    return text, ["careers-mobility.md § Internal vacancies", "careers-mobility.md § Applying for an internal role"]
