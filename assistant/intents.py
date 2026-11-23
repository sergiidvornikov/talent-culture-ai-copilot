"""Questions the assistant answers without searching policies: "what can you do?"
and "which jobs are open?". Rules are simple and visible, so they are easy to audit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_HELP = {
    "en": re.compile(r"^\s*(help|hi|hello|hey)\s*[?!.]*\s*$|what (do|can) you (know|do|help)|what can i ask|"
                     r"what (topics|questions)|how (do|does) (this|it) work|what are you able to", re.I),
    "es": re.compile(r"^\s*¿?\s*(ayuda|hola)\s*[?!.]*\s*$|qu[eé] sabes|qu[eé] puedes (hacer|responder)|"
                     r"qu[eé] puedo preguntar|c[oó]mo funciona|qu[eé] temas", re.I),
}
_VACANCIES = {
    "en": re.compile(r"\b(jobs?|roles?|vacanc\w*|openings?|positions?)\b.*\b(available|open|hiring|"
                     r"advertised|are there)\b|\b(open|available|current|internal)\s+(jobs?|roles?|"
                     r"vacanc\w*|positions?|openings?)\b|^\s*what (kind of )?(jobs|roles|vacancies|positions)\b|"
                     r"\bare there\b.*\b(jobs?|roles?|vacanc\w*|positions?|openings?)\b|"
                     r"\b(job board|internal job board)\b", re.I),
    "es": re.compile(r"\bvacantes?\b|puestos? (abiertos|disponibles|libres)|ofertas de (empleo|trabajo)|"
                     r"qu[eé] (trabajos|puestos) hay|tabl[oó]n (interno )?(de )?(empleo|vacantes)", re.I),
}
_MOBILITY = {
    "en": re.compile(r"\b(jobs?|roles?|vacanc\w*|openings?|positions?|job board|internal move|"
                     r"move internally|another (job|role|team)|change teams?|switch roles?)\b", re.I),
    "es": re.compile(r"\b(vacantes?|puestos?|ofertas?|tabl[oó]n|traslado|moverme|"
                     r"cambio de (puesto|equipo)|movilidad)\b", re.I),
}

# Short set shown as clickable examples in the app.
EXAMPLES = {
    "en": ["How many days of annual leave do I get?", "How do I get a raise?",
           "How do I get promoted?", "What is the notice period?", "What jobs are open?"],
    "es": ["¿Cuántos días de vacaciones tengo?", "¿Cómo puedo conseguir un aumento?",
           "¿Cómo puedo conseguir un ascenso?", "¿Cuál es el preaviso?", "¿Qué vacantes hay?"],
}

# One suggested follow-up per policy document, used in help and not-found replies.
TOPIC_EXAMPLES = {
    "en": {
        "leave.md": "How many days of annual leave do I get?",
        "hybrid-working.md": "Can I work from abroad?",
        "expenses.md": "What is the hotel limit in London?",
        "learning-development.md": "Will the bank pay for my CFA exams?",
        "onboarding.md": "How long is the probation period?",
        "careers-mobility.md": "How do I get promoted?",
        "pay-reward.md": "How do I get a raise?",
        "employment-terms.md": "What is the notice period?",
        "performance-reviews.md": "When are performance reviews?",
    },
    "es": {
        "leave.md": "¿Cuántos días de vacaciones tengo?",
        "hybrid-working.md": "¿Puedo trabajar desde el extranjero?",
        "expenses.md": "¿Cuál es el límite del hotel en Londres?",
        "learning-development.md": "¿El banco paga mi CFA?",
        "onboarding.md": "¿Cuánto dura el periodo de prueba?",
        "careers-mobility.md": "¿Cómo puedo conseguir un ascenso?",
        "pay-reward.md": "¿Cómo puedo conseguir un aumento?",
        "employment-terms.md": "¿Cuál es el preaviso?",
        "performance-reviews.md": "¿Cuándo son las evaluaciones del desempeño?",
    },
}


def is_help(text: str, lang: str) -> bool:
    return bool(_HELP[lang].search(text))


def is_vacancies(text: str, lang: str) -> bool:
    return bool(_VACANCIES[lang].search(text))


def looks_like_mobility(text: str, lang: str) -> bool:
    return is_vacancies(text, lang) or bool(_MOBILITY[lang].search(text))


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
    if lang == "es":
        lines += ["", "Para vacantes y movimientos internos, abre el módulo **Internal Mobility**.",
                  "Los asuntos delicados (acoso, despidos, reclamaciones) se derivan a una persona."]
    else:
        lines += ["", "For open roles and internal moves, open the **Internal Mobility** module.",
                  "Sensitive matters (harassment, redundancy, grievances) are passed to a person."]
    return "\n".join(lines)


def not_found_suffix(chunks, lang: str, query: str = "", hits=None) -> str:
    """After a refusal, name the closest topics and suggest a question; point job
    and internal-move questions at the Internal Mobility module."""
    closest = []
    seen: set[str] = set()
    for item in hits or []:
        chunk, score = item[0], item[1]
        if score <= 0 or chunk.citation in seen:
            continue
        seen.add(chunk.citation)
        closest.append(chunk)
        if len(closest) == 3:
            break

    bits: list[str] = []
    if closest:
        names = "; ".join(c.section for c in closest)
        if lang == "es":
            bits.append(f"Lo más cercano en las políticas es: {names}.")
        else:
            bits.append(f"The closest policy topics are: {names}.")
        suggestions: list[str] = []
        for c in closest:
            q = TOPIC_EXAMPLES[lang].get(c.doc)
            if q and q not in suggestions:
                suggestions.append(q)
    else:
        names = ", ".join(t.lower() if lang == "en" else t for t in topics(chunks))
        if lang == "es":
            bits.append(f"Puedo ayudarte con: {names}.")
        else:
            bits.append(f"I can help with: {names}.")
        suggestions = list(EXAMPLES[lang][:3])

    if looks_like_mobility(query, lang):
        if lang == "es":
            bits.append("Para vacantes y movimientos internos, abre el módulo **Internal Mobility**.")
        else:
            bits.append("For open roles and internal moves, open the **Internal Mobility** module.")

    if suggestions:
        quoted = ", ".join(f"«{q}»" if lang == "es" else f'"{q}"' for q in suggestions[:3])
        bits.append(("Prueba, por ejemplo: " if lang == "es" else "Try, for example: ") + quoted)

    return "\n\n" + " ".join(bits)


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
