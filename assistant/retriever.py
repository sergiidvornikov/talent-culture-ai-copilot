"""Load policy documents, split them into sections and find the most relevant ones.

Uses BM25, a classic keyword-ranking method, so the project has no heavy
dependencies and every ranking decision can be explained to a stakeholder.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "be", "can", "i", "my", "me", "do", "does", "how", "what", "when", "where",
    "which", "who", "it", "at", "by", "with", "from", "if", "as", "this", "that",
    "you", "your", "we", "our", "much", "many", "am", "there", "any", "should",
    "will", "would", "need", "have", "has", "get", "per", "another", "kind", "type", "sort",
}


# Everyday words employees use -> words the policies use.
SYNONYMS = {
    "sick": ["sicknes", "unwell"], "ill": ["sicknes", "unwell"],
    "holiday": ["leave"], "vacation": ["leave"], "pto": ["leave"],
    "spain": ["abroad"], "france": ["abroad"], "overseas": ["abroad"], "country": ["abroad"],
    "wfh": ["home"], "remote": ["home"],
    "fly": ["flight"], "plane": ["flight"], "train": ["rail"],
    "dinner": ["entertainment"], "lunch": ["entertainment"],
    "course": ["learning"], "training": ["learning"],
    "job": ["role", "vacancy"], "jobs": ["role", "vacancy"], "position": ["role", "vacancy"],
    "opening": ["vacancy"], "openings": ["vacancy"], "promoted": ["promotion"],
    "promotion": ["promoted", "grade", "level"], "promotions": ["promotion", "grade"],
    "senior": ["promotion", "level"], "higher": ["promotion", "level"], "career": ["promotion"],
    "internally": ["internal"], "move": ["internal", "role"], "transfer": ["internal", "secondment"],
    "raise": ["rise", "increase"], "raises": ["rise", "increase"],
    "rise": ["raise", "increase"], "increment": ["raise", "increase"],
    "timeframe": ["period", "notice", "probation", "service"],
    "timeframes": ["period", "notice", "probation", "service"],
    "appraisal": ["performance", "review", "rating"],
    "appraisals": ["performance", "review", "rating"],
}


# Spanish (accents are folded away before matching, so "días" and "dias" are the same word).
STOPWORDS_ES = {
    "a", "al", "algun", "alguna", "con", "como", "cual", "cuales", "cuando", "cuanto", "cuanta",
    "cuantos", "cuantas", "de", "del", "donde", "el", "ella", "en", "es", "esta", "estan", "este",
    "hay", "la", "las", "le", "lo", "los", "me", "mi", "mis", "necesito", "no", "o", "para", "pero",
    "por", "puedo", "puede", "pueden", "que", "quien", "quiero", "se", "si", "son", "su", "sus",
    "tengo", "tiene", "tienen", "tu", "tus", "un", "una", "uno", "y", "ya", "hacer", "debo",
    "mucho", "mucha", "muchos", "muchas", "cada",
    "conseguir", "consigo", "lograr", "obtengo", "obtener", "obtiene", "pide", "pedir",
}

SYNONYMS_ES = {
    "baja": ["enfermedad"], "enfermo": ["enfermedad"], "enferma": ["enfermedad"],
    "malo": ["enfermedad"], "bajas": ["enfermedad"],
    "espana": ["extranjero"], "francia": ["extranjero"], "fuera": ["extranjero"],
    "teletrabajo": ["casa"], "teletrabajar": ["casa"], "remoto": ["casa"],
    "avion": ["vuelos"], "volar": ["vuelos"], "vuelo": ["vuelos"], "tren": ["viajes"],
    "cena": ["atenciones"], "comida": ["atenciones"], "restaurante": ["atenciones"],
    "curso": ["formacion"], "cursos": ["formacion"], "capacitacion": ["formacion"],
    "traspasar": ["traspaso"], "arrastrar": ["traspaso"], "sobrantes": ["traspaso"],
    "maternidad": ["permisos"], "paternidad": ["permisos"], "bebe": ["permisos"],
    "ordenador": ["portatil"], "computadora": ["portatil"],
    "aprobacion": ["aprobadas"], "aprobar": ["aprobadas"], "autorizacion": ["aprobadas"],
    "ano": ["anuales", "derecho"], "oficina": ["asistencia"], "presencial": ["asistencia"],
    "trabajo": ["puesto", "vacante"], "empleo": ["puesto", "vacante"], "ascenso": ["promocion"],
    "ascender": ["promocion", "nivel"], "superior": ["promocion", "nivel"], "carrera": ["promocion"],
    "cambiar": ["interno", "puesto"], "traslado": ["interno", "comision"],
    "promocion": ["ascenso", "nivel"], "promocionar": ["promocion", "ascenso"],
    "aumento": ["subida", "incremento", "sueldo"], "aumentos": ["subida", "incremento"],
    "subida": ["aumento", "incremento", "sueldo"], "incremento": ["aumento", "subida"],
    "sueldo": ["salario", "aumento"], "salario": ["sueldo", "aumento"],
    "plazo": ["preaviso", "prueba", "permanencia"], "plazos": ["preaviso", "prueba", "permanencia"],
    "timeframe": ["preaviso", "prueba", "permanencia"],
    "preaviso": ["aviso"], "permanencia": ["antiguedad", "servicio"],
    "desempeno": ["evaluacion", "calificacion", "objetivos"],
    "evaluacion": ["desempeno", "calificacion"], "evaluaciones": ["desempeno", "calificacion"],
}


def fold(text: str) -> str:
    """Lower-case and strip accents: 'Días' -> 'dias'."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _stem(word: str, lang: str = "en") -> str:
    """Very light stemming so 'working' matches 'work' and 'days' matches 'day'."""
    if lang == "es":
        if word.endswith("ciones") and len(word) > 7:
            return word[:-2]
        if word.endswith("es") and len(word) > 5:
            return word[:-2]
        if word.endswith("s") and len(word) > 4:
            return word[:-1]
        return word
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]
    # Keep words such as "bonus" or "basis" intact; only treat a trailing "s" as a plural.
    if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        return word[:-1]
    return word


def tokenize(text: str, expand: bool = False, lang: str = "en") -> list[str]:
    stop, syn = (STOPWORDS_ES, SYNONYMS_ES) if lang == "es" else (STOPWORDS, SYNONYMS)
    text = fold(text) if lang == "es" else text.lower()
    words = [w for w in re.findall(r"[a-z0-9£]+", text) if w not in stop and len(w) > 1]
    tokens = [_stem(w, lang) for w in words]
    if expand:
        extras = [s for w, t in zip(words, tokens) for s in syn.get(w, []) + syn.get(t, [])]
        tokens += [_stem(s, lang) for s in extras]
    return tokens


@dataclass
class Chunk:
    doc: str        # file name, e.g. "leave.md"
    title: str      # document title
    section: str    # section heading
    text: str

    @property
    def citation(self) -> str:
        return f"{self.doc} § {self.section}"


def load_chunks(folder: str | Path) -> list[Chunk]:
    """Split each markdown file into one chunk per '## ' section."""
    chunks: list[Chunk] = []
    for path in sorted(Path(folder).glob("*.md")):
        content = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        for block in re.split(r"^## ", content, flags=re.MULTILINE)[1:]:
            heading, _, body = block.partition("\n")
            chunks.append(Chunk(path.name, title, heading.strip(), body.strip()))
    return chunks


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75, lang: str = "en"):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.lang = lang
        # Section heading and document title are indexed with the body text.
        self.docs = [tokenize(f"{c.title} {c.section} {c.section} {c.text}", lang=lang) for c in chunks]
        self.avg_len = sum(len(d) for d in self.docs) / max(len(self.docs), 1)
        df = Counter(term for d in self.docs for term in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def coverage(self, query: str, chunk: Chunk) -> float:
        """Share of the question's meaning (IDF-weighted) found in a chunk.

        Words the policies never use (e.g. 'share price') count fully against
        coverage, which is how off-topic questions are detected.
        """
        terms = set(tokenize(query, lang=self.lang))
        if not terms:
            return 0.0
        max_idf = max(self.idf.values())
        tf = self.tf[self.chunks.index(chunk)]
        total = sum(self.idf.get(t, max_idf) for t in terms)
        hit = sum(self.idf.get(t, max_idf) for t in terms if t in tf)
        syn = SYNONYMS_ES if self.lang == "es" else SYNONYMS
        def syn_stems(term: str) -> list[str]:
            return [_stem(x, self.lang) for x in syn.get(term, [])]
        hit += sum(self.idf.get(s, 0) for t in terms if t not in tf
                   for s in syn_stems(t) if s in tf)
        return min(hit / total, 1.0)

    def score(self, query: str, i: int) -> float:
        total, length = 0.0, len(self.docs[i])
        for term in tokenize(query, expand=True, lang=self.lang):
            if term not in self.tf[i]:
                continue
            f = self.tf[i][term]
            denom = f + self.k1 * (1 - self.b + self.b * length / self.avg_len)
            total += self.idf[term] * f * (self.k1 + 1) / denom
        return total

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        scored = [(self.chunks[i], self.score(query, i)) for i in range(len(self.chunks))]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [(c, s) for c, s in scored[:k] if s > 0]
