"""Recruiting workflow: job description, inclusive-language check, interview kit,
scorecards and a human decision gate, with every step audit-logged.

Automation handles the drafting, consistency and admin. People approve the job
description, choose who to interview and make the hiring decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .mobility import DATA, ROOT, label

MUST_WEIGHT, NICE_WEIGHT = 2, 1
RUBRIC = {
    1: "No relevant example, or the example does not show the skill.",
    3: "Relevant example; limited depth, scope or measurable result.",
    5: "Strong, specific example with a measurable result; explains trade-offs and lessons.",
}

# ---- 1. Inclusive-language check ----------------------------------------------------
# Based on research on gender-coded job adverts (Gaucher, Friesen & Kay, 2011) and
# common age- and ability-related exclusions. Each entry: term -> (category, suggestion).
LEXICON = {
    "rockstar": ("gender-coded", "skilled"), "ninja": ("gender-coded", "expert"),
    "guru": ("gender-coded", "specialist"), "aggressive": ("gender-coded", "ambitious"),
    "dominant": ("gender-coded", "leading"), "dominate": ("gender-coded", "lead"),
    "fearless": ("gender-coded", "confident"), "competitive": ("gender-coded", "motivated"),
    "headstrong": ("gender-coded", "determined"), "manpower": ("gender-coded", "staff"),
    "chairman": ("gender-coded", "chair"), "he will": ("gender-coded", "you will"),
    "young": ("age-related", "remove"), "energetic": ("age-related", "motivated"),
    "digital native": ("age-related", "confident with digital tools"),
    "recent graduate": ("age-related", "early in your career (if needed at all)"),
    "native english": ("national-origin", "fluent English"),
    "native speaker": ("national-origin", "fluent"),
    "mother tongue": ("national-origin", "fluent"),
    "culture fit": ("bias risk", "values alignment, defined in specific behaviours"),
    "must be able to stand": ("ability-related", "describe the actual task"),
    "clean-shaven": ("religion-related", "remove"),
}
MAX_ESSENTIAL = 5   # long essential lists put off qualified applicants


@dataclass
class Finding:
    term: str
    category: str
    suggestion: str


def check_language(text: str, essential_count: int | None = None) -> list[Finding]:
    low = text.lower()
    found = [Finding(t, c, s) for t, (c, s) in LEXICON.items()
             if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low)]
    if re.search(r"\b\d{2,}\+?\s*years", low):
        found.append(Finding("high years-of-experience requirement", "age-related",
                             "describe the skills needed rather than years"))
    if essential_count is not None and essential_count > MAX_ESSENTIAL:
        found.append(Finding(f"{essential_count} essential requirements", "too many essentials",
                             f"keep essentials to {MAX_ESSENTIAL} or fewer; move the rest to desirable"))
    return found


# ---- 2. Job description --------------------------------------------------------------

def draft_job_description(role: dict) -> str:
    """Draft from the structured role. With an API key the LLM writes the prose;
    the offline template is used otherwise. Both go through the same check."""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return _llm_jd(role)
        except Exception:
            pass
    return _template_jd(role)


def _template_jd(role: dict) -> str:
    lines = [f"# {role['title']}", f"{role['location']} · {role['work_pattern']}", "",
             "## About the role", role["summary"], "", "## What you'll do"]
    lines += [f"- {r}" for r in role["responsibilities"]]
    lines += ["", "## What you'll need"] + [f"- {label(s)}" for s in role["must"]]
    lines += ["", "## Good to have"] + [f"- {label(s)}" for s in role["nice"]]
    lines += ["", "## How we hire",
              "Every candidate is asked the same questions and scored against the same criteria. "
              "If you need an adjustment at any stage, tell us and we will make it. "
              "We welcome applications from people of all backgrounds, and we are open to "
              "flexible working."]
    return "\n".join(lines)


def _llm_jd(role: dict) -> str:
    import anthropic

    spec = json.dumps({**role, "must": [label(s) for s in role["must"]],
                       "nice": [label(s) for s in role["nice"]]}, ensure_ascii=False)
    msg = anthropic.Anthropic().messages.create(
        model=os.getenv("HR_ASSISTANT_MODEL", "claude-sonnet-5-5"), max_tokens=900, temperature=0.3,
        system=("Write a clear, inclusive job advert in markdown from the structured role. "
                "Use only the facts given. List essential and good-to-have skills separately. "
                "Avoid gender-coded, age-related and jargon-heavy wording. No years-of-experience "
                "requirements. Under 350 words. End with a 'How we hire' section on structured, "
                "fair interviews and adjustments."),
        messages=[{"role": "user", "content": spec}],
    )
    return msg.content[0].text


# ---- 3. Interview kit ----------------------------------------------------------------

def interview_kit(role: dict) -> list[dict]:
    """One block per required skill: questions, weight and the shared rubric."""
    bank = json.loads((DATA / "interview_questions.json").read_text(encoding="utf-8"))
    kit = []
    for weight, skills in ((MUST_WEIGHT, role["must"]), (NICE_WEIGHT, role["nice"])):
        for s in skills:
            questions = bank.get(s) or [f"Tell me about a time you used {label(s).lower()} "
                                        "in your work. What was the result?"]
            kit.append({"skill": s, "label": label(s), "essential": weight == MUST_WEIGHT,
                        "weight": weight, "questions": questions, "rubric": RUBRIC})
    return kit


# ---- 4. Scorecards and calibration ----------------------------------------------------

@dataclass
class ScorecardSummary:
    candidate: str
    weighted_score: float                 # 1-5
    essential_below_3: list[str] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def flags(self) -> list[str]:
        out = []
        if self.missing:
            out.append("Missing ratings: " + ", ".join(self.missing))
        if self.disagreements:
            out.append("Interviewers disagree by 2+ points on: " + ", ".join(self.disagreements)
                       + ". Discuss before deciding.")
        if self.essential_below_3:
            out.append("Below 3 on essential skills: " + ", ".join(self.essential_below_3))
        return out


def summarise_scorecard(candidate: str, kit: list[dict],
                        ratings: dict[str, dict[str, int | None]]) -> ScorecardSummary:
    """ratings = {interviewer: {skill_id: 1-5 or None}}"""
    s = ScorecardSummary(candidate, 0.0)
    total = weight_sum = 0.0
    for item in kit:
        sid = item["skill"]
        scores = [r.get(sid) for r in ratings.values()]
        given = [x for x in scores if x is not None]
        if len(given) < len(scores):
            s.missing.append(item["label"])
        if not given:
            continue
        if max(given) - min(given) >= 2:
            s.disagreements.append(item["label"])
        avg = sum(given) / len(given)
        if item["essential"] and avg < 3:
            s.essential_below_3.append(item["label"])
        total += avg * item["weight"]
        weight_sum += item["weight"]
    s.weighted_score = round(total / weight_sum, 2) if weight_sum else 0.0
    return s


def demo_ratings(candidate: str, kit: list[dict], match) -> dict[str, dict[str, int]]:
    """Synthetic interview scores for the demo, loosely based on the skills match."""
    held = set(match.matched)
    transferable = {n for n, _ in match.transferable}
    out = {"Interviewer A": {}, "Interviewer B": {}}
    for item in kit:
        sid = item["skill"]
        base = 4 if sid in held else 3 if sid in transferable else 2
        h = int(hashlib.md5(f"{candidate}{sid}".encode()).hexdigest(), 16)
        jitter = -2 if h % 13 == 0 else {0: 1, 1: -1}.get(h % 4, 0)   # mostly close, sometimes not
        out["Interviewer A"][sid] = max(1, min(5, base + jitter))
        out["Interviewer B"][sid] = max(1, min(5, base))
    return out


# ---- 5. Decision gate and audit -------------------------------------------------------

AUDIT_LOG = ROOT / "logs" / "recruiting_audit.jsonl"


def log_event(event: str, role: dict, **details) -> None:
    """Record each human approval in the workflow (JD sign-off, shortlist choice)."""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event,
           "role": role["id"], **details}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


DECISIONS = ["Offer", "Hold", "Reject"]


def record_decision(role: dict, candidate: str, decision: str, reason: str, decided_by: str,
                    summary: ScorecardSummary,
                    log_path: str | Path = AUDIT_LOG) -> dict:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    if len(reason.strip()) < 15:
        raise ValueError("A decision needs a written reason (at least 15 characters).")
    if not decided_by.strip():
        raise ValueError("The person making the decision must be named.")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(), "event": "hiring_decision",
        "role": role["id"], "candidate": candidate, "decision": decision, "reason": reason.strip(),
        "decided_by": decided_by.strip(), "weighted_score": summary.weighted_score,
        "open_flags": summary.flags, "ai_role": "drafting and decision support only",
    }
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record
