# Mini-Project — `cart-crdt`: The Cart, Active-Active Across Two Regions, Proven Convergent and Correct

> Promote the cart to genuine active-active: both Week-19 regions accept writes to the same cart, a CRDT merges them, and after a partition-and-heal the cart converges to a **lossless, intended** state — convergence *and* correctness, both proven. Plus a per-field consistency map (which field uses which CRDT/policy and why), a metadata-cost budget with bounded growth, and a correctness monitor that catches the convergent-but-wrong footgun.

This is the artifact that turns "we used a CRDT" into "the cart survives a region partition with no lost updates, and I can prove the converged value is the one the customer intended." After this week, active-active is a *defensible posture*: both regions write locally with no failover-RTO, the cart converges losslessly under partition (which read-local/write-primary could never do), and every field's consistency model is labeled and justified.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `cart-crdt` *is* the capstone's `cart-service` ("OR-set CRDT shopping cart, multi-region active-active" — the syllabus capstone spec). It sits on the Week-19 two-region substrate (now genuinely active-active, not just failover) and under the Week-21 zero-trust security stack (SPIFFE/SPIRE + OPA on every cross-region hop). Week 22's gameday Drill A (region failover) and the capstone demo's "cart-CRDT convergence across a simulated partition" run on exactly this. Build it so the convergence is *proven* (not asserted) and the metadata is *bounded* (not unbounded), because that's what the capstone and the gameday will exercise.

---

## What you will build

A repo `cart-crdt` with five deliverables:

1. **`cart/`** — the CRDT cart itself: items as an **OR-set / multiset** (add-wins, observed-remove), quantities that **sum** under concurrency (PN-counter / Automerge Counter), and at least one field that uses a **non-CRDT policy** (a shipping address resolved via siblings, or a last-modified LWW where LWW is *correct*). Built on Automerge (or a documented equivalent), not hand-rolled.
2. **`active-active/`** — the cart running **active-active across the two Week-19 regions**: both regions accept writes to the same cart, synced via the CRDT's binary sync protocol, with a network partition you can induce and heal.
3. **`convergence/`** — the **proven convergence demo**: partition the regions, write concurrently to both, heal, and assert **CONVERGED** (replicas byte-identical) *and* **LOSSLESS** (every acknowledged add present) *and* **INTENT** (quantities summed, removes only undid what they observed). Exits non-zero if any of the three fails.
4. **`metadata/`** — the **metadata-cost budget**: drive realistic add/remove churn, measure tombstone / history growth, and demonstrate a **compaction / causal-stability GC** that bounds it. A before/after on document size.
5. **`consistency-map.md`** — the **per-field consistency map**: a table of every cart field, the CRDT type or policy it uses, and *why* the converged value of that type is the intended one — including the fields that are deliberately *not* CRDTs (the inventory dependency that needs strong consistency).

By the end you have a public repo of a CRDT cart + an active-active multi-region run + a convergence-AND-correctness proof + a bounded-metadata demonstration + a consistency map any reviewer can audit.

---

## Why this and not "just use a CRDT library"

You could `npm i @automerge/automerge` and call the cart "a CRDT." Don't stop there — that's the gap this whole week is about. A defensible CRDT posture gives you:

- **Convergence you proved AND correctness you proved**, not just "it converged." The default convergence check is the easy, misleading half; this project's monitor asserts losslessness and intent too — the difference between a cart that delights users and one that silently eats their items (the Challenge).
- **Active-active that actually buys something**: local writes in every region, no single-writer bottleneck, no failover-RTO on the write path, partition-tolerant — the thing Week 19's read-local/write-primary explicitly could *not* do.
- **A per-field consistency map**, so "are we eventually or strongly consistent" has a *per-field* answer you can defend, not a blanket claim that quietly applies a convergent-but-wrong policy to a field that needed strong consistency.
- **Bounded metadata**, so the cart works in month three (after a million add/remove cycles) and not just in the demo — the thing that quietly kills naive CRDT deployments.

The local-first and collaborative-app ecosystems will hand you CRDT documents for free. Building the cart deliberately — choosing each field's type, proving correctness, bounding metadata — is what lets you trust them and defend the design.

---

## Repo layout

```
cart-crdt/
├── README.md
├── cart/
│   ├── cart.mjs                  # the CRDT cart: OR-set items, summed quantities, sibling/LWW fields
│   └── policies.md               # the conflict policy for each field (links to consistency-map.md)
├── active-active/
│   ├── deploy/                   # cart deployed into both Week-19 regions, syncing via CRDT
│   └── partition.sh              # induce + heal a network partition between the regions
├── convergence/
│   └── prove.mjs                 # partition -> concurrent writes -> heal -> assert CONVERGED+LOSSLESS+INTENT
├── metadata/
│   ├── churn.mjs                 # drives add/remove cycles, measures tombstone/history growth
│   └── BUDGET.md                 # metadata growth + the compaction/GC that bounds it
└── consistency-map.md            # per-field: type, policy, why the converged value is intended
```

---

## Deliverable 1 — `cart/` (the CRDT cart, modeled per field)

The cart, with each field's type chosen for its semantics (Lecture 1 §3):

- **Items:** an OR-set / multiset (add-wins, observed-remove). A concurrent add in another region survives; a remove only undoes the adds it observed. This is the lossless core.
- **Quantities:** summed under concurrency (a Counter / PN-counter, or counting OR-set adds). Concurrent "+2" and "+3" → 5. Document the removal subtlety (don't model remove as a raw decrement that can go negative — Exercise 1 stretch).
- **At least one non-auto-merge field:** a shipping address resolved via **siblings** (Exercise 3), *or* a last-modified timestamp as an LWW-register where LWW is the *correct* choice. The point is to show you can pick a *different* policy when the field needs it.

Document each field's policy in `cart/policies.md` (and the consolidated `consistency-map.md`).

---

## Deliverable 2 — `active-active/` (across the two regions)

Run the cart active-active across the Week-19 Kind regions: both regions accept writes to the same cart and sync via the CRDT's binary update protocol. `partition.sh` induces a *real* network partition (block the sync path between regions) and heals it. This is the syllabus lab: "Promote the cart to active-active across both Kind regions using a CRDT. Partition the regions for 5 minutes. Heal. Verify convergence." — done on genuinely separated replicas, not in one process.

> **The rule the project enforces:** the convergence must be demonstrated on *separated* replicas with a *real* partition (sync blocked), not just an in-process `merge()`. An in-process merge proves the algebra; a real partition-and-heal proves the *deployment*.

---

## Deliverable 3 — `convergence/` (proven convergent AND correct)

The heart of the project. `prove.mjs` runs the partition-heal and asserts **all three**:

1. **CONVERGED** — region A and region B reach byte-identical cart state.
2. **LOSSLESS** — every add acknowledged in *either* region during the partition is present after heal.
3. **INTENT** — quantities are the *sum* of concurrent adds; a remove undid only the adds it observed; no LWW-style silent overwrite.

It exits **non-zero** if any assertion fails. A convergence proof that checks only #1 is the Challenge's bug waiting to happen — the green-but-wrong cart. Checking #2 and #3 is what makes "converged" mean "correct."

---

## Deliverable 4 — `metadata/` (bounded cost)

This is the deliverable that separates this project from a tutorial. Measure, on *your* cart:

1. **Growth under churn:** drive thousands of add/remove cycles and measure the tombstone count / op-history / document size growing while the *logical* cart stays small.
2. **The bound:** implement (or configure) a **compaction / causal-stability GC** — reclaim tombstones once all regions have observed the remove; snapshot/compact the Automerge history. Show document size after compaction tracks the *data* size, not the *edit count*.

Write `BUDGET.md`: a before/after on document size under churn, and a paragraph on the GC strategy and its safety condition (causal stability — only reclaim what all replicas have seen). "After N add/remove cycles the document grew to X without GC and stays at Y with it" is the sentence that proves you can run CRDTs past the demo.

---

## Deliverable 5 — `consistency-map.md` (per-field, defended)

A table that is the senior artifact of the week:

| Field | Type / policy | Converged value is correct because... | If we'd used LWW... |
|---|---|---|---|
| items | OR-set | concurrent adds all survive (add-wins) | one region's cart silently discarded |
| quantity | Counter (PN) | concurrent adds sum | only one add counted |
| last-modified | LWW-register | newest *is* the intended value here | (LWW is correct here) |
| shipping address | siblings (app/user resolve) | no safe auto-merge; surface the conflict | a real edit silently dropped |
| **inventory stock** | **strong consistency (NOT a CRDT)** | a CRDT would converge to an *oversold* count | overselling |

Plus a paragraph: "are we eventually or strongly consistent?" is answered **per field**, not system-wide — and the inventory row is why (it's deliberately *not* a CRDT, because the correct behavior under concurrency is coordination, not convergence). This map is what a reviewer audits to see you understand CRDTs are a per-field tool, not a system-wide religion.

---

## Rules

- **You may** read the Automerge/Yjs/Redis-CRDT docs, the Shapiro and Dynamo papers, and the lecture notes.
- **You must not** declare the cart "correct" by checking only convergence. The proof must assert losslessness and intent too (Deliverable 3). A convergence-only check is the Challenge's bug.
- **You must not** model a *set* field (items) as an LWW-register or a *summed* field (quantity) as LWW — those are the footguns this week exists to prevent.
- **You must not** report bounded metadata without a GC whose safety condition (causal stability) you state — reclaiming a tombstone a replica hasn't seen resurrects deleted items.
- **You must not** make any field a CRDT that needs strong consistency (the inventory dependency) — label it correctly in the map.
- Automerge 2.x (or a documented equivalent), Node 20+, the two Week-19 Kind regions. Everything runs locally.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-20-cart-crdt-<yourhandle>`.
- [ ] The cart models items as an OR-set/multiset and quantities as a summing counter, built on a real CRDT library (not hand-rolled).
- [ ] The cart runs **active-active across the two Week-19 regions** with a *real* partition you induce and heal (`partition.sh`).
- [ ] `convergence/prove.mjs` asserts CONVERGED **and** LOSSLESS **and** INTENT, and exits non-zero if any fails — demonstrated passing on the OR-set cart and failing on an LWW variant.
- [ ] `metadata/BUDGET.md` shows tombstone/history growth under churn and a causal-stability GC that bounds it, with a before/after document size.
- [ ] `consistency-map.md` labels every field's type/policy with a justification, including the inventory dependency as deliberately strong-consistency (not a CRDT).
- [ ] A `README.md` with the active-active topology, the convergence proof output, the metadata budget, and a paragraph on when a CRDT is the right tool and when it isn't.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Correct per-field CRDT modeling** | 20 | Items = OR-set, quantity = summing counter, a sibling/LWW field where appropriate; built on a real library. |
| **Active-active across real regions** | 15 | Both regions write; a *real* partition induced and healed (not in-process merge). |
| **Convergence AND correctness proof** | 25 | CONVERGED + LOSSLESS + INTENT all asserted; passes on OR-set, fails on LWW; non-zero exit on failure. |
| **Bounded metadata** | 20 | Real growth measured under churn; causal-stability GC/compaction bounds it; safety condition stated. |
| **Per-field consistency map** | 15 | Every field labeled + justified; inventory correctly marked strong-consistency-not-CRDT. |
| **Docs & hygiene** | 5 | Clear README, topology diagram, sensible commits, no secrets/artifacts checked in. |

**90+** is portfolio-grade and *is* the capstone's cart-service. **70–89** works but likely checks convergence without correctness, or reports unbounded metadata. **Below 70** usually means a set/quantity field was modeled as LWW (the footgun) or the inventory dependency was made a CRDT — fix those first; they're the things this week exists to prevent.

---

## Stretch goals

- **Correctness monitor in CI.** A check that asserts not just convergence but "every acknowledged add survives," wired into CI so a future type-choice regression (someone swaps an OR-set for an LWW) fails the build. The Challenge's lesson, automated.
- **Redis Active-Active variant.** Model the cart's data tier as Redis Active-Active CRDTs (OR-set + PN-counter) instead of an in-app Automerge document, and compare: where does the convergence live, and what does each cost? The documents-vs-primitives split made concrete.
- **Sibling resolution UI.** For the shipping-address field, actually surface both siblings to a (mock) client and require a choice, rather than auto-picking — the honest conflict-resolution path.
- **Five-minute partition, real timing.** Run the syllabus's literal "partition for 5 minutes, heal, verify" with real wall-clock timing and a load generator writing throughout, and prove zero lost adds across the whole window.

---

## Common pitfalls (read before you start)

The mistakes that cost the most points and the most debugging:

- **Checking convergence, not correctness.** The single biggest trap: asserting "the replicas are equal" and stopping. They can be equal *and wrong* (the LWW footgun). Your proof must assert losslessness and intent too.
- **Modeling a set as LWW.** Making the cart's items a single last-write-wins value. It converges and silently eats concurrent adds — the Challenge, reproduced in your own code.
- **Modeling quantity as an overwrite.** Concurrent quantity changes stomp each other instead of summing. Use a Counter (PN-counter).
- **No metadata budget.** Reporting "it works" without measuring tombstone/history growth and bounding it with GC. It works in the demo and degrades in production.
- **Premature GC.** Reclaiming tombstones before causal stability → an item resurrects after a sync. GC only what *all* replicas have seen.
- **Making inventory a CRDT.** Putting a must-not-oversell field under a CRDT. It converges to an oversold count. Label it strong-consistency in the map.
- **In-process "partition."** Demonstrating convergence with an in-process `merge()` instead of a real network partition between the regions. The merge proves the algebra; only a real partition proves the deployment.

A submission that avoids all seven is portfolio-grade; the lost points cluster on the first (convergence-not-correctness) and the last (no real partition).

## How this connects to the rest of C22

- **Week 3 (CRDT theory)** is the OR-set/PN-counter/convergence theory this puts into production with real libraries.
- **Week 19 (multi-region)** is the two-region substrate; here the cart goes from read-local/write-primary to genuinely active-active (the thing failover couldn't give you).
- **Week 21 (zero-trust)** secures every cross-region cart hop with SPIFFE/SPIRE mTLS and OPA policy.
- **Week 22 (gameday) + capstone** run the convergence-across-a-partition demo and the region-failover drill on this exact cart — it *is* the capstone's `cart-service`.

## A suggested order of work

If you're not sure where to start:

1. **Day 1 (Thursday):** model the cart's items as an OR-set and quantities as a Counter in `cart/` (Automerge), and get the *in-process* convergence proof (`convergence/prove.mjs`) asserting CONVERGED + LOSSLESS + INTENT. Prove the algebra first.
2. **Day 1–2:** write the per-field consistency map (`consistency-map.md`) — it's quick once you've modeled the fields, and it forces you to label the inventory dependency as not-a-CRDT.
3. **Day 2 (Friday):** take it active-active across the two real Week-19 regions (`active-active/`) with a *real* partition (`partition.sh`), and re-run the convergence proof on genuinely separated replicas.
4. **Day 2–3:** the metadata budget (`metadata/`) — drive churn, measure the growth, apply causal-stability GC, capture before/after.
5. **Day 3 (Saturday):** the correctness-monitor-in-CI stretch, and the README writeup.

The dependency that trips people: do the *correctness* proof (not just convergence) before the multi-region deployment, so you catch a wrong type choice in-process where it's easy to debug, rather than across two clusters where it isn't.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
