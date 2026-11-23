"""Fairness audit: are shortlists balanced across groups?

Reads diversity data that is held separately and never used for matching.
Uses the adverse impact ratio (AIR): each group's selection rate divided by
the highest group's rate. Below 0.8 (the "four-fifths rule") is a warning sign
that needs investigating, not proof of bias. Small groups are reported but not judged.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from .mobility import DATA, MobilityCopilot

AIR_THRESHOLD = 0.8
MIN_GROUP = 3            # below this many people, rates are too unstable to judge


def age_band(age: int) -> str:
    return "Under 30" if age < 30 else "30-44" if age < 45 else "45+"


@dataclass
class GroupResult:
    attribute: str
    group: str
    people: int
    selected: int
    opportunities: int
    rate: float
    air: float | None
    status: str          # ok | review | too few to judge | not assessed


def audit(copilot: MobilityCopilot, shortlist_size: int = 5) -> list[GroupResult]:
    diversity = json.loads((DATA / "demographics.json").read_text(encoding="utf-8"))["records"]
    groups = {
        "Gender": {e["id"]: e["gender"].title() for e in copilot.employees},
        "Age band": {e["id"]: age_band(e["age"]) for e in copilot.employees},
        "Ethnicity": {eid: r["ethnicity"] for eid, r in diversity.items()},
    }
    selected = defaultdict(int)
    for role in copilot.roles:
        for m in copilot.candidates_for_role(role, top=shortlist_size):
            selected[m.employee_id] += 1
    n_roles = len(copilot.roles)

    results: list[GroupResult] = []
    for attr, mapping in groups.items():
        members = defaultdict(list)
        for eid, g in mapping.items():
            members[g].append(eid)
        rates = {}
        for g, ids in members.items():
            sel = sum(selected[i] for i in ids)
            rates[g] = (len(ids), sel, len(ids) * n_roles, sel / (len(ids) * n_roles))
        judged = [r[3] for g, r in rates.items() if r[0] >= MIN_GROUP and g != "Prefer not to say"]
        best = max(judged) if judged else 0
        for g, (n, sel, opp, rate) in sorted(rates.items(), key=lambda kv: -kv[1][0]):
            if g == "Prefer not to say":
                air, status = None, "not assessed"
            elif n < MIN_GROUP:
                air, status = None, "too few to judge"
            else:
                air = round(rate / best, 2) if best else None
                status = "ok" if air is not None and air >= AIR_THRESHOLD else "review"
            results.append(GroupResult(attr, g, n, sel, opp, round(rate, 2), air, status))
    return results
