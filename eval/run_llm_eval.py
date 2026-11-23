"""Check the model layer is provider-neutral:  python eval/run_llm_eval.py

Uses stand-in client libraries, so it needs no keys, packages or network.
"""
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant import llm  # noqa: E402

CALLS = []


def fake_openai():
    class _Completions:
        def __init__(self, cfg): self.cfg = cfg
        def create(self, **kw):
            CALLS.append({"sdk": "openai", **self.cfg, **kw})
            msg = types.SimpleNamespace(content="ok")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class OpenAI:
        def __init__(self, **cfg):
            self.chat = types.SimpleNamespace(completions=_Completions(cfg))
    mod = types.ModuleType("openai")
    mod.OpenAI = OpenAI
    mod.AzureOpenAI = OpenAI
    return mod


def fake_anthropic():
    class _Messages:
        def create(self, **kw):
            CALLS.append({"sdk": "anthropic", **kw})
            return types.SimpleNamespace(content=[types.SimpleNamespace(text="ok")])

    class Anthropic:
        def __init__(self, **cfg): self.messages = _Messages()
    mod = types.ModuleType("anthropic")
    mod.Anthropic = Anthropic
    return mod


def set_env(**kw):
    for k in ["LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "OPENAI_API_KEY",
              "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"]:
        os.environ.pop(k, None)
    os.environ.update(kw)


def main() -> int:
    sys.modules["openai"], sys.modules["anthropic"] = fake_openai(), fake_anthropic()
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'✓' if cond else '✗'} {name}")

    print("1. Offline by default")
    set_env()
    check("no provider set -> offline", not llm.is_enabled() and llm.describe() == "offline")
    check("offline policy answer still works", "Offline mode" in llm.generate("q", ["text"]))
    set_env(LLM_PROVIDER="openai", LLM_API_KEY="k")
    check("provider without a model stays offline", not llm.is_enabled())

    print("2. Every provider goes through the same call")
    cases = {
        "openai": dict(LLM_PROVIDER="openai", LLM_MODEL="m", OPENAI_API_KEY="k"),
        "gemini": dict(LLM_PROVIDER="gemini", LLM_MODEL="m", GEMINI_API_KEY="k"),
        "azure_openai": dict(LLM_PROVIDER="azure_openai", LLM_MODEL="m", AZURE_OPENAI_API_KEY="k",
                             AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com"),
        "gateway": dict(LLM_PROVIDER="gateway", LLM_MODEL="m", LLM_API_KEY="k",
                        LLM_BASE_URL="https://llm-gateway.internal/v1"),
        "anthropic": dict(LLM_PROVIDER="anthropic", LLM_MODEL="m", ANTHROPIC_API_KEY="k"),
    }
    for name, env in cases.items():
        set_env(**env)
        CALLS.clear()
        out = llm.complete("system rules", "user text")
        c = CALLS[-1] if CALLS else {}
        sent_system = ("system rules" in str(c.get("messages", ""))) or c.get("system") == "system rules"
        check(f"{name}: returns text, sends system prompt and model", out == "ok" and sent_system
              and c.get("model") == "m")
    set_env(**cases["gemini"]); CALLS.clear(); llm.complete("s", "u")
    check("gemini uses Google's OpenAI-compatible endpoint", "googleapis" in CALLS[-1].get("base_url", ""))
    set_env(**cases["gateway"]); CALLS.clear(); llm.complete("s", "u")
    check("gateway uses the bank's internal endpoint", CALLS[-1].get("base_url") == "https://llm-gateway.internal/v1")

    print("3. Bad settings fail clearly")
    set_env(LLM_PROVIDER="watson")
    try:
        llm.provider(); check("unknown provider rejected", False)
    except llm.LLMConfigError:
        check("unknown provider rejected", True)

    print("4. No module calls a provider directly")
    direct = [p.name for p in (ROOT / "assistant").glob("*.py")
              if p.name != "llm.py" and any(t in p.read_text(encoding="utf-8")
                                            for t in ("import anthropic", "import openai"))]
    check(f"only llm.py imports a provider SDK (others: {direct or 'none'})", not direct)

    print("\nAll checks passed" if ok else "\nSome checks FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
