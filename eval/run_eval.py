"""Measure the assistant before rollout:  python eval/run_eval.py

Checks, for a fixed set of test questions:
- retrieval: is the correct policy section among the sources it finds?
- routing:   does it answer, say "not found", or escalate when it should?
- PII:       is personal data removed before processing?
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant import PolicyAssistant  # noqa: E402
from assistant.guardrails import redact_pii  # noqa: E402


def main() -> int:
    assistant = PolicyAssistant(log_path=ROOT / "logs" / "eval.jsonl")
    cases = [json.loads(l) for l in (ROOT / "eval" / "questions.jsonl").read_text().splitlines() if l]

    routing_ok = retrieval_ok = retrieval_total = 0
    for case in cases:
        q = case["question"]
        hits = assistant.retriever.search(q, k=assistant.top_k)
        answer = assistant.ask(q)
        ok_route = answer.status == case["expected_status"]
        routing_ok += ok_route
        mark = "✓" if ok_route else "✗"
        line = f"{mark} [{answer.status:9}] {q}"
        if "expected_source" in case:
            retrieval_total += 1
            found = [c.citation for c, _ in hits]
            if case["expected_source"] in found:
                retrieval_ok += 1
            else:
                line += f"\n      expected {case['expected_source']}, got {found}"
        print(line)

    pii_sample = "My email is jane.doe@example.com, NI number QQ 12 34 56 C, phone 07700 900123"
    redacted, kinds = redact_pii(pii_sample)
    pii_ok = not any(s in redacted for s in ("jane.doe", "QQ 12", "07700"))

    print("\nResults")
    print(f"  Retrieval hit rate (top 3): {retrieval_ok}/{retrieval_total}")
    print(f"  Correct routing:            {routing_ok}/{len(cases)}")
    print(f"  PII redaction test:         {'pass' if pii_ok else 'FAIL'} ({', '.join(kinds)})")
    return 0 if routing_ok == len(cases) and retrieval_ok == retrieval_total and pii_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
