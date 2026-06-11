# Week 23 — Contract Testing, Property-Based Testing, and Capacity Planning

Welcome to the week you stop testing examples and start testing *guarantees*. For twenty-two weeks you have built a polyglot system: a Rust cart, Go inventory and payment, Python order and search, all talking gRPC across a Kafka spine and an Istio mesh. Every one of those services has unit tests — example-based tests, the kind where you feed in a known input and assert a known output. Those tests are necessary and they are not enough. They catch the bugs you thought of. This week is about the two test families that catch the bugs you *didn't*: **contract tests**, which lock the boundary between two services so a producer can't break a consumer without the build going red, and **property-based tests**, which generate thousands of inputs you'd never have written by hand and hunt for the one that violates an invariant. Then we close the week with the third discipline a staff engineer is expected to have and most don't: **capacity planning** — the math (Little's Law, the queueing curve, the Universal Scalability Law) that tells you how many replicas a service needs *before* you ship it, instead of after the pager goes off.

The throughline is the same one this whole course has pushed: **the failures that hurt in distributed systems are the ones at the boundary and the ones under load, and both are invisible to example-based tests.** A consumer-driven contract test catches the boundary failure — the day the Go inventory team renames a Protobuf field and the Python order service that depended on it breaks in production three weeks later. A property-based test catches the under-specified failure — the CRDT merge that's commutative for the inputs you tried and *not* for the one weird interleaving you didn't. And a capacity model catches the load failure — the service you sized for "feels about right" that falls off the queueing cliff at 1.4x your launch traffic. This week makes all three of those failures something you find on your laptop on a Tuesday, not in an incident channel on a Saturday.

This is also the week that directly arms the **capstone defense** next week. The syllabus assessment matrix puts a **mock staff system-design interview** at the end of this week — 60 minutes, an external reviewer, scored on a rubric — and "defend a capacity model on paper" is exactly what that interview tests. So treat the capacity-planning memo here not as homework but as the rehearsal for the room you walk into next week.

## Learning objectives

By the end of this week, you will be able to:

- **Author** a consumer-driven contract test with **Pact**: write the consumer's expectation, generate the pact file, verify it against the real provider, and publish it to a **Pact Broker** so the contract gates both sides' pipelines.
- **Explain** why consumer-driven contract testing closes the polyglot gap that integration tests and shared schemas alone do not — and where contract testing *stops* (it verifies the shape and the agreed interactions, not the business semantics).
- **Write** property-based tests with **Hypothesis** (Python), **fast-check** (TypeScript/JS), **gopter** (Go), and **proptest** (Rust): define a generator, state an invariant, and let the framework shrink a failing case to its minimal reproduction.
- **Prove** the algebraic laws a CRDT must satisfy — commutativity, associativity, idempotence — as properties, and find the merge bug a hand-written test would have missed.
- **Apply** the queueing math of capacity: **Little's Law** (L = λW) to relate concurrency, arrival rate, and latency; the **utilization-latency curve** (why latency explodes as ρ → 1); and the **Universal Scalability Law** to model where adding replicas stops helping and starts hurting.
- **Produce** a one-page capacity-planning memo for a service: the arrival rate, the per-request service time, the concurrency the math demands, the replica count with headroom, and the cost — defensible under cross-examination.
- **Connect** fault-injection-at-the-unit-level (failpoints, `proptest` with injected errors) to the chaos engineering of Week 22: the same failures, tested cheaply in-process before you test them expensively in-cluster.

## Prerequisites

This week assumes you have completed **C22 weeks 1–22**, or have equivalent fluency. Specifically:

- The **capstone services** in some runnable form: the `cart` CRDT (Rust, Week 3/20), `inventory` and `payment` (Go), `order` and `search` (Python). You will write contract tests *between* them, so you need at least two of them callable.
- **gRPC + Protobuf** fluency (Week 5): you can read a `.proto`, generate stubs, and reason about backward/forward compatibility. Contract testing sits on top of this typed surface.
- **CRDT theory** (Weeks 3 and 20): the OR-set, the merge function, and the convergence guarantee. The property tests this week target exactly that merge.
- **The reliability patterns and the queueing primitives from Week 18**: SLIs/SLOs, p99 vs p99.9, Little's Law and the Universal Scalability Law in outline. This week takes them from outline to a memo you defend.
- A working language toolchain for each generator you run: **Python 3.11+** with `pytest`, **Go 1.22+**, **Rust (stable)** with `cargo`, and **Node 20+** for `fast-check`. You will not run all four in anger; pick the two that match your capstone's hottest boundary, and read the rest.

You do **not** need prior Pact or property-testing experience. We start at the consumer's first expectation and build to a published, pipeline-gating broker.

## Topics covered

- **Consumer-driven contract testing with Pact**: the consumer writes its expectation against a *mock* provider; Pact records the agreed interactions into a **pact file**; the real provider replays that file in verification. The flow that makes a polyglot system safe: the Python consumer's pact verified against the Go provider, both gated by the broker.
- **The Pact Broker and `can-i-deploy`**: publishing pacts and verification results, tagging by branch/environment, and the `can-i-deploy` gate that refuses a deploy that would break a live consumer. This is the contract testing that *blocks the pipeline*, not the kind that decorates a wiki.
- **Contract testing's boundaries**: what a pact proves (the agreed request/response shape and the named interactions) and what it does not (full business correctness, every possible input, the *semantics* behind the shape). Why you still need integration tests and the property tests below.
- **Property-based testing**, four languages: **Hypothesis** (Python), **fast-check** (JS/TS), **gopter** (Go), **proptest** (Rust). The model: a *generator* produces inputs, an *invariant* must hold for all of them, and a *shrinker* reduces any failure to its minimal form. Why a shrunk counterexample is worth a hundred example-based tests.
- **Properties of a CRDT merge**: commutativity (`merge(a,b) == merge(b,a)`), associativity (`merge(merge(a,b),c) == merge(a,merge(b,c))`), idempotence (`merge(a,a) == a`), and the partial-order monotonicity that defines a join-semilattice. Encoding these as properties and finding the merge bug.
- **Fault-injection at the unit level**: `proptest`/Hypothesis with injected errors, failpoints, and the "inject a duplicate delivery and assert no double-charge" test — the in-process cousin of Week 11's idempotent consumer and Week 22's chaos drills.
- **Capacity planning math**: **Little's Law** (L = λW) and its three readings; the **M/M/c queueing model** and the utilization-latency curve (latency ∝ 1/(1−ρ)); the **Universal Scalability Law** (the contention + coherency terms that bend throughput back down); and **cost-aware design** — translating the model into a replica count and a dollar figure.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Contract testing with Pact; the broker; `can-i-deploy`     |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Pact consumer + provider verification across the polyglot  |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Property-based testing; Hypothesis/fast-check/gopter/proptest |  2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | CRDT-merge properties; unit-level fault injection          |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Capacity planning: Little's Law, queueing, USL; the memo    |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work (broker + properties + memo)        |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, mock-interview prep, review                          |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                            | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The Pact docs, the four property-testing libraries, the queueing-theory references |
| [lecture-notes/01-contract-testing-with-pact.md](./lecture-notes/01-contract-testing-with-pact.md) | Consumer-driven contracts, the pact file, provider verification, the broker, `can-i-deploy`, and what contract tests don't catch |
| [lecture-notes/02-property-based-testing-and-capacity-planning.md](./lecture-notes/02-property-based-testing-and-capacity-planning.md) | Property-based testing in four languages, the CRDT-merge laws, unit-level fault injection, and the capacity math (Little's Law, queueing, USL) |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-pact-consumer-and-provider.md](./exercises/exercise-01-pact-consumer-and-provider.md) | Write a Pact consumer test (Python order → Go inventory), generate the pact, verify it against the provider, publish to a broker |
| [exercises/exercise-02-property-tests-crdt-merge.py](./exercises/exercise-02-property-tests-crdt-merge.py) | Hypothesis property tests proving the OR-set merge is commutative, associative, and idempotent — and a planted bug to find and shrink |
| [exercises/exercise-03-capacity-model.py](./exercises/exercise-03-capacity-model.py) | A runnable capacity calculator: Little's Law, the M/M/c utilization-latency curve, and the USL fit — outputs the replica count and the memo numbers |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-contract-that-passed-but-prod-broke.md](./challenges/challenge-01-the-contract-that-passed-but-prod-broke.md) | A green pact suite and a production break — find the gap between "the shape matched" and "the behavior was right" |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the capacity-planning memo you defend in the mock interview |
| [mini-project/README.md](./mini-project/README.md) | `marketplace-contracts`: a published Pact broker for the capstone, a property-tested CRDT merge, and a capacity model for the order service |

## The "the test found a bug you didn't write" promise

C22 uses a recurring marker for every exercise that ends in the machinery *proving* something, not just running. This week's canonical one is a property-based test shrinking a generated failure to its minimal counterexample — the machine handing you a bug you never thought to write:

```
$ pytest exercises/exercise-02-property-tests-crdt-merge.py -q
...F
Falsifying example: test_merge_is_commutative(
    a=ORSet(adds={('x', 1)}, removes=set()),
    b=ORSet(adds=set(), removes={('x', 1)}),
)
merge(a, b) != merge(b, a)
  merge(a, b) = ORSet(elements={'x'})
  merge(b, a) = ORSet(elements=set())
```

That `Falsifying example`, already shrunk to the smallest inputs that break the law, is the property tester earning its keep: it found an ordering of one add and one remove that your merge handles asymmetrically — a real convergence bug, in a test you never hand-wrote. When the shrunk case is two elements instead of two thousand, you can read the bug directly. The point of this week is to make `Falsifying example` and a published, green Pact broker as ordinary as `istioctl proxy-status` became in Week 8 — the difference between "my tests pass" and "I have evidence my system is correct at the boundary and under the inputs I can't enumerate."

## Stretch goals

If you finish the regular work early and want to push further:

- Add **bi-directional contract testing** (Pact's newer mode): verify a provider's OpenAPI/Protobuf-derived contract against the consumer's pact *without* replaying the provider, and reason about when that's a sound shortcut and when it isn't.
- Wire **`can-i-deploy`** into a real GitHub Actions matrix across two services in different languages, and demonstrate it *blocking* a deploy that would break a deployed consumer. The block is the whole point.
- Write a **stateful property test** (Hypothesis `RuleBasedStateMachine` or `proptest`'s state-machine testing) that models a sequence of cart operations across a partition and asserts convergence after heal — the property version of Week 20's partition drill.
- Fit the **Universal Scalability Law** to *real* load-test data from your capstone (`k6`/`fortio` runs at increasing concurrency), recover the contention and coherency coefficients, and predict the throughput ceiling. Then test the prediction.

## Up next

Week 24 is capstone-only. There is no new topic — you assemble the full **Polyglot Marketplace Backbone**, run it active-active across two regions, defend it in a staff-engineer architecture review, record the demo, and execute the two mandatory chaos drills. The contract suite, the property-tested merge, and the capacity memo you build this week are three of the deliverables you walk in with: the broker URL with green contracts is a required capstone artifact, the property tests are your evidence the CRDT converges, and the capacity memo is what you defend when a reviewer asks "how do you know two replicas is enough." Push your `marketplace-contracts` mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
