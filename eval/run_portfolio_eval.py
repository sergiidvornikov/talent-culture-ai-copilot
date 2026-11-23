"""Test the AI portfolio scoring, governance gates and monitoring:  python eval/run_portfolio_eval.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from assistant import portfolio  # noqa: E402


def main() -> int:
    ok = True
    rows = portfolio.ranked()
    by_id = {r["id"]: r for r in rows}

    print("1. Register is well formed")
    funcs = {r["function"] for r in rows}
    scopes = {r["scope"] for r in rows}
    in_range = all(1 <= r[k] <= 5 for r in rows for k in portfolio.CRITERIA)
    weights = sum(portfolio.ASSUME["weights"].values())
    checks = {f"{len(rows)} use cases, all scores 1-5": in_range,
              "weights sum to 1": abs(weights - 1) < 1e-9,
              "all three functions covered": funcs == set(portfolio.FUNCTIONS),
              "local and global scope covered": {"Local UK", "Global"} <= scopes,
              "every stage represented": {r["stage"] for r in rows} == set(portfolio.STAGES)}
    for name, passed in checks.items():
        print(f"   {'✓' if passed else '✗'} {name}")
        ok &= passed

    print("2. Scoring is reproducible by hand")
    uc = by_id["UC01"]    # impact 4, feasibility 5, scalability 4, risk 2
    expected = round((0.4 * 4 + 0.3 * 5 + 0.3 * 4) / 5 * 100 - 5 * (2 - 1), 1)
    print(f"   UC01 priority {uc['priority']} (hand calculation {expected})")
    ok &= uc["priority"] == expected
    order = [r["priority"] for r in rows if r["wave"] != "Do not proceed"]
    print(f"   ranking is in descending priority order: {order == sorted(order, reverse=True)}")
    ok &= order == sorted(order, reverse=True)
    raising = dict(uc, risk=5)
    print(f"   raising risk lowers priority: {portfolio.priority_score(raising) < uc['priority']}")
    ok &= portfolio.priority_score(raising) < uc["priority"]

    print("3. Governance gates")
    base = dict(by_id["UC02"])
    gates = {
        "high-risk, no human review -> Stop": (dict(base, human_in_loop=False), "Stop"),
        "no DPIA -> Hold": (dict(base, dpia_done=False), "Hold"),
        "high-risk with DPIA and human -> Proceed with controls": (base, "Proceed with controls"),
        "low-risk with DPIA -> Proceed": (dict(by_id["UC10"]), "Proceed"),
    }
    for name, (case, want) in gates.items():
        got = portfolio.governance(case)[0]
        print(f"   {'✓' if got == want else '✗'} {name} (got {got})")
        ok &= got == want
    stopped = by_id["UC11"]
    print(f"   automatic CV rejection (UC11): {stopped['decision']}, wave '{stopped['wave']}', ranked last: "
          f"{rows[-1]['id'] == 'UC11'}")
    ok &= stopped["decision"] == "Stop" and stopped["wave"] == "Do not proceed" and rows[-1]["id"] == "UC11"

    print("4. Business case arithmetic")
    bc = portfolio.business_case(by_id["UC05"])
    want = 160 * 12 * portfolio.ASSUME["loaded_hourly_cost_gbp"]
    print(f"   UC05 annual benefit £{bc['annual_benefit']:,} (expected £{want:,})")
    ok &= bc["annual_benefit"] == want and bc["first_year_net"] == want - 8000 - 12000

    print("5. Scale candidates")
    cands = portfolio.scale_candidates()
    clean = all(c["stage"] in ("pilot", "live") and c["decision"] != "Stop"
                and set(c["planned_regions"]) - set(c["live_regions"]) for c in cands)
    print(f"   {len(cands)} candidates; all live or in pilot, none stopped, all with new regions: {clean}")
    ok &= bool(cands) and clean

    print("6. Adoption, impact and monitoring")
    tools = portfolio.tool_summary()
    sane = all(0 < t["adoption"] <= 1 and t["active"] <= t["eligible"] for t in tools)
    months = portfolio.impact_by_month()
    growing = list(months.values())[-1]["hours_saved"] > list(months.values())[0]["hours_saved"]
    flags = portfolio.monitoring_flags()
    print(f"   {len(tools)} tools tracked; adoption within 0-100%: {sane}; impact grows over time: {growing}")
    print(f"   {len(flags)} monitoring flag(s) raised for the review")
    ok &= sane and growing and any("Internal Mobility" in f for f in flags)
    ok &= all(t["id"] in by_id and by_id[t["id"]]["stage"] in ("pilot", "live") for t in tools)

    print("\nAll checks passed" if ok else "\nSome checks FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
