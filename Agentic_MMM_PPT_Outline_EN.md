# Agentic MMM — Product Introduction Deck · Content Plan (EN)

> **Audience:** Executives / decision-makers (fluent in the business and in MMM — skip primers and pain-point setup)
> **Length:** Tight, high-density ≈ 11 slides · **Voice:** thesis-first, judgment- and value-centric, light on mechanics
> **Three-part arc:** **Philosophy (reframe) → Concept (decompose a fixed workflow into AI-Native) → Product (capabilities)**

---

## Slide 1 · Cover
- **Title:** Agentic MMM
- **Standfirst (one-line stance):** A fixed workflow is not a no-go zone for agentic AI — push autonomy *down into each node*.
- **Visual:** single core thesis + logo / date. No feature list on the cover.
- **Speaker note:** Open on the reframe, not the product. The deck earns the product by first winning the argument.

---

# Part 1 · Philosophy (Slides 2–4)
> Purpose: overturn the most common executive misjudgment about "AI-Native," then install the value framework the rest of the deck stands on.

### Slide 2 · Drop the "AI-Native vs. AI-Embedded" anxiety
- **The flawed chain:** fixed workflow → no room for free planning → agentic behavior can't be expressed → "we can only be Embedded."
- **Where it breaks:** it treats *free planning* as the essence of agentic behavior. It isn't.
- **The real essence:** *dynamically deciding the next action from the current state* — which holds perfectly well inside a fixed sequence. The room to operate simply shifts from the orchestration layer down into the individual node.
- **Load-bearing conclusion:** **Agentic is a local property, not a global one.** For MMM — driving tens of millions in budget allocation under an explainability mandate — human-in-the-loop is not a defect; it is a prerequisite for trust and compliance.

### Slide 3 · Change the axis: from "architecture label" to "value density"
- The binary "Native vs. Embedded" derails the discussion. The useful axis: **can the human's cognitive load be moved continuously upward at every judgment node?**
- Same fixed workflow, poor vs. strong implementation:
  - human as **operator** → human as **chief reviewer**
  - step-by-step operation → step-by-step approval → **exceptions only**
- **Core metaphor:** not a chat box, not a black-box dashboard — a **review workstation where "AI submits a PR, the human reviews it."**
- **North-star metric:** whether **time-per-review keeps falling.** Everything else (models-per-person, declining rejection-rate-over-time) ladders up to this.

### Slide 4 · Positioning: lower the capability threshold by *exactly one tier*
- Not "replace the expert," not "anyone can use it." The precise claim: **lower the capability threshold required to deliver a *trustworthy* MMM by exactly one tier.**
- **Senior:** throughput multiplied — one person does the work of a former team; cycle time from weeks to days. Certain, safe value capture.
- **Mid-level** (knows marketing, has statistical fundamentals, not an MMM expert): with AI, delivers what previously required a Senior. **This is where TAM genuinely — and safely — expands.**
- **Junior / true novice:** still can't reach it, and shouldn't. What they lack is *judgment*, which is exactly what AI should least, and most dangerously, attempt to replace right now.
- **One line:** **"Down one tier" is value; "all the way down" is risk.**

---

# Part 2 · Product Concept (Slides 5–7)
> Purpose: show how we take a deterministic, fixed workflow, decompose it into per-node roles, and assign autonomy node-by-node — which is what actually makes the product AI-Native.

### Slide 5 · Deterministic skeleton, probabilistic flesh
- The workflow is a **fixed DAG: 6 stages / ~33 nodes** — data alignment → cleaning → adstock/saturation transforms → model specification → fit diagnostics → business-sanity check → calibration → budget optimization → output.
- The orchestration layer is **deliberately deterministic;** autonomy lives *inside the node*. This is "demote agentic from a global to a local property," implemented.
- **Visual:** the fixed workflow canvas (lane = agent × column = stage). Message: *the sequence is fixed, but every node is an ocean of judgment* — keep this outlier or drop it? is this saturation inflection reasonable? this channel's ROI conflicts with business intuition — is the model wrong or the intuition wrong?

### Slide 6 · Decompose the work: node-level four-quadrant autonomy (M / A / C / H)
- Ask two questions of every node — *does it need judgment?* × *is information sufficient / risk high?* — and sort into four classes:
  - **M — Mechanical:** rules fully execute, **zero AI** (having an LLM do deterministic computation is expensive *and* unreliable).
  - **A — AI-Automatable:** AI generates, machine-checkable schema, **human spot-checks after the fact.**
  - **C — Cognitive:** needs thinking but bears no responsibility → rendered as **suggestion + evidence + candidates**, awaiting a person. **The highest-value zone.**
  - **H — Human-only:** responsibility cannot be delegated (e.g., final model selection — **never auto-selected;** the gate presents Pareto candidates for a person to choose).
- **Published mix ≈ 45% M / 20% A / 22% C / 13% H.** Automation savings come from **M + A (~2/3 of effort);** differentiated value concentrates in **C quality and the H decision experience.** All design freedom lives at the **C/A boundary** — and that is where engineering effort is concentrated.

### Slide 7 · That is AI-Native: four value-amplifying moves
- **Role reversal:** the modeler shifts from "running the model once" to "reviewing an already-run draft that arrives with full reasoning" (Proposal: structured `diff` + rationale + evidence).
- **Make uncertainty explicit:** key outputs (ROI, saturation inflection) carry confidence and sensitivity, not a lone point estimate — the crux of MMM's trust problem.
- **Proactive anomaly routing:** AI judges, against business priors, "these 3 spots need a human," directing attention precisely onto the C-class nodes.
- **Consistency through memory:** the modeler's implicit preferences distilled into long-term memory, reused across refresh cycles — a dividend unique to high-frequency, *repeating* fixed workflows.
- **Close on:** **AI-Native is not "an AI button bolted on" — it is AI as the way the workflow runs.**

---

# Part 3 · Product Capabilities (Slides 8–10)
> Purpose: translate the philosophy into capabilities an executive can see. One core idea per slide, image-heavy, text-light.

### Slide 8 · A review workstation — not a chat box, not a black-box dashboard
- **Navigation *is* the workstation:** Project (three-column workbench) / Workflow Canvas / Decisions / Assets / Knowledge; chat is demoted to a floating assistant dock, so spatial structure is preserved — you always know "which step am I on."
- **HumanWorkbench:** surfaces **one waiting item at a time** ("What needs you" + "N more waiting"); when nothing needs a person it shows a **calm state** ("AI is working on X").
- **Rhythm set by autonomy tier:** M/A run through and batch for after-the-fact spot-check; only C/H actually block and wait. **Never a confirmation pop-up at every step** — that would turn the human into the bottleneck.
- **Two anti-patterns it refuses:** chat-box-over-workflow (loses spatial structure) and black-box dashboard (review becomes theater).

### Slide 9 · The atomic unit: Decision Card + Insight Engine
- **DecisionCard** — conclusion-first design:
  - top line = the AI conclusion and the point you must judge; numbers/rationale/counterfactuals visually de-emphasized below
  - **uncertainty is a first-class citizen** (confidence + data-sparsity flags; low-confidence proposals downgraded from one-click-apply to must-edit)
  - **every option spells out its consequence** ("Then: …") — answering "what if we *don't* pick A," precomputed per option
  - **action equals decision:** buttons carry decision semantics ("Accept / Refit under prior / Ask a question"), not OK/Cancel
- **Proposal → Apply protocol:** AI **never writes state directly;** every change is a structured `diff` + rationale + evidence that passes **three gates (schema → rule → human)** before applying.
- **Insight Engine:** proactively emits four finding types — **connection / gap / conflict / reference** — and each *must* carry a suggested action that lands back in the workflow. *"An insight without an action is noise."*

### Slide 10 · The trust layer: global traceability + the right to challenge
- **End-to-end lineage:** one click reconstructs "what AI decided, what changed, and why" — serving compliance *and* letting the human dare to let go.
- **Artifact lifecycle:** `draft → proposed → confirmed → frozen`; a Knowledge change-ledger records add/delete/merge × reason × source × who-confirmed, auto-appended on acceptance.
- **"Challenge" verb:** interrogate any number ("why is this elasticity so high?") → AI assembles evidence — prior range, collinearity VIF, cross-project recall — and answers.
- **One line:** **AI proposes, the expert reviews, the expert is responsible — the responsibility chain is closed structurally,** not by convention.

---

## Slide 11 · Close & call to action
- **Three-line callback:** Philosophy (autonomy pushed down, value density) · Concept (four-quadrant decomposition → AI-Native) · Product (review workstation + trust layer).
- **"Why now":** first-mover advantage, and a **reusable paradigm** for the company's other product lines — decided by three questions: *are errors invisible? × are consequences high-risk? × is feedback fast and cheap?* (MMM hits the worst case on all three → "amplify the expert"; a low-risk, instant-feedback line like copy generation → "novice-usable" instead.)
- **CTA:** pilot proposal / live demo / next steps.

---

## Appendix notes & to-supply
- **Assets to add:** product screenshots (Workflow Canvas, Decision Card, Insight Engine), real mix/case figures, brand color + logo.
- **Honest roadmap (internal-only optional slide):** time-per-review not yet instrumented; uncertainty currently qualitative words rather than numeric intervals (`ROI 3.8 [2.9–4.7]`); autonomy tiers static, not yet an adjustable "must-review → spot-check" knob backed by acceptance-rate evidence.
- **If compressing to ≤ 10 slides:** merge Slides 9 + 10 into a single "Core interaction & trust" slide.
- **Design guidance:** executive deck — one core idea per slide, images over text, no jargon stacking; keep mechanism names (proposal/gate/automation-class) off-slide and speak the business language.
