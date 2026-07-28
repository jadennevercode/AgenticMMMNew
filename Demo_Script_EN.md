# AgenticMMM — Product Demo Script

> **Audience**: Prospective clients / brands · **Duration**: ~12 minutes · **Demo case**: a real MMM project, already run to completion
> **How to use**: `SAY` is the spoken narration — read it verbatim; `[ACTION]` is the synchronized on-screen action; `[PAUSE]` is a beat for emphasis or interaction.
> **Positioning**: An AI-Native Marketing Mix Modeling (MMM) platform — a complete consulting methodology (5 agents × 5 delivery stages) crystallized into a human-in-the-loop, fully transparent, manageable workflow system.

---

## Opening (~1.5 min)

`SAY`
"Good morning, everyone, and thank you for your time. Today, I'll introduce our product — AgenticMMM — and give you a live, end-to-end demonstration of how it delivers a real Marketing Mix Modeling project.

Before I begin, let me take a moment to make two things clear: what MMM is, and the problem we set out to solve.

Marketing Mix Modeling — MMM for short — is a well-established discipline in marketing science. It answers the question every marketing leader cares about most: **for every dollar I spend, how much business does it actually generate?** TV, e-commerce, offline, promotions — what is each channel's true contribution to sales? What is the return on investment? If I increase or cut a budget, how will sales respond? And how should I reallocate next quarter's budget across channels to maximize return?

So how does MMM do it? In simple terms, it splits the sales over a period into two parts: a 'base' — the sales you'd get even with no advertising — and the extra sales that each marketing and promotional activity drove on top of that. It tracks no individual consumer's data; instead, from aggregate historical sales and media data, it uses statistics to work out how much each channel contributed.

It also respects two realities of marketing: first, a carryover effect — the ad you run today keeps working for the following weeks; and second, diminishing returns — the more you pour into one channel, the less each additional dollar brings back. Because it accounts for both, MMM can explain each channel's past return and project how best to split future budget — and it sidesteps privacy concerns by design.

Its value is beyond dispute — but the way it has traditionally been delivered carries a fundamental pain point. And that is exactly what I want to talk about today."

[PAUSE]

---

## Part 1 · Product Philosophy (~2.5 min)

`SAY`
"A traditional MMM project typically takes six to twelve weeks and relies on a dedicated team of consultants, data engineers, and modeling scientists. But the core burden of this delivery model is not the time it takes — it is that **it places an extraordinary cognitive load on people.**

In a traditional, process-driven delivery, every step depends heavily on expert judgment: how to structure the factors, which data is usable, how to set the model priors, whether the results align with business logic. And on top of making these judgments, the experts must also carry out an enormous amount of mechanical, repetitive, low-value execution — cleaning data, aligning formats, tuning parameters over and over. **The high-order cognition of experts gets buried under low-order labor.**"

[PAUSE]

`SAY`
"The design philosophy of AgenticMMM is built entirely around **relieving that cognitive load.** We distill it into three principles.

**Principle one: draw a clear line between three roles — AI, Human, and Machine — and assign every piece of work to whichever is best suited to it.**

We classify every task in the project into three kinds:

- **Machine** handles deterministic computation — data extraction and transformation, regression fitting, quality scoring. This work has exactly one correct answer, so we hand it to code: fast and error-free.
- **AI** handles grounded generation — business interpretation, key business questions, decision recommendations. This work requires understanding and expression, but it must be built strictly on real data and real model results.
- **Human** handles judgment and decisions — the critical junctures that require business experience, trade-offs, and accountability.

This division of labor frees the expert entirely from mechanical labor and concentrates their cognitive resources where a human is truly needed."

[PAUSE]

`SAY`
"**Principle two: Human-in-the-Loop, or HITL — ensuring people step in only when it is necessary.**

This is critical. We do not chase full automation, nor do we exhaust people by making them confirm everything. The system places decision nodes at every critical quality gate — **the workflow deliberately blocks there and waits for human confirmation, while everywhere else, AI and Machine advance autonomously, without interruption.**

Here is an example: data validation uses a three-state score. A pass is cleared automatically; an unusable metric is discarded automatically with an alert; **and only the borderline, questionable metrics bring a person into the decision.** A person's attention is therefore directed precisely to where judgment is most needed, rather than consumed indiscriminately.

**Principle three works on two levels — Artifacts-Driven and Human-Intuitive.**

Being Artifacts-Driven means the entire workflow is organized around **concrete deliverables**, rather than an opaque, black-box process. This yields four practical benefits. First, **visible progress** — the status of every deliverable is clear at a glance. Second, **controllable quality** — every deliverable is a natural unit for human review and sign-off. Third, **full traceability** — every deliverable carries version history and lineage, so the final report can be traced all the way back to the model, data, and interviews it rests on. Fourth, **reliable propagation** — the moment a deliverable is rejected, every affected downstream output is automatically reset and rebuilt, so no inconsistency is ever left behind.

Being Human-Intuitive means **the system presents work the way a person thinks, rather than forcing the person to adapt to the machine's logic.** A project unfolds naturally along the hierarchy of Stage → Deliverable → build process; business factors are presented as an intuitive factor tree; items requiring a decision are gathered into a single, clear inbox. The user needs to learn no complex system concepts — everything is presented in the business language they already know."

---

## Part 2 · Feature Layout (~1.5 min)

`SAY`
"Built on this philosophy, the core of the product is carried by three interfaces. Let me walk through each."

[ACTION] Switch to the Workflow canvas

`SAY`
"**First, Workflow.** This is the methodology blueprint the product crystallizes, visualized as a directed acyclic graph, a DAG. The horizontal axis is the five delivery stages; the vertical swim lanes are the five agents. Every task node is labeled with its collaboration mode — whether it is executed autonomously by Machine, generated by AI, or requires human intervention. Click any node to see its inputs, outputs, dependencies, and reasoning log. This single diagram is the complete picture of how the project runs."

[ACTION] Switch to the Project workspace

`SAY`
"**Second, Project.** This is the primary workspace for execution and delivery, and the direct embodiment of the Artifacts-Driven principle. The interface is organized along the hierarchy of Stage spine → Deliverable list → build process: the stage progress sits at the top, the full set of deliverables for that stage on the left, and the main area shows exactly how each deliverable is built. The real materials a project needs are uploaded through the Project Folder; items requiring human confirmation are handled right here. All of the user's day-to-day work happens in this one interface."

[ACTION] Switch to the Knowledge base

`SAY`
"**Third, Knowledge.** This is the platform's hub for accumulation and reuse. MMM industry knowledge — factor templates, interview frameworks, validation rules — is accumulated here, organized by industry, editable, maintainable, and versioned. Every new project inherits the relevant industry's knowledge base from here; and every confirmation and correction a person makes during a project flows back and enriches this knowledge base. **The platform therefore grows smarter with every project it runs.**"

---

## Part 3 · Live Case Demonstration (~5 min)

`SAY`
"Enough talk — let the results speak for themselves. What I have open here is a project that has **already run to completion** — a real modeling dataset of some twenty thousand rows. Traditionally, this is six to twelve weeks of output from a full expert team.

Over the next few minutes, I'll walk you through its results from the top, and I'd ask you to watch just one thing: **behind these results, how did the three roles — AI, Human, and Machine — divide the work and collaborate to produce them.**"

[ACTION] Open the completed project

### Stage 1 — Business Understanding: teaching the AI your business (~70 sec)

`SAY`
"Stage one, Business Understanding. This used to be the most cognitively demanding part of the entire project — a consultant poring over the Statement of Work, industry reports, and a dozen interview transcripts, then hand-drawing a factor tree from experience.

The project scope you see here was framed automatically by the Business Agent after it read the client's SOW: product lines, channels, regions, and time granularity, all of it. And this entire factor tree was generated by it drawing on industry knowledge — from the top-level business drivers all the way down to modelable metrics, each factor matched with its indicators; the common parts recalled directly, the specific parts added by it on its own, with their sources labeled."

[ACTION] Show the project scope and factor tree

`SAY`
"And the crux is in these flagged nodes. **AI ran through the entire process, yet it never decided for anyone.** Every factor the AI added was, at the time, placed in front of a person to confirm or reject; and every one of those judgments flowed back into the knowledge base, making the platform smarter with use. **This is what AI-Native collaboration looks like: AI and Machine carry all the heavy lifting, and the human appears only where a real decision must be made.**"

[ACTION] Show a factor node's confirm / reject trail

`SAY`
"The interview step shows this even more fully. This interview outline was generated by the agent after it had first read all existing materials and drafted its own first-pass answers, leaving only the questions that truly needed validating in person; once the notes came back, it compared them automatically and highlighted, right on the factor tree, what should change and why — the person only had to confirm. Following on, this is the data-request document it generated, and the single Business Understanding summary into which it folded the scope, factor tree, and interview insights. A stage that once took weeks — its results, all here in front of you."

[ACTION] Show the interview outline, the highlighted factor-tree changes, the data-request document, and the Business Understanding summary

### Stage 2 — Data Intake & Quality: hand the grind to the Machine (~55 sec)

`SAY`
"Stage two, Data Intake & Quality. Once the data was back, this used to be a data engineer's most grueling weeks — cleaning, aligning, checking column by column. **This deterministic work, the kind with exactly one right answer, was taken over entirely by the Machine.**

Look at this data-quality scorecard: the system scores every metric across a few dimensions — consistency, accuracy, comprehensiveness, granularity. A full score is cleared automatically, a failing one is discarded with an alert — the vast majority, it handles on its own. And this flagged metric is the one that landed on the borderline and was brought specifically to a person to decide — **the human's attention landed precisely on the one place that needed judgment.**"

[ACTION] Show the data-quality scorecard (with one flagged borderline item)

`SAY`
"Once validation passes, the multi-source data is automatically cleaned, mapped, and integrated into this unified wide-table master dataset on the right, together with a data dictionary. Notice one elegant thing: **the columns of this wide table are the factor tree itself — the business structure and the data structure are one and the same.** From raw data to final dataset, every step is traceable."

[ACTION] Show the wide-table master dataset and the data dictionary

### Stage 3 — Validation & Hypotheses: business and statistics, both put to the test (~55 sec)

`SAY`
"Stage three, Validation & Hypotheses. Clean isn't enough — the data has to withstand two interrogations at once: business, and statistical.

First, business validation: the Data Agent drills down through the factor tree layer by layer, checking whether each metric makes commercial sense, then auto-generates charts and trend interpretations for the client to sign off on — **another gate guarded by a human.** Once cleared comes statistical validation: it screens each metric with coefficient of variation, correlation, and collinearity, then runs a quick regression pre-fit to produce rough contribution and ROI ranges for each factor, finally locking the model input."

[ACTION] Show the factor-tree drill-down, the chart sign-off, the statistical screening, and the model-input list

`SAY`
"And more importantly, this stage also distilled the **modeling priors** — the likely elasticity range of a given channel, that a competitor's effect should be negative, that brand search leads sales. Each of these hypotheses was confirmed by the client, becoming a constraint for the next stage's modeling. Business intuition and statistical rigor, brought together in one system."

[ACTION] Show the list of priors

### Stage 4 — Modeling: what should be computed is never invented by AI (~60 sec)

`SAY`
"Stage four, Modeling. First, model choice: when you need to iterate ROI quickly, use OLS; when you need high precision and want to feed business priors in to guide the result, use a Bayesian probabilistic model. Those business hypotheses from the last stage were translated here into mathematical constraints.

Here I'll draw a hard line: every number you see in the report — adstock, saturation curves, each channel's contribution and ROI — **comes from a real regression engine, computed one by one, not conjured up by a language model.** AI-Native never means letting AI make things up; what should be computed is left, faithfully, to computation."

[ACTION] Show the model fit results and each channel's contribution / ROI

`SAY`
"After tuning comes technical validation — and not on a single metric: goodness of fit, prediction accuracy, residuals, contribution decomposition, all cross-validated across dimensions, where any single red flag stops the model. Only when all of that passes does model selection come. These here are the Pareto-optimal candidates the system produced, laid out side by side. **The system never picks for anyone automatically** — the one finally chosen was this one, owned by a person. Because choosing a model is, at its core, a business trade-off."

[ACTION] Show the technical validation and the Pareto candidate comparison, with the final selected model

### Stage 5 — Reporting: from looking back to looking forward (~65 sec)

`SAY`
"Stage five, Reporting. The Report Agent turned cold coefficients into an entire language the business understands. Look at this report: the decomposition chart shows you how sales break down into Base plus the contribution of each channel; the Due-to chart attributes 'why did sales rise or fall this period' to each individual channel; the ROI chart sets every channel's return next to an industry benchmark line, with a reminder that upper-funnel channels have naturally lower ROI yet real value, and can't be extrapolated linearly. Every chart is a templated chart plus AI adding business-contextual narration — both standard and business-savvy. And you can question it directly, say, 'Why does this channel have the highest ROI?' — it answers, grounded in the real model results."

[ACTION] Show the decomposition chart, the Due-to chart, the ROI chart, and the interactive Q&A

`SAY`
"But here is the real highlight: **the model is not the finish line — it's the starting line.** This simulator, delivered to the client, can be re-run at any time — set the total budget and your business constraints, and it runs a marginal optimization on the real response curves, telling you directly how to split the money for the greatest return. Traditionally, a modeling team would compute this one question for days; here, it's seconds, and you can play out as many scenarios as you like.

A real MMM project, carried all the way from a single SOW to an executable budget recommendation — that is what it ultimately delivers."

[PAUSE] Show the before-and-after allocation comparison

---

## Part 4 · Closing (~1.5 min)

`SAY`
"In a little over ten minutes, we have walked through a complete, real MMM project. Let me close on three points.

**First, this is AI-Native, not AI-attached.** We did not bolt a chat box onto legacy software; we rebuilt from the skeleton of the process outward. The methodology is crystallized into a visible workflow, AI, Human, and Machine each play their proper role, and AI reaches into every step rather than floating on the surface.

**Second, it relieves the cognitive burden on people — it does not replace their judgment.** Machine takes on mechanical computation, AI takes on grounded generation, and the human — through Human-in-the-Loop — is called precisely to every juncture that genuinely requires judgment: not one interruption too many, not one checkpoint too few. Everything is artifacts-driven, visible, and traceable, presented in a way people already understand.

**Third, it delivers not just a report, but a lasting decision capability.** Once the model is complete, you can return to the simulator at any time to play out any budget scenario; and the platform keeps evolving as each project deposits knowledge into it.

For a brand, this means three things: **a faster delivery cycle, a lower project cost, and — because the entire process is visible, controllable, and traceable — results you can trust more.**

Thank you. I'd be glad to run through any specific scenario you care about, live, right now."

[PAUSE] Move to Q&A

---

## Appendix A — Pre-Demo Checklist

- [ ] Backend running (`uvicorn`, port 8000), the `danone-mizone` project `reset` to a clean state
- [ ] Frontend dev server running (port 5173)
- [ ] The case's SOW / brand materials / interview notes ready (if showing the upload step live)
- [ ] If time is tight on the day: pre-run the project to Stage 3, and focus live on the two highlights — the model-selection gate and the simulation optimizer
- [ ] Backup demo: show a "send back for rework" to reveal the automatic downstream reset and version increment (if the client is focused on quality control)

## Appendix B — Timing Cheat Sheet

| Segment | Duration | Core message |
|---|---|---|
| Opening | 1.5 min | What MMM is, how it works, and the problem it solves |
| ① Philosophy | 2.5 min | Relieving cognitive load · AI/Human/Machine split · HITL · Artifacts-Driven · Human-Intuitive |
| ② Feature layout | 1.5 min | Workflow · Project · Knowledge |
| ③ Live case | 5 min | Three roles collaborating · all five stages · from a SOW to a budget recommendation · **model selection never auto-picked** |
| ④ Closing | 1.5 min | Faster · cheaper · more trustworthy |
