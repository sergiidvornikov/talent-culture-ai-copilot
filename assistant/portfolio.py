"""AI use-case portfolio: score, prioritise, check governance gates, build a simple business
case and monitor adoption and impact.

Scoring is a transparent formula, not a model, so every rank can be explained to a sponsor:
    value      = 0.40 impact + 0.30 feasibility + 0.30 scalability   (each 1-5, scaled to 100)
    priority   = value - 5 x (risk - 1)                               (risk 1-5, 5 = highest)
Governance gates are separate from the score: a high-value use case can still be stopped.
"""
from __future__ import annotations

import json
from collections import defaultdict

from .mobility import DATA

_REG = json.loads((DATA / "use_cases.json").read_text(encoding="utf-8"))
_ADOPT = json.loads((DATA / "adoption.json").read_text(encoding="utf-8"))
ASSUME = _REG["assumptions"]
FUNCTIONS = ["Talent & Culture", "Marketing", "Communications"]
STAGES = ["idea", "assessed", "pilot", "live"]
CRITERIA = ("impact", "feasibility", "scalability", "risk")


def use_cases() -> list[dict]:
    return [dict(u) for u in _REG["use_cases"]]


def value_score(uc: dict) -> float:
    w = ASSUME["weights"]
    raw = sum(w[k] * uc[k] for k in ("impact", "feasibility", "scalability"))
    return round(raw / 5 * 100, 1)


def priority_score(uc: dict) -> float:
    return round(value_score(uc) - ASSUME["risk_penalty_per_point"] * (uc["risk"] - 1), 1)


def governance(uc: dict) -> tuple[str, list[str]]:
    """Return (decision, reasons). Decisions: Stop, Hold, Proceed with controls, Proceed."""
    reasons, high = [], uc["eu_ai_act"] == "high"
    if high and not uc["human_in_loop"]:
        return "Stop", ["High-risk (EU AI Act) decision with no human review; automated decisions "
                        "about people need meaningful human involvement (GDPR Art. 22)."]
    if not uc["dpia_done"]:
        reasons.append("Data protection impact assessment (DPIA) not completed.")
    if uc["risk"] >= 4 or high:
        reasons += ["High-risk category: needs bias testing, human sign-off, audit log and "
                    "monitoring before and after go-live."]
    if not uc["dpia_done"]:
        return "Hold", reasons
    return ("Proceed with controls" if reasons else "Proceed"), reasons


def wave(uc: dict) -> str:
    decision, _ = governance(uc)
    if decision == "Stop":
        return "Do not proceed"
    p = priority_score(uc)
    if p >= ASSUME["wave1_min"]:
        return "Wave 1"
    return "Wave 2" if p >= ASSUME["wave2_min"] else "Backlog"


def business_case(uc: dict) -> dict:
    rate = ASSUME["loaded_hourly_cost_gbp"]
    benefit = uc["est_hours_saved_month"] * 12 * rate
    net_month = benefit / 12 - uc["run_cost_gbp_year"] / 12
    return {"annual_benefit": round(benefit), "annual_run_cost": uc["run_cost_gbp_year"],
            "build_cost": uc["build_cost_gbp"],
            "first_year_net": round(benefit - uc["run_cost_gbp_year"] - uc["build_cost_gbp"]),
            "payback_months": round(uc["build_cost_gbp"] / net_month, 1) if net_month > 0 else None}


def ranked() -> list[dict]:
    rows = []
    for u in use_cases():
        decision, reasons = governance(u)
        rows.append({**u, "value": value_score(u), "priority": priority_score(u), "wave": wave(u),
                     "decision": decision, "gate_reasons": reasons, **business_case(u)})
    return sorted(rows, key=lambda r: (r["wave"] == "Do not proceed", -r["priority"]))


def scale_candidates() -> list[dict]:
    """Live or pilot solutions with high scalability and regions still to roll out to."""
    return [r for r in ranked() if r["stage"] in ("pilot", "live") and r["scalability"] >= 4
            and set(r["planned_regions"]) - set(r["live_regions"]) and r["decision"] != "Stop"]


# ---- Adoption, impact and monitoring --------------------------------------------------------

def series(uc_id: str) -> list[dict]:
    return sorted((r for r in _ADOPT["records"] if r["uc"] == uc_id), key=lambda r: r["month"])


def impact_by_month() -> dict[str, dict]:
    """Realised hours saved and active users per month, all tools."""
    out: dict[str, dict] = defaultdict(lambda: {"hours_saved": 0, "active": 0})
    for r in _ADOPT["records"]:
        out[r["month"]]["hours_saved"] += r["hours_saved"]
        out[r["month"]]["active"] += r["active"]
    return dict(sorted(out.items()))


def tool_summary() -> list[dict]:
    names = {u["id"]: u for u in use_cases()}
    rows = []
    for uc_id in sorted({r["uc"] for r in _ADOPT["records"]}):
        s, u = series(uc_id), names[uc_id]
        last = s[-1]
        rows.append({"id": uc_id, "name": u["name"], "function": u["function"], "stage": u["stage"],
                     "adoption": round(last["active"] / last["eligible"], 3), "active": last["active"],
                     "eligible": last["eligible"], "hours_saved_month": last["hours_saved"],
                     "plan_hours_month": u["est_hours_saved_month"],
                     "realised_vs_plan": round(last["hours_saved"] / u["est_hours_saved_month"], 2),
                     "satisfaction": last["satisfaction"],
                     "hours_saved_total": sum(r["hours_saved"] for r in s),
                     "incidents_total": sum(r["incidents"] for r in s), "months_live": len(s)})
    return rows


def monitoring_flags() -> list[str]:
    """Plain-language flags for the monthly portfolio review."""
    flags = []
    for t in tool_summary():
        if t["months_live"] >= 3 and t["adoption"] < 0.25:
            flags.append(f"{t['name']}: adoption {t['adoption']:.0%} of eligible users after "
                         f"{t['months_live']} months; check awareness, training and fit.")
        if t["satisfaction"] < 3.5:
            flags.append(f"{t['name']}: satisfaction {t['satisfaction']} is below 3.5.")
        if t["realised_vs_plan"] < 0.5 and t["months_live"] >= 3:
            flags.append(f"{t['name']}: realised hours are {t['realised_vs_plan']:.0%} of plan.")
        s = series(t["id"])
        if s[-1]["incidents"] > 0:
            flags.append(f"{t['name']}: {s[-1]['incidents']} incident(s) in {s[-1]['month']}; review "
                         "in the AI governance forum.")
    return flags


def incident_months() -> list[str]:
    return [f"{r['uc']} {r['month']}" for r in _ADOPT["records"] if r["incidents"]]
