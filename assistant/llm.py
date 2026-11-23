"""One place where every module talks to a language model.

The project is model-agnostic. Choose the provider with environment variables;
nothing else in the code changes:

    LLM_PROVIDER   offline (default) | openai | azure_openai | gemini | anthropic | gateway
    LLM_MODEL      the model or deployment name your licence gives you
    LLM_API_KEY    the key (or OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY)
    LLM_BASE_URL   for "gateway": the bank's internal, OpenAI-compatible endpoint
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION   for "azure_openai"

In a bank, the right setting is usually "gateway" or "azure_openai": calls go through
the approved platform that handles logging, content filtering and data residency.
With no provider set, every module runs offline using templates and keyword methods,
so the demo and all evaluations work without any key or internet access.
"""
from __future__ import annotations

import os

PROVIDERS = {"offline", "openai", "azure_openai", "gemini", "anthropic", "gateway"}
_KEY_FALLBACK = {"openai": "OPENAI_API_KEY", "azure_openai": "AZURE_OPENAI_API_KEY",
                 "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
                 "gateway": "LLM_API_KEY"}
# Google serves Gemini through an OpenAI-compatible endpoint, so one client covers both.
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class LLMConfigError(RuntimeError):
    pass


def provider() -> str:
    p = os.getenv("LLM_PROVIDER", "offline").strip().lower()
    if p not in PROVIDERS:
        raise LLMConfigError(f"LLM_PROVIDER must be one of {sorted(PROVIDERS)}, not '{p}'.")
    return p


def _api_key(p: str) -> str | None:
    return os.getenv("LLM_API_KEY") or os.getenv(_KEY_FALLBACK.get(p, ""))


def is_enabled() -> bool:
    """True when a provider, a model and a key are all configured."""
    p = provider()
    return p != "offline" and bool(os.getenv("LLM_MODEL")) and bool(_api_key(p))


def describe() -> str:
    """Short label for the UI, e.g. 'gemini · gemini-model-name' or 'offline'."""
    return f"{provider()} · {os.getenv('LLM_MODEL')}" if is_enabled() else "offline"


def complete(system: str, user: str, max_tokens: int = 500, temperature: float = 0.0) -> str:
    """Send one system + user message to the configured model and return its text."""
    if not is_enabled():
        raise LLMConfigError("No model configured: set LLM_PROVIDER, LLM_MODEL and an API key.")
    p, model, key = provider(), os.environ["LLM_MODEL"], _api_key(provider())

    if p == "anthropic":
        import anthropic

        r = anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature, system=system,
            messages=[{"role": "user", "content": user}])
        return r.content[0].text

    import openai  # OpenAI, Azure OpenAI, Gemini and most internal gateways speak this API

    if p == "azure_openai":
        client = openai.AzureOpenAI(api_key=key, azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                                    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))
    elif p == "gemini":
        client = openai.OpenAI(api_key=key, base_url=_GEMINI_URL)
    elif p == "gateway":
        if not os.getenv("LLM_BASE_URL"):
            raise LLMConfigError("LLM_PROVIDER=gateway needs LLM_BASE_URL (the internal endpoint).")
        client = openai.OpenAI(api_key=key, base_url=os.environ["LLM_BASE_URL"])
    else:
        client = openai.OpenAI(api_key=key)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        r = client.chat.completions.create(model=model, max_tokens=max_tokens,
                                           temperature=temperature, messages=messages)
    except Exception as err:  # newer reasoning models reject max_tokens / custom temperature
        if "max_tokens" not in str(err) and "temperature" not in str(err):
            raise
        r = client.chat.completions.create(model=model, max_completion_tokens=max_tokens,
                                           messages=messages)
    return r.choices[0].message.content or ""


# ---- Policy assistant prompt ------------------------------------------------------------

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


def generate(question: str, excerpts: list[str], lang: str = "en") -> str:
    if not is_enabled():
        return _offline_answer(excerpts, lang)
    context = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(excerpts, start=1))
    return complete(SYSTEM_PROMPT,
                    f"Policy excerpts:\n\n{context}\n\nEmployee question: {question}",
                    max_tokens=500, temperature=0)


def _offline_answer(excerpts: list[str], lang: str = "en") -> str:
    if lang == "es":
        return ("(Modo sin conexión, sin modelo configurado. Texto de política más relevante:)\n\n"
                f"{excerpts[0]} [1]")
    return ("(Offline mode, no model configured. Most relevant policy text:)\n\n"
            f"{excerpts[0]} [1]")
