# Lecture 2 — Property-Based Testing and Capacity Planning

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can write property-based tests in Hypothesis, fast-check, gopter, and proptest; encode the algebraic laws a CRDT merge must satisfy and find the bug a hand-written test misses; inject faults at the unit level; and build a defensible capacity model from Little's Law, the M/M/c queueing curve, and the Universal Scalability Law.

Two disciplines, one theme. Lecture 1 closed the *boundary-shape* gap with contracts. This lecture closes two more: the *input-space* gap (property-based testing — the inputs you never thought to write) and the *load* gap (capacity planning — the math that tells you a service will fall over at 1.4x before it does). Both are about replacing intuition with something stronger: a generator that searches the input space, and a model that predicts the load curve.

The sentence to carry through:

> **Example tests check the cases you imagined; property tests check the law for cases you didn't; and a capacity model checks the curve before traffic does — together they cover the failures that example tests and "it felt about right" never will.**

---

## Part 1 — Property-Based Testing

### 1.1 The model: generator, invariant, shrinker

An example-based test is `assert f(2, 3) == 5`. A property-based test is `for all integers a, b: f(a, b) == f(b, a)`. The shift is from a *specific input/output pair* to a *law that must hold for all inputs*. Three pieces make it work:

1. **The generator** (Hypothesis calls it a *strategy*, fast-check an *arbitrary*, gopter and proptest a *generator/strategy*) produces random inputs of the right shape — integers, strings, lists, your custom CRDT type, sequences of operations.
2. **The invariant** (the *property*) is the law the framework checks for every generated input: commutativity, "round-trips to itself," "never panics," "the output is sorted," "no double-charge."
3. **The shrinker** is the part that makes property testing *usable*. When the framework finds an input that violates the property, it doesn't hand you the giant random input it happened to generate — it automatically *shrinks* it, repeatedly simplifying (smaller numbers, shorter lists, fewer operations) while the failure persists, until it has the **minimal counterexample**. A bug shrunk to "two elements, one add, one remove" is one you can read; the un-shrunk version with two thousand random elements is not.

> **The shrinker is why property testing beats fuzzing for correctness.** A fuzzer finds a crash and hands you a 4 KB blob. A property tester finds a *law violation* and hands you the smallest input that breaks it. The shrunk counterexample is the bug report you'd have written by hand if you'd thought of the case — which, by definition, you didn't.

### 1.2 The hard part is choosing the property

The mechanics are easy; the skill is knowing *what law to assert*. A few patterns that find real bugs:

- **Round-trip / inverse:** `decode(encode(x)) == x`. Catches serialization bugs. For your Protobuf surface: `parse(serialize(msg)) == msg`.
- **Algebraic laws:** commutativity, associativity, idempotence (the CRDT case, §1.4). Catches order-dependence and double-apply bugs.
- **Invariants the operation preserves:** "after any sequence of cart ops, the quantity is never negative." Catches the state machine that can reach an illegal state.
- **Oracle / model-based:** compare your fast implementation against a slow, obviously-correct reference. `my_sort(xs) == sorted(xs)`. Catches optimization bugs.
- **Metamorphic:** when you can't state the exact output, state how the output *changes* with the input. "Adding an item to the cart never decreases the total." Catches a class of bug where you don't have a closed-form oracle.

The reflex to build: when you write a function, ask "what's true for *every* input, not just this one?" That question, asked honestly, is most of property-based testing.

One more discipline that separates a property test that finds bugs from one that doesn't: **bias the generator toward the interesting region.** A naive generator of "any integer" rarely produces 0, -1, `INT_MAX`, or the boundary values where bugs cluster; a good strategy explicitly mixes in those edge cases. For the CRDT, the interesting region is *collisions* — the same `(element, tag)` appearing as both an add on one replica and a remove on another — so you make the element and tag alphabets *small* (a handful of values), which makes collisions frequent and the bugs surface fast. A property test over a huge, uniform input space can run for thousands of examples and never hit the one interleaving that breaks the law, simply because the breaking case is a measure-zero corner of an enormous space. The skill is shaping the generator so the corners are common. This is the property-testing equivalent of "test the boundary values" — except the framework explores the boundaries *combinatorially*, which is exactly the search no human writes by hand.

A related tool: when you *know* a specific case is important (a regression you fixed, a corner you worry about), pin it with `@example` (Hypothesis) or the equivalent — the framework checks that exact input *every* run, in addition to the generated ones, so a known-bad case can never silently drop out of coverage. Generated breadth plus pinned depth is the strongest combination.

### 1.3 The same property in four languages

Your system is polyglot, so here's the *same* property — "reversing a list twice gives back the original" — in all four frameworks, so the model transfers and you can drop into whichever language owns the boundary you're testing.

**Hypothesis (Python):**

```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_reverse_twice_is_identity(xs):
    assert list(reversed(list(reversed(xs)))) == xs
```

**fast-check (TypeScript):**

```typescript
import fc from "fast-check";

test("reverse twice is identity", () => {
  fc.assert(
    fc.property(fc.array(fc.integer()), (xs) => {
      const twice = [...xs].reverse().reverse();
      return JSON.stringify(twice) === JSON.stringify(xs);
    }),
  );
});
```

**gopter (Go):**

```go
func TestReverseTwice(t *testing.T) {
    properties := gopter.NewProperties(nil)
    properties.Property("reverse twice is identity", prop.ForAll(
        func(xs []int) bool {
            return reflect.DeepEqual(reverse(reverse(xs)), xs)
        },
        gen.SliceOf(gen.Int()),
    ))
    properties.TestingRun(t)
}
```

**proptest (Rust):**

```rust
proptest! {
    #[test]
    fn reverse_twice_is_identity(xs in proptest::collection::vec(any::<i32>(), 0..100)) {
        let mut twice = xs.clone();
        twice.reverse();
        twice.reverse();
        prop_assert_eq!(twice, xs);
    }
}
```

Four syntaxes, one idea: declare the generator (`lists of integers`, `array of integer`, `SliceOf(Int)`, `vec of i32`), state the property, let the framework generate and shrink. Once you see the pattern, every framework is the same framework.

### 1.4 The CRDT-merge laws: where property testing earns its keep

Your capstone's `cart` is an OR-set CRDT, and CRDTs are the single best advertisement for property-based testing, because their *correctness is defined by algebraic laws*. A state-based CRDT's merge must form a **join-semilattice**: the merge is the least-upper-bound operation, and for that to guarantee convergence it *must* be —

- **Commutative:** `merge(a, b) == merge(b, a)`. Replicas that receive updates in different orders must converge. If merge isn't commutative, two regions that saw the same updates in different sequences end up *different* — a split-brain that never heals.
- **Associative:** `merge(merge(a, b), c) == merge(a, merge(b, c))`. The grouping of merges must not matter, because in a real partition you have no control over how updates batch.
- **Idempotent:** `merge(a, a) == a`. Re-delivering the same state (which *will* happen — at-least-once delivery, retries, anti-entropy) must not change the result.

These three laws *are* the convergence guarantee. A CRDT that violates any of them does not converge, and the bug is exactly the kind an example-based test misses — you'd have to *guess* the asymmetric interleaving to catch commutativity by example, and the whole point is you can't guess it. The property test *searches* for it:

```python
from hypothesis import given, strategies as st

# A strategy that builds random OR-sets (adds and removes with unique tags).
orsets = st.builds(make_random_orset, st.lists(st.tuples(st.text(), st.integers())))

@given(orsets, orsets)
def test_merge_commutative(a, b):
    assert merge(a, b).elements() == merge(b, a).elements()

@given(orsets, orsets, orsets)
def test_merge_associative(a, b, c):
    assert merge(merge(a, b), c).elements() == merge(a, merge(b, c)).elements()

@given(orsets)
def test_merge_idempotent(a):
    assert merge(a, a).elements() == a.elements()
```

When one of these fails — and on a real, hand-written merge, one often does — Hypothesis hands you the shrunk counterexample: the minimal pair of OR-sets whose merge is order-dependent. That's a convergence bug found on your laptop, in seconds, that would otherwise surface as "the cart shows different totals in us-east and us-west after a partition heal" three weeks into the capstone. Exercise 2 plants exactly such a bug for you to find and shrink.

> **This is the deepest payoff of the week:** the OR-set's *reason for existing* is that it converges, and convergence *is* the three laws, and property testing is the only practical way to check laws over an input space you can't enumerate. Week 3 taught you the CRDT; Week 20 ran it across regions; this week *proves* the merge that makes both work. The property test is the bridge between the theory and the trust.

### 1.5 Stateful property testing: sequences, not single inputs

The OR-set laws above test single merges. The deeper bugs live in *sequences*: a series of cart operations, interleaved across replicas, with a partition in the middle. Stateful property testing (Hypothesis's `RuleBasedStateMachine`, proptest's state-machine support) generates *random sequences of operations* and checks an invariant after each — or checks the system against a simple reference model.

The capstone-relevant property: **for any sequence of adds and removes split across two replicas, with a partition and a heal, the two replicas converge to the same set.** The state machine generates the operation sequence and the partition point; the property asserts post-heal equality. This is the property-test version of Week 20's manual partition drill — and it explores thousands of interleavings you'd never run by hand. It's a stretch goal this week and a genuinely strong capstone artifact: "I didn't just demonstrate convergence once; I property-tested it across generated interleavings."

### 1.6 Fault injection at the unit level

Property testing pairs naturally with **fault injection**, and doing it at the *unit* level — in-process, in milliseconds — is the cheap cousin of Week 22's in-cluster chaos drills. The idea: make the generator produce not just inputs but *failures* — a duplicate delivery, an injected error from a dependency, a retry — and assert the invariant still holds.

The canonical capstone case is the **idempotent consumer** (Week 11): inject a duplicate `order.placed.v1` delivery and assert the payment is charged exactly once.

```python
@given(st.lists(st.sampled_from(["deliver", "deliver-duplicate", "restart"]), min_size=1))
def test_no_double_charge_under_any_delivery_sequence(events):
    consumer = PaymentConsumer()
    order = make_order("ord-1", amount=100)
    for e in events:
        if e == "deliver":            consumer.handle(order)
        elif e == "deliver-duplicate": consumer.handle(order)   # same idempotency key
        elif e == "restart":           consumer = consumer.recover_from_checkpoint()
    # INVARIANT: no matter how many duplicate deliveries or restarts, charge once.
    assert consumer.total_charged("ord-1") == 100
```

Generating *sequences* of deliver/duplicate/restart and asserting "charged exactly once" over all of them is far stronger than the one hand-written "send it twice" test — because the framework finds the sequence (restart *between* the duplicate and the dedup-store write, say) that your hand-written test didn't include. This is the unit-level rehearsal of the Week 22 "kill the consumer mid-batch, restart, re-process, show zero double-charge" chaos drill, run in-process so you find the bug before you ever stand up a cluster. The same failure, tested two ways at two costs — and the cheap one first.

Frameworks like Rust's `fail` crate and Go's `gofail` add **failpoints** — named injection sites in your code you can trigger from a test — for the cases where the failure is deep in the call stack (a write that fails after the commit but before the ack). Combined with proptest, you generate *where* the fault fires as part of the input, and assert the invariant survives every injection point. That's how you test "crash at the worst possible moment" exhaustively instead of hoping you picked the worst moment by hand.

---

## Part 2 — Capacity Planning

You've tested correctness. Now: **how many replicas does this service need, and how do you know before the pager tells you?** This is the math that separates "I deployed two replicas because that felt safe" from "I deployed three replicas because the arrival rate is 800 rps, the service time is 5 ms, and the queueing curve says two replicas hit 80% utilization where p99 latency triples — here's the memo." A staff engineer is expected to have this math, and the mock interview at the end of this week tests it directly.

### 2.1 Little's Law: the one equation you must own

**Little's Law** is the most useful equation in systems performance, and it's almost embarrassingly simple:

```
L = λ · W
```

- **L** = the average number of requests *in the system* (concurrency / in-flight requests).
- **λ** (lambda) = the average *arrival rate* (requests per second).
- **W** = the average *time a request spends in the system* (latency, in seconds).

It holds for *any* stable system, regardless of distribution, with no assumptions — which is what makes it so powerful. Three readings, each a different question answered:

1. **How much concurrency does my load imply?** If you serve λ = 500 rps and each request takes W = 0.020 s (20 ms), then L = 500 × 0.020 = **10 requests in flight on average.** You need a thread/connection/goroutine pool that can hold at least 10, plus headroom for variance, or requests queue.

2. **What latency does my concurrency limit impose?** If your connection pool caps you at L = 50 concurrent requests and you're serving λ = 1000 rps, then W = L/λ = 50/1000 = **0.050 s = 50 ms** is the *floor* on average latency — you literally cannot go faster than that with that pool at that load, because the pool is the bottleneck. This is why "raise the pool size" is sometimes the latency fix and sometimes the thing that just moves the bottleneck downstream.

3. **What throughput can I sustain?** If a downstream dependency can hold L = 100 in-flight and each call takes W = 0.200 s, then λ = L/W = 100/0.200 = **500 rps** is your ceiling against that dependency. Past it, requests queue and W climbs, which (since L is capped) *drops* λ — the cascading-failure shape.

> **Little's Law is the first thing to reach for in a capacity question and the first thing to reach for in a *production incident*.** "Latency is up and concurrency is pinned at the pool max" + Little's Law tells you instantly whether you're pool-bound (raise the pool or shed load) or genuinely slow (the W went up for a real reason). The capstone runbook's "what do you look at first" answer often *is* this triangle: λ, W, and L, and which one moved.

### 2.2 Utilization and the latency cliff (M/M/c)

Little's Law tells you the *average*. It does *not* tell you the worst thing about capacity, which is that **latency doesn't grow linearly with load — it explodes as you approach saturation.** This is the single most important non-intuition in capacity planning, and it comes from queueing theory.

Model a service with `c` replicas (or `c` server threads) as an **M/M/c queue**: Poisson arrivals at rate λ, exponential service at rate μ per server (so one server handles μ requests/sec; service time = 1/μ). Define **utilization**:

```
ρ = λ / (c · μ)
```

ρ is the fraction of total capacity in use. The catastrophe is the shape of the *waiting time* as a function of ρ. For a single server (c=1), the mean response time is:

```
W = (1/μ) / (1 − ρ)
```

Read that denominator. At ρ = 0.5, the `1/(1−ρ)` factor is 2 — response time is double the raw service time. At ρ = 0.8, it's 5. At ρ = 0.9, it's 10. At ρ = 0.95, it's 20. At ρ = 0.99, it's **100**. The latency doesn't degrade gracefully as you load the system — it goes vertical near saturation:

```
   latency
     ^                                        .
     |                                       .
     |                                     .
     |                                  .
     |                            .  .
     |                  .  .  .
     |   .  .  .  .  .
     +-------------------------------------------> utilization ρ
     0        0.5       0.7    0.8   0.9  0.95  1.0
                                    ^^^^^^^^^^^
                              the cliff: small ρ increases,
                              huge latency increases
```

The operational rule that falls out: **target a utilization well below 1 — typically 0.6–0.7 for a latency-sensitive service — because the headroom between your target and 1.0 is what absorbs bursts without the latency going vertical.** A service run at 90% utilization "to save money" is a service one traffic spike away from a latency incident, and the queueing curve is *why*. When a reviewer asks "why three replicas, not two," the answer is this curve: two replicas put you at ρ = 0.85 where p99 is already climbing; three drop you to ρ = 0.57 with room for a burst. (Adding replicas raises `c`, which lowers ρ for the same λ — that's the lever.)

The tail is worse than the mean. The formulas above are for *average* W; the p99 and p99.9 climb the cliff *sooner and steeper*, because the tail is dominated by the requests that arrived during a transient queue buildup. This is why Week 18 hammered p99 vs p99.9 vs p99.99: your SLO lives in the tail, and the tail saturates before the mean does. A capacity model that sizes for the mean utilization and ignores the tail will under-provision exactly the metric your SLO is written against.

### 2.3 The Universal Scalability Law: why more replicas eventually hurt

Little's Law and M/M/c assume adding capacity *helps* — that `c` replicas do `c` times the work. The **Universal Scalability Law (USL)** is the correction: real systems don't scale linearly, and past a point they scale *negatively*. The USL models throughput `X(N)` as a function of concurrency/node-count `N`:

```
              N
X(N) = ─────────────────────────
        1 + α(N−1) + β·N(N−1)
```

Three terms, and the whole story is in the two Greek letters:

- The **`N`** in the numerator is the ideal: linear speedup, `N` workers do `N`× the work.
- **`α` (alpha) — contention.** The cost of serialization: the fraction of work that *can't* be parallelized (Amdahl's law is this term alone). Shared locks, a single-writer database, a hot partition. As α grows, the curve flattens — you approach a ceiling and adding workers stops helping.
- **`β` (beta) — coherency.** The cost of *coordination*: workers having to talk to each other to stay consistent (cache coherency, cross-replica gossip, distributed-lock chatter, the CRDT anti-entropy traffic). This term is `N(N−1)` — it grows *quadratically*. Past a peak, β makes the curve **bend back down**: adding workers makes total throughput *worse*, because they spend more time coordinating than working.

```
   throughput X(N)
     ^
     |            ___________            <- ideal linear (no α, no β)
     |          /
     |        /        ......            <- contention only (α): flattens to a ceiling
     |      / .....               .
     |    /...               .         <- contention + coherency (α,β): PEAKS then DROPS
     |  /.              .
     |/.          .
     +----------------------------------> N (workers / replicas / nodes)
                  ^peak
```

Why this matters for the capstone: your active-active CRDT cart has a **coherency cost** (the cross-region anti-entropy that keeps replicas converging) — that's a β term, and it means there's a point past which adding regions/replicas *reduces* effective throughput because coordination dominates. Your single-writer-per-SKU inventory has a **contention cost** (the lease serializes writes to a SKU) — that's an α term, and it caps how much that SKU's writes can scale no matter how many replicas you add. The USL is the math that says "this is the ceiling, and here's *which term* causes it" — which tells you whether to fix it by reducing serialization (α: shard the hot SKU) or reducing coordination (β: weaken the consistency, batch the anti-entropy). You fit α and β to load-test data (the stretch goal), and the fit predicts the ceiling *before* you hit it.

### 2.4 From model to memo to dollars: cost-aware design

The output of capacity planning is not a number; it's a **memo** that ties the math to a replica count and a cost, defensible under cross-examination. The structure:

1. **The demand.** Arrival rate λ at peak (measured or projected): "order-service peaks at 800 rps on a flash sale, 200 rps steady."
2. **The service.** Per-request service time W (measured under *light* load, so it's the raw cost, not the queued cost): "p50 service time 5 ms, p99 25 ms, measured at 50 rps."
3. **The concurrency.** Little's Law: L = λ·W = 800 × 0.005 = 4 in-flight at p50; budget for the p99 service time and for variance.
4. **The replica count.** Pick a target utilization (0.65), invert ρ = λ/(c·μ) for `c`: with μ = 200 rps/replica (= 1/0.005), c = λ/(ρ·μ) = 800/(0.65×200) = **6.2 → 7 replicas** to keep ρ ≤ 0.65 at peak, with the queueing curve as the justification for not running hotter.
5. **The headroom and the failure case.** "7 replicas at peak; if one fails, ρ jumps to 0.76 — still inside the SLO, so we survive a single-replica loss without a latency breach. Two losses put us at 0.91, on the cliff — that's the autoscaling trigger."
6. **The cost.** 7 replicas × (CPU/memory request) × (cost per unit) = the monthly bill, and the cost-per-request: monthly / (λ × seconds-in-month). The senior insight, same as the GCP capstone's: name what's *fixed* (the always-on replicas) vs *per-request*, because that's where the optimization lever is.

That memo is the deliverable. The mock interview asks you to produce it live for a service you didn't pre-plan, which is why the math has to be in your fingers, not in a spreadsheet you copy. Exercise 3 is a runnable calculator that produces these numbers for the order service; the homework turns it into the memo you defend.

> **Cost-aware design is capacity planning with the dollar column filled in.** The same model that sizes the replica pool prices it, and the same headroom decision (0.65 vs 0.85 utilization) is a cost decision (more replicas, fewer incidents, higher bill). "We run at 0.65 and pay for the headroom because a latency breach costs more than the extra replicas" is a *defensible* sentence; "we run two replicas because it felt right" is not. The difference is this lecture.

### 2.5 A worked capacity question, start to finish

Make it concrete with the exact shape of the mock-interview question. The reviewer says: "Your order service needs to handle a flash sale. Walk me through sizing it." Here's the answer, in the order you'd give it, narrating the math:

> "First, demand. The product team says the flash sale peaks at 800 requests per second, against a steady-state of 200. I'll size for the peak. Second, service time — I measured it at low load, 50 rps, so I'm measuring the *raw* cost without queueing: p50 is 5 milliseconds, p99 is 25. Order fans out to cart, inventory, and payment, so most of that 5 ms is waiting on those three gRPC calls, which I'll note because it means my service time depends on *their* latency. Third, Little's Law: 800 rps times 5 milliseconds is 4 requests in flight on average, so my connection pools and goroutine budget need to hold at least four, with headroom for the p99 tail — call it sixteen to be safe. Fourth, replicas: one replica handles 1/0.005 = 200 rps at saturation, but I never run at saturation. To hold utilization at 0.65 I need 800 / (0.65 × 200) = 6.2, round up to seven replicas. I pick 0.65 because the queueing factor there is about 2.3x; if I ran at 0.9 it'd be 10x and the p99 would blow my SLO. Fifth, failure: lose one replica and I'm at six, utilization 0.67 — still inside the band, so a single-replica failure doesn't breach the SLO. Two losses put me at 0.91, on the cliff, so two-replicas-down is my autoscaling trigger and my page. Sixth, cost: seven replicas at half a CPU and 512 megs each is the fixed floor; doubling traffic to 1600 rps means fourteen replicas, so the cost scales roughly linearly with peak demand above the floor. Most of the bill is the always-on seven, not per-request."

That answer takes ninety seconds, uses no spreadsheet, and survives every follow-up because each number is derived, not asserted. *That* is what "defend a capacity model on paper" means, and it's what the mock interview scores. Notice the moves that read as senior: measuring service time under *light* load (so it's raw, not queued), naming that order's latency *depends on its dependencies*, justifying the utilization target with the cliff, and naming the failure headroom and the autoscaling trigger. None of it is advanced math — it's Little's Law and one queueing factor — but the *discipline* of deriving every number is what separates a staff answer from a guess.

### 2.6 Where each kind of test lives: the economics

Step back and place all of this week's tools on one map, because the literacy is knowing *which test catches which bug at what cost*. A defensible test suite is a portfolio, not a single technique:

| Test kind | Catches | Cost | Where it runs |
|---|---|---|---|
| **Example/unit test** | The cases you imagined | Cheapest | In-process, milliseconds |
| **Property test** | The cases you didn't (laws over an input space) | Cheap | In-process, seconds |
| **Contract test (Pact)** | Boundary-shape drift between services | Cheap | Per-service CI, no integration env |
| **Capacity model** | Under-provisioning before launch | Cheap | On paper / a calculator |
| **Integration test** | Real cross-service wiring | Expensive | A stood-up environment |
| **Chaos drill (Week 22)** | Survival under real infra failure | Most expensive | In-cluster, a gameday |

The economic argument runs left to right: **push every bug as far left as it will go.** The double-charge bug from this week's challenge *can* be caught by a chaos drill (expensive, in-cluster, Week 22) — but it's *cheaper* to catch it with a property test (in-process, seconds). The boundary-shape break *can* be caught by an integration test (expensive, needs both services up) — but it's *cheaper* to catch it with a contract test (per-service CI, no integration env). The under-provisioning *can* be caught by a load test in production (catastrophically expensive — it's an outage) — but it's *cheaper* to catch it with a capacity model (on paper, before launch). The skill this week builds is the judgment to put each guarantee at its cheapest reliable layer, and to know when a cheap layer's guarantee *stops* and you must pay for the expensive one. Contract testing stops at shape; property testing stops at the invariants you thought to assert; the capacity model stops at the assumptions you fed it. Knowing exactly where each stops is what the capstone's reviewers test.

---

## 3. Recap

You should now be able to:

- Write property-based tests in Hypothesis, fast-check, gopter, and proptest, and explain the generator/invariant/shrinker model and why the shrunk counterexample is the payoff.
- Choose properties that find real bugs (round-trip, algebraic laws, preserved invariants, oracle, metamorphic), and encode the CRDT-merge laws (commutativity, associativity, idempotence) that *are* the convergence guarantee.
- Inject faults at the unit level — duplicate deliveries, failpoints, generated failure sequences — to test idempotency and crash-safety in-process, as the cheap cousin of Week 22's chaos drills.
- Apply Little's Law (L = λW) in its three readings, explain the M/M/c utilization-latency cliff (why latency goes vertical as ρ → 1 and why you target 0.6–0.7), and use the Universal Scalability Law's α/β terms to predict where scaling stops helping and starts hurting.
- Turn the math into a capacity memo: demand, service time, concurrency, replica count at a target utilization, the single-failure headroom, and the cost — defensible under cross-examination in next week's mock interview.

### The capacity-planning mistakes to avoid

The recurring ways a capacity model misleads, so your memo doesn't:

- **Sizing for the mean, paying in the tail.** The averages from Little's Law and the mean from M/M/c are not your SLO — your SLO lives at p99 or p99.9, which climbs the queueing cliff *sooner* than the mean. Size for the tail percentile your SLO names, not the average, or you'll under-provision exactly the metric you're graded on.
- **Measuring service time under load.** If you measure W while the system is already queued, you've baked the queueing into the "service time" and your model double-counts it. Measure W at *light* load to get the raw per-request cost, then let the M/M/c math *add* the queueing. Measuring under load is the most common reason a model says "we're fine" right up until it isn't.
- **Ignoring the dependency chain.** The order service's service time *is* the latency of cart + inventory + payment. If you size order in isolation and one dependency slows down, order's W rises, its utilization rises, and it falls off its own cliff — driven by a dependency you didn't model. Name the chain: a capacity model for an orchestrator is a model of its slowest dependency.
- **Forgetting the failure case.** A model that sizes for the happy path and never asks "what's ρ when one replica dies" has no headroom story — and the headroom story is the whole point of not running at 0.95. Always compute the single-failure utilization; it's where the autoscaling trigger comes from.

Avoid those four and your memo survives cross-examination. Fall into them and the model gives false confidence — which, under load, becomes an outage with a paper trail saying "the math said we were fine."

Next: the exercises put all of this on your capstone — a real Pact consumer/provider pair, property tests against your OR-set merge, and the capacity calculator that produces your memo. Continue to [the exercises](../exercises/README.md).

---

## References

- *Hypothesis docs*: <https://hypothesis.readthedocs.io/>
- *fast-check docs*: <https://fast-check.dev/>
- *gopter*: <https://github.com/leanovate/gopter>
- *proptest book*: <https://proptest-rs.github.io/proptest/intro.html>
- *Little's Law*: <https://en.wikipedia.org/wiki/Little%27s_law>
- *M/M/c queue*: <https://en.wikipedia.org/wiki/M/M/c_queue>
- *The Universal Scalability Law (Gunther)*: <https://www.vanguardsw.com/wp-content/uploads/2014/06/Universal-Scalability-Law.pdf>
- *Google SRE Workbook — Managing Load*: <https://sre.google/workbook/managing-load/>
