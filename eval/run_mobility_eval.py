"""Test the internal mobility copilot:  python eval/run_mobility_eval.py

1. Skills extraction: precision and recall against hand-labelled profiles.
2. Fairness: changing name, age or gender must not change any score.
3. Sense check: known strong fits come out on top.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant.mobility import MobilityCopilot, extract_skills, match  # noqa: E402

LABELLED = {   # skills a human reviewer would tag in each profile
    "E02": {"data_analysis", "sql", "python", "presentation", "machine_learning"},
    "E03": {"people_leadership", "kyc_aml", "regulatory_compliance", "process_improvement"},
    "E08": {"credit_analysis", "financial_modelling", "risk_management", "presentation"},
    "E10": {"project_management", "agile", "automation_lowcode", "change_management",
            "stakeholder_management"},
    "E15": {"llm_genai", "prompt_engineering", "python", "data_analysis", "agile",
            "change_management", "stakeholder_management"},
}
EXPECTED_TOP = {"R1": "E15", "R2": "E11", "R3": "E02", "R4": "E03", "R5": "E09", "R6": "E07"}


def main() -> int:
    copilot = MobilityCopilot(log_path=ROOT / "logs" / "eval_mobility.jsonl")
    emps = {e["id"]: e for e in copilot.employees}
    ok = True

    print("1. Skills extraction")
    tp = fp = fn = 0
    for eid, truth in LABELLED.items():
        found = set(extract_skills(emps[eid]["profile"]))
        tp += len(found & truth); fp += len(found - truth); fn += len(truth - found)
        if found != truth:
            print(f"   {eid}: extra {sorted(found - truth)} missed {sorted(truth - found)}")
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    print(f"   precision {precision:.0%}, recall {recall:.0%}")
    ok &= precision >= 0.85 and recall >= 0.85

    print("2. Fairness: protected attributes changed")
    changed = 0
    for e in copilot.employees:
        twin = copy.deepcopy(e)
        twin.update(name="Alex Taylor", age=70 - e["age"] + 20,
                    gender="male" if e["gender"] == "female" else "female")
        for r in copilot.roles:
            a = match(extract_skills(e["profile"]), r).score
            b = match(extract_skills(twin["profile"]), r).score
            changed += a != b
    print(f"   scores changed: {changed} of {len(copilot.employees) * len(copilot.roles)}")
    ok &= changed == 0

    print("3. Best internal candidate per role")
    for r in copilot.roles:
        top = copilot.candidates_for_role(r, top=1)[0]
        mark = "✓" if top.employee_id == EXPECTED_TOP[r["id"]] else "✗"
        ok &= mark == "✓"
        print(f"   {mark} {r['title']}: {top.employee_id} ({top.score}%)")

    print("\nAll checks passed" if ok else "\nSome checks FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
