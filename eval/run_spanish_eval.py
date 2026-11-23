"""Test the Spanish policy path:  python eval/run_spanish_eval.py

Checks routing and retrieval on Spanish questions, language detection, Spanish personal-data
masking, that the English results are unaffected, and that the Spanish policies carry exactly
the same figures as the English originals (so a translation cannot silently change a number).
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant import PolicyAssistant  # noqa: E402
from assistant.guardrails import detect_language, redact_pii  # noqa: E402
from assistant.retriever import load_chunks  # noqa: E402


def cases(name: str) -> list[dict]:
    return [json.loads(l) for l in (ROOT / "eval" / name).read_text(encoding="utf-8").splitlines() if l]


def numbers(text: str) -> list[str]:
    """Figures in a text, ignoring thousands separators: '£1,000' and '1.000 £' both give '1000'."""
    return sorted(re.sub(r"[.,]", "", n) for n in re.findall(r"\d+(?:[.,]\d{3})*", text))


def main() -> int:
    ok = True
    assistant = PolicyAssistant(log_path=Path(tempfile.gettempdir()) / "eval_es_usage.jsonl")
    es_cases, en_cases = cases("questions_es.jsonl"), cases("questions.jsonl")

    print("1. Spanish questions: routing and retrieval")
    routing = retrieval = top1 = retrieval_total = 0
    for c in es_cases:
        hits = assistant.retriever_es.search(c["question"], k=assistant.top_k)
        ans = assistant.ask(c["question"])
        good = ans.status == c["expected_status"] and ans.language == "es"
        routing += good
        line = f"{'✓' if good else '✗'} [{ans.status:9}] {c['question']}"
        if "expected_source" in c:
            retrieval_total += 1
            found = [h.citation for h, _ in hits]
            top1 += found[:1] == [c["expected_source"]]
            if c["expected_source"] in found:
                retrieval += 1
            else:
                line += f"\n      expected {c['expected_source']}, got {found}"
        if not good or "expected_source" in c and c["expected_source"] not in [h.citation for h, _ in hits]:
            print("  ", line)
    print(f"   routing {routing}/{len(es_cases)}, retrieval hit rate (top 3) {retrieval}/{retrieval_total}, "
          f"correct section ranked first {top1}/{retrieval_total}")
    ok &= routing == len(es_cases) and retrieval == retrieval_total and top1 == retrieval_total

    print("2. Answers cite Spanish sources and reply in Spanish")
    ans = assistant.ask("¿Cuántos días de vacaciones tengo al año?")
    print(f"   sources: {ans.sources}; Spanish refusal text on unknown topic: "
          f"{assistant.ask('¿Cuál es la aportación al plan de pensiones?').text.startswith('No he encontrado')}")
    ok &= ans.sources == ["leave.md § Derecho a vacaciones anuales"]
    ok &= assistant.ask("¿Cuál es la aportación al plan de pensiones?").text.startswith("No he encontrado")

    print("3. Language detection")
    en_ok = sum(detect_language(c["question"]) == "en" for c in en_cases)
    es_ok = sum(detect_language(c["question"]) == "es" for c in es_cases)
    print(f"   English questions detected as English: {en_ok}/{len(en_cases)}; "
          f"Spanish as Spanish: {es_ok}/{len(es_cases)}")
    ok &= en_ok == len(en_cases) and es_ok == len(es_cases)

    print("4. Spanish personal data is masked")
    sample = "Mi DNI es 12345678Z, mi NIE X1234567L y mi móvil +34 612 345 678"
    redacted, kinds = redact_pii(sample)
    pii_ok = not any(s in redacted for s in ("12345678Z", "X1234567L", "612 345"))
    print(f"   {'pass' if pii_ok else 'FAIL'} ({', '.join(kinds)})")
    ok &= pii_ok

    print("5. Spanish policies match the English ones")
    en = load_chunks(ROOT / "policies")
    es = load_chunks(ROOT / "policies" / "es")
    same_shape = [(c.doc) for c in en] == [(c.doc) for c in es]
    diffs = [f"{a.citation}" for a, b in zip(en, es) if numbers(a.text) != numbers(b.text)]
    print(f"   {len(es)} sections in {len({c.doc for c in es})} documents; same document and section order: "
          f"{same_shape}; sections whose figures differ: {len(diffs)}" + (f" {diffs}" if diffs else ""))
    ok &= same_shape and not diffs

    print("6. English path unchanged")
    en_route = sum(assistant.ask(c["question"], "en").status == c["expected_status"] for c in en_cases)
    print(f"   English routing {en_route}/{len(en_cases)}")
    ok &= en_route == len(en_cases)

    print("\nAll checks passed" if ok else "\nSome checks FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
