"""Thin wrapper around the language model.

With an ANTHROPIC_API_KEY set, answers come from Claude. Without one, the
assistant runs in offline mode and returns the most relevant policy text,
so the demo and the evaluation still work with no key or internet access.
"""
from __future__ import annotations

import os

SYSTEM_PROMPT = """You are the HR Policy Assistant for employees of Northbank CIB.

Rules:
1. Answer ONLY from the numbered policy excerpts provided. Never use outside knowledge.
2. Cite every factual statement with its excerpt number in square brackets, e.g. [1].
3. If the excerpts do not answer the question, reply exactly:
   "I couldn't find this in the policies. Please contact Talent & Culture."
   (for a Spanish question: "No he encontrado esto en las políticas. Por favor, contacta con Talent & Culture.")
4. Reply in the same language as the question (English or Spanish). The excerpts are
   already in that language; keep amounts, dates and policy names exactly as written.
5. Be concise: at most five sentences or a short bullet list.
6. Do not give legal advice or comment on individual cases."""

DEFAULT_MODEL = os.getenv("HR_ASSISTANT_MODEL", "claude-sonnet-5-5")


def generate(question: str, excerpts: list[str], lang: str = "en") -> str:
    context = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(excerpts, start=1))
    if not os.getenv("ANTHROPIC_API_KEY"):
        return _offline_answer(excerpts, lang)

    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=500,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Policy excerpts:\n\n{context}\n\nEmployee question: {question}",
        }],
    )
    return response.content[0].text


def _offline_answer(excerpts: list[str], lang: str = "en") -> str:
    if lang == "es":
        return ("(Modo sin conexión, sin clave de API. Texto de política más relevante:)\n\n"
                f"{excerpts[0]} [1]")
    return ("(Offline mode, no API key set. Most relevant policy text:)\n\n"
            f"{excerpts[0]} [1]")
