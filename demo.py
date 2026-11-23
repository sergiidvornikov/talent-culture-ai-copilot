"""Bilingual walkthrough in the terminal, offline:  python demo.py

Shows the same controls working in English and Spanish: policy questions with sources,
a comms draft that passes the brand and compliance check, and the top of the AI portfolio.
"""
import os
import tempfile
from pathlib import Path

os.environ["LLM_PROVIDER"] = "offline"   # keep the demo offline and repeatable

from assistant import PolicyAssistant, comms, portfolio  # noqa: E402


def main() -> None:
    log = Path(tempfile.gettempdir()) / "demo_usage.jsonl"
    assistant = PolicyAssistant(log_path=log)
    print("== Policy assistant: same question, two languages ==")
    for q in ["Can I work from Spain for a week?", "¿Puedo teletrabajar desde España una semana?",
              "Quiero denunciar acoso por parte de mi jefe"]:
        a = assistant.ask(q)
        print(f"\n> {q}\n  [{a.language}, {a.status}] sources: {a.sources or '-'}")

    print("\n== Communications Studio: draft, check, approval gate ==")
    for name in ("Graduate programme (press release, EN)", "Comunicado de prensa (ES)"):
        brief = comms.DEMO_BRIEFS[name]
        text, source = comms.draft(brief)
        findings = comms.review(text, brief.kind, brief.lang)
        print(f"\n{name}: drafted by {source}; blocking issues {len(comms.blockers(findings))}, "
              f"warnings {len(findings) - len(comms.blockers(findings))}; "
              f"approvers needed: {' + '.join(comms.required_approvers(brief.kind))}")

    print("\n== AI portfolio: top priorities ==")
    for r in portfolio.ranked()[:5]:
        print(f"  {r['id']} {r['name']:<48} {r['function']:<17} priority {r['priority']:>5}  {r['wave']}, {r['decision']}")
    stopped = [r for r in portfolio.ranked() if r["decision"] == "Stop"]
    for r in stopped:
        print(f"  STOPPED: {r['name']}: {r['gate_reasons'][0]}")


if __name__ == "__main__":
    main()
