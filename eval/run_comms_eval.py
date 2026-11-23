"""Test the Communications Studio controls:  python eval/run_comms_eval.py

Checks that the brand and compliance rules catch seeded problems, that generated drafts are
clean, and that the approval gate cannot be bypassed. Runs offline (the LLM is switched off
so results are repeatable).
"""
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

os.environ["LLM_PROVIDER"] = "offline"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant import comms  # noqa: E402

SEEDED_EN = ("We guarantee risk-free returns and will outperform every rival: the best bank around! "
             "Unpublished results are strong. Contact jane.doe@example.com. We expect growth. [quote TBC]")
EXPECTED_EN = {"guarantee", "risk-free", "outperform", "best bank", "unpublished results",
               "personal data: EMAIL", "forward-looking statement", "unresolved placeholder",
               "missing disclaimer: 'forward-looking statements'"}
SEEDED_ES = "Resultado garantizado y sin riesgo. Somos el mejor banco; tenemos información privilegiada."
EXPECTED_ES = {"garantizado", "sin riesgo", "el mejor banco", "información privilegiada"}


def main() -> int:
    ok = True
    log = Path(tempfile.gettempdir()) / "eval_comms_audit.jsonl"
    log.unlink(missing_ok=True)

    print("1. Seeded problems are caught")
    found = {f.term for f in comms.review(SEEDED_EN, "press_release", "en")}
    missed = EXPECTED_EN - found
    print(f"   English: caught {len(EXPECTED_EN & found)}/{len(EXPECTED_EN)}"
          + (f"; missed {sorted(missed)}" if missed else ""))
    ok &= not missed
    found_es = {f.term for f in comms.review(SEEDED_ES, "client_post", "es")}
    missed_es = EXPECTED_ES - found_es
    print(f"   Spanish: caught {len(EXPECTED_ES & found_es)}/{len(EXPECTED_ES)}"
          + (f"; missed {sorted(missed_es)}" if missed_es else ""))
    ok &= not missed_es
    warn = {f.term for f in comms.review("A synergy and a paradigm shift! Wow! Great! NorthBank CIB.",
                                         "internal_announcement", "en") if f.severity == "warn"}
    print(f"   tone and brand warnings: {sorted(warn)}")
    ok &= {"synergy", "paradigm shift", "exclamation marks", "NorthBank CIB"} <= warn

    print("2. Generated drafts from the demo briefs are clean")
    dirty = []
    for name, brief in comms.DEMO_BRIEFS.items():
        text, source = comms.draft(brief)
        issues = comms.review(text, brief.kind, brief.lang)
        if issues or source != "template":
            dirty.append(name)
    print(f"   {len(comms.DEMO_BRIEFS) - len(dirty)}/{len(comms.DEMO_BRIEFS)} drafts with no findings"
          + (f"; dirty: {dirty}" if dirty else ""))
    ok &= not dirty

    print("3. The tool never invents a quote")
    base = comms.DEMO_BRIEFS["Graduate programme (press release, EN)"]
    text, _ = comms.draft(replace(base, quote=""))
    blocked = any(f.term == "unresolved placeholder" for f in comms.review(text, "press_release", "en"))
    print(f"   missing quote leaves a placeholder that blocks approval: {blocked}")
    ok &= blocked

    print("4. Approval gate")
    ext = comms.DEMO_BRIEFS["Client post (EN)"]
    good, _ = comms.draft(ext)
    both = {"Communications": "Sam Lee", "Compliance": "Riley Cho"}
    cases = {
        "blocking issue in text": lambda: comms.approve("client_post", "en", good, good + " Guaranteed!", both, True, log),
        "no Compliance approver": lambda: comms.approve("client_post", "en", good, good, {"Communications": "Sam Lee"}, True, log),
        "same person twice": lambda: comms.approve("client_post", "en", good, good, {"Communications": "Sam", "Compliance": "sam"}, True, log),
        "blank name": lambda: comms.approve("client_post", "en", good, good, {"Communications": "Sam Lee", "Compliance": " "}, True, log),
    }
    for name, call in cases.items():
        try:
            call()
            print(f"   ✗ accepted: {name}"); ok = False
        except ValueError:
            print(f"   ✓ refused: {name}")
    warned = good + " This is a leverage story."
    try:
        comms.approve("client_post", "en", good, warned, both, False, log)
        print("   ✗ accepted unacknowledged warning"); ok = False
    except ValueError:
        print("   ✓ refused: warnings not acknowledged")
    final = good.replace("Webinar", "Online webinar")
    rec = comms.approve("client_post", "en", good, final, both, True, log)
    checks = {"approved_by recorded": rec["approved_by"] == both,
              "human edit detected": rec["edited_by_human"] is True,
              "text fingerprint present": len(rec["final_hash"]) == 16,
              "AI role limited": rec["ai_role"] == "drafting and checks only"}
    for name, passed in checks.items():
        print(f"   {'✓' if passed else '✗'} {name}")
        ok &= passed
    internal, _ = comms.draft(comms.DEMO_BRIEFS["AI Academy launch (internal, EN)"])
    comms.approve("internal_announcement", "en", internal, internal, {"Communications": "Sam Lee"}, True, log)
    print("   ✓ internal message needs one Communications approver")

    print("5. Audit log")
    comms.log_draft(base, text, "template", log)
    events = [r["event"] for r in comms.read_log(log)]
    print(f"   {len(events)} entries: {events.count('comms_approved')} approvals, "
          f"{events.count('comms_drafted')} drafts")
    ok &= events.count("comms_approved") == 2 and events.count("comms_drafted") == 1

    print("\nAll checks passed" if ok else "\nSome checks FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
