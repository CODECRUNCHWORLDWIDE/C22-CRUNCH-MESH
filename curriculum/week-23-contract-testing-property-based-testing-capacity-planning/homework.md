# Week 23 Homework

Six problems that drive the week's three disciplines into your fingers. The full set should take about **5 hours**. Work in your Week 23 Git repository (the same workspace as the exercises and the `marketplace-contracts` mini-project) so every problem produces a commit you can point to — and so the capacity memo is ready for the mock staff system-design interview that closes this week.

The headline deliverable is **Problem 4 — the order-service capacity memo**, the artifact you defend in the mock interview. Treat it as the one-page document a staff engineer reads before deciding whether to trust your sizing, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have a **Pact broker** running (Exercise 1), **Hypothesis/proptest** installed (Exercise 2), and the **capacity calculator** (Exercise 3) to hand. Problems 1–3 produce contracts and properties; Problems 4–6 produce the memo and the analysis.

---

## Problem 1 — Contract a second boundary

**Problem statement.** Exercise 1 contracted `order → inventory`. Now contract a *second* capstone boundary: either `cart → payment` (gRPC) or `order → search` over `order.placed.v1` (a message pact). Write the consumer test, generate the pact, verify it against the provider (real or stub), and publish to the broker. Note in `notes/week-23/contracts.md` which boundary, which pact type (request/response vs message), and why that type fits.

**Acceptance criteria.**

- `notes/week-23/contracts.md` records the boundary, the pact type, and the published-and-verified result (a broker screenshot or the verification output).
- The pact has at least two interactions (e.g., a success and an empty/error state), each with a provider state where the response depends on data.
- Committed.

**Hint.** For the message pact (`order → search`), there's no request/response — the consumer (search) declares the message shape it expects and the handler that processes it, and the provider (order) verifies the message it *produces* matches. This is the right model for the Kafka event spine.

**Estimated time.** 50 minutes.

---

## Problem 2 — Demonstrate the gate blocking a break

**Problem statement.** Prove `can-i-deploy` blocks, don't just prove it passes. Take a contracted boundary, deliberately make a backward-incompatible provider change (rename a field, make an optional field required, change a status code), re-verify, and run `can-i-deploy`. Capture the non-zero exit and the message naming the consumer that would break. Then fix it and capture the gate going green.

**Acceptance criteria.**

- `notes/week-23/gate-block.md` shows the breaking change, the failed provider verification, and the `can-i-deploy` non-zero exit naming the consumer.
- You show the fixed version passing the gate (green) again.
- You state in one sentence why this block is the difference between contract testing that gates a pipeline and contract testing that decorates a wiki.
- Committed.

**Hint.** Remember to `record-deployment` the consumer to an environment first, so `can-i-deploy` has a live consumer to reason about. Without a recorded deployment, the broker has nothing to check against and the gate is meaningless.

**Estimated time.** 40 minutes.

---

## Problem 3 — Property-test your real CRDT merge

**Problem statement.** Take the *real* OR-set merge from your capstone `cart` (Rust, or whatever language yours is in) and write the three convergence-law properties against it: commutativity, associativity, idempotence. Run them. Then deliberately introduce the bug from Exercise 2 (make removes non-symmetric) and show a property failing with a shrunk counterexample. Restore the correct merge and show all three green.

**Acceptance criteria.**

- `notes/week-23/crdt-properties.md` (or a `proptest`/Hypothesis file) with the three laws against your *real* merge, all passing.
- A captured shrunk counterexample from the deliberately-broken merge, with a one-sentence explanation of the convergence failure it represents.
- You note which law(s) the bug violated and which still passed — and why that means you test all three.
- Committed.

**Hint.** Keep the generator's alphabets small (a handful of elements, a handful of tags) so collisions are frequent and the shrunk counterexample is tiny and readable. A property test with a huge input space takes longer to find the bug and harder-to-read counterexamples.

**Estimated time.** 50 minutes.

---

## Problem 4 — The order-service capacity memo (headline deliverable)

**Problem statement.** This is the syllabus skill ("defend a capacity model on paper") and the subject of the mock interview. Write a one-page memo at `notes/week-23/order-capacity-memo.md` sizing the `order` service, backed by a *measured* service time and the queueing math. Your memo must hit these headings:

1. **Demand** — the peak arrival rate λ (steady and burst), with where the number comes from.
2. **Service time** — the per-request W you *measured* under light load (the run that produced it), p50 and p99.
3. **Concurrency** — Little's Law: L = λ·W, and what pool/concurrency that implies.
4. **Replica count** — the `c` that holds your target utilization (state the target and *why* — the queueing cliff), with the utilization-latency table from the calculator.
5. **Failure headroom** — what happens to ρ and latency when one replica is lost; does the SLO survive? Where's the autoscaling trigger?
6. **Cost** — the monthly cost at that replica count, the cost-per-request, and the fixed-vs-per-request split.

**Acceptance criteria.**

- `notes/week-23/order-capacity-memo.md` exists, fits on roughly one page (500–800 words), and hits all six headings.
- The **service time** is *measured* (a `k6`/`fortio` run at low concurrency), not assumed.
- The replica count is *derived* from the math, and the target utilization is *justified* by the queueing curve, not asserted.
- The memo addresses the single-replica-failure case and names the autoscaling trigger.
- Committed.

**Hint.** The strongest memos answer the follow-up before it's asked: "why 0.65 and not 0.9" (the 1/(1−ρ) cliff), "what at 2x" (re-run the model — the replica count roughly doubles or ρ goes over the cliff), "how do you know W" (the measured run). Rehearse defending each number out loud; the mock interview will probe exactly these.

**Estimated time.** 1 hour.

---

## Problem 5 — Idempotency under duplicate delivery

**Problem statement.** Write a property-based test that proves your payment consumer charges exactly once under *any* sequence of duplicate deliveries and restarts (the Challenge-1 invariant, on your real consumer). Generate sequences of `deliver`/`duplicate`/`restart`, run them, and assert exactly one charge per idempotency key. Show it failing on a deliberately non-idempotent version and passing on the real one.

**Acceptance criteria.**

- `notes/week-23/idempotency.md` (or a test file) with the property over generated delivery sequences.
- A captured failure (shrunk sequence) on a non-idempotent handler and a pass on the idempotent one.
- You note where the *real* invariant is enforced (a DB unique constraint on `idempotency_key`), not just in application code, and why that matters for the multi-replica capstone.
- Committed.

**Hint.** The key insight is that the invariant lives at the storage layer — a process-local lock works in a test but not across replicas. Your property test can use the toy lock; your *writeup* must name the DB constraint as the real fix. This is the in-process rehearsal for the capstone's "Drill B: no double-process under broker loss."

**Estimated time.** 45 minutes.

---

## Problem 6 — Fit the USL to real data (analysis)

**Problem statement.** Run your capstone's order (or cart) service under increasing concurrency with `k6`/`fortio` — say 1, 2, 4, 8, 16, 32, 48, 64 concurrent — and record the throughput at each. Fit the Universal Scalability Law (the calculator's `--usl-demo` machinery, with *your* data) to recover α (contention) and β (coherency), and predict the throughput peak. Then state whether your measured ceiling matched the prediction.

**Acceptance criteria.**

- `notes/week-23/usl-fit.md` with your measured (concurrency, throughput) data, the fitted α/β/γ, and the predicted peak N.
- A one-paragraph interpretation: is your service contention-bound (α dominates — flattens to a ceiling) or coherency-bound (β dominates — peaks and drops)? What would you change to push the ceiling up?
- Committed.

**Hint.** A service with a single-writer bottleneck (inventory's per-SKU lease) is contention-bound (α); a service with cross-replica coordination (the CRDT cart's anti-entropy) is coherency-bound (β). The fitted coefficients tell you *which*, which tells you the *fix* — shard the hot resource (α) or weaken/batch the coordination (β). You need `numpy` + `scipy` for the fit: `pip install numpy scipy`.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Contract a second boundary | 50 min |
| 2 — Demonstrate the gate blocking | 40 min |
| 3 — Property-test the real CRDT merge | 50 min |
| 4 — Order-service capacity memo (headline) | 1 h 0 min |
| 5 — Idempotency under duplicate delivery | 45 min |
| 6 — Fit the USL to real data | 35 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `marketplace-contracts` [mini-project](./mini-project/README.md) is in the same workspace — next week the broker URL, the property tests, and the capacity memo are all capstone deliverables you defend. Then take the [quiz](./quiz.md) with your notes closed, and rehearse the capacity memo out loud for the mock interview.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Second contract (P1)** | 15 | A real second boundary contracted, two interactions with provider states, published and verified. |
| **Gate block (P2)** | 15 | A *demonstrated* `can-i-deploy` refusal of a breaking change, then a green fix. |
| **CRDT properties (P3)** | 15 | Three laws against the *real* merge; a deliberately-broken merge shown to fail and shrink. |
| **Capacity memo (P4)** | 25 | Measured service time; derived replica count; justified target utilization; failure headroom; cost. |
| **Idempotency property (P5)** | 15 | No-double-charge over generated sequences; the DB-constraint fix named for multi-replica. |
| **USL fit (P6)** | 15 | Real data fitted; α/β recovered; contention-vs-coherency diagnosis with the right fix. |

**90+** is portfolio-grade and your capstone is three deliverables closer to done. **70–89** is solid but the memo likely uses an assumed (not measured) service time, or the property tests run against a toy instead of your real code. **Below 70** usually means Problem 2 or 4 was treated as a formality — they're the two that prove you understand the *gate* (not just the contract) and the *cost-under-load* (not just the happy path), which is the difference between testing a system and operating one.
