"""Test the recruiting workflow and fairness controls:  python eval/run_recruiting_eval.py"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant import fairness, recruiting  # noqa: E402
from assistant.mobility import MobilityCopilot  # noqa: E402

BIASED = ("We want a young, energetic rockstar with a competitive, aggressive streak. "
          "Must be a native English speaker and a digital native with 10+ years in banking. "
          "Great culture fit.")
EXPECTED_TERMS = {"young", "energetic", "rockstar", "competitive", "aggressive",
                  "native english", "digital native", "culture fit",
                  "high years-of-experience requirement"}


def main() -> int:
    ok = True
    copilot = MobilityCopilot(log_path=Path(tempfile.gettempdir()) / "eval_audit.jsonl")

    print("1. Inclusive-language check")
    found = {f.term for f in recruiting.check_language(BIASED)}
    missed = EXPECTED_TERMS - found
    print(f"   caught {len(EXPECTED_TERMS & found)}/{len(EXPECTED_TERMS)} seeded issues"
          + (f"; missed {sorted(missed)}" if missed else ""))
    ok &= not missed
    clean = [r["id"] for r in copilot.roles
             if recruiting.check_language(recruiting.draft_job_description(r), len(r["must"]))]
    print(f"   generated adverts with issues: {len(clean)} of {len(copilot.roles)}")
    ok &= not clean

    print("2. Interview kit covers every required skill")
    for r in copilot.roles:
        kit = {i["skill"] for i in recruiting.interview_kit(r)}
        need = set(r["must"]) | set(r["nice"])
        ok &= kit == need
    print("   all roles covered" if ok else "   GAPS FOUND")

    print("3. Scorecard flags")
    kit = recruiting.interview_kit(copilot.roles[0])
    a = {i["skill"]: 4 for i in kit}
    b = dict(a, python=2, change_management=None)
    s = recruiting.summarise_scorecard("T1", kit, {"A": a, "B": b})
    checks = {"disagreement": "Python" in s.disagreements,
              "missing rating": "Change management" in s.missing,
              "weighted score in 1-5": 1 <= s.weighted_score <= 5}
    for name, passed in checks.items():
        print(f"   {'✓' if passed else '✗'} {name}")
        ok &= passed

    print("4. Decision gate refuses decisions without reason or owner")
    log = Path(tempfile.gettempdir()) / "eval_decisions.jsonl"
    for args in [("Offer", "", "Jane"), ("Offer", "Strong evidence on all essentials", ""),
                 ("Maybe", "Strong evidence on all essentials", "Jane")]:
        try:
            recruiting.record_decision(copilot.roles[0], "T1", *args, s, log_path=log)
            print(f"   ✗ accepted {args}"); ok = False
        except ValueError:
            pass
    rec = recruiting.record_decision(copilot.roles[0], "T1", "Offer",
                                     "Strong evidence on all essentials", "Jane", s, log_path=log)
    print(f"   ✓ invalid decisions refused; valid one logged with {len(rec['open_flags'])} open flag(s)")

    print("5. Diversity data is used only by the audit")
    users = [p.name for p in (ROOT / "assistant").glob("*.py")
             if "demographics" in p.read_text(encoding="utf-8")]
    print(f"   modules reading diversity data: {users}")
    ok &= users == ["fairness.py"]
    results = fairness.audit(copilot)
    print(f"   audit produced {len(results)} group results; "
          f"{sum(r.status == 'review' for r in results)} flagged for review")

    print("\nAll checks passed" if ok else "\nSome checks FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
