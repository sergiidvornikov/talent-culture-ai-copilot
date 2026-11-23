# Talent & Culture AI Copilot

GenAI tools for a bank's Talent & Culture, Marketing and Communications functions, built as a working prototype that runs offline (no API key needed):

1. **HR Policy Assistant (English and Spanish)**: answers employees' policy questions only from the bank's own documents, with a source for every answer.
2. **Internal Mobility Copilot**: matches employees to internal roles on skills, explains every match, and builds a learning plan to close the gaps.
3. **Recruiting Workflow**: takes a vacancy from advert to decision. AI drafts, checks and organises; people approve, choose and decide.
4. **Fairness Audit**: checks whether shortlists are balanced across groups, using diversity data that never feeds the matching.
5. **Communications Studio**: drafts internal announcements, press releases and client posts in English or Spanish, checks them against brand, tone and compliance rules, and blocks publication until the right people approve.
6. **AI Portfolio**: scores AI use cases across Talent & Culture, Marketing and Communications on impact, feasibility, scalability and risk, applies governance gates, and tracks adoption and impact.

> Built on **fictional** data for "Northbank CIB". No real company or employee data is used. This is an independent portfolio project, not a product of any real bank.

---

## 1. HR Policy Assistant

**Problem.** Talent & Culture teams answer the same questions every day (*How many days can I carry over? Can I work from abroad? How do I get a raise?*). The answers are in long policy documents that employees don't read. The demo set covers leave, hybrid working, expenses, learning, onboarding, careers and internal mobility, pay and reward, employment terms, and performance reviews (English and Spanish).

```
question ─► Guardrails ─► Retrieval ─► Grounded answer ─► Usage log
            mask personal   find the 3     LLM answers ONLY     status, sources,
            data; route     most relevant  from those sections, latency → adoption
            sensitive cases policy sections citing each one     dashboard
            to a person
```

| Control | What it does |
|---|---|
| PII redaction | Masks emails, phone, NI and card numbers before anything reaches the model |
| Escalation | Grievance, harassment, redundancy etc. go straight to a person (English and Spanish) |
| Coverage check | If the policies don't cover the question, it says so rather than guessing, names the closest topics and suggests example questions |
| Grounded answers | The LLM answers only from retrieved text, cites each statement, replies in the employee's language |
| Usage dashboard | Adoption, referral rate and the policies that generate the most questions |
| Help and routing | "What can you do?" lists every policy topic with example questions; "What jobs are open?" lists live internal vacancies and points to the Internal Mobility module; unanswered job or internal-move questions are pointed at that module too |

## 2. Internal Mobility Copilot

**Problem.** Banks hire externally for roles that people inside could fill. Employees can't see which roles they're close to, and recruiters can't see internal talent by skill.

```
profile text ─► Anonymise ─► Skills extraction ─► Explainable match ─► Learning plan ─► Audit log
                remove name,  map to the bank's     has / transferable    smallest set of   "pending human
                age, gender   skills taxonomy       / missing skills      courses for gaps  review"
```

- **Employee view:** "Which internal roles fit me, and what would get me there?"
- **Recruiter view:** an anonymised internal shortlist for any open role.
- **Skills extraction:** a transparent keyword method against the taxonomy; with a model configured, the LLM also reads the profile but may only answer with skills from the taxonomy (anything else is discarded).
- **Scoring:** essential skills count double; a related skill earns half credit as "transferable" (e.g. SQL from Python), so adjacent talent isn't overlooked.

### Why the governance matters
AI used for recruitment, promotion or task allocation is **high-risk under the EU AI Act**. The prototype is designed for that:
- protected attributes are removed before matching, and a test proves they can't change a score,
- every score is broken down into skills held, transferable and missing; there's no hidden model,
- the tool recommends and a person decides; every recommendation is audit-logged.

## 3. Recruiting Workflow

**Problem.** Hiring is slow and inconsistent: adverts vary in quality, interviews are unstructured, and decisions are hard to explain afterwards.

```
vacancy ─► 1. Advert ─────► 2. Internal ─────► 3. Interview ─► 4. Scorecards ──► 5. Decision
           AI drafts it;    candidates first:  kit: questions   weighted score;   a person decides,
           inclusive-       anonymised         + 1-5 rubric     flags missing     with a written
           language check;  matches; manager   per required     ratings and       reason; logged
           manager approves chooses who        skill            interviewer
                            to interview                        disagreement
```

| What is automated | What stays with a person |
|---|---|
| Drafting the advert from the role's skills | Approving the advert (blocked until the language check is clean) |
| Inclusive-language check: gender-coded, age-related, national-origin wording, too many essentials | Choosing who to interview |
| Internal shortlist, anonymised | Scoring answers in interview |
| Structured interview kit for every required skill | Discussing disagreements before deciding |
| Weighted scorecard with calibration flags | The hiring decision and its reason |
| Audit log of every approval and decision | |

## 4. Fairness Audit

Diversity data (gender, age band, ethnicity; synthetic, voluntarily disclosed) is held in a separate file that only the audit reads; a test enforces this. The audit compares each group's shortlist rate using the **adverse impact ratio** (the "four-fifths rule"): below 0.80 is a warning sign to investigate, not proof of bias. Groups under 3 people are reported but not judged.

In the demo data the audit flags three groups for review **even though protected attributes never reach the matching**: the skills a role asks for can still produce unequal outcomes. This is why matching needs an outcome audit, not just anonymisation.

Languages are treated as job-relevant skills (e.g. Spanish for a Madrid role), never as a count, which could act as a proxy for national origin.

## 5. Communications Studio

**Problem.** Communications and Marketing teams write the same kinds of text repeatedly (announcements, press releases, client posts), and every external text needs a compliance review that is slow when drafts arrive with avoidable problems.

```
brief ─► Draft ─────────► Brand, tone and ─► Approval gate ─────────► Audit log
         template, or     compliance check    internal: Communications   hash of the approved text,
         LLM if a key     blocks or warns     external: Communications   approvers, whether a person
         is set                               + Compliance (2 people)    edited the AI draft
```

| What is automated | What stays with a person |
|---|---|
| First draft from the facts in the brief, in English or Spanish | Supplying the facts and the spokesperson's quote (the tool never invents a quote; a missing one leaves a placeholder that blocks approval) |
| Required disclaimer and forward-looking caveat for external text | Approving: one approver for internal text, two different people (Communications and Compliance) for external text |
| Blocks unapproved claims ("guaranteed", "risk-free"), unsubstantiated superlatives, confidential-information wording, personal data, unfilled placeholders | Deciding whether warnings matter (tone, jargon, length, inclusive language, brand-name spelling) |
| Audit entry for every draft and approval | Publishing; the tool never posts anything |

The brand and compliance rules live in `data/comms_brand.json`, so the Communications and Compliance teams can own and version them without touching code.

## 6. AI Portfolio

**Problem.** AI ideas arrive from every team. Without a common way to compare them, effort goes to whoever asks loudest, and risky ideas slip through.

```
use-case register ─► Score ───────────► Governance gate ─────► Business case ─► Monitor
 14 fictional ideas   impact, feasibility, Stop / Hold /          hours saved ×      adoption, hours saved,
 across T&C,          scalability, risk    Proceed with controls  cost vs build+run  satisfaction, incidents
 Marketing, Comms     (formula shown)      (EU AI Act, DPIA)
```

- **Transparent score:** `0.40 impact + 0.30 feasibility + 0.30 scalability` (scaled to 100) minus 5 points per risk point above 1. The weights are in `data/use_cases.json`.
- **Governance is separate from the score.** A high-risk use case needs a completed DPIA and a person reviewing every outcome. In the demo, "automatic CV screening and rejection" is stopped, and "employee survey comment analysis" is on hold until its DPIA is done.
- **Business case:** hours saved at full rollout × assumed hourly cost, against build and run cost, with payback in months.
- **Scale view:** live or pilot tools with high scalability and regions still to roll out to.
- **Adoption and impact dashboard:** active users against eligible users, realised against planned hours, satisfaction and incidents per tool, with plain-language flags for the monthly review. The adoption figures are synthetic; in production they come from usage logs, surveys and the incident register.
- **Score a new idea** in the app with the same formula and gates.

## Spanish support

The policy assistant detects the language of the question (a transparent function-word count) and searches the matching policy set: `policies/` for English and `policies/es/` for Spanish. Spanish has its own stop words, accent folding, light stemming and synonyms, and the same guardrails: Spanish personal data (DNI/NIE, +34 phone numbers) is masked, sensitive topics (`acoso`, `despido`, `denuncia`…) are escalated, and unknown topics get a Spanish "not found" reply. The Communications Studio drafts and checks in Spanish too, with Spanish claim and confidentiality rules and a Spanish disclaimer. The Spanish policy texts are demonstration translations; an evaluation checks that every figure matches the English original.

`python demo.py` shows the same questions in both languages, offline.

---

## Results

```
python eval/run_eval.py              # policy assistant (English)
  Retrieval hit rate (top 3): 30/30
  Correct routing:            39/39  (answer / not found / escalate / help)
  PII redaction test:         pass

python eval/run_mobility_eval.py     # internal mobility
  Skills extraction:          precision 100%, recall 96% (offline keyword mode)
  Fairness:                   0 of 90 scores change when name, age or gender change
  Best candidate per role:    6/6 match the expected internal candidate

python eval/run_recruiting_eval.py   # recruiting and fairness
  Inclusive-language check:   9/9 seeded issues caught; 0 of 6 generated adverts flagged
  Interview kits:             every required skill covered for every role
  Scorecards:                 disagreement and missing-rating flags work
  Decision gate:              refuses decisions with no reason or no named decision-maker
  Diversity data:             read only by the audit module

python eval/run_comms_eval.py        # communications studio
  Seeded problems caught:     9/9 English, 4/4 Spanish; tone and brand warnings raised
  Generated drafts:           5/5 demo drafts (EN and ES) have no findings
  Quotes:                     a missing quote blocks approval; the tool never invents one
  Approval gate:              refuses blocking text, a missing Compliance approver, the same person
                              twice, a blank name and unacknowledged warnings
  Audit log:                  approvers, text fingerprint and human-edit flag recorded

python eval/run_portfolio_eval.py    # AI portfolio
  Register:                   14 use cases, scores 1-5, all three functions, local and global scope
  Scoring:                    UC01 priority 81.0 matches the hand calculation; ranking is ordered
  Governance gates:           Stop / Hold / Proceed with controls / Proceed all behave as specified
  Business case:              arithmetic matches (UC05 benefit £105,600)
  Monitoring:                 adoption within 0-100%, 2 flags raised for the review

python eval/run_spanish_eval.py      # Spanish policy path
  Routing:                    29/29 (answer / not found / escalate / help)
  Retrieval:                  21/21 in the top 3; correct section ranked first 21/21
  Language detection:         39/39 English and 29/29 Spanish questions
  PII (DNI, NIE, +34 phone):  masked
  Policy parity:              42 sections in 9 documents; 0 sections whose figures differ from English

python eval/run_all.py               # all seven, one PASS/FAIL line each
```

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py                    # runs offline: no model or key needed
python demo.py                          # bilingual walkthrough in the terminal
python eval/run_all.py                  # run every evaluation
```

The app needs no secrets and makes no network calls unless a model is configured, so it runs as-is on Streamlit Community Cloud (main file `app.py`). Audit and usage logs are written to `logs/` (git-ignored) when the app is used.

## Choosing a model

The project is **model-agnostic**. Every module calls one function, `llm.complete()` in `assistant/llm.py`, and the provider is chosen with settings, not code changes:

| `LLM_PROVIDER` | Use it for |
|---|---|
| `offline` (default) | No model: templates and keyword methods. The live demo runs this way. |
| `gateway` | The bank's approved internal LLM endpoint (OpenAI-compatible), with its logging, filtering and data-residency controls. **The right choice in production.** |
| `azure_openai` | An Azure OpenAI deployment |
| `openai` | OpenAI (e.g. an enterprise licence) |
| `gemini` | Google Gemini |
| `anthropic` | Anthropic |

```bash
pip install openai            # or: pip install anthropic
export LLM_PROVIDER=gateway
export LLM_MODEL=<model or deployment name>
export LLM_API_KEY=<key>
export LLM_BASE_URL=https://<internal-llm-gateway>/v1
streamlit run app.py
```

See `.env.example` for every setting. `eval/run_llm_eval.py` checks that each provider is called the same way and that no other module talks to a provider directly.

## Project structure

```
assistant/
  guardrails.py   PII redaction and escalation rules
  retriever.py    policy loading, BM25 ranking, coverage check
  llm.py          the single model call for every module (any provider), offline fallback
  agent.py        policy assistant orchestration and usage log
  mobility.py     skills extraction, anonymisation, matching, learning plans, audit log
  recruiting.py   advert drafting, inclusive-language check, interview kit, scorecards, decision gate
  fairness.py     adverse impact audit on separately held diversity data
  comms.py        brief to draft, brand/tone/compliance check, approval gate, audit log
  portfolio.py    use-case scoring, governance gates, business case, adoption monitoring
data/             fictional employees, roles, courses, interview questions, skills taxonomy,
                  diversity data (synthetic, audit only), brand and compliance rules,
                  AI use-case register, synthetic adoption data
policies/         fictional HR policies (English); policies/es/ holds the Spanish versions
eval/             test sets and seven evaluation scripts (run_all.py runs them together)
app.py            Streamlit app with all six modules
demo.py           bilingual, offline walkthrough
```

## Role fit: AI transformation in Talent & Culture, Marketing & Communications

How the prototype lines up with the work of an AI transformation lead for these functions, locally and globally:

| Area of the work | What the prototype shows |
|---|---|
| Identify and prioritise AI use cases | AI Portfolio: 14 use cases across Talent & Culture, Marketing and Communications, scored on impact, feasibility, scalability and risk with a visible formula, local and global scope, and a "score a new idea" form |
| Assess feasibility and business case | Feasibility and scalability scores; hours saved against build and run cost, with payback; governance gates that can stop or hold an idea regardless of score |
| Build GenAI apps, automations and self-service agents | Six working modules in Python: retrieval-grounded policy agent, skills-matching copilot, drafting workflows, a comms drafting assistant; LLM calls through an API with an offline fallback |
| Use LLMs, APIs and prompt engineering | Model-agnostic: one call point that works with OpenAI, Azure OpenAI, Gemini, Anthropic or an internal gateway. Constrained prompts (answer only from excerpts, cite each statement, fixed refusal text, bilingual), taxonomy-constrained skills extraction, brand-rule-constrained drafting |
| Workflow automation and low-code thinking | Multi-step workflows with human approval gates; the portfolio includes a low-code automation use case; rules (brand, disclaimers, scoring weights) are in JSON that business teams can own |
| Drive adoption and scale across geographies | Usage and adoption dashboards, monthly monitoring flags, and a view of which live tools are ready to roll out to new regions |
| Governance, privacy and responsible AI | PII masking (UK and Spanish identifiers), escalation of sensitive topics, protected attributes removed before matching, fairness audit, audit logs with human sign-off, EU AI Act and DPIA gates in the portfolio |
| Marketing and external communications | Communications Studio: on-brand drafting, claims and confidentiality checks, mandatory disclaimers, two-person approval for external text |
| English and Spanish | Spanish policy assistant, Spanish comms drafting and checks, a bilingual demo, and a test that translated policies keep the same figures |
| Measurable outcomes | Seven evaluation scripts with explicit pass criteria, run before any policy, taxonomy, rule or prompt change |

What it deliberately does not claim: the data is fictional and small, the adoption figures are synthetic, and it has not been through a real security, legal or model-risk review.

## Fitting it into a bank's existing stack
Most large banks already own an HR suite, a skills platform and a communications and approvals process. The value of a tool like this is the **layer on top**: using the bank's approved LLM platform to make existing skills data, policies and brand rules useful in daily work. In production:
- **Model access:** set `LLM_PROVIDER=gateway` so every call goes through the bank's approved LLM gateway (logging, content filtering, data-residency and cost controls). All modules share the single call point in `assistant/llm.py`, so nothing else changes.
- **HR suite (for example Workday):** read employees, roles, skills and open vacancies from the HR system and skills platform instead of JSON files; write approved adverts and decisions to the ATS; keep diversity data in a separate, access-controlled store.
- **Teams and intranet:** surface the policy assistant and the comms drafting in Teams or the intranet, with single sign-on, and open an HR ticket on escalation. Publishing stays with the channel owners.
- **EU AI Act:** recruitment, promotion and task allocation are high-risk uses. That means a risk-management process, documented data governance, logging, human oversight, accuracy and robustness testing, and transparency to the people affected, and the portfolio's gates are the place to enforce it. Check requirements for each country the tool operates in.
- **GDPR and UK GDPR:** a DPIA before any use on employee data, data minimisation (PII masked before the model, anonymised matching), a lawful basis and retention limits for the logs, no solely automated decisions about people, and a route for subject-access and objection requests.
- **Approvals and records:** replace the file-based audit log with the bank's records system; keep the two-person approval for external communications in the existing compliance workflow.
- **Operations:** run the evaluation sets as regression tests before every policy, taxonomy, brand-rule or prompt change, and feed real usage and incident data into the portfolio dashboard.
