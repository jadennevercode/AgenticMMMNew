# Agentic MMM — Product Concept (Revised) · Artifacts-Driven

> Replaces **Part 2 · Product Concept** in the deck outline.
> Old framing (deterministic skeleton → M/A/C/H → four moves) is folded in as supporting detail; the new organizing idea is **the Artifact, not the process step.**
> Audience: executives · dense, thesis-first.

---

## The reframe in one line

The workflow is fixed, fragmented, and alternates between human and machine — but **none of that is the point. The deliverable is.** So we organize the entire product around building **Artifacts**, and realize AI-Native behavior and Human–AI collaboration *inside the scope of each Artifact.*

Four pillars carry this:

| # | Pillar | One-line claim |
|---|--------|----------------|
| 1 | **Artifacts-Driven** | Make the deliverable — not the step — the unit of work, collaboration, and autonomy. |
| 2 | **Transparent & Traceable** | The whole build is explicit and traceable — every Artifact's "Draws on / Feeds into," with human review on the steps that matter. |
| 3 | **AI Cognitive** | AI's job is to lower the human's cognitive load — recommend, pre-answer, pre-compute. |
| 4 | **Canvas** | A spatial surface to iterate Artifacts — import/export, direct edit, natural-language change. |

---

## Pillar 1 · Artifacts-Driven

**The problem with a step-centric view.** An MMM run is a fixed, fragmented sequence of small tasks that ping-pong between human and machine. If you build the product around *steps*, you inherit all the friction — pop-ups, hand-offs, "which step am I on" — and none of the value. Steps are a means; nobody is paid to complete a step.

**The move.** Make the **Artifact the organizing unit.** Each stage exists only to produce or refine a concrete deliverable — a cleaned dataset, a model specification, a diagnostics report, a calibrated model, a budget-allocation plan. The Artifact is the contract between human and AI: AI proposes changes *to an Artifact*; the human accepts, edits, or rejects *an Artifact*.

**Why this is the right frame for AI-Native + Human–AI collaboration.**

- **Scope.** AI-Native autonomy and human judgment are both defined *relative to a specific Artifact*, not scattered across the timeline. "What can AI do here, what must the human own here" becomes a per-Artifact question — clean, bounded, answerable.
- **Hand-off clarity.** Alternating human/machine work stops being chaotic, because each hand-off is just "the Artifact's current state + what changed." Nothing is lost between turns.
- **Outcome alignment.** Optimizing for Artifact quality optimizes for what the client actually buys — not for process throughput.

> Carries the old "deterministic skeleton, probabilistic flesh" idea — the skeleton now *is* the chain of Artifacts; the probabilistic work happens inside each one.

---

## Pillar 2 · Transparent & Traceable (how it will be built)

**The build itself is explicit and traceable.** Nothing is a black box. Before and while it runs, you can see *how it will be built* — the plan, the stages, who/what is responsible for each. The process is not inferred after the fact; it is declared up front and traceable throughout.

**Every Artifact declares its lineage — "Draws on" and "Feeds into."** Each deliverable is wired into an explicit dependency graph:

- **Draws on** — the upstream Artifacts (and data/knowledge) this one is built from. You can always trace backward to what it rests on.
- **Feeds into** — the downstream Artifacts this one affects. You can always trace forward to what changes if this changes.

This turns the chain of Artifacts into a transparent graph: pick any deliverable and see, in both directions, exactly where it came from and what depends on it.

**Human review is on the steps that matter (HITL).** The important nodes carry a visible, traceable review state — *a human has reviewed this*. Accountability isn't assumed; it's recorded on the Artifact, so anyone can see which deliverables passed a human gate and which are still AI-drafted.

**Why executives should care.** Explicit "how it will be built" + Draws-on/Feeds-into lineage + recorded human review converts "a model said so" into "here is exactly how this was produced, what it depends on, and who signed off." That is the precondition for trust, for compliance under an explainability mandate, and for a human being willing to approve a budget decision worth tens of millions.

> Folds in the old trust thesis: traceability and human-review status are no longer a separate "trust layer" bolted on — they are properties of *every* Artifact by construction.

---

## Pillar 3 · AI Cognitive (lower the human's cognitive load)

**The goal is not "AI does everything."** AI's primary objective is to **reduce the human's cognitive burden** at each judgment point — to move the human from originating work to reviewing it.

**How AI contributes wherever it can.**

- **Recommend.** Surface a conclusion-first recommendation with rationale, so the human starts from a position, not a blank page.
- **Pre-answer.** Pre-fill draft responses to the questions a step raises, leaving the human to confirm or adjust rather than compose.
- **Pre-compute.** Prepare the candidate options, the counterfactuals ("if not this, then…"), and the evidence *before* the human arrives at the decision.
- **Route attention.** Flag the few spots that genuinely need a person; let the rest pass.

**The effect.** The human's effort shifts from "produce and check everything" to "judge what matters." Cognitive load moves continuously upward — which is exactly the value-density thesis from Part 1, now operationalized as a design rule for *what AI should do inside an Artifact.*

---

## Pillar 4 · Canvas

**The Canvas is the form.** Artifacts need a better medium than chat or a static dashboard for optimization, adjustment, and collaboration. The **Canvas** is a spatial, manipulable surface where an Artifact lives and improves.

**What the Canvas enables.**

- **Continuous iteration.** The human keeps refining the Artifact in place — not regenerating it from scratch each time.
- **Import / export.** Bring an Artifact in, take it out — the Canvas is interoperable, not a walled garden.
- **Natural-language editing.** Change the Artifact by describing the change ("re-fit OOH under the tighter prior," "split this channel by region") — direct manipulation *and* language, together.
- **The collaboration medium.** AI proposals land on the Canvas; the human reviews, tweaks, and accepts there. It is where Human–AI collaboration physically happens.

> Replaces "review workstation as a metaphor" with a concrete surface: the workstation *is* the Canvas, and the Artifact is what sits on it.

---

## Suggested slide mapping (Part 2, revised)

To keep the deck tight (~11 slides), Part 2 becomes **one overview + the four pillars condensed**:

- **Slide 5 — Concept overview:** "Artifacts-Driven" reframe + the 4-pillar table (the chain-of-Artifacts visual).
- **Slide 6 — Pillars 1 & 2:** Artifacts-Driven (left) + Transparent & Traceable (right), with a Draws-on/Feeds-into lineage illustration.
- **Slide 7 — Pillars 3 & 4:** AI Cognitive (recommend / pre-answer / pre-compute) + Canvas (iterate / import-export / NL edit), with a Canvas mock.

Alternatively, if you want one slide per pillar, Part 2 expands to 4 slides and the deck grows to ~12.

---

## Open items to confirm before I rebuild the deck
- One slide per pillar (deck → ~12) **or** the condensed 1-overview + 2-detail mapping above (deck stays ~11)?
- Any product screenshot of the actual **Canvas** to drop into Pillar 4?
- Keep these four as the *entire* Concept, or retain a brief nod to the M/A/C/H autonomy classes as supporting detail under Pillar 1?
