"""The assistant: guardrails -> retrieval -> grounded answer -> usage log."""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import guardrails, intents, llm
from .retriever import BM25Retriever, load_chunks

ROOT = Path(__file__).resolve().parent.parent
NOT_FOUND = "I couldn't find this in the policies. Please contact Talent & Culture."
ESCALATE = ("This looks like a sensitive matter that should be handled by a person. "
            "Please contact your Talent & Culture business partner or the confidential "
            "Speak Up line.")
NOT_FOUND_ES = "No he encontrado esto en las políticas. Por favor, contacta con Talent & Culture."
ESCALATE_ES = ("Este asunto parece delicado y debe tratarlo una persona. Por favor, contacta con tu "
               "business partner de Talent & Culture o con el canal confidencial Speak Up.")


@dataclass
class Answer:
    question: str
    text: str
    status: str                       # answered | not_found | escalated | help
    sources: list[str] = field(default_factory=list)
    pii_redacted: list[str] = field(default_factory=list)
    top_score: float = 0.0
    latency_ms: int = 0
    language: str = "en"              # en | es: decides which policy set is searched


class PolicyAssistant:
    def __init__(self, policy_dir: str | Path = ROOT / "policies",
                 log_path: str | Path = ROOT / "logs" / "usage.jsonl",
                 min_coverage: float = 0.45, top_k: int = 3):
        self.retriever = BM25Retriever(load_chunks(policy_dir))
        # Spanish policies (demo translations) live in policies/es; if absent, Spanish
        # questions fall back to the English set.
        es_dir = Path(policy_dir) / "es"
        self.retriever_es = (BM25Retriever(load_chunks(es_dir), lang="es")
                             if es_dir.is_dir() and any(es_dir.glob("*.md")) else None)
        self.log_path = Path(log_path)
        self.min_coverage = min_coverage  # below this, the policies don't cover the question
        self.top_k = top_k

    def retriever_for(self, lang: str) -> BM25Retriever:
        return self.retriever_es if lang == "es" and self.retriever_es else self.retriever

    def ask(self, question: str, lang: str | None = None) -> Answer:
        """lang: 'en' or 'es'. Detected from the question when not given."""
        start = time.perf_counter()
        clean, pii = guardrails.redact_pii(question)
        lang = lang or guardrails.detect_language(clean)
        es = lang == "es"
        retriever = self.retriever_for(lang)
        lang = retriever.lang                     # report the language actually searched

        if guardrails.needs_escalation(clean):
            answer = Answer(clean, ESCALATE_ES if es else ESCALATE, "escalated", pii_redacted=pii)
        elif intents.is_help(clean, lang):
            answer = Answer(clean, intents.help_text(retriever.chunks, lang), "help", pii_redacted=pii)
        elif intents.is_vacancies(clean, lang):
            text, sources = intents.vacancies_text(lang)
            answer = Answer(clean, text, "answered", sources, pii, 1.0)
        else:
            hits = retriever.search(clean, k=self.top_k)
            top = max((retriever.coverage(clean, c) for c, _ in hits), default=0.0)
            if top < self.min_coverage:
                text = (NOT_FOUND_ES if es else NOT_FOUND) + intents.not_found_suffix(retriever.chunks, lang)
                answer = Answer(clean, text, "not_found", pii_redacted=pii, top_score=top)
            else:
                excerpts = [f"({c.citation}) {c.text}" for c, _ in hits]
                text = llm.generate(clean, excerpts, lang)
                cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
                sources = [hits[n - 1][0].citation for n in sorted(cited) if 0 < n <= len(hits)]
                refused = text.strip().startswith(("I couldn't find", "No he encontrado"))
                status = "not_found" if refused else "answered"
                answer = Answer(clean, text, status, sources, pii, top)
        answer.language = lang

        answer.latency_ms = int((time.perf_counter() - start) * 1000)
        self._log(answer)
        return answer

    def _log(self, answer: Answer) -> None:
        """Append one line per question so adoption and quality can be tracked."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        record = asdict(answer)
        record.pop("text")            # keep the log light; questions are already redacted
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
