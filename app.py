"""Talent & Culture AI Copilot. Run with:  streamlit run app.py"""
import json
from collections import Counter

import streamlit as st

from assistant import PolicyAssistant
import pandas as pd

from assistant import comms, fairness, intents, llm, portfolio, recruiting
from assistant.mobility import MobilityCopilot, label, learning_plan


st.set_page_config(page_title="Talent & Culture AI Copilot", page_icon="💬", layout="wide")


@st.cache_resource
def get_assistant() -> PolicyAssistant:
    return PolicyAssistant()


@st.cache_resource
def get_mobility() -> MobilityCopilot:
    return MobilityCopilot()


module = st.sidebar.radio("Module", ["Policy Assistant", "Internal Mobility", "Recruiting Workflow",
                                     "Fairness Audit", "Communications Studio", "AI Portfolio"])
st.sidebar.caption("Demo using fictional Northbank CIB data. Runs offline; no API key needed.")
st.sidebar.caption(f"Model: {llm.describe()} (set LLM_PROVIDER to use any provider or the bank's gateway)")


# ---- Module 1: Policy assistant ---------------------------------------------------
def policy_page() -> None:
    assistant = get_assistant()
    st.title("HR Policy Assistant")
    st.caption("Answers employee questions from Talent & Culture policies, with sources. "
               "Responde en español a preguntas en español, con las fuentes.")
    choice = st.radio("Language / Idioma", ["Auto-detect", "English", "Español"], horizontal=True)
    lang = {"Auto-detect": None, "English": "en", "Español": "es"}[choice]

    if "history" not in st.session_state:
        st.session_state.history = []
    for role, content, sources in st.session_state.history:
        with st.chat_message(role):
            st.markdown(content)
            if sources:
                st.caption("Sources: " + " · ".join(sources))

    if not st.session_state.history:
        st.caption("Try a question / Prueba una pregunta:")
        examples = intents.EXAMPLES["es" if lang == "es" else "en"]
        cols = st.columns(len(examples))
        for col, ex in zip(cols, examples):
            if col.button(ex, key=f"ex_{ex}", width="stretch"):
                st.session_state.queued_question = ex

    typed = st.chat_input("Ask about leave, pay, careers, notice periods… / Pregunta sobre vacaciones, retribución, carrera…")
    if question := (typed or st.session_state.pop("queued_question", None)):
        st.session_state.history.append(("user", question, []))
        with st.chat_message("user"):
            st.markdown(question)
        answer = assistant.ask(question, lang)
        with st.chat_message("assistant"):
            st.markdown(answer.text)
            st.caption(f"Language: {'Español' if answer.language == 'es' else 'English'}")
            if answer.sources:
                st.caption("Sources: " + " · ".join(answer.sources))
            if answer.pii_redacted:
                st.info("Personal data was removed before processing: " + ", ".join(answer.pii_redacted))
        st.session_state.history.append(("assistant", answer.text, answer.sources))

    with st.sidebar:
        st.header("Usage dashboard")
        records = []
        if assistant.log_path.exists():
            records = [json.loads(l) for l in assistant.log_path.read_text().splitlines() if l]
        total = len(records)
        st.metric("Questions asked", total)
        if total:
            status = Counter(r["status"] for r in records)
            st.metric("Answered from policy", f"{status['answered'] / total:.0%}")
            st.metric("Referred to Talent & Culture",
                      f"{(status['not_found'] + status['escalated']) / total:.0%}")
            langs = Counter(r.get("language", "en") for r in records)
            st.metric("Asked in Spanish", f"{langs['es'] / total:.0%}")
            topics = Counter(s.split(" § ")[0] for r in records for s in r["sources"])
            if topics:
                st.subheader("Most asked-about policies")
                st.bar_chart(dict(topics.most_common(5)))


# ---- Module 2: Internal mobility ---------------------------------------------------
def show_match(m, show_plan: bool = True) -> None:
    st.progress(m.score / 100, text=f"**{m.score}%** fit")
    cols = st.columns(3)
    cols[0].markdown("**Has**\n\n" + ("\n".join(f"- {label(s)}" for s in m.matched) or "–"))
    cols[1].markdown("**Transferable**\n\n" + ("\n".join(
        f"- {label(n)} *(from {label(v)})*" for n, v in m.transferable) or "–"))
    cols[2].markdown("**Gaps**\n\n" + ("\n".join(
        f"- {label(s)}{' (essential)' if s in m.missing_must else ''}" for s in m.missing) or "–"))
    if show_plan and m.missing:
        plan = learning_plan(m.missing)
        if plan:
            st.markdown("**Suggested learning plan** (" + str(sum(c["hours"] for c in plan)) + " hours)")
            for c in plan:
                st.markdown(f"- {c['title']} · {c['hours']}h · covers {', '.join(c['covers'])}")


def mobility_page() -> None:
    copilot = get_mobility()
    st.title("Internal Mobility Copilot")
    st.caption("Skills-based matching of employees to internal roles. The tool recommends; "
               "a person decides. Name, age and gender are removed before matching.")
    tab_emp, tab_rec = st.tabs(["Employee view: my next role", "Recruiter view: internal shortlist"])

    with tab_emp:
        options = {f"{e['id']} · {e['current_role']}": e for e in copilot.employees}
        emp = options[st.selectbox("Employee (demo profiles)", list(options))]
        with st.expander("Profile and skills found"):
            st.write(emp["profile"])
            st.write("**Skills found:** " + ", ".join(label(s) for s in copilot.skills_for(emp)))
        for m in copilot.roles_for_employee(emp):
            with st.container(border=True):
                st.subheader(m.role_title)
                show_match(m)

    with tab_rec:
        roles = {f"{r['id']} · {r['title']}": r for r in copilot.roles}
        role = roles[st.selectbox("Open role", list(roles))]
        st.caption("Essential: " + ", ".join(label(s) for s in role["must"]) +
                   "  ·  Desirable: " + ", ".join(label(s) for s in role["nice"]))
        for m in copilot.candidates_for_role(role):
            with st.container(border=True):
                st.markdown(f"**Candidate {m.employee_id}** (anonymised)")
                show_match(m, show_plan=False)
        st.info("Every shortlist is written to the audit log with status 'pending human review'.")



# ---- Module 3: Recruiting workflow ----------------------------------------------------
def recruiting_page() -> None:
    copilot = get_mobility()
    st.title("Recruiting Workflow")
    st.caption("AI drafts, checks and organises. People approve the advert, choose who to "
               "interview and make every hiring decision. Each approval is audit-logged.")
    roles = {f"{r['id']} · {r['title']}": r for r in copilot.roles}
    role = roles[st.selectbox("Vacancy", list(roles))]
    key = role["id"]

    # Step 1: job description
    st.header("1 · Job description")
    if f"jd_{key}" not in st.session_state:
        st.session_state[f"jd_{key}"] = recruiting.draft_job_description(role)
    jd = st.text_area("Draft (edit freely)", key=f"jd_{key}", height=320)
    findings = recruiting.check_language(jd, len(role["must"]))
    if findings:
        st.warning("Inclusive-language check found issues:")
        st.table(pd.DataFrame([{"Wording": f.term, "Issue": f.category, "Suggestion": f.suggestion}
                               for f in findings]))
    else:
        st.success("Inclusive-language check: no issues found.")
    c1, c2 = st.columns([2, 1])
    approver = c1.text_input("Hiring manager", key=f"appr_{key}")
    if c2.button("Approve advert", key=f"approve_{key}", disabled=bool(findings) or not approver):
        recruiting.log_event("jd_approved", role, approved_by=approver)
        st.session_state[f"jd_ok_{key}"] = approver
    if st.session_state.get(f"jd_ok_{key}"):
        st.caption(f"Approved by {st.session_state[f'jd_ok_{key}']}. Ready to post in the ATS.")

    # Step 2: internal candidates first
    st.header("2 · Internal candidates first")
    st.caption("Anonymised internal matches. External applicants arrive through the ATS and "
               "are assessed with the same interview kit.")
    matches = copilot.candidates_for_role(role)
    st.dataframe(pd.DataFrame([{"Candidate": m.employee_id, "Fit": f"{m.score}%",
                                "Has": ", ".join(label(x) for x in m.matched),
                                "Gaps": ", ".join(label(x) for x in m.missing)} for m in matches]),
                 hide_index=True, width="stretch")
    chosen = st.multiselect("Who will you interview? (your decision)",
                            [m.employee_id for m in matches],
                            default=[m.employee_id for m in matches[:3]], key=f"chosen_{key}")

    # Step 3: interview kit
    st.header("3 · Structured interview kit")
    kit = recruiting.interview_kit(role)
    kit_md = [f"# Interview kit: {role['title']}", "",
              "Score every answer 1-5 against the rubric. Ask every candidate the same questions.", ""]
    for item in kit:
        with st.expander(f"{item['label']} {'(essential, weight 2)' if item['essential'] else '(desirable)'}"):
            for q in item["questions"]:
                st.markdown(f"- {q}")
            st.caption(" · ".join(f"**{k}**: {v}" for k, v in item["rubric"].items()))
        kit_md += [f"## {item['label']}"] + [f"- {q}" for q in item["questions"]] + [""]
    kit_md += ["## Rubric"] + [f"- **{k}**: {v}" for k, v in recruiting.RUBRIC.items()]
    st.download_button("Download interview kit", "\n".join(kit_md),
                       file_name=f"interview_kit_{key}.md")

    # Step 4: scorecards
    st.header("4 · Scorecards")
    st.caption("Demo ratings are pre-filled; edit them as interviewers would.")
    by_id = {m.employee_id: m for m in matches}
    summaries = {}
    for cid in chosen:
        ratings = recruiting.demo_ratings(cid, kit, by_id[cid])
        df = pd.DataFrame({"Skill": [i["label"] for i in kit],
                           "Essential": [i["essential"] for i in kit],
                           **{who: [r[i["skill"]] for i in kit] for who, r in ratings.items()}})
        with st.container(border=True):
            st.subheader(f"Candidate {cid}")
            edited = st.data_editor(df, key=f"sc_{key}_{cid}", hide_index=True,
                                    disabled=["Skill", "Essential"], width="stretch")
            back = {who: {i["skill"]: (None if pd.isna(edited.loc[n, who]) else int(edited.loc[n, who]))
                          for n, i in enumerate(kit)} for who in ratings}
            summ = recruiting.summarise_scorecard(cid, kit, back)
            summaries[cid] = summ
            st.metric("Weighted score (1-5)", summ.weighted_score)
            for flag in summ.flags:
                st.warning(flag)

    # Step 5: decision
    st.header("5 · Decision (human)")
    if summaries:
        ranked = sorted(summaries.values(), key=lambda s: s.weighted_score, reverse=True)
        st.caption("Ranked by weighted score for reference only: "
                   + " > ".join(f"{s.candidate} ({s.weighted_score})" for s in ranked))
        with st.form(f"decision_{key}"):
            cid = st.selectbox("Candidate", [s.candidate for s in ranked])
            decision = st.radio("Decision", recruiting.DECISIONS, horizontal=True)
            reason = st.text_area("Reason, tied to the interview evidence")
            who = st.text_input("Decided by")
            if st.form_submit_button("Record decision"):
                try:
                    rec = recruiting.record_decision(role, cid, decision, reason, who, summaries[cid])
                    st.success(f"Recorded: {rec['decision']} for {cid} by {rec['decided_by']}.")
                except ValueError as err:
                    st.error(str(err))


# ---- Module 4: Fairness audit -----------------------------------------------------------
def fairness_page() -> None:
    st.title("Fairness Audit")
    st.caption("Are internal shortlists balanced across groups? Diversity data is held "
               "separately and never used for matching; it is used only here, to check outcomes.")
    k = st.slider("Shortlist size per role", 3, 8, 5)
    results = fairness.audit(get_mobility(), shortlist_size=k)
    df = pd.DataFrame([{"Attribute": r.attribute, "Group": r.group, "People": r.people,
                        "Shortlisted": f"{r.selected} of {r.opportunities}",
                        "Selection rate": f"{r.rate:.0%}",
                        "Impact ratio": "–" if r.air is None else f"{r.air:.2f}",
                        "Status": r.status} for r in results])
    st.dataframe(df, hide_index=True, width="stretch")
    flagged = [r for r in results if r.status == "review"]
    if flagged:
        st.warning("Below the four-fifths threshold: " + "; ".join(
            f"{r.attribute} / {r.group} ({r.air:.2f})" for r in flagged)
            + ". Next step: check whether the role requirements driving this are genuinely needed.")
    st.info("Impact ratio = a group's selection rate divided by the highest group's rate. Below 0.80 "
            "is a warning sign that needs investigating, not proof of bias. Groups under 3 people "
            "are too small to judge. With 15 synthetic employees this is a demonstration; in "
            "practice the audit runs across many vacancies.")



# ---- Module 5: Communications Studio ---------------------------------------------------
def comms_page() -> None:
    st.title("Communications Studio")
    st.caption("AI drafts internal announcements, press releases and client posts and checks them against "
               "brand, tone and compliance rules. People approve: Communications for internal messages, "
               "Communications and Compliance (two different people) for anything external. "
               "Every draft and approval is audit-logged.")
    demo_name = st.selectbox("Start from a demo brief", list(comms.DEMO_BRIEFS))
    demo = comms.DEMO_BRIEFS[demo_name]
    k = demo_name   # widget keys change with the demo, so fields reset when it changes

    c1, c2 = st.columns(2)
    kinds = list(comms.KINDS)
    kind = c1.selectbox("Type", kinds, index=kinds.index(demo.kind), key=f"kind_{k}",
                        format_func=lambda x: comms.KINDS[x]["label"])
    lang = c2.radio("Language", list(comms.LANGS), index=list(comms.LANGS).index(demo.lang), key=f"lang_{k}",
                    horizontal=True, format_func=lambda x: comms.LANGS[x])
    headline = st.text_input("Headline", demo.headline, key=f"head_{k}")
    points = st.text_area("Key facts (one per line; the draft uses only these)",
                          "\n".join(demo.key_points), height=130, key=f"pts_{k}")
    with st.expander("Spokesperson, quote and details"):
        d1, d2 = st.columns(2)
        spokesperson = d1.text_input("Spokesperson (name, title)", demo.spokesperson, key=f"sp_{k}")
        date = d2.text_input("Date", demo.date, key=f"date_{k}")
        quote = st.text_input("Quote (must come from the spokesperson; the tool never invents quotes)",
                              demo.quote, key=f"quote_{k}")
        contact = d1.text_input("Contact (internal)", demo.contact, key=f"contact_{k}")
        link = d2.text_input("Link (client post)", demo.link, key=f"link_{k}")

    if st.button("Generate draft", type="primary"):
        brief = comms.Brief(kind, headline, [p.strip() for p in points.splitlines() if p.strip()],
                            lang, date, spokesperson, quote, contact, link)
        text, source = comms.draft(brief)
        comms.log_draft(brief, text, source)
        st.session_state.update(comms_original=text, comms_text=text, comms_source=source,
                                comms_kind=kind, comms_lang=lang, comms_approved=None)

    if "comms_text" not in st.session_state:
        st.info("Generate a draft to see the checks and the approval step.")
        return

    kind, lang = st.session_state.comms_kind, st.session_state.comms_lang
    st.header("1 · Draft (edit freely)")
    st.caption(f"Written by: {'language model' if st.session_state.comms_source == 'llm' else 'offline template'}")
    text = st.text_area("Draft", key="comms_text", height=340, label_visibility="collapsed")

    st.header("2 · Brand, tone and compliance check")
    findings = comms.review(text, kind, lang)
    blocking = comms.blockers(findings)
    m1, m2 = st.columns(2)
    m1.metric("Blocking issues", len(blocking))
    m2.metric("Warnings", len(findings) - len(blocking))
    if findings:
        st.table(pd.DataFrame([{"Severity": "Blocks approval" if f.severity == "block" else "Warning",
                                "Found": f.term, "Issue": f.category, "Suggestion": f.suggestion}
                               for f in findings]))
    else:
        st.success("No issues found.")
    if comms.KINDS[kind]["external"] and not blocking:
        st.caption("External content: the approved disclaimer is present.")
    if comms.KINDS[kind]["external"] and any(f.category == "required disclaimer" for f in blocking):
        st.code(comms.disclaimer(kind, lang), language=None)

    st.header("3 · Approval (human)")
    roles = comms.required_approvers(kind)
    st.caption("Required: " + " and ".join(roles) + (" (two different people)" if len(roles) > 1 else "") + ".")
    cols = st.columns(len(roles))
    names = {r: cols[i].text_input(f"{r} approver", key=f"apr_{r}") for i, r in enumerate(roles)}
    warned = len(findings) > len(blocking)
    ack = st.checkbox("I have reviewed the warnings", disabled=not warned, value=not warned)
    if st.button("Approve for publication", disabled=bool(blocking)):
        try:
            rec = comms.approve(kind, lang, st.session_state.comms_original, text, names, ack)
            st.session_state.comms_approved = rec
        except ValueError as err:
            st.error(str(err))
    rec = st.session_state.get("comms_approved")
    if rec:
        st.success("Approved by " + ", ".join(f"{n} ({r})" for r, n in rec["approved_by"].items())
                   + f". Text fingerprint {rec['final_hash']}. A person publishes it; the tool does not.")
        st.download_button("Download approved text", text, file_name=f"{kind}_{rec['final_hash']}.md")

    with st.expander("Audit log"):
        log = comms.read_log()
        if log:
            st.dataframe(pd.DataFrame(log).iloc[::-1], hide_index=True, width="stretch")
        else:
            st.caption("No entries yet.")


# ---- Module 6: AI portfolio ---------------------------------------------------------------
def portfolio_page() -> None:
    st.title("AI Portfolio")
    st.caption("Use cases across Talent & Culture, Marketing and Communications, scored on impact, "
               "feasibility, scalability and risk, with governance gates, a simple business case and "
               "an adoption and impact dashboard. Fictional data.")
    tab_rank, tab_impact, tab_new = st.tabs(["Prioritisation", "Adoption and impact", "Score a new idea"])

    with tab_rank:
        rows = portfolio.ranked()
        f1, f2 = st.columns(2)
        funcs = f1.multiselect("Function", portfolio.FUNCTIONS, default=portfolio.FUNCTIONS)
        stages = f2.multiselect("Stage", portfolio.STAGES, default=portfolio.STAGES)
        rows = [r for r in rows if r["function"] in funcs and r["stage"] in stages]
        df = pd.DataFrame([{"ID": r["id"], "Use case": r["name"], "Function": r["function"],
                            "Scope": r["scope"], "Stage": r["stage"], "Impact": r["impact"],
                            "Feasibility": r["feasibility"], "Scalability": r["scalability"],
                            "Risk": r["risk"], "Priority": r["priority"], "Wave": r["wave"],
                            "Governance": r["decision"], "Payback (months)": r["payback_months"]}
                           for r in rows])
        st.dataframe(df, hide_index=True, width="stretch")
        st.caption("Priority = 0.40 impact + 0.30 feasibility + 0.30 scalability (scaled to 100), minus 5 points "
                   "for each risk point above 1. Governance gates are separate from the score: a use case "
                   "can rank well and still be on hold or stopped.")
        if rows:
            st.scatter_chart(pd.DataFrame({"Value score": [r["value"] for r in rows],
                                           "Risk": [r["risk"] for r in rows],
                                           "Function": [r["function"] for r in rows]}),
                             x="Value score", y="Risk", color="Function")
        for r in rows:
            if r["decision"] in ("Stop", "Hold"):
                (st.error if r["decision"] == "Stop" else st.warning)(
                    f"**{r['id']} {r['name']}: {r['decision']}.** " + " ".join(r["gate_reasons"]))
        with st.expander("Business case and detail for one use case"):
            by_id = {f"{r['id']} · {r['name']}": r for r in portfolio.ranked()}
            r = by_id[st.selectbox("Use case", list(by_id))]
            st.write(r["description"])
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Annual benefit", f"£{r['annual_benefit']:,}")
            b2.metric("Build + first-year run", f"£{r['build_cost'] + r['annual_run_cost']:,}")
            b3.metric("First-year net", f"£{r['first_year_net']:,}")
            b4.metric("Payback (months)", r["payback_months"] if r["payback_months"] else "–")
            st.caption(f"Benefit = {r['est_hours_saved_month']} hours/month at full rollout × 12 × "
                       f"£{portfolio.ASSUME['loaded_hourly_cost_gbp']}/hour (assumption). "
                       f"EU AI Act class: {r['eu_ai_act']}. Human in the loop: {'yes' if r['human_in_loop'] else 'no'}. "
                       f"DPIA: {'done' if r['dpia_done'] else 'not done'}.")
        st.subheader("Ready to scale to new regions")
        st.dataframe(pd.DataFrame([{"Use case": r["name"], "Live in": ", ".join(r["live_regions"]),
                                    "Next": ", ".join(sorted(set(r["planned_regions"]) - set(r["live_regions"]))),
                                    "Scalability": r["scalability"], "Governance": r["decision"]}
                                   for r in portfolio.scale_candidates()]),
                     hide_index=True, width="stretch")

    with tab_impact:
        tools = portfolio.tool_summary()
        months = portfolio.impact_by_month()
        last = list(months.values())[-1]
        total_hours = sum(m["hours_saved"] for m in months.values())
        i1, i2, i3, i4 = st.columns(4)
        i1.metric("Tools live or in pilot", len(tools))
        i2.metric("Active users (latest month)", f"{last['active']:,}")
        i3.metric("Hours saved, latest month", f"{last['hours_saved']:,}")
        i4.metric("Hours saved to date", f"{total_hours:,}",
                  help=f"About £{total_hours * portfolio.ASSUME['loaded_hourly_cost_gbp']:,} at the assumed hourly cost")
        st.line_chart(pd.DataFrame({"Hours saved": [m["hours_saved"] for m in months.values()]},
                                   index=list(months)))
        st.dataframe(pd.DataFrame([{"Tool": t["name"], "Stage": t["stage"],
                                    "Adoption": f"{t['adoption']:.0%} ({t['active']} of {t['eligible']})",
                                    "Hours saved (month)": t["hours_saved_month"],
                                    "Plan at full rollout": t["plan_hours_month"],
                                    "Realised vs plan": f"{t['realised_vs_plan']:.0%}",
                                    "Satisfaction (1-5)": t["satisfaction"],
                                    "Incidents to date": t["incidents_total"]} for t in tools]),
                     hide_index=True, width="stretch")
        st.subheader("Monitoring flags for the monthly review")
        flags = portfolio.monitoring_flags()
        for f in flags:
            st.warning(f)
        if not flags:
            st.success("No flags this month.")
        st.caption("Adoption and impact figures are synthetic. In production they come from usage logs, "
                   "short surveys and the incident register, alongside each tool's own audit log.")

    with tab_new:
        st.caption("Score a new idea with the same formula and gates before it enters the backlog.")
        n1, n2 = st.columns(2)
        idea = {"impact": n1.slider("Business impact", 1, 5, 3), "feasibility": n1.slider("Feasibility", 1, 5, 3),
                "scalability": n1.slider("Scalability", 1, 5, 3), "risk": n2.slider("Risk (5 = highest)", 1, 5, 2),
                "eu_ai_act": n2.selectbox("EU AI Act class", ["minimal", "limited", "high"]),
                "dpia_done": n2.checkbox("DPIA completed", True),
                "human_in_loop": n2.checkbox("A person reviews every outcome", True),
                "est_hours_saved_month": n1.number_input("Hours saved per month at full rollout", 0, 5000, 100),
                "build_cost_gbp": n2.number_input("Build cost (£)", 0, 500000, 20000, step=1000),
                "run_cost_gbp_year": n2.number_input("Run cost per year (£)", 0, 500000, 10000, step=1000)}
        decision, reasons = portfolio.governance(idea)
        s1, s2, s3 = st.columns(3)
        s1.metric("Priority score", portfolio.priority_score(idea))
        s2.metric("Wave", portfolio.wave(idea))
        s3.metric("Governance", decision)
        for r in reasons:
            st.warning(r)
        bc = portfolio.business_case(idea)
        st.caption(f"First-year net £{bc['first_year_net']:,}; payback "
                   f"{bc['payback_months'] if bc['payback_months'] else 'not within the run costs'} months.")


{"Policy Assistant": policy_page, "Internal Mobility": mobility_page,
 "Recruiting Workflow": recruiting_page, "Fairness Audit": fairness_page,
 "Communications Studio": comms_page, "AI Portfolio": portfolio_page}[module]()
