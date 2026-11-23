"""Internal mobility copilot: skills extraction, explainable matching and learning plans.

Design principles (high-risk HR AI under the EU AI Act):
- Protected attributes (name, age, gender) are removed before any matching.
- Every score is explainable: matched, transferable and missing skills.
- The tool recommends; a person decides. Every recommendation is audit-logged.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import llm

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROTECTED = {"name", "age", "gender", "photo", "nationality", "date_of_birth"}

MUST_WEIGHT, NICE_WEIGHT, TRANSFERABLE_CREDIT = 2.0, 1.0, 0.5


def _load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


TAXONOMY = _load("skills.json")
SKILLS: dict = TAXONOMY["skills"]
RELATED: list[list[str]] = TAXONOMY["related"]


def label(skill_id: str) -> str:
    return SKILLS[skill_id]["label"]


# ---- 1. Skills extraction -----------------------------------------------------

def extract_skills(text: str) -> list[str]:
    """Map free text to skills in the bank's taxonomy.

    With an API key, an LLM reads the text and may only answer with taxonomy
    IDs; otherwise a transparent keyword method is used. Results from both are
    combined so the LLM can catch skills described in unusual words.
    """
    found = _keyword_skills(text)
    if llm.is_enabled():
        found |= _llm_skills(text)
    return sorted(found)


def _keyword_skills(text: str) -> set[str]:
    low = text.lower()
    found = set()
    for sid, s in SKILLS.items():
        for alias in s["aliases"]:
            if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", low):
                found.add(sid)
                break
    return found


def _llm_skills(text: str) -> set[str]:
    catalogue = "\n".join(f"{sid}: {s['label']}" for sid, s in SKILLS.items())
    reply = llm.complete(
        system=("Identify which skills from the catalogue the profile shows clear evidence of. "
                "Reply with a JSON array of skill IDs only. Never infer skills without evidence."),
        user=f"Catalogue:\n{catalogue}\n\nProfile:\n{text}", max_tokens=300, temperature=0)
    try:
        ids = json.loads(re.search(r"\[.*\]", reply, re.S).group(0))
    except (AttributeError, json.JSONDecodeError):
        return set()
    return {i for i in ids if i in SKILLS}          # anything outside the taxonomy is discarded


# ---- 2. Anonymisation -----------------------------------------------------------

def anonymise(employee: dict) -> dict:
    """Return the record without protected attributes. Matching only ever sees this."""
    return {k: v for k, v in employee.items() if k not in PROTECTED}


# ---- 3. Explainable matching ----------------------------------------------------

@dataclass
class Match:
    employee_id: str
    role_id: str
    role_title: str
    score: int                                   # 0-100
    matched: list[str] = field(default_factory=list)
    transferable: list[tuple[str, str]] = field(default_factory=list)  # (needed, via skill held)
    missing: list[str] = field(default_factory=list)
    missing_must: list[str] = field(default_factory=list)

    @property
    def explanation(self) -> str:
        parts = [f"{self.score}% fit for {self.role_title}."]
        if self.matched:
            parts.append("Has: " + ", ".join(label(s) for s in self.matched) + ".")
        if self.transferable:
            parts.append("Transferable: " + ", ".join(
                f"{label(n)} (from {label(v)})" for n, v in self.transferable) + ".")
        if self.missing:
            parts.append("Gaps: " + ", ".join(label(s) for s in self.missing) + ".")
        return " ".join(parts)


def _related_held(skill: str, held: set[str]) -> str | None:
    for group in RELATED:
        if skill in group:
            for other in group:
                if other != skill and other in held:
                    return other
    return None


def match(skills: list[str], role: dict, employee_id: str = "") -> Match:
    held = set(skills)
    m = Match(employee_id, role["id"], role["title"], 0)
    total = got = 0.0
    for weight, required in ((MUST_WEIGHT, role["must"]), (NICE_WEIGHT, role["nice"])):
        for s in required:
            total += weight
            if s in held:
                got += weight
                m.matched.append(s)
            elif (via := _related_held(s, held)):
                got += weight * TRANSFERABLE_CREDIT
                m.transferable.append((s, via))
                m.missing.append(s)
            else:
                m.missing.append(s)
            if s not in held and required is role["must"]:
                m.missing_must.append(s)
    m.score = round(100 * got / total)
    return m


# ---- 4. Learning plan ------------------------------------------------------------

def learning_plan(missing: list[str]) -> list[dict]:
    """Smallest set of catalogue courses covering the gaps (greedy)."""
    courses, todo, plan = _load("courses.json"), set(missing), []
    while todo:
        best = max(courses, key=lambda c: len(todo & set(c["skills"])))
        covered = todo & set(best["skills"])
        if not covered:
            break
        plan.append({**best, "covers": [label(s) for s in sorted(covered)]})
        todo -= covered
    return plan


# ---- 5. The copilot ----------------------------------------------------------------

class MobilityCopilot:
    def __init__(self, log_path: str | Path = ROOT / "logs" / "mobility_audit.jsonl"):
        self.roles = _load("roles.json")
        self.employees = _load("employees.json")
        self.log_path = Path(log_path)
        self._skills_cache: dict[str, list[str]] = {}

    def skills_for(self, employee: dict) -> list[str]:
        safe = anonymise(employee)
        if safe["id"] not in self._skills_cache:
            self._skills_cache[safe["id"]] = extract_skills(safe["profile"])
        return self._skills_cache[safe["id"]]

    def roles_for_employee(self, employee: dict, top: int = 3) -> list[Match]:
        """Employee view: which internal roles fit me, and what would close the gap?"""
        skills = self.skills_for(employee)
        results = sorted((match(skills, r, employee["id"]) for r in self.roles),
                         key=lambda m: m.score, reverse=True)[:top]
        self._audit("employee_view", employee["id"], results)
        return results

    def candidates_for_role(self, role: dict, top: int = 5) -> list[Match]:
        """Recruiter view: anonymised internal shortlist for a role."""
        results = sorted((match(self.skills_for(e), role, e["id"]) for e in self.employees),
                         key=lambda m: m.score, reverse=True)[:top]
        self._audit("recruiter_view", role["id"], results)
        return results

    def _audit(self, view: str, subject: str, results: list[Match]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "view": view, "subject": subject,
            "recommendations": [{"employee": m.employee_id, "role": m.role_id, "score": m.score}
                                for m in results],
            "decision": "pending human review",
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def as_dict(m: Match) -> dict:
    return asdict(m)
