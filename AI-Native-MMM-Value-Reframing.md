# Reframing the Value of AI-Native Products in Deterministic, High-Frequency Workflows

### A case study on Agentic MMM (Marketing Mix Modeling)

> Management briefing · Internal discussion draft
> **This edition is enhanced in place**: each conceptual claim now carries a `▶ In the product` note mapping it to the current Agentic MMM build (front-end prototype + v2 architecture, 2026-06-13). Notes are grounded in the actual code and design docs; where the product does *not* yet meet the concept, it is flagged honestly rather than papered over.

---

## Verdict up front: does the product embody this thesis?

**Yes — to an unusually high degree.** The product was designed against a six-point philosophy (`08-product-architecture-v2.md`) that is essentially an independent re-derivation of this briefing. The two documents agree on the core moves without sharing a source, which is the strongest possible evidence that the thesis is the right frame.

Concretely, the central ideas of this briefing are already load-bearing in the build:

- **"Agentic is a local property, not a global one"** → the product locks a fixed 6-stage / 33-node workflow but tags *every node* with an autonomy class (`AutomationClass = M | A | C | H`), so autonomy is decided per node, exactly as argued.
- **"AI submits a PR, the human reviews"** → implemented as the **Proposal→Apply** protocol: AI never writes state directly; every change is a structured `diff` + rationale + evidence that passes three gates before applying.
- **"The atomic unit is a review card"** → implemented as `DecisionCard.tsx`: conclusion-first question, "Look at" evidence chips, an explicit AI recommendation, options that each spell out their consequence ("Then: …"), and decision-semantic confirm.
- **"Proactive anomaly routing"** → implemented as the **Insight Engine** (`connection / gap / conflict / reference` findings that must carry a suggested action that lands back in the workflow).
- **"Lower the threshold by exactly one tier, never to novices"** → reflected in a terminology-isolation discipline and a decision UX that presumes a qualified reviewer (the card shows a prior deviation but assumes you know what the prior *should* be).

The gaps that remain are concentrated in three places — quantified uncertainty, the time-per-review north-star metric, and an adjustable autonomy knob — and are detailed in the new "Alignment scorecard and gaps" section near the end. None of them contradict the thesis; they are the next increment of it.

---

## Executive Summary

The thesis in one line: **In workflows that are fixed in sequence and require frequent human review, AI's value does not come from "free planning" — it comes from continuously moving the human's cognitive load upward at each judgment node.**

- **Stop fixating on architecture labels.** "We can't make it AI-Native, only AI-Embedded" is a false anxiety. For something like MMM — which drives tens of millions in budget allocation and demands explainability — human-in-the-loop is not a defect; it is a prerequisite for compliance and trust.
- **The axis of opposition is wrong.** The real axis is not "fixed vs. free workflow" but "judgment density at each node." The sequence is fixed, but the autonomy level inside each node can be designed independently — Agentic behavior is a local property, not a global one.
- **The method lands as a node-level four-quadrant framework.** Classify each node by "needs judgment × information sufficiency / risk level," and progressively lift the human from "operator" to "exception-only reviewer."
- **The product form is a review workstation, not a chat box.** The best metaphor is "AI submits a PR, the human reviews it." The single north-star metric: whether time-per-review keeps falling.
- **The positioning is "lower the required capability threshold by exactly one tier."** Neither replacing experts nor making it usable by anyone: multiply Senior throughput, let mid-level talent reach work that previously required a Senior — while judgment responsibility always stays with a qualified person.

> ▶ **In the product.** All five summary points have a concrete home: point 1 → human touchpoints are modeled as first-class objects (11 of them: decisions + inputs), not bolted on; point 2 → the `M/A/C/H` task taxonomy; point 3 → the four-class taxonomy with a published mix of ≈45% M / 20% A / 22% C / 13% H; point 4 → the Proposal→Apply "PR" channel and the `DecisionCard`; point 5 → the "built for a qualified reviewer, not a novice" stance baked into the decision UX. Point 4's north-star metric (time-per-review) is the one summary item **not yet instrumented** — see gaps.

---

## Part 1 · Reframing the Problem

---

## A Fixed Workflow ≠ Agentic Failure

The common misjudgment: fixed workflow → no room for free planning → Agentic capability can't be expressed → it can only be Embedded.

The flaw in this chain is **treating "free planning" as the essence of Agentic behavior.**

- Free planning is just one expression of Agentic behavior, not its core.
- The core is "deciding what to do next dynamically, based on the current state" — which holds perfectly well inside a fixed workflow.
- Its room to operate simply shifts from the "orchestration layer" down into the "individual node."

**Conclusion: A fixed workflow is not a no-go zone for Agentic behavior — it demotes Agentic from a global property to a local one.**

> ▶ **In the product.** This is the architecture's founding decision. The workflow is a fixed DAG (6 stages, ~33 nodes, lane = agent × column = stage, rendered in `WorkflowCanvas.tsx`), but **autonomy lives inside the node**: each `TaskBlueprint` carries a `class: AutomationClass`. The orchestration layer is deliberately deterministic ("确定性骨架，概率填肉" — deterministic skeleton, probabilistic flesh); the agentic behavior is expressed node-by-node. This is precisely "demote Agentic from a global property to a local one," implemented.

---

## MMM Confirms It: Fixed Sequence, but Each Node Is an Ocean of Judgment

The MMM sequence is highly fixed:

> Data alignment → cleaning → adstock / saturation transforms → model specification → fit diagnostics → business-sanity check → calibration → budget optimization → output

Yet every node is full of judgment calls:

- Keep this outlier or drop it?
- Is the inflection point of this saturation curve reasonable?
- This channel's ROI conflicts with business intuition — is the model wrong, or is the intuition wrong?

**These are exactly the parts Agentic behavior should take on.**

> ▶ **In the product.** These exact judgment calls are enumerated as `C`/`H` sub-steps in the v2 task-tagging table. Examples already in the scenario: `2.11/2.12` data scoring with a "0.5-point disposition" (keep / down-weight / re-collect) routed to a human; `2.34` OLS pre-validation "range read" tagged `C`; `3.4` business check ending in a human "final model selection" (`H`) that **never auto-selects** — the Gate presents Pareto candidates for a person to choose.

---

## Drop "Native vs. Embedded," Use "Value Density" Instead

That binary derails the discussion. A more useful axis: **whether the human's cognitive load can be continuously moved upward.**

The same fixed workflow:

| Poor implementation | Good implementation |
|---|---|
| Makes the human an **operator** | Makes the human a **chief reviewer** |
| Manual step-by-step operation | Step-by-step decisions |
| Step-by-step decisions | Step-by-step approvals |
| Step-by-step approvals | **Exceptions only** |

"Amplifying AI's value" has nothing to do with the architecture label — it is about how far along this upward path you get.

> ▶ **In the product.** The "upward path" is visible in the behavior badges (`CLASS_LABEL` in `ui-language.ts`): *Runs automatically* (M) · *AI draft* (A) · *AI analysis* (C) · *Your decision* (H). The `HumanWorkbench` / `TaskWorkbench` deliberately surface **one waiting item at a time** ("What needs you", with "N more waiting"), and show a **calm state** ("AI is working on X") when nothing needs a person — i.e., the human is steered toward "chief reviewer / exceptions only," not "operator." How far up the path the product actually gets is bounded by the missing autonomy knob (gaps §).

---

## Part 2 · Methodology

---

## Core Method: Node-Level Autonomy in Four Quadrants

The "fixed" in a fixed workflow only locks the **node sequence** — it does not lock **each node's autonomy level.** Ask two things of every node — does it need judgment, and is information sufficient / risk high — and sort into four classes:

| Node type | How to handle | Human's role |
|---|---|---|
| **Deterministically computable** (field alignment, unit conversion, format checks) | Pure Automation (scripts/rules), **AI should not touch it** | No involvement |
| **Needs judgment + full info** (standard convergence diagnostics, sign-of-coefficient checks against priors) | AI executes autonomously + fully auditable trail | Spot-check after the fact |
| **Needs judgment + incomplete info / high risk** (ROI-conflict trade-offs, whether to introduce a new prior) | **AI proposes + human decides (highest-value zone)** | Decide |
| **Essentially human** (external messaging, budget politics, org dynamics) | Human leads, AI only supplies ammunition | Lead |

> Anti-pattern note: having an LLM do the deterministic computation of the first class is both expensive and unreliable.
> The entire design freedom of the product lives in the boundary between classes two and three.

> ▶ **In the product.** This is a near-exact match to the **`M / A / C / H` Automation Class taxonomy** (`08 §2`):
> - **M (Mechanical)** = your class one — "rules can fully execute, zero AI"; the doc even repeats your anti-pattern verbatim ("having an LLM do deterministic computation is expensive and unreliable").
> - **A (AI-Automatable)** = your class two — AI generates, machine-checkable schema, human spot-checks.
> - **C (Cognitive)** = your class three — "needs to think but doesn't bear responsibility," rendered as **suggestion + evidence + candidates**, awaiting a person.
> - **H (Human-only)** = your class four — responsibility cannot be delegated.
>
> The published mix is ≈**45% M / 20% A / 22% C / 13% H**, with the explicit claim that automation savings come from M+A (~⅔ of effort) while differentiated value lives in C quality and H decision experience — i.e., the product has already located "the design freedom at the class two/three boundary" and is concentrating effort there.

---

## A Cognitive Flip: Turn "Frequent Review" from a Constraint into a Target

Don't write "humans must review frequently" into the **constraints** column — write it into the **KPI** column.

Why do humans review so often? Because AI output isn't trustworthy enough, or because review is too costly. So Agentic behavior should **aim straight at "the marginal cost of each review":**

- Goal: from "spend 5 minutes checking line by line" → "spend 5 seconds glancing at the 3 anomalies AI flagged."
- Metrics: time-per-review, number of models one person can manage, the rejection-rate-over-time curve trending down.

Once this flip is established, the leverage points for Agentic behavior become obvious: proactively surface anomalies, make uncertainty explicit, and carry memory across nodes.

> ▶ **In the product.** The *leverage points* are built; the *measurement* is not. Built: proactive anomaly surfacing (Insight Engine), uncertainty made qualitative (`confidenceWording`), and cross-node memory (Knowledge change ledger + Solution library). **Missing: the KPI itself.** There is no instrumented "time-per-review," "models-per-person," or "rejection-rate-over-time" telemetry — the app tracks Day/progress, not review economics. Adopting these three as real, displayed metrics is the highest-leverage gap to close, because this briefing names them as the single north star.

---

## Four Value-Amplifying Moves for MMM (None Require a Freer Workflow)

1. **Role reversal** — the modeler shifts from "running the model once" to "reviewing an already-run draft that comes with full reasoning."
2. **Make uncertainty explicit** — key outputs (ROI, saturation inflection points) carry confidence intervals and sensitivity, not lone point estimates. This is the crux of MMM's trust problem.
3. **Proactive anomaly routing** — AI judges, against business priors, "these 3 spots need a human," directing attention precisely to the third-class nodes.
4. **Consistency through memory** — distill the modeler's implicit preferences into long-term memory, reused across refresh cycles. Memory is valuable *because* the workflow repeats — a dividend unique to high-frequency, fixed workflows.

> ▶ **In the product — move by move.**
> 1. **Role reversal — done.** Proposal→Apply means AI produces a draft `diff` + `rationale` + `evidence`; the human reviews rather than operates.
> 2. **Uncertainty explicit — partial.** `confidence` exists on every Proposal/Insight and surfaces as *words* ("High confidence" / "Fairly confident" / "Uncertain — please double-check"), with low-confidence proposals downgraded from one-click-apply to must-edit. **But** outputs are not yet shown as numeric intervals (`ROI 3.8 [2.9–4.7]`) with sensitivity — and this briefing calls that "the crux of MMM's trust problem." Real gap.
> 3. **Proactive anomaly routing — done.** The Insight Engine emits `connection / gap / conflict / reference` findings, each required to carry a `suggestedAction` that lands back in the workflow ("insight without an action is noise").
> 4. **Memory — partial.** The Knowledge module captures accepted changes in a *change ledger* and promotes project learnings to a *Solution library* across projects. What is **not** yet closed: decision-level preference learning (a person's `note`/choice steering the *next* similar proposal). The hook (`note` on every decision) exists; the learning loop does not.

---

## Part 3 · Product Form and Human–Computer Interaction

---

## Core Metaphor: Not a Chat Box — a Workstation Where "AI Submits a PR, the Human Reviews"

The two most common traps:

- **Forcing a chat box** → compresses a spatially-structured workflow into a linear dialogue; the human has to scroll to know "which step am I on."
- **A black-box dashboard** → shows results without reasoning; the human can only click "approve" on instinct, making review meaningless.

The best metaphor = **code review (GitHub PR) + an engineer's workbench**, mapping item by item:

| Agentic product | PR review |
|---|---|
| Fixed workflow | Fixed pipeline stages |
| AI runs through once | AI submits a PR |
| Human reviews | Code review |
| AI provides rationale | PR description + inline comments |
| Human rejects | Request changes |
| Proactive anomaly routing | CI auto-flagged failing checks |
| Preferences captured | AI learns the reviewer's taste |

**The whole front end = a workstation for efficiently reviewing AI's work.**

> ▶ **In the product.** The build is explicitly a workstation, not a chat box: navigation is **Project (three-column workbench) / Workflow Canvas / Decisions / Assets / Knowledge**, with chat demoted to a floating Assistant dock — the spatial structure is preserved, you always see "which step am I on." The PR mapping is almost literal:
>
> | This briefing | The product |
> |---|---|
> | AI submits a PR | a `Proposal` (structured `diff`, never free text) |
> | PR description + inline comments | `rationale` + `evidence` (EvidenceAnchor → exact artifact location) |
> | Code review | the `DecisionCard` / Gate review |
> | Request changes | reject → "回炉" task, rejection reason re-injected into AI context |
> | CI auto-flagged checks | the three gates (schema → rule → human) + Insight Engine |
> | AI learns the reviewer's taste | *aspirational* — see "memory" gap above |
>
> The one row not yet real is the last — "learns the reviewer's taste."

---

## The Atomic Unit: Design Principles for a "Review Card"

The review card is the product's atomic unit; its quality directly determines the core KPI of time-per-review.

- **Conclusion first, process after** — the top line is AI's conclusion and the point you must judge; numbers, rationale, and counterfactuals are visually de-emphasized below. This embodies cognitive-load lifting.
- **Uncertainty is a first-class citizen, with semantics** — write `ROI 3.8 (interval 2.9–4.7)`, `Confidence: medium · sparse data`, not a bare point estimate `3.8`. Bare numbers create false precision — the very crux of MMM's trust crisis.
- **The counterfactual must be present** — precompute "what happens if you don't do this (e.g., refit under the prior → R² drops to 0.82)." What the human most wants to know is not "AI picked A" but "what if we don't pick A."
- **Action equals decision, and writes back to memory** — buttons carry decision semantics like "Accept / Refit under prior / Ask a question," not "OK/Cancel"; the choice and its reason are remembered, so next time a similar conflict arises AI proposes along your preference first.

> ▶ **In the product — `DecisionCard.tsx`, principle by principle.**
> - **Conclusion first — done.** Card header = `Step id · agent`, then the `question` (the point to judge) up top; evidence and options sit below.
> - **Uncertainty first-class — partial.** Confidence is present but **qualitative**, not the `ROI 3.8 (2.9–4.7)` form this principle specifically prescribes. This is the single clearest divergence from the briefing's review-card spec.
> - **Counterfactual present — done.** Every option renders a `consequence` line ("Then: …"), e.g. an option's downstream effect — exactly "what if we don't pick A," precomputed per option.
> - **Action = decision, write-back — partial.** Buttons carry decision semantics (options + "Confirm choice", an AI-`recommended` option pre-selected) and a free-text `note` "for the record." The choice is recorded and resolved; what is **not** yet wired is feeding that choice/`note` back so AI "proposes along your preference next time."
>
> Implementation note worth preserving: the card holds local state, so the workbench mounts it with `key={focus.id}` to avoid state bleeding across tasks — a real bug was fixed here (attachment count stuck at 7/4).

---

## Four Principles That Run Through the Whole Front End

- **Interaction rhythm is set by autonomy tiers, not one-size-fits-all.** Run class-one and class-two nodes through in one pass, batched for after-the-fact review; only class three actually blocks and waits for a human nod. Never pop up at every step — that turns the human into a human bottleneck.
- **Autonomy needs a visible, adjustable knob.** As trust builds, downgrade a class of nodes from "must review" to "spot-check." The downgrade decision should be backed by evidence (e.g., "you accepted 28 of the last 30 such proposals").
- **Rejection must be structured, not a free-text box.** Guide the human to specify "prior wrong / model wrong / data wrong" — each feeds the memory system entirely different downstream behavior.
- **Global traceability.** One click produces an audit trail of "what AI decided, what was changed, and why." It serves compliance and also lets the human dare to let go.

> ▶ **In the product — scored.**
> - **Rhythm by tier — done.** M/A run through and batch for spot-check; only C/H block. The workbench's "one item at a time + N more waiting + calm state" is exactly "never pop up at every step."
> - **Adjustable autonomy knob — missing.** Classes are **static** per task blueprint. There is no UI to downgrade "must review → spot-check," and no "you accepted 28 of the last 30" evidence to justify it. This is a named gap.
> - **Structured rejection — partial.** Decision *options* are structured (radio choices with consequences), but the rejection rationale is a **free-text `note`**, not the guided "prior wrong / model wrong / data wrong" taxonomy that routes different downstream behavior. Half-built.
> - **Global traceability — done (strong).** Lineage triples on every artifact, an `ArtifactState` lifecycle (`draft → proposed → confirmed → frozen`), a Knowledge change ledger (add/delete/merge × reason × source × who-confirmed, auto-appended on acceptance), and evidence anchors. This is arguably the product's most complete pillar.

---

## Anti-Patterns to Avoid

- **A chat box dressed up as a fixed workflow** — loses the spatial structure of the process.
- **A black-box dashboard** — results without reasoning; review becomes theater.
- **Confirmation pop-ups at every step** — the interruption cost exceeds the errors they prevent.
- **Flat information with no attention routing** — hands the highest-value action, "filtering on the human's behalf," right back to the human.

> ▶ **In the product.** The build actively avoids all four: chat is a side dock not the spine (anti-pattern 1); every result carries rationale + evidence + the option to "challenge" in the Asset workspace (anti-pattern 2); only C/H block while M/A batch (anti-pattern 3); the Insight Engine does the "filtering on the human's behalf" (anti-pattern 4). There is also a fifth discipline the product adds that this briefing does not name: **internal-vs-UI language isolation** — a `BANNED_UI_TERMS` list (proposal, gate, copilot, automation class, …) enforced by `copy-check.mjs`, so the UI only speaks the user's business language. Worth folding back into the briefing as a principle.

> One-line principle: **The front end isn't displaying AI's results — it's running a workstation for efficient human review of AI's work. The only measure of how good it is: whether time-per-review keeps falling.**

---

## Part 4 · Value Positioning

---

## The Value Is Neither "Replacing Experts" nor "Anyone Can Do It"

The real positioning = **lower the "capability threshold required to deliver a trustworthy MMM" by exactly one tier.**

Capability is a continuum, not an expert/novice binary:

- **Senior** → throughput multiplied; one person does the work of a former team, cycle time from weeks to days. Value that is certain to capture, and safe.
- **Mid-level** (knows marketing, has statistical fundamentals, not an MMM expert) → with AI assistance, delivers what previously only a Senior could. **This is where TAM genuinely — and safely — expands.**
- **Junior / true novice** → still can't reach it. What they lack isn't operational skill, it's judgment — and judgment is exactly what AI should least, and most dangerously, attempt to replace right now.

**"Down one tier" is value; "all the way down" is risk.**

> ▶ **In the product.** The UX encodes "for a qualified reviewer, not a novice": the `DecisionCard` shows "this elasticity deviates from the prior" but assumes the reviewer *knows what the prior should be* — useless to a novice, exactly as the briefing warns. H-class steps are framed as multiple-choice (candidates + AI recommendation + consequences), which multiplies a competent person's throughput without handing judgment to AI. The terminology-isolation rule (hide mechanism names, show business language) also serves "down one tier": mid-level users get expert-grade behavior without needing the expert's vocabulary.

---

## Why MMM Should Not Be Built for Novices

- **Errors are invisible.** An MMM model can converge perfectly, show high R² and beautiful charts, yet — due to collinearity, misattribution, or a mis-set prior — produce a completely misleading ROI. Recognizing "looks right, is actually wrong" is the expert's core capability, the hardest thing to replace with an interface.
- **The review workstation presumes a qualified reviewer.** Hand a novice a card saying "OOH ROI deviates from prior" and they won't know what the prior should be, what the deviation means, or whether to accept or refit. The workstation is useless to them.
- **The responsibility chain breaks.** Expert tool: AI proposes, expert reviews, expert is responsible — a clean chain. Novice tool: a misattribution sends tens of millions in budget the wrong way — pin it on the vendor (unaffordable) or the user (unfair) — unsustainable either way.
- **The UI is mutually exclusive.** Building for novices means hiding complexity and offering one-click generation; building for experts means exposing parameters and uncertainty and leaving hooks for intervention. You cannot optimize both ends at once.

> ▶ **In the product.** The responsibility chain is enforced structurally: **AI never writes state** (Proposal→Apply), `H`-class decisions are never auto-settled, and the "challenge" verb in the Asset workspace lets a competent reviewer interrogate any number ("why is this elasticity so high?" → AI assembles evidence: prior range, collinearity VIF, cross-project recall). This is the "AI proposes, expert reviews, expert is responsible" chain made literal. The product has chosen the expert end of the mutually-exclusive UI — parameters, uncertainty, and intervention hooks are exposed, not hidden behind one-click generation.

---

## A Transferable Positioning Framework (Three Questions)

"Amplify the expert" is not a universal conclusion — it's forced by MMM's domain characteristics. To decide which direction any workflow should go, ask three things:

| Dimension | MMM's answer | Implication |
|---|---|---|
| Are errors **invisible**? | Yes (looks right, is wrong) | More invisible → more expert needed |
| Are consequences **high-risk**? | Yes (moves tens of millions in budget) | Higher risk → more expert needed |
| Is feedback **fast and cheap**? | No (campaign results take months) | Slower & costlier → more expert needed |

MMM hits the worst case on all three → decisively lean toward "amplify the expert."
Counter-example: marketing-copy generation (errors visible at a glance, near-zero cost to redo, low risk) → "novice-usable" works perfectly.

**Different product lines within the same company can have opposite positioning, depending on the answers to these three questions.**

> ▶ **In the product.** This three-question framework is not yet an explicit artifact in the codebase, but the product's every default is consistent with MMM scoring "worst case on all three": invisible errors → the Insight Engine's `conflict`/`gap` detectors hunt for "looks right, is wrong"; high risk → no auto-apply, no auto-model-selection; slow feedback → heavy up-front gating rather than fast trial-and-error. If the company extends to other product lines, this framework is the reusable decision rule for whether to clone the "expert workstation" form or build a novice one-click tool instead.

---

## Alignment scorecard and gaps (new)

A blunt, per-claim scorecard of this briefing against the 2026-06-13 build. "Done" = implemented and load-bearing; "Partial" = hook exists, loop not closed; "Missing" = not present.

| Briefing claim | Status | Where it lives / what's missing |
|---|---|---|
| Agentic = local property (autonomy per node) | **Done** | `AutomationClass` on every `TaskBlueprint`; fixed DAG |
| Node four-quadrant method | **Done** | `M/A/C/H` taxonomy, full task-tagging table, ≈45/20/22/13 mix |
| AI never writes state directly ("submits a PR") | **Done** | Proposal→Apply, three gates, single write channel |
| Review card: conclusion-first | **Done** | `DecisionCard` header → question → evidence → options |
| Review card: counterfactual per option | **Done** | each option's "Then: …" consequence line |
| Proactive anomaly routing | **Done** | Insight Engine (`connection/gap/conflict/reference` + required action) |
| Global traceability / audit | **Done** | lineage triples, artifact lifecycle, Knowledge change ledger |
| Rhythm set by autonomy tier (no pop-up spam) | **Done** | M/A batch, C/H block; one-item workbench + calm state |
| Built for qualified reviewer, not novice | **Done** | decision UX presumes prior knowledge; expert-end UI |
| Internal-vs-UI language isolation *(product adds this)* | **Done** | `BANNED_UI_TERMS` + `copy-check.mjs` |
| Uncertainty as numeric intervals (`ROI 3.8 [2.9–4.7]`) | **Partial** | confidence is qualitative words only; no intervals/sensitivity |
| Action writes back to preference memory | **Partial** | `note`/choice recorded; no next-proposal preference learning |
| Structured rejection taxonomy | **Partial** | options structured; rejection reason is free text |
| Cross-project memory | **Partial→Done** | Knowledge ledger + Solution library exist; decision-level learning missing |
| Time-per-review as north-star metric | **Missing** | no review-economics telemetry at all |
| Adjustable autonomy knob (downgrade w/ evidence) | **Missing** | classes static; no "28 of last 30 accepted" downgrade |

**The three gaps that matter most**, in priority order:

1. **Instrument the north-star metric.** This briefing says the *only* measure of the front end is whether time-per-review keeps falling — yet it is the one thing not measured. Add per-review timing, models-per-person, and a rejection-rate-over-time curve. Without this, every other improvement is unfalsifiable.
2. **Make uncertainty numeric on the cards.** Move from "Fairly confident" to `ROI 3.8 (2.9–4.7) · medium · sparse data`. The briefing calls this "the crux of MMM's trust crisis"; the qualitative version under-delivers on the product's own trust thesis.
3. **Ship the adjustable autonomy knob.** Static classes cap how far the human can climb the operator→exceptions-only ladder. Let trust, backed by acceptance-rate evidence, downgrade a class from "must review" to "spot-check." This is what converts the architecture from "good HITL" into "compounding leverage."

None of these is a redesign; each is the next increment along the line the product is already on.

---

## Conclusion and Recommendations

**Core thesis**

> The value of AI-Native MMM is neither "replacing experts" nor "anyone can do it" — it is "lowering, by exactly one tier, the capability threshold required to deliver a trustworthy MMM." Senior throughput multiplies, mid-level talent reaches expert-level work, and judgment responsibility always stays with a qualified person.

**Three concrete recommendations for the product**

1. **Positioning**: lead with "expert productivity + letting mid-level reach expert work"; do not make "novice-usable" the core selling point.
2. **Form**: design as a "review workstation" rather than a chat/dashboard, with "time-per-review keeps falling" as the single north-star metric.
3. **Method**: use the node four-quadrant framework for autonomy tiering; concentrate engineering effort on the boundary of classes two/three and on the review-card experience of class three.

> ▶ **In the product — status of the three recommendations.** (1) Positioning is honored in the UX (expert-end, qualified-reviewer assumptions) though not yet in any market-facing copy. (2) Form is done — it *is* a review workstation; the north-star metric is the missing half. (3) Method is done — `M/A/C/H` tiering with effort concentrated at the C boundary, exactly as recommended. **Net: the product has executed recommendations 2 and 3 structurally; the open work is the measurement layer (metric) and the trust layer (numeric uncertainty + adjustable autonomy).**

**Reusable assets**

- The node-level four-quadrant autonomy framework — *realized as the `M/A/C/H` taxonomy.*
- The review-workstation interaction paradigm (PR-review metaphor) — *realized as Proposal→Apply + `DecisionCard`.*
- The three-question positioning framework (extensible to the company's other product lines) — *not yet an explicit artifact; recommend formalizing it as a reusable decision rule for new product lines.*
- *(Added by the product)* The internal-vs-UI language isolation discipline — a transferable pattern for any expert tool that must hide its mechanism and speak the user's domain.
