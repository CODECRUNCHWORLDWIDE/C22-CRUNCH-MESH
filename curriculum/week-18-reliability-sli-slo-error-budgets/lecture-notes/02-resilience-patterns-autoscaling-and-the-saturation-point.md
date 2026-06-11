# Lecture 2 — Resilience Patterns, Autoscaling, and the Saturation Point

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can implement the named resilience patterns (circuit breaker, bulkhead, timeout, retry-with-jitter, backpressure, load shedding, admission control) and explain the failure each prevents; configure HPA and KEDA-on-lag autoscaling and say why each fits; and reason about capacity and tail latency with Little's Law, the Universal Scalability Law, and HDR histograms.

Lecture 1 defined the budget. This lecture is how you *keep* the system inside it when reality pushes back — a slow dependency, a traffic spike, a partial failure that wants to cascade. Three parts: (1) the resilience patterns, (2) autoscaling, (3) capacity and tail latency. The through-line:

> **Every reliability pattern is a deliberate way to fail *small* — bound the wait, isolate the blast radius, shed the marginal request — because the alternative is failing *big*: one slow dependency taking down the whole system through a cascade you didn't design against.**

---

## Part 1 — The resilience patterns

### 1.1 Timeouts: bound every wait

The most basic pattern, and the most skipped. **Every** call to anything that can be slow — a network call, a DB query, a lock acquisition — must have a **timeout**. A call with no timeout is a thread (or goroutine, or connection) that can be held *forever* by a hung dependency, and if enough of them hang, you exhaust the pool and the *caller* dies too — the dependency's slowness becomes your outage. The rule: an unbounded wait is a bug. Set the timeout from the *caller's* budget, not the callee's hope: if your own SLO is "respond in 250 ms," you cannot afford to wait 5 s on payment — you time out at, say, 200 ms and degrade. Timeouts are the foundation every other pattern builds on; a circuit breaker with no underlying timeout still hangs.

### 1.2 Retries — with jitter and a budget

Retries recover *transient* failures (a dropped packet, a brief blip). Done naively, they *amplify* an outage into a catastrophe. Two non-negotiable disciplines:

**Jitter.** If a dependency blips and 10,000 callers all retry after exactly 1 second, they arrive *simultaneously* — a synchronized thundering herd that hammers the recovering dependency at the worst moment and knocks it back down, which triggers another synchronized retry, and so on. The fix is **randomized backoff (jitter)**: each caller waits a *random* duration, spreading the retries out so the dependency sees a smooth trickle instead of a wall. Exponential backoff *with full jitter* is the standard:

```
# Full jitter (the AWS-recommended form): random between 0 and the exponential cap.
sleep = random_between(0, min(cap, base * 2 ** attempt))
```

Plain exponential backoff *without* jitter still synchronizes (everyone doubles to the same value); full jitter is what actually de-synchronizes the herd. This is the single most important retry detail, and getting it wrong is the subject of this week's challenge.

**A retry budget.** Even jittered retries add load. If a backend is failing 50% of requests and every failure retries 3×, you've *quadrupled* the load on an already-struggling backend — the retry storm. The fix is a **retry budget**: cap retries at a small *fraction* of total traffic (e.g. "retries may be at most 10% of requests"). When failures spike, the budget is exhausted and further retries are suppressed — so retries help with *isolated* transients but *can't* amplify a *widespread* failure. This is the same `retry_budget` you met in Envoy in Week 7; here you implement it in the app. The principle: **retries are for the rare transient, not the systemic failure — and the budget is what enforces that distinction automatically.**

And: **only retry idempotent operations.** Retrying a non-idempotent "charge the card" can double-charge. This is exactly why Week 11's idempotency keys exist; retries and idempotency are two halves of one design.

### 1.3 The circuit breaker

When a dependency is *durably* failing (not a blip — actually down or melting), continuing to call it is pure waste: every call burns a timeout, holds a thread, and adds load to the thing that's already drowning. The **circuit breaker** stops the bleeding. It's a state machine wrapping the dependency call:

- **Closed** (normal): calls pass through. The breaker counts failures.
- **Open** (tripped): once failures cross a threshold, the breaker *opens* and **fails fast** — calls return an error *immediately* without even attempting the dependency. This (a) stops loading the failing dependency so it can recover, and (b) protects the caller from piling up on timeouts.
- **Half-open** (probing): after a cooldown, the breaker lets a *trickle* of probe calls through. If they succeed, it closes (recovered); if they fail, it re-opens (still down).

```
        failures exceed threshold
  ┌────────────────────────────────────┐
  ▼                                     │
[CLOSED] ──failures──▶ [OPEN] ──cooldown──▶ [HALF-OPEN] ──probe fails──┐
  ▲  (calls pass)     (fail fast)         (trickle probes)             │
  │                                            │ probe succeeds        │
  └────────────────────────────────────────────┘◀─────────────────────┘
```

The breaker turns "slow, cascading failure" into "fast, contained failure": instead of every cart request hanging 5 s on dead payment and exhausting cart's threads (taking cart down too), the breaker opens and cart *immediately* returns a degraded response ("checkout temporarily unavailable") — fast, and without dragging cart into payment's grave. **The circuit breaker is how one dependency's failure stays one dependency's failure** instead of becoming a system-wide cascade. The exercise wraps the payment dependency in `sony/gobreaker` and demonstrates it opening under failure and recovering through half-open.

The two tuning decisions that matter, and the trap in each:

- **When to trip (open).** Trip on a *failure ratio over a minimum volume*, not a raw count. "Open after 5 consecutive failures" is fragile — a low-traffic service hits 5 failures from noise, and a high-traffic one needs a *proportion*, not a count. The robust rule is "open when ≥ N requests *and* failure-ratio ≥ X%" (e.g. ≥ 20 requests and ≥ 50% failing), so you don't trip on a tiny sample and you do trip on a real problem. The minimum-volume guard is what stops a sleepy service from flapping open on two unlucky requests.
- **How long to stay open (cooldown) and how to probe.** Too short a cooldown and you re-probe a still-dead dependency constantly (adding load); too long and you stay degraded after it's recovered. And the half-open probe must be a *trickle* — a few requests — not the full firehose: a breaker that dumps *all* traffic onto the dependency the instant it half-opens just re-storms it and re-opens, a "half-open stampede." Let a handful of probes through; close only if they succeed. (This trickle is exactly the `MaxRequests` setting in the exercise's breaker, and the half-open-stampede is a stretch goal in the challenge.)

The breaker also composes with the timeout and retry from §1.1–1.2 as a *single* guarded call: timeout bounds each attempt, jittered+budgeted retry recovers a transient, and the breaker wraps the whole thing so a *durable* failure trips fast instead of retrying into the void. The order matters — the breaker is the outermost layer, because once it's open there's no point timing-out or retrying a call you're not going to make.

### 1.4 Bulkheads: isolate the blast radius

Named after a ship's watertight compartments: a breach floods one compartment, not the whole hull. A **bulkhead** isolates resource pools so one dependency's problem can't consume *all* your resources. Concretely: if cart calls payment, inventory, and shipping all from *one* shared thread/connection pool, and payment hangs, payment's hung calls eventually consume *every* thread in the shared pool — and now cart can't call inventory or shipping *either*, even though those are healthy. One sick dependency starved the calls to the healthy ones.

The bulkhead gives each dependency its *own* bounded pool: payment gets 20 connections, inventory gets 20, shipping gets 10. Now payment hanging exhausts only *payment's* 20 — cart can still reach inventory and shipping. The failure is *compartmentalized*. Bulkheads and circuit breakers compose: the bulkhead caps how much one dependency can hurt you, the breaker stops calling it once it's clearly failing. (The mesh gives you a coarse version of this for free — recall Envoy/Istio connection pools and outlier detection from Week 7/8 — but in-app bulkheads give finer, per-call-path control.)

In Go, a bulkhead is often just a bounded semaphore per dependency — a buffered channel sized to the pool:

```go
// One bounded "compartment" per dependency. Acquiring a slot is non-blocking-with-timeout,
// so a saturated dependency REJECTS fast (shed) instead of queueing unboundedly.
type Bulkhead struct{ slots chan struct{} }

func NewBulkhead(size int) *Bulkhead {
	return &Bulkhead{slots: make(chan struct{}, size)} // size = the pool cap for THIS dependency
}

func (b *Bulkhead) Do(ctx context.Context, call func() error) error {
	select {
	case b.slots <- struct{}{}: // got a slot in this dependency's compartment
		defer func() { <-b.slots }()
		return call()
	case <-ctx.Done(): // no slot available in time -> reject FAST; don't pile up
		return ErrBulkheadFull
	}
}

// Separate compartments: payment saturating cannot starve inventory or shipping.
var (
	paymentBH   = NewBulkhead(20)
	inventoryBH = NewBulkhead(20)
	shippingBH  = NewBulkhead(10)
)
```

The key line is the `ctx.Done()` branch: when payment's 20 slots are all taken (payment is hung), a new payment call *rejects immediately* rather than waiting for a slot — so the rejection is fast and bounded, and the calls to inventory/shipping (different compartments) are completely unaffected. That fast rejection is also load shedding (§1.5) at the dependency boundary: a full bulkhead *sheds* the marginal call to a saturated dependency instead of queueing it into the death spiral.

### 1.5 Backpressure, load shedding, and admission control

These three handle **overload** — more work arriving than you can do — and the key insight is that *queueing unboundedly is not a solution, it's a slower death.*

**Backpressure** is pushing back on the *producer* when you can't keep up, instead of accepting work into an unbounded queue. An unbounded queue under sustained overload grows without limit: latency climbs (every request waits behind the whole queue — Little's Law, §3.1), memory grows until OOM, and by the time you process a request the caller has already timed out — you do the work and throw away the answer. Backpressure (a bounded queue that *rejects* or *blocks* when full) converts "accept everything and get slower forever" into "accept what you can and tell the rest to back off" — which is a *better* experience for everyone, because a fast "try later" beats a 30-second wait for a response nobody's listening for anymore.

**Load shedding** is the server-side version: under overload, *deliberately drop* the marginal request to protect the latency of the rest. Dropping 10% of requests fast so 90% stay fast is almost always better than serving 100% slowly until everything times out. The senior framing: under overload, *some* requests will fail no matter what — load shedding lets you *choose which*, fast and cheaply, instead of having the failure mode chosen for you (everything collapses).

**Admission control** decides *at the door* whether to accept a request, often by **criticality**: under pressure, keep serving the checkout (revenue-critical) and shed the recommendations sidebar (nice-to-have). This requires tagging requests by criticality and is how you degrade *gracefully* — the system gets *narrower* under load, not *broken*. Graceful degradation is the goal: a checkout that works without recommendations beats a homepage that's fully featured and down.

> **The unifying principle of Part 1:** under stress, *fail small and fast on purpose* — bound the wait (timeout), recover transients safely (jittered, budgeted retry), stop calling the dead (circuit breaker), compartmentalize (bulkhead), and shed the marginal load (backpressure / shedding / admission control). Every one of these is choosing a *small, controlled* failure now to prevent a *large, uncontrolled* one later. The team that doesn't design these in doesn't avoid failure — it just gets the big uncontrolled version, which is the cascading outage Week 22's gameday will hand you if you skipped this.

### 1.6 Graceful degradation and criticality

The patterns above are mechanisms; **graceful degradation** is the *design intent* they serve: when a dependency fails, the system should get *narrower*, not *broken*. A checkout page that loses its recommendations carousel because the recommendation service is down is *degraded but working*; a checkout page that 500s because recommendations is down is *broken*. The difference is whether you treated the recommendation call as *critical* (its failure fails the page) or *optional* (its failure is absorbed, the page renders without it).

This requires tagging your dependencies and requests by **criticality**:

- **Critical path** — the calls without which the request is meaningless. For checkout: inventory reservation and payment. If these fail, the checkout genuinely fails (and you say so cleanly, via the circuit breaker's fast, clear error).
- **Best-effort** — the calls that enrich but aren't essential. Recommendations, recently-viewed, the loyalty-points preview. If these fail or are slow, you *drop them and serve the page anyway* — a timeout on a best-effort call returns an empty result, not an error.

The implementation is a discipline more than a tool: every cross-service call is classified, best-effort calls have *aggressive* timeouts and *swallow* failures (returning a sensible empty default), and critical calls get the full breaker/bulkhead/retry treatment. The admission-control angle (§1.5) is the same idea at the door: under overload, *shed* the best-effort work first to protect the critical path. A cart that can always take a payment, even when it can't show you recommendations, is a cart that degrades gracefully — and that's a *design choice* you make call by call, not an accident.

> **The connection to the SLO:** graceful degradation is *how you defend the SLO under partial failure.* If your availability SLI counts "served the checkout" (not "served every widget on the page"), then dropping the recommendations carousel keeps you *inside* the SLO while a dependency is down — the degradation is invisible to the metric that matters. This is why the SLI definition (Lecture 1 §1.4 — what counts as a good event) and the degradation design must be made *together*: you degrade exactly the things your SLI doesn't count, so partial failure doesn't burn budget. Design the SLI and the degradation as one decision.

---

## Part 2 — Autoscaling

### 2.1 HPA: scaling on CPU and custom metrics

The **Horizontal Pod Autoscaler** scales replica count to hit a target metric. The classic is CPU: "keep average CPU at 70%; add pods when it's higher, remove when lower."

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: { name: cart, namespace: shop }
spec:
  scaleTargetRef: { apiVersion: apps/v1, kind: Deployment, name: cart }
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: { type: Utilization, averageUtilization: 70 }
```

CPU-based HPA works for *CPU-bound, synchronous* services — a request-serving API whose load tracks CPU. It works *poorly* for the things it's most often misapplied to: an I/O-bound service (low CPU while saturated on connections) or — the big one — an **async consumer**, where CPU tells you nothing about whether you're keeping up with the *queue*.

### 2.2 KEDA: scaling an event-driven consumer on lag

For the Kafka consumer (Week 10), the right signal isn't CPU — it's **consumer lag**: how many messages are sitting in the topic *unprocessed*. Lag is the direct measure of "are we keeping up?" Lag growing = falling behind = scale up; lag near zero = caught up = scale down (even to zero). **KEDA** (Kubernetes Event-Driven Autoscaling) scales on exactly these external signals:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata: { name: order-consumer, namespace: shop }
spec:
  scaleTargetRef: { name: order-consumer }
  minReplicaCount: 1
  maxReplicaCount: 50
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: kafka:9092
        consumerGroup: order-consumers
        topic: order.placed.v1
        lagThreshold: "100"          # scale up to keep each replica's lag under ~100 messages
```

Why lag beats CPU for this workload: a consumer can be *100% behind* (lag exploding) while its CPU is *low* (it's I/O-waiting on a slow downstream, or simply under-provisioned in replicas) — CPU-based HPA would *not* scale it up, and the lag would grow unbounded until the topic's retention drops messages on the floor. Lag-based scaling responds to the thing that actually matters: the backlog. This is the syllabus's KEDA-on-Kafka-lag lab, and it's how an event-driven system stays caught up under a burst.

### 2.3 The autoscaling tradeoffs

Autoscaling is not free, and the failure modes are worth naming:

- **Cold start.** A new pod takes time to become ready (image pull, JVM warmup, sidecar ready — recall Week 8's sidecar startup). If your spike is faster than your pod-start time, scaling *up* is always *behind* the spike. Mitigations: keep a warm buffer (`minReplicas` above the floor), pre-pull images, scale on a *leading* indicator (lag rising) not a *lagging* one (latency already bad).
- **Flapping.** Naive scaling oscillates: scale up → metric drops → scale down → metric rises → scale up. The fix is **stabilization windows** (don't scale down for N minutes after scaling up) and hysteresis (different thresholds for up vs down).
- **Scaling to zero** (KEDA can) saves money for spiky/rare workloads but reintroduces cold-start latency on the first request — fine for a batch consumer, bad for a user-facing path. Match the policy to the workload.
- **Autoscaling is not a fix for a saturation problem.** If your system *gets slower* past a certain concurrency (the USL peak, §3.2), adding more pods past that point can make things *worse*, not better — more contention on the shared bottleneck (the database, the lock). Autoscaling assumes more replicas = more throughput, which stops being true at the saturation point. Which is why you must know where that point is — Part 3.

### 2.4 Autoscaling, load shedding, and the SLO together

A subtle point that ties autoscaling back to the budget. Autoscaling and load shedding are *complementary*, not alternatives, and you need both because they operate on different timescales:

- **Autoscaling** handles load that's *sustained* enough to provision for — it takes seconds-to-minutes to add capacity (cold start, §2.3), so it's the *slow* response to *durable* load growth.
- **Load shedding** handles the *instantaneous* overload that arrives *faster* than you can scale — the spike between "traffic jumped" and "new pods are ready." It's the *fast* response that protects your latency (and SLO) during the gap autoscaling can't cover.

The failure mode of relying on autoscaling alone: a sudden 3× spike arrives, autoscaling starts adding pods, but the new pods take 90 seconds to be ready — and during those 90 seconds the existing pods are overwhelmed, latency collapses, the SLO burns, and (worse) the overwhelmed pods may fail health checks and get killed, *reducing* capacity exactly when you need it. Load shedding covers that gap: while autoscaling catches up, you *shed* the marginal request so the requests you *do* serve stay fast and inside the SLO. The pairing is the senior pattern: **shed to survive the spike, scale to handle the new normal.** And both are governed by the same SLO — you shed to *protect* the error/latency budget, and you scale to stop *needing* to shed. An autoscaler with no load-shedding backstop has a latency cliff every time traffic outruns pod-start time.

---

## Part 3 — Capacity and tail latency

### 3.1 Little's Law: the identity behind everything

**Little's Law** is one equation that governs every queue:

```
L = λ × W

  L = average number of items in the system (concurrency / queue length)
  λ = arrival rate (requests per second)
  W = average time in the system (latency)
```

It's deceptively simple and *everywhere*:

- **Concurrency sizing.** If you serve λ = 1000 req/s at W = 0.1 s latency, you have L = 100 requests in flight on average — so you need at least 100 concurrent workers/connections. Under-provision and requests queue (raising W, which raises L further — a vicious cycle).
- **The overload spiral.** Hold throughput λ fixed; if latency W rises (a slow dependency), L rises — more requests pile up in flight, consuming more memory and connections, which slows things further, raising W again. This is the unbounded-queue death spiral from §1.5, and Little's Law is *why* it spirals.
- **Concurrency limits / load shedding.** Solving for the right concurrency cap is a Little's-Law calculation: pick the L that holds W (latency) at your SLO under expected λ, and *shed* beyond it. Netflix's adaptive concurrency limits are Little's Law turned into a control loop.

If you internalize one capacity equation, it's this one. Most overload incidents are Little's Law collecting its debt.

**A worked sizing.** Suppose cart must serve λ = 2000 req/s at the SLO, and each request's average time-in-system is W = 0.08 s (80 ms — your serving plus dependency waits). Then the average in-flight concurrency is L = λ × W = 2000 × 0.08 = **160 requests in flight**. That number drives real decisions: you need at least 160 worker slots (goroutines / threads / connection-pool entries) just to keep up *on average* — and because traffic is bursty, you provision *above* the average (say 2–3× headroom, ~400 slots) so a short burst doesn't immediately queue. Now flip it: if your connection pool to payment is capped at *100*, then by Little's Law you can only sustain λ = L / W = 100 / 0.08 = **1250 req/s** through that pool before requests start queueing for a connection — and queueing raises W, which (at fixed λ) raises required L, which exceeds the 100 you have, and you spiral. So the payment pool size *is* a throughput ceiling you can compute in advance, not discover in an incident. This is the calculation behind every "why did we fall over at 1250 req/s when each box looked only 40% busy" postmortem: the bottleneck wasn't CPU, it was a pool whose size capped concurrency below what the arrival rate demanded.

The same law sets your **load-shedding threshold**: pick the maximum in-flight L that still holds W at your latency SLO, and shed any request that would push you past it. That's not a guess — it's L = λ × W_slo solved for the L you can afford. Netflix's adaptive concurrency limits do exactly this as a live control loop: they continuously estimate the L that keeps latency at target and shed beyond it, so the system self-tunes its own concurrency cap to the current conditions. Little's Law is the theory; adaptive concurrency is the theory wearing a feedback loop.

### 3.2 The Universal Scalability Law: why more isn't always faster

Naively, doubling your workers doubles throughput. Reality: throughput rises, then *flattens*, then *falls*. The **Universal Scalability Law (USL)** models why:

```
            N
C(N) = ─────────────────────────
        1 + α(N−1) + βN(N−1)

  N = concurrency (workers/cores/nodes)
  α = contention: the serialized fraction (Amdahl's law — the part that can't parallelize)
  β = coherency: the cost of keeping N workers consistent (cross-talk, cache coherence, lock coordination)
```

Two penalties fight the linear gain:

- **Contention (α)** — the serialized part (a shared lock, a single-writer DB, a critical section). This is Amdahl's Law: even a tiny serial fraction caps your speedup. With contention alone, throughput *asymptotes* — adding workers gives diminishing returns toward a ceiling.
- **Coherency (β)** — the cost of keeping all N workers *agreeing* (cache-line bouncing, lock-coordination chatter, cross-node consistency). This is the killer: β is *quadratic* in N, so past a peak, adding workers makes throughput *go down* — they spend more time coordinating than working.

The practical payoff: **there is a peak concurrency past which more load makes your system slower, and it's almost never where you'd guess.** Below the peak, scale out. *At* the peak, you're maxed. *Past* it, scaling out *hurts* — the fix is to reduce α (kill the serialization — shard the lock, the single-writer DB) or β (reduce coordination), not to add workers. Knowing your USL peak tells you when autoscaling will help and when it's pouring fuel on a contention fire. The homework has you *find* this peak empirically by load-testing at rising concurrency and watching throughput crest and fall.

**A worked shape.** Suppose you measure throughput as you raise concurrency and fit the USL with α = 0.03 (3% serialized) and β = 0.0005 (a small coherency cost). The curve looks like this:

| Concurrency N | Throughput C(N) | What's happening |
|---:|---:|---|
| 1 | 1.00 | baseline |
| 10 | 7.5 | near-linear; contention barely felt |
| 30 | 15.4 | gains flattening (contention α biting) |
| 45 | 16.7 | **the peak** — adding workers stops helping |
| 60 | 16.3 | *past the peak*: throughput now *falling* |
| 100 | 13.9 | coherency β dominating; more workers = less work |

Two lessons jump out of that table. First, the peak is at N≈45 — *not* at "as many as you can afford"; past 45, every added worker makes the system *slower*, so an autoscaler that keeps adding pods past 45 is actively harming throughput while raising your bill. Second, a *tiny* β (0.0005) is what bends the curve back down — coherency cost is quadratic, so even a small coordination overhead eventually dominates. That's why "we added more replicas and it got *slower*" is a real and common phenomenon, and why the fix is never "more replicas" but "find and remove the α/β source" (shard the contended lock, partition the single-writer, cut the cross-node chatter). The USL turns "it doesn't scale" from a vibe into a diagnosis: *which* coefficient is killing you, and therefore *what* to fix.

### 3.3 Tail latency: why the mean lies

The average latency is a comforting lie. If 99% of requests take 50 ms and 1% take 5 s, your *mean* might be ~100 ms — which describes *no actual request* and hides that 1-in-100 users wait 5 seconds. Users don't experience the mean; they experience *their* request, and the slow ones are what they remember and complain about. So you measure the **tail**: p99, p99.9, p99.99 — "the slowest 1%, 0.1%, 0.01% of requests."

Two reasons the tail matters more than it seems:

- **Fan-out amplifies the tail.** If one user request fans out to 100 backend calls (a BFF gathering from many services — the cart's exact shape) and *waits for all of them*, the user's latency is the **max** of 100 samples. Even if each backend's p99 is good, the *probability that at least one of the 100 is in its slow tail* is high — so the user-facing p99 is driven by the backends' p99.9 or worse. **At fan-out scale, the tail is the typical experience.** This is why p99.9 and p99.99 aren't paranoia; they're what your fanned-out requests actually hit.
- **The tail predicts overload.** A rising p99.9 while p50 stays flat is the *early warning* of saturation (queues forming for the unlucky requests) before the median moves. The tail moves first.

Where the tail bites in *your* system specifically — worth naming because it's the cart's exact shape:

- **The BFF fan-out.** `bff` → `cart` + `inventory` + `payment` + `recommendations`, waiting on all → the user's latency is the *max* of those, so the user-facing p99 is driven by the *worst* backend's tail. One slow dependency tail = a slow user, even if every backend's median is fine.

- **The retry that hides in the tail.** A request that retried once (Lecture 2 §1.2) takes ~2× a normal request — retries don't change p50 but they *fatten the tail*, because the retried requests land out there. A rising p99 with a flat p50 is sometimes just retries doing their job; sometimes it's the early overload signal. Distinguishing them is why you watch *both* percentiles.

- **GC and lock pauses.** A stop-the-world GC or a contended lock stalls a *handful* of requests for tens of milliseconds — invisible in p50, glaring in p99.9. These are the classic "the tail is the GC" findings.

The practical instruction: dashboard p50 *and* p99 *and* p99.9 side by side, and treat a divergence between them (p50 flat, tail climbing) as the signal it almost always is — something is forming a queue or pausing for the unlucky few, and it's about to be everyone.

And one more rule that ties the tail back to the SLO: **your latency SLI should be set at a percentile, not the mean** (the anti-pattern from Lecture 1 §4.3). "99% of requests under 250 ms" is an SLI that tracks the tail your users feel; "average under 250 ms" is an SLI that lets the slow 1% hide behind the fast 99%. The whole reason last week made you align histogram buckets to your SLO threshold is so this percentile SLI is *measurable* — the tail-latency discipline here and the bucket discipline there are the same requirement viewed from two weeks.

### 3.4 Measuring the tail honestly: HDR histograms and coordinated omission

You cannot measure p99.9 from a mean and a standard deviation, and you cannot measure it from naive sampling — you need the *full distribution* recorded with enough resolution in the tail. **HDR (High Dynamic Range) histograms** record values across a huge range (microseconds to minutes) at constant relative precision, so the p99.99 is *measured*, not estimated. (This is the app-side cousin of last week's Prometheus-histogram-bucket lesson: resolution where the decision is made.)

The subtle, infamous trap is **coordinated omission** (Gil Tene's term): a naive load tester sends a request, *waits* for the response, then sends the next. When the server stalls for 2 s, the tester *doesn't send* the requests it would have sent during the stall — so the stall is recorded as *one* slow sample instead of the *thousands* of requests that would have piled up waiting. The result *systematically under-reports the tail* — your "p99.9 = 80 ms" is fiction because the test omitted exactly the bad samples. Correct load testing sends at a *fixed rate* regardless of response (or corrects for the omission), so the queue that forms during a stall is actually represented. `k6`, `wrk2`, and HdrHistogram-aware tools handle this; the naive loop-and-wait benchmark does not. When you measure the saturation point in the homework, sending at a fixed open-loop rate is what makes the tail numbers *true*.

---

## 3.5 The pattern-to-failure cheat sheet

Pin this. Each reliability pattern exists to prevent one specific failure, and reaching for the wrong one (or none) is how the failure lands:

- **Unbounded wait on a slow dependency** → **timeout**. The foundation; everything else assumes it.

- **A transient blip the user shouldn't see** → **retry** — but only *with jitter* (de-synchronize the herd) and *a budget* (don't amplify a widespread failure) and only on *idempotent* operations.

- **A durably-failing dependency dragging you down** → **circuit breaker** (fail fast, give it room, recover via half-open probes).

- **One sick dependency starving calls to the healthy ones** → **bulkhead** (isolated per-dependency pools).

- **More work arriving than you can do** → **backpressure** (bounded queue, reject when full), **load shedding** (drop the marginal request), **admission control** (shed by criticality — keep the critical path, drop the best-effort).

- **A dependency's failure that should narrow, not break, the product** → **graceful degradation** (best-effort calls swallow failures; the page renders without the carousel).

- **Sustained load growth** → **autoscaling** (HPA on CPU/custom, KEDA on the right signal like Kafka lag) — but capped at the **USL peak**, past which more replicas hurt.

- **An instantaneous spike faster than you can scale** → **load shedding** to survive the gap while autoscaling catches up.

The senior move is reading a failure and naming the missing pattern instantly: "payment is down and cart is hanging" → "no timeout + no breaker"; "we added pods and it got slower" → "past the USL peak, contention"; "a 30-second blip caused a 20-minute outage" → "retry storm: no jitter, no budget, no breaker." That diagnostic reflex — failure → missing pattern → fix — is what this whole lecture is training, and it's exactly what the challenge and Week 22's gameday test.

## 4. Recap

You should now be able to:

- Apply the resilience patterns and name the failure each prevents: timeouts (unbounded wait), jittered+budgeted retries (thundering herd / retry storm), circuit breaker (cascading failure from a dead dependency), bulkhead (one dependency starving the others), backpressure/load-shedding/admission-control (overload collapse).
- Configure HPA (CPU/custom) and KEDA (Kafka lag), and explain why an event-driven consumer scales on lag, not CPU — and the cold-start/flapping/scale-to-zero tradeoffs.
- Use Little's Law (L = λW) to size concurrency and explain the overload spiral, and the USL to find the saturation peak past which more concurrency reduces throughput.
- Measure tail latency honestly with HDR histograms, explain why the mean lies and why fan-out makes the tail the typical experience, and avoid coordinated omission in load testing.

The thread tying both lectures together: **reliability is a number you measure, defend, and protect.** Three verbs, one per layer:

- **Measure** — the SLO and its error budget (Lecture 1), watched by multi-window burn-rate alerts.
- **Defend** — the error-budget policy and the "100% is wrong" argument (Lecture 1), which keep the number honest against pressure.
- **Protect** — the resilience patterns and capacity limits (this lecture), which keep the running system inside the number under stress.

Neither layer is enough alone: an SLO with no resilience patterns is a target you'll miss the first time a dependency blips; resilience patterns with no SLO are effort you can't prioritize or defend. Together they're the difference between hoping a system is reliable and *engineering* it to be — measured, budgeted, defended, and protected. That is the whole of Phase 3's reliability discipline, and it's what Phase 4 (region failover, the gameday, the capstone) will spend three weeks trying to break.

Next: the exercises put all of this on your cart topology — the SLO + burn-rate alerts, the circuit breaker around payment, and KEDA on Kafka lag. Continue to [the exercises](../exercises/README.md).

---

## References

- *Google SRE Book — Addressing Cascading Failures*: <https://sre.google/sre-book/addressing-cascading-failures/>
- *Marc Brooker — Exponential Backoff And Jitter*: <https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/>
- *Martin Fowler — CircuitBreaker*: <https://martinfowler.com/bliki/CircuitBreaker.html>
- *Netflix — concurrency-limits*: <https://github.com/Netflix/concurrency-limits>
- *KEDA — Kafka scaler*: <https://keda.sh/docs/latest/scalers/apache-kafka/>
- *Neil Gunther — Universal Scalability Law*: <http://www.perfdynamics.com/Manifesto/USLscalability.html>
- *Gil Tene — How NOT to Measure Latency*: <https://www.youtube.com/watch?v=lJ8ydIuPFeU>
