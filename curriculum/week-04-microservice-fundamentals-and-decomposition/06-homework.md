# Week 4 Homework

Six problems that revisit the week's topics and force decomposition judgement into your fingers. The full set should take about **5 hours**. Work in your Week 4 Git repository (the same workspace as the exercises and the `marketplace-seam` mini-project) so every problem produces at least one commit you can point to at the Phase 1 architecture review in Week 12.

The headline deliverable is **Problem 4 — the decomposition memo**, called out explicitly in the syllabus. Treat it as the artifact a staff engineer hands a CTO, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Go 1.23+** and **Python 3.12+** available — Problems 2, 5, and 6 use the exercise tools and the mini-project code.

---

## Problem 1 — The language-test audit

**Problem statement.** Take any system you currently work on (or the Bookhive system from Exercise 1) and produce a **language-test table**: list every important domain noun and what it means to each team/context that uses it. Mark every noun whose meaning *changes* across contexts — each is a boundary you've discovered empirically. Write it to `notes/week-04/language-test.md`.

**Acceptance criteria.**

- `notes/week-04/language-test.md` exists with at least eight domain nouns, each with its meaning in two or more contexts.
- At least two nouns are marked as *changing meaning* across contexts, with the implied boundary named.
- For one changing noun, you explicitly state "this is why we do NOT build a single `XService`."
- Committed.

**Hint.** The richest nouns are the ones everyone uses: "user," "order," "product," "account," "item." Start there. If a noun means the same thing everywhere, it's boring; the boundaries are at the nouns that shift.

**Estimated time.** 35 minutes.

---

## Problem 2 — Score your own topology

**Problem statement.** Sketch a candidate service topology for the system from Problem 1 (4–8 services). Encode it in the `Topology` form used by `exercise-02-decompose-the-monolith.py` (owned tables, operations, sync calls) and run the analyzer. Drive it to **0 ERROR**: no shared tables, no entity services. Capture the before (if it had faults) and after output.

**Acceptance criteria.**

- A `notes/week-04/topology-score.md` records your topology, the analyzer output, and the changes you made to reach 0 ERROR.
- If your first sketch had a shared table or an entity service, the before/after is shown. If it was clean first try, say so and explain which heuristic kept you clean.
- Committed.

**Hint.** The most common self-inflicted ERROR is two services listing the same table in `owned_tables` because "they both need that data." That's the shared database. The fix is to give the table one owner and have the other service *call* the owner — change your `sync_calls`, not your `owned_tables`.

**Estimated time.** 45 minutes.

---

## Problem 3 — Break a distributed monolith

**Problem statement.** Construct a topology with a *synchronous dependency cycle* (e.g. `order` calls `payment` synchronously and `payment` calls back into `order` synchronously) in the `exercise-03-distributed-monolith-smell.go` `Topology` form. Run the detector and confirm it reports the cycle and a non-zero exit. Then **break the cycle with a single asynchronous edge** and confirm the detector now passes. Document which edge you made async and why that direction.

**Acceptance criteria.**

- `notes/week-04/cycle-break.md` shows the flawed topology (detector reports `sync-cycle`, exits 1) and the fixed topology (no cycle, exits 0).
- You state *which* edge you made asynchronous and *why that direction* (the side that can tolerate eventual notification, not the side that needs an immediate answer).
- Committed.

**Hint.** `payment` needs an immediate yes/no from the card network, so `order → payment` often wants to stay synchronous *at the moment of charge*; but `payment → order` ("the charge settled") is a notification `order` can receive asynchronously. Make the *notification* async, not the *request*.

**Estimated time.** 40 minutes.

---

## Problem 4 — The decomposition memo (headline deliverable)

**Problem statement.** This is the syllabus deliverable. Write a full decomposition memo for the system from Problems 1–3 (or for the Challenge's Marketplace monolith if you'd rather use a richer example) at `notes/week-04/decomposition-memo.md`, with all six sections from Lecture 2 §3.1:

1. **Context** — the pain the decomposition solves.
2. **Proposed topology** — contexts with subdomain kind, owner, owned tables, and a context map with named relationship patterns.
3. **Heuristics applied** — which heuristic put each non-obvious boundary, and how you resolved any disagreements.
4. **Data ownership table** — every table's owner; how cross-service reads are resolved (gRPC vs event-fed read model); no service reads another's tables.
5. **Three rejected alternatives** — an over-decomposed one, an under-decomposed one, and a plausible-but-wrong boundary, *each with a specific reason it lost*.
6. **Risks and migration path** — incremental (strangler-fig); which service you extract first and why.

**Acceptance criteria.**

- `notes/week-04/decomposition-memo.md` exists and hits all six headings.
- The topology passes the Problem 2 analyzer (0 ERROR) and the Problem 3 detector (no cycle); paste both as evidence.
- **Three** rejected alternatives, each with a *specific* named reason (an anti-pattern or a violated heuristic), not "it was worse."
- At least one **anti-corruption layer** appears in the context map and is justified.
- The migration path names the *first* service to extract and the reasoning.
- Committed.

**Hint.** The rejected-alternatives section is where this memo is won or lost. The strongest move: include the *seductive* wrong answer (the single `ProductService`) and reject it with the exact reasoning from the challenge trap — three meanings of "product," plus a hot read path contending with a transactional write path. A reviewer who sees you reject the obvious trap trusts everything else you wrote.

**Estimated time.** 1 hour 15 minutes.

---

## Problem 5 — Prove the boundary holds

**Problem statement.** In your `marketplace-seam` mini-project, run `make verify` and capture the evidence that the `cart`↔`catalog` boundary is real: the grep finds no cross-owned database references, the API path works, and the in-container attempt to connect to the *foreign* database fails. Write the evidence to `notes/week-04/boundary-proof.md`.

**Acceptance criteria.**

- `notes/week-04/boundary-proof.md` shows: the clean grep output, a successful end-to-end `curl` (add item → cart reflects it with catalog's name), and the failed foreign-DB connection attempt from inside the `cart` container.
- You state in one sentence why the failed connection is the *point*, not a bug.
- Committed.

**Hint.** If your `cart` *can* reach `catalog_db`, the boundary is a lie — go remove the credential from `cart`'s environment. The proof you want is `psql $CATALOG_DATABASE_URL` failing from inside the cart container *because the variable doesn't exist there*, not because of a firewall.

**Estimated time.** 40 minutes.

---

## Problem 6 — The price-snapshot demonstration

**Problem statement.** Demonstrate the price-snapshot invariant in your mini-project: add an item to a cart, then change that product's price in `catalog`, then re-read the cart and show the *original* (snapshotted) price is unchanged. Capture it in `notes/week-04/price-snapshot.md`.

**Acceptance criteria.**

- `notes/week-04/price-snapshot.md` shows: add item (price X) → update catalog price to Y → re-read cart still shows X.
- You explain in two sentences why the price lives in `cart_db` and is not re-fetched live (a price change must not retroactively alter carts; the locked price is law).
- Committed.

**Hint.** If your cart's price *changes* when catalog's does, you're re-fetching live on read instead of snapshotting on add. Move the price into the `cart` line-item write path and stop reading it from catalog at read time.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Language-test audit | 35 min |
| 2 — Score your own topology | 45 min |
| 3 — Break a distributed monolith | 40 min |
| 4 — Decomposition memo (headline) | 1 h 15 min |
| 5 — Prove the boundary holds | 40 min |
| 6 — Price-snapshot demonstration | 30 min |
| **Total** | **~4 h 45 min** |

---

## Rubric (for the headline memo, Problem 4)

| Criterion | Excellent (full) | Adequate (half) | Missing (zero) |
|---|---|---|---|
| **Topology correctness** | Passes both tools (0 ERROR, no cycle); no entity services; clean data ownership. | Passes one tool; a minor smell remains. | A shared database or entity service in the chosen topology. |
| **Heuristics named** | Every non-obvious boundary cites its heuristic; disagreements resolved with the priority rule. | Most boundaries justified; one hand-waved. | Boundaries asserted without heuristics. |
| **Rejected alternatives** | Three, each with a specific named reason (anti-pattern or violated heuristic); includes the seductive trap. | Three present but reasons are vague ("worse"). | Fewer than three, or none. |
| **Anti-corruption layer** | Present, justified, placed in the right (downstream) context. | Present but under-justified. | Absent. |
| **Migration path** | Incremental strangler-fig; names the first extraction and the reasoning. | Names a path but not the first step. | Big-bang or absent. |

**Full marks across the board** is the artifact you bring to the Week 12 architecture review. Anything less, revise before then — you'll defend it live.

When you've finished all six, push your repo and make sure the `marketplace-seam` [mini-project](./07-mini-project/00-overview.md) is in the same workspace — Week 5 turns its HTTP boundary into a typed gRPC contract. Then take the [quiz](./05-quiz.md) with your notes closed.
