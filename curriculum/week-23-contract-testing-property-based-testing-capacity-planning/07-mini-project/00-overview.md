# Mini-Project — `marketplace-contracts`: A Published Broker, Property-Tested Merge, and a Capacity Model

> Lock your capstone's polyglot boundaries with a published Pact broker, prove your OR-set CRDT merge converges with property-based tests, and size the order service with a defensible capacity model. By the end you have three capstone deliverables in hand: a green broker URL, a property-tested merge that is *evidence* the cart converges, and a one-page capacity memo you defend in next week's mock interview.

This is the artifact that turns "my services talk to each other and seem fine" into "I have evidence my boundaries hold, my CRDT converges, and my services are sized for their load." After this week, three of the capstone's required deliverables exist: the syllabus names "a published Pact broker URL with green contracts" as a mandatory deliverable, the property-tested merge is your proof the active-active cart converges (the thing the demo's partition-heal shows live), and the capacity memo is what a staff reviewer asks for when they say "how do you know this is sized right."

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `marketplace-contracts` is three capstone deliverables, built now so next week is assembly and defense, not authoring. The broker runs in-cluster as the capstone requires. The property tests are the evidence behind the demo's CRDT-convergence segment. The capacity memo is the rehearsal for the mock staff system-design interview that closes this week — and the input to the architecture document next week.

---

## What you will build

A repo `marketplace-contracts` with four deliverables:

1. **`broker/`** — a Pact Broker running in-cluster (Helm or a Deployment), plus the consumer tests and provider verifications for the capstone's named boundaries: `cart ↔ inventory`, `cart ↔ payment` (gRPC pacts), and `order → search` over `order.placed.v1` (a message pact). All green, all published.
2. **`pipeline/`** — the `can-i-deploy` gate wired so that a provider change which would break a live consumer is *refused*. A demonstrated block (deliberately break a provider, watch the gate say no) is the deliverable, not just a passing gate.
3. **`properties/`** — property-based tests proving the OR-set merge is commutative, associative, and idempotent (the three convergence laws), plus the idempotent-consumer property (no double-charge under duplicate delivery). Run against the *real* merge from your Rust `cart` (proptest) and the *real* consumer logic.
4. **`capacity/`** — a capacity model for the `order` service: arrival rate, service time, Little's-Law concurrency, the replica count at a target utilization, the single-failure headroom, and the cost — written up as a one-page memo you defend.

By the end you have a public repo containing a broker you can point a reviewer at, a property suite that is *evidence* (not assertion) of convergence, and a memo that survives "how do you know two replicas is enough."

---

## Why this and not "just write some tests"

You could add a few example tests on each boundary and call the system tested. Don't stop there — that's the gap this whole week is about. A defensible test-and-capacity posture gives you:

- **Boundaries that can't silently break.** A published, gating broker means the Go inventory team *cannot* ship a change that breaks the Python order service without the pipeline refusing it. That's a structural guarantee, not a hope that someone runs the integration suite.
- **Convergence you can prove, not just demonstrate.** The capstone demo shows the cart converging across one partition heal. The property tests show it converges across *thousands of generated interleavings*. One is an anecdote; the other is evidence. A reviewer who sees the property suite knows the convergence isn't luck.
- **A capacity story that survives cross-examination.** "Seven replicas because Little's Law gives four in flight, the queueing curve says target 0.65, and we survive a single-replica loss inside the SLO" beats "two replicas felt right" in exactly the room you walk into next week.

---

## Repo layout

```
marketplace-contracts/
├── README.md
├── broker/
│   ├── deploy/                    # broker Helm values or Deployment + Service
│   ├── cart-inventory/            # gRPC pact: cart (consumer) <-> inventory (provider)
│   │   ├── consumer_test.rs       #   or .py — cart's expectation of inventory
│   │   └── provider_verify_test.go#   inventory replays the pact
│   ├── cart-payment/              # gRPC pact: cart <-> payment
│   └── order-search/              # MESSAGE pact: order.placed.v1 producer/consumer
├── pipeline/
│   ├── can-i-deploy.sh            # the gate, run before any deploy
│   └── demo-block.md              # the demonstrated REFUSAL of a breaking change
├── properties/
│   ├── crdt_merge_proptest.rs     # commutativity/associativity/idempotence on the REAL merge
│   ├── idempotent_consumer.py     # no double-charge under duplicate delivery
│   └── stateful_convergence.py    # (stretch) sequence-of-ops convergence after partition
├── capacity/
│   ├── model.py                   # the capacity calculator (from Exercise 3), parameterized
│   └── ORDER-CAPACITY-MEMO.md     # the one-page memo you defend
└── audit/
    └── verify_contracts.sh        # asserts the broker is green and can-i-deploy passes
```

---

## Deliverable 1 — `broker/` (the published, green broker)

Stand up the Pact Broker in-cluster (the capstone requires it in-cluster, not on your laptop). Then build the three contracts:

- **`cart ↔ inventory`** — a gRPC pact over `inventory.v1.InventoryService/CheckStock` (and the reserve path). Cart is the consumer; inventory the provider. Use the `pact-protobuf-plugin`.
- **`cart ↔ payment`** — the gRPC pact over the charge path. Note: this is the boundary the challenge's double-charge lived on, so your pact here proves the *shape*; the property test (Deliverable 3) proves the *idempotency semantics*. Document that division in the boundary's README.
- **`order → search`** — a **message pact** over `order.placed.v1`. Order is the producer; search the consumer. This locks the event-schema so order can't add a required field that search chokes on.

Every pact published, every provider verification green, visible in the broker UI. Capture the broker URL — it's a capstone deliverable.

> **The rule the audit enforces:** the broker must be *green*, and the contracts must be *real* — principal boundaries that match your actual capstone topology, not toy interactions. A broker with one trivial pact "to have a broker" misses the point; the contracts must cover the boundaries the syllabus names.

---

## Deliverable 2 — `pipeline/` (the gate that blocks)

Wire `can-i-deploy` so a deploy that would break a live consumer is refused. The deliverable is the *demonstrated refusal*: in `demo-block.md`, break a provider (rename a Protobuf field on inventory, say), re-verify, run `can-i-deploy`, and capture the **non-zero exit** that names the consumer it would break. Then fix it and capture the gate going green.

That demonstrated block is the single most convincing contract-testing artifact you can show a reviewer: it proves the gate isn't decorative — it physically refuses a breaking change. Record the `record-deployment` calls too, so the broker knows what's live where (the input that makes `can-i-deploy`'s answer trustworthy).

---

## Deliverable 3 — `properties/` (convergence and idempotency as evidence)

Two property suites against your *real* code:

- **`crdt_merge_proptest.rs`** — translate the three laws (commutativity, associativity, idempotence) into Rust `proptest` against your *actual* cart OR-set merge from Week 3/20. This is the evidence behind the demo's partition-heal segment: the merge converges not just for the one partition you show, but for every interleaving proptest generates. If a law fails, you've found a convergence bug *before* the capstone demo, not during it.
- **`idempotent_consumer.py`** — the property from the challenge: for any sequence of deliveries including duplicates and a restart, the payment is charged exactly once. This is the in-process proof of the capstone's "Drill B: Kafka broker loss — no double-process" requirement, run cheaply before the expensive in-cluster drill.

> **The rule the audit enforces:** the property tests must run against your *real* merge and *real* consumer logic, not a toy copy. The whole value is that the evidence is about the code that ships. A property test against a re-implemented toy proves nothing about the capstone.

Stretch: `stateful_convergence.py` — a `RuleBasedStateMachine` that generates op-sequences across two replicas with a partition and asserts post-heal convergence. This is the property version of Week 20's drill and a standout capstone artifact.

---

## Deliverable 4 — `capacity/` (the memo you defend)

A capacity model for the `order` service (the orchestrator — the busiest synchronous service, since it fans out to cart, inventory, and payment per order):

1. **Measure** the order service's per-request service time under *light* load (so it's the raw cost, not the queued cost) — `k6`/`fortio` at low concurrency, read the p50/p99.
2. **Project** the peak arrival rate (a flash-sale scenario: steady 200 rps, peak 800 rps).
3. **Run** `capacity/model.py` (parameterized from Exercise 3) to get Little's-Law concurrency, the replica count at target utilization (0.65), the utilization-latency table, and the single-failure headroom.
4. **Write** `ORDER-CAPACITY-MEMO.md` — one page — with: the demand, the service time and where you measured it, the concurrency, the replica count and *why that target utilization*, the single-replica-failure verdict, the autoscaling trigger, and the monthly cost with cost-per-request and the fixed-vs-per-request split.

The memo must survive the mock interview's cross-examination: "why 0.65 and not 0.9?" (the queueing cliff), "what happens at 2x?" (re-run the model), "how do you know the service time?" (you measured it, here's the run). Rehearse defending it out loud before next week.

---

## Deliverable 5 — `audit/verify_contracts.sh` (the posture is verifiable)

A script that makes the whole posture *checkable*, not claimed — the same discipline as Week 8's `verify_mesh.sh`. Against the running broker and your suites it must:

1. Assert the broker is reachable and **green** for all three named boundaries (query the broker API for the latest verification result per pact; fail if any is unverified or failed).
2. Run `can-i-deploy` for each provider against the deployed-consumer set and assert it passes — and, as a negative test, assert it *fails* when pointed at the known-breaking version (so you've proven the gate actually gates).
3. Run the property suites and assert they pass (the merge laws and the idempotency property both green).
4. Exit **0** when every assertion passes; exit **non-zero** naming the first failure.

```bash
#!/usr/bin/env bash
set -euo pipefail
BROKER=${PACT_BROKER_URL:?set PACT_BROKER_URL}
fail() { echo "CONTRACT AUDIT FAIL: $1" >&2; exit 1; }

# 1. all three pacts verified green?
for pair in "cart/inventory" "cart/payment" "order/search"; do
  c="${pair%/*}-service"; p="${pair#*/}-service"
  pact-broker can-i-deploy --pacticipant "$c" --latest \
    --to-environment production --broker-base-url "$BROKER" >/dev/null \
    || fail "$c -> $p contract is not green"
done

# 3. property suites pass?
pytest properties/idempotent_consumer.py -q || fail "idempotency property failed"
( cd properties && cargo test --quiet ) || fail "CRDT merge properties failed"

echo "CONTRACT AUDIT PASS: broker green, gate enforces, properties hold."
```

The non-zero-on-weakness behavior is the point: this script can gate a capstone deploy or a CI run, the same way `verify_mesh.sh` gated the mesh posture in Week 8. A reviewer runs it once and knows the whole contract-and-property posture is real.

## Rules

- **You may** read the Pact docs, the property-testing library docs, and the queueing references for the stretch.
- **You must not** declare a boundary "contracted" with a trivial pact that doesn't match your real topology. The contracts must cover the syllabus-named boundaries with real interactions.
- **You must not** report a capacity number you didn't derive from a measured service time. "I assumed 5 ms" is not a measurement; `k6` at 50 rps reading p50 = 5 ms is.
- **You must not** run the property tests against a toy re-implementation. They run against the real merge and the real consumer.
- **You must not** claim the broker is green if `can-i-deploy` doesn't actually pass — the audit checks.
- Pact (broker in-cluster), Hypothesis/proptest, `k6`/`fortio`. Everything runs locally on Kind.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-23-marketplace-contracts-<yourhandle>`.
- [ ] The Pact Broker runs in-cluster and is green for `cart↔inventory`, `cart↔payment`, and `order→search` (message pact). The broker URL is captured for the capstone.
- [ ] `can-i-deploy` passes for compatible versions, and `demo-block.md` shows it *refusing* a deliberately-breaking provider change with a non-zero exit naming the consumer.
- [ ] `crdt_merge_proptest.rs` proves the *real* OR-set merge is commutative, associative, and idempotent.
- [ ] `idempotent_consumer.py` proves no double-charge under any generated duplicate-delivery sequence.
- [ ] `ORDER-CAPACITY-MEMO.md` derives the replica count from a *measured* service time, justifies the target utilization with the queueing curve, and states the single-failure headroom and the cost.
- [ ] `audit/verify_contracts.sh` exits **0** when the broker is green and `can-i-deploy` passes, and **non-zero** otherwise — demonstrated.
- [ ] A `README.md` with the boundary map, the three deliverables, and a paragraph on what each test proves and what it doesn't (shape vs semantics vs load).
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Contract coverage** | 20 | The three named boundaries contracted with real interactions; broker green; gRPC + message pacts both present. |
| **The gate (`can-i-deploy`)** | 15 | A *demonstrated* refusal of a breaking change, not just a passing gate. |
| **CRDT-merge properties** | 20 | The three laws proven against the *real* merge; a deliberately-broken merge shown to fail a law and shrink. |
| **Idempotency property** | 15 | No-double-charge proven over generated duplicate/restart sequences against real consumer logic. |
| **Capacity memo** | 20 | Replica count from a *measured* service time; target utilization justified by the queueing curve; single-failure headroom and cost. |
| **Auditability & docs** | 10 | `verify_contracts.sh` asserts green-and-gating; README explains shape-vs-semantics-vs-load. |

**90+** is portfolio-grade and three capstone deliverables ready to defend. **70–89** works but likely has a thin broker (trivial pacts), a capacity memo with assumed-not-measured numbers, or property tests against a toy. **Below 70** usually means the broker isn't actually gating or the properties don't run against real code — fix those first; they're the two things this week exists to produce.

---

## Suggested order of work

- **Thursday.** Stand up the broker in-cluster. Build the first gRPC pact (`cart ↔ inventory`) end to end: consumer test → pact → provider verification → published green. Don't move on until the broker UI shows one green contract — that's the loop you'll repeat twice more.
- **Friday (morning).** Add `cart ↔ payment` and the `order → search` message pact. Then wire `can-i-deploy` and *demonstrate the block* — break a provider, watch the gate refuse, fix it, watch it pass. Capture both in `demo-block.md`.
- **Friday (afternoon).** Property tests: the three CRDT-merge laws against your real merge, and the idempotency property against your real consumer. Deliberately break each, watch it fail-and-shrink, restore, watch it pass. These are the convergence and no-double-charge evidence.
- **Saturday.** The capacity memo. Measure the order service's service time under light load, run the model, write `ORDER-CAPACITY-MEMO.md`, and rehearse defending it out loud — the mock interview is this week. Finish with `verify_contracts.sh` green and a clean push.

## What "done" looks like

A reviewer opens your repo, clicks the broker URL, and sees three green contracts covering the boundaries the syllabus names — gRPC for the synchronous hops, a message pact for the event spine. They read `demo-block.md` and see `can-i-deploy` *refusing* a breaking change by name, which tells them the gate is real, not decorative. They run your property suite and watch it prove the OR-set merge is commutative, associative, and idempotent across thousands of generated interleavings — the evidence that the cart converges, not a single lucky demo. They read `ORDER-CAPACITY-MEMO.md` and find a replica count derived from a measured service time, a target utilization justified by the queueing cliff, and a single-failure headroom — a sizing they can cross-examine and that holds. Then they run `verify_contracts.sh` and it exits zero. Every one of those is a capstone deliverable, built and defensible. That is what "three deliverables down, before the capstone week even starts" looks like.

## A note on doing this against real services vs stubs

The honest tension this week: the strongest version of every deliverable runs against your *real* capstone services, but those services may not all be ready by Week 23. The right move is to do as much as possible against the real code and to be explicit about what's stubbed. A contract verified against a real provider is stronger than one verified against a stub — but a contract against a stub still locks the *consumer's* expectation, which is half the value and can be re-verified against the real provider the day it's ready. A property test against your real merge is the whole point; a property test against a re-implemented toy proves nothing about what ships. So: real merge and real consumer for the properties (non-negotiable — that's the evidence), real providers for the contracts where you can and documented stubs where you can't, and a measured service time for the capacity memo even if the service is still rough. Document every stub in the README so a reviewer knows exactly what's proven against production code and what's a placeholder to be re-verified. That honesty is itself a senior signal — it's the same "name your own limitations" discipline the architecture review rewards next week.

## How this connects to the rest of C22

- **Week 5 (gRPC/Protobuf)** gave you the typed surface; this week's contracts sit on top of it, catching the boundary breaks the schema permits but a consumer can't survive.
- **Weeks 3 & 20 (CRDTs)** gave you the OR-set and ran it across regions; this week *proves* the merge converges, which is the evidence behind the capstone demo's partition-heal segment.
- **Week 11 (idempotent consumers)** and **Week 22 (chaos)** are the same double-charge bug; this week tests it cheaply in-process, before the expensive in-cluster drill.
- **Week 18 (reliability + queueing)** gave you Little's Law and the USL in outline; this week turns them into a memo you defend.
- **Week 24 (capstone)** consumes all three deliverables: the broker URL is a required artifact, the property tests are the convergence evidence, and the capacity memo is the architecture document's sizing section and the mock interview's subject.

When you've finished, push the repo and take the [quiz](../05-quiz.md). Then rehearse the capacity memo out loud — the mock interview is this week.
