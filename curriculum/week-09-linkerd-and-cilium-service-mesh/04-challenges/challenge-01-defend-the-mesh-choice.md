# Challenge 1 — Defend the Mesh Choice

**Time estimate:** ~90 minutes.

## Problem statement

You are in a staff design review. You've brought an ADR recommending a service mesh (one of Istio, Linkerd, Cilium — or "no mesh") for a hypothetical org, backed by the benchmark you ran this week. Three senior engineers on the panel are going to push on your reasoning. Your job is not to "win" — it's to demonstrate that your recommendation is *load-bearing*: that you've thought about the objections, you concede the ones with merit, you answer the ones that are answerable with evidence, and you either hold your position or change it for a stated reason.

This mirrors the most important meeting in a platform engineer's life: the one where a real architectural decision gets made or unmade. A recommendation that collapses at the first "but what about X" was never a recommendation. A recommendation that *refuses* to move even when X is a genuine problem is dogma. The staff-engineer skill is the middle: a position you can defend, with the intellectual honesty to update it when the argument warrants.

## Setup

Pick an org (or reuse the one from your homework ADR). State it concretely: number of services, number of teams, the dominant traffic pattern (L4-heavy vs L7-heavy), security/compliance requirements, and the existing infrastructure (especially the CNI — it matters for Cilium). Then write your one-paragraph recommendation: which mesh (or none), and the single strongest reason.

Now respond, in writing, to each of the three objections below. This challenge is the *defense*, not the original ADR.

## The three objections

### Objection 1 — Cost (from the FinOps-minded engineer)

> "A mesh isn't free. You're adding latency to every request and memory to every pod — at our scale that's real money and real tail-latency. Justify the spend, with numbers, or tell me why we're not just doing mTLS in a shared library and calling it a day."

Your response must:

- Quote your **actual benchmark numbers** (p50/p99 overhead, proxy memory) for the mesh you recommended.
- **Extrapolate to the org's scale** (per-pod memory × pod count; tail latency × the call-chain depth).
- Either justify the cost by what the mesh buys that a shared library can't (uniform enforcement across teams, telemetry, policy without per-team work) — or, if the org is small enough, **concede the objection and recommend no mesh** (the Week 7 gateway-plus-library answer). One of these must be your honest answer; pick based on the org.

### Objection 2 — Features (from the engineer who's hit a wall before)

> "You picked [Linkerd / Cilium] for its simplicity/efficiency. But in eighteen months we're going to need [rich L7 routing / complex multi-cluster / a filter that only Envoy has], and then we're doing a painful migration. Why not pick the mesh that can do everything from day one?"

Your response must:

- Acknowledge the **real limit** of your chosen mesh (Linkerd's narrower L7; Cilium's younger L7 + CNI coupling; or, if you chose Istio, its operational weight).
- State whether the org **actually needs** the feature in question, or whether it's a hypothetical. (Designing for a need you don't have is its own mistake.)
- Define a **reversal condition**: the specific, observable trigger that would make you migrate (e.g., "if L7-routing requirements grow past N namespaces, we revisit Istio"). A position with a stated reversal condition is stronger than one without — it shows you're not betting the org on being right forever.

### Objection 3 — "Why not the popular one" (from the risk-averse director)

> "Everyone uses Istio. If we pick something else and it goes wrong, that's on us. If we pick the popular one and it goes wrong, at least we made the safe choice. Why are we being clever?"

Your response must:

- Take the **cargo-cult argument seriously** — popularity *does* mean more docs, more hiring pool, more Stack Overflow answers; that's a real benefit, not nothing.
- Counter it with the **actual fit argument**: the most popular mesh is not the best mesh for every org, and adopting Istio's operational surface for a 6-service shop (or any org that doesn't need its depth) is *itself* a risk — a control plane nobody can operate is not "the safe choice."
- Land on a position: either "popularity is decisive here because [reason]" or "fit beats popularity here because [reason]." Don't dodge.

## Acceptance criteria

- [ ] A file `challenge-01-defense.md` containing: the stated org, the one-paragraph recommendation, and a section per objection with a substantive written response.
- [ ] **Objection 1** is answered with your real benchmark numbers extrapolated to the org's scale — not hand-waving about "overhead."
- [ ] **Objection 2** names a concrete reversal condition (the trigger that would make you migrate).
- [ ] **Objection 3** takes the popularity argument seriously AND lands on a clear position.
- [ ] At least one objection results in you **conceding something** — a real limitation acknowledged, or (legitimately) a change to your recommendation. A defense that concedes nothing is a tell that you didn't engage.
- [ ] Committed to your Week 9 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

Two failure modes, opposite ends:

- **The immovable defense.** You answer every objection by re-asserting your original choice, conceding nothing. This reads as someone who decided first and reasoned backward. Real reviews surface real problems; if *none* of three pointed objections moved you even a little, you either got lucky or you're not listening. Find the objection that genuinely has merit for your org and concede it explicitly.
- **The collapse.** You fold at the first push and change your recommendation to whatever the objector implied. This reads as someone with no conviction. An objection having *merit* is not the same as it being *decisive*; "yes, that's a real cost, and here's why it's still worth it" is a stronger answer than "you're right, let's do the other thing." Hold your position when the evidence supports it; move only when it genuinely doesn't.

The "popular one" objection has a specific trap: it's tempting to dismiss popularity as pure cargo-culting. Don't. Popularity is a real, legitimate input (hiring, docs, community) — and *also* not decisive on its own. The mature answer holds both truths.

## Stretch

- Write the **counter-ADR**: argue the *opposite* recommendation as persuasively as you can. If you recommended Linkerd, write the best case for Istio. Being able to argue the other side is how you know your own argument is honest — and it's exactly the Week 23 interview skill.
- Add a fourth objection of your own — the hardest one *you* can think of against your recommendation — and answer it. The objection you most don't want to face is usually the one that matters.
- Bring a **peer** in: have someone else read your ADR and play the panel live. Defending out loud, in real time, is a different and harder skill than defending on paper — and it's the Week 23 format.

## Why this matters

The midterm architecture-review essay (end of Week 12) and the mock staff system-design interview (Week 23) are both, fundamentally, this: a defensible position under cross-examination. The capstone defense in Week 24 is this in front of external reviewers. The mesh choice is a perfect rehearsal because it's a real decision with no single right answer — exactly the kind of question a staff interview asks. The engineer who can say "here's my call, here's the evidence, here's what I concede, and here's what would change my mind" is the one who passes the loop and gets to make the calls. Practice it here, where the only thing at stake is the grade.
