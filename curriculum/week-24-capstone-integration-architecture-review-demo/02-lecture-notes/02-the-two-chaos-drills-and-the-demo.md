# Lecture 2 — The Two Chaos Drills and the 12-Minute Demo

> **Duration:** ~1 hour reading + the drills and the recording are the week's hands-on.
> **Outcome:** You can execute the two mandatory chaos drills (region failover and Kafka broker loss), measure the recovery and prove zero data loss / zero double-charge, write the blameless postmortem each requires, and record the 12-minute demo to the syllabus spec.

Lecture 1 was the review you defend in. This lecture is the *evidence* you defend with: the two chaos drills the capstone mandates, and the demo that shows the system working. These are not optional — the syllabus lists "two chaos-drill postmortems (mandatory)" and a "12-minute recorded demo" as required deliverables, each with a 60% floor. A region-failover you described but didn't run, or a broker-loss where you can't prove no-double-charge, fails the deliverable regardless of how polished the rest is.

The sentence to carry through:

> **A chaos drill is a measured experiment with a hypothesis, not a heroic firefight — you state what you expect to happen, break the thing on purpose, measure the gap between expectation and reality, and the postmortem is that gap written down.**

---

## Part 1 — Drill A: Region Failover Under Load

### 1.1 The hypothesis

The syllabus is precise: "Kill the primary region during a 1k-RPS load test. Document the impact, the recovery, and the lessons." So state the hypothesis before you break anything — this is the discipline that separates a chaos *experiment* from a chaos *accident*:

> **Hypothesis:** Under sustained 1k RPS, killing the primary region causes a brief elevation in error rate and latency as traffic shifts to the surviving region, recovery completes within our RTO target (say, 60 seconds), and **zero orders are lost or double-charged** — the cart converges, in-flight Temporal workflows resume on the surviving region's workers, and the Kafka backlog drains.

The hypothesis names the two things you'll measure: the **RTO** (how fast you recover) and the **data integrity** (zero loss, zero double-charge). A drill without a stated hypothesis is just breaking things; the hypothesis is what makes the result *mean* something.

### 1.2 The two failure domains, which fail differently

The insight that makes your postmortem read as senior: a region loss is *not one failure* — it's several failure domains failing at once, and they fail *differently*. Walk them:

- **The cart (CRDT, eventually consistent).** The surviving region keeps serving cart reads and writes from its own replica. The dead region's recent cart updates that hadn't yet anti-entropied are *not lost* — they're in the dead region's Postgres, which survives the region's compute loss if storage is replicated, and they converge when the region returns. During the outage, a customer's cart is served from the surviving region; on heal, the OR-set merge reconciles. **No data loss, brief divergence.** This is *why* you chose a CRDT for the cart: it degrades gracefully under exactly this failure.
- **Inventory (single-writer-per-SKU lease, strongly consistent).** A SKU whose lease-holder was in the dead region can't be written until the lease expires and is re-acquired by the surviving region. So inventory *writes* for those SKUs pause for the lease-expiry window (seconds), then resume. Reads continue. **No oversell, brief write-pause for affected SKUs.** This is *why* the lease has a bounded TTL — so a dead writer doesn't block a SKU forever.
- **Payment (Temporal workflow, exactly-once).** In-flight charge workflows whose workers were in the dead region are *not lost* — Temporal's history is durable, and workers in the surviving region pick up the workflows where they left off (deterministic replay, Week 12). A charge that was mid-flight resumes and completes exactly once. **No double-charge, no lost charge.** This is *why* you used Temporal instead of choreography for the saga.

The postmortem's strongest paragraph is the one that says "the region loss hit three failure domains, and here's how each behaved, by design" — because it shows you understood the *per-domain* consistency choices when you made them, not in hindsight.

### 1.3 Running the drill

Exercise 2 (`exercise-02-region-failover-drill.py`) drives this. The shape:

```bash
# 1. Start the 1k-RPS load against the BFF (both regions serving):
k6 run --vus 200 --duration 5m load/place-orders.js &

# 2. Establish steady state: error rate ~0, both regions healthy. Record t0.

# 3. Inject the fault: kill the primary region's workloads (chaos-mesh, or just
#    drain the cluster). This is the "region goes dark" moment. Record t_fault.
kubectl --context kind-region-primary delete pods --all -n shop --grace-period=0

# 4. Probe once per second: error rate, latency, which region serves. Record the
#    first SLO breach (t_impact) and the recovery (t_recover).

# 5. Measure: RTO = t_recover - t_fault. Then verify integrity:
#    - no order lost (count orders in == orders processed, across both regions)
#    - no double-charge (each idempotency key charged exactly once)
#    - the Kafka backlog drained, the DLQ stayed empty

# 6. Reverse the fault (bring the region back), confirm the cart converges on heal.
```

The number you report is the **measured RTO** and the **integrity result**, not an estimate. "Recovery was 47 seconds, zero orders lost, zero double-charges, DLQ stayed at zero, cart converged on heal in 12 seconds" is a drill result. "It should fail over in about a minute" is not.

### 1.4 The postmortem for Drill A

The blameless postmortem (Google SRE format) has a fixed structure, and you fill it from the *measured* drill:

- **Summary.** One paragraph: what was broken, the impact, the recovery time.
- **Impact.** Who/what was affected and for how long: "During the 47-second failover, the user-visible error rate peaked at 4% (requests in flight to the dead region), then recovered. No orders were lost or double-charged."
- **Timeline.** Timestamped: t0 steady state, t_fault region killed, t_impact first error, t_recover SLO restored, t_heal cart converged. Times in seconds.
- **Root cause.** *Why* the impact happened — not "the region died" (that's the trigger), but "the surviving region took the lease-expiry window to re-acquire writes for SKUs whose writer was in the dead region, which paused those writes for ~10 seconds."
- **What went well / what didn't.** Honest. "The CRDT cart degraded perfectly; the inventory write-pause was longer than expected because the lease TTL was conservative."
- **Action items.** Each an owner and a fix: "Tune the lease TTL down from 30s to 10s to shorten the write-pause (owner: me). Add a burn-rate alert specifically on inventory write-latency during failover (owner: me)."

> **Blameless means you fix the *system*, not blame a person.** There's no person to blame in a solo capstone, but the discipline still matters: the postmortem asks "what about the system let this happen and how do we change the system," not "who messed up." That framing is what makes a postmortem a *learning* artifact instead of a punishment, and it's the framing a hiring panel looks for when they ask about your on-call experience.

---

### 1.5 A worked postmortem for Drill A

To make the format concrete, here is a complete (abbreviated) Drill A postmortem, the kind Exercise 2 produces and you polish. Read it as the target shape:

```
# Postmortem — Drill A: Region Failover Under Load

## Summary
On 2026-06-10 we killed the primary region (us-east) during a sustained 1k-RPS
load test. Traffic failed over to us-west in 47 seconds (RTO target: 60s). Zero
orders were lost and zero were double-charged. The cart converged on heal in 12s.
Overall: PASS.

## Impact
- Duration: 47s of elevated error rate (peak 11%, requests in flight to the dead
  region) before the LB shifted traffic and us-west warmed.
- Orders: 47,200 sent during the drill; 46,891 succeeded; 309 failed (in-flight to
  the dead region at the instant of failure — clients retried successfully).
- Data integrity: zero double-charges (verified: HAVING COUNT(*) > 1 returned 0 rows),
  zero lost orders (orders_ok == distinct charged keys), DLQ depth unchanged at 0.

## Timeline (UTC)
- 14:02:06  steady state established (t0): both regions healthy, error rate ~0.1%.
- 14:03:06  FAULT: us-east workloads killed (region "goes dark").
- 14:03:09  IMPACT: error rate crosses 5% as in-flight requests to us-east fail.
- 14:03:21  LB health-check marks us-east backend unhealthy; traffic shifts to us-west.
- 14:03:53  RECOVERED: error rate back under 5% (us-west warm). RTO = 47s.
- 14:08:30  us-east restored; cart anti-entropy reconciles divergent writes.
- 14:08:42  cart CONVERGED across both regions (12s after region return).

## Root cause
The 47-second RTO is dominated by two factors: the LB health-check interval (we shift
traffic only after 3 failed 5s checks = ~15s) and the us-west cold-start for the
under-provisioned services (~20s to scale to handle the full load alone). Neither is
a bug; both are tunable. The deeper root cause (five whys): we had never drilled
failover, so the health-check interval was a default nobody had matched to the RTO.

## What went well / what didn't
- Well: the CRDT cart degraded exactly as designed — us-west served throughout, and
  the divergent partition-window writes converged on heal with zero loss.
- Well: in-flight Temporal charge workflows resumed on us-west workers and completed
  exactly once (no double-charge, no lost charge).
- Didn't: the inventory write-pause for SKUs whose lease-holder was in us-east lasted
  ~18s (the lease TTL), longer than necessary for the RTO target.

## Action items
- [ ] [me] Lower the LB health-check interval to shift traffic faster (target RTO < 30s).
- [ ] [me] Tune the inventory lease TTL down from 30s to 12s to shorten the write-pause.
- [ ] [me] Add a burn-rate alert on inventory write-latency specifically during failover.
- [ ] [me] Add failover to the regular drill cadence so RTO regressions are caught.
```

Study what makes it strong: the summary leads with the *measured* RTO and the *integrity result*; the timeline is timestamped to the second; the root cause goes past "the region died" to the systemic gap; the "what went well" section honestly credits the design choices that worked (the CRDT, Temporal) *and* names the one that underperformed (the lease TTL); and every action item is owned and concrete. That's a postmortem a hiring panel reads as "this person has run incidents." Yours, from the real drill, will look just like it — with your numbers.

## Part 2 — Drill B: Kafka Broker Loss, No Double-Process

### 2.1 The hypothesis

The syllabus again: "Lose a Kafka broker mid-traffic. Demonstrate that the exactly-once consumers do not double-process, and that the outbox guarantees integrity." The hypothesis:

> **Hypothesis:** Losing one Kafka broker mid-traffic causes producers to retry to the surviving in-sync replicas (a brief produce-latency blip) and causes consumers to rebalance, possibly re-delivering some in-flight messages — but because every consumer is idempotent (idempotency key + the outbox-backed dedup), **no order is processed twice and no customer is double-charged.** The DLQ stays empty.

This drill targets the single most important correctness property of the event spine: **exactly-once *effect* despite at-least-once *delivery*.** Kafka gives you at-least-once; a broker loss and the consumer rebalance it triggers is exactly the moment a message gets re-delivered. If your idempotency is wrong, *this* is when the double-charge happens. The drill proves it doesn't.

### 2.2 Why a broker loss triggers redelivery

The mechanism, so your postmortem can name it precisely (not "Kafka is flaky"):

- Kafka replicates each partition across brokers; one is the leader, the others are in-sync replicas (ISR). When the leader broker dies, a surviving ISR is elected the new leader.
- Producers that were mid-publish to the dead leader retry to the new leader — a brief latency blip, no data loss (the message was either acked by the ISR or retried).
- Consumers in a group **rebalance** when the cluster topology changes. A consumer that had pulled a batch but not yet committed its offset when the rebalance happened will, after rebalance, **re-pull that batch** — at-least-once delivery in action. *This is the redelivery.*
- Your idempotent consumer (Week 11): on re-pulling a message it already processed, it checks the idempotency key against the dedup store (the outbox / a unique constraint) and **skips the duplicate effect**. The message is "processed" again, but the *effect* (the charge, the order-placed) happens exactly once.

The outbox closes the last gap: the consumer writes its effect *and* records the processed key in the *same transaction*, so it can't process the effect and then crash before recording the key (which would cause a re-process). The outbox makes "I did the work" and "I recorded that I did the work" atomic.

### 2.3 Running the drill

Exercise 3 (`exercise-03-broker-loss-no-double-process.py`) drives this. The shape:

```bash
# 1. Start a steady stream of orders, each with a unique idempotency key:
k6 run --vus 50 --duration 3m load/place-orders.js &

# 2. Record the set of order IDs sent and the charge count per key (should be 1 each).

# 3. Mid-stream, kill one Kafka broker (the leader for some partitions):
kubectl delete pod kafka-1 -n kafka --grace-period=0
#    -> partition leadership fails over to an ISR; consumers rebalance and
#       re-deliver in-flight messages.

# 4. Let the stream finish and the consumers drain. Then ASSERT THE INVARIANT:
#    for every idempotency key, the payment was charged EXACTLY ONCE.
#    - count charges per idempotency_key in the payment DB -> all == 1
#    - the DLQ depth is 0
#    - orders sent == orders placed (no loss)

# 5. The integrity proof: if any key has charge_count > 1, the drill FAILS — the
#    idempotency is broken. Zero double-charges is the pass condition.
```

The pass condition is binary and measured: **every idempotency key charged exactly once.** Not "looks fine" — a SQL count grouped by idempotency key, all rows equal to 1. That query *is* the proof, and it goes in the postmortem.

### 2.4 The postmortem for Drill B

Same SRE structure, with the integrity proof front and center:

- **Summary.** "Killed Kafka broker kafka-1 mid-traffic at 1k orders/min. Producers retried to the new ISR leader (produce p99 blipped to 180ms for ~8s), consumers rebalanced and re-delivered 23 in-flight messages, and the idempotent consumers correctly skipped all 23 duplicate effects. Zero double-charges, zero data loss, DLQ empty."
- **Impact.** The produce-latency blip, the count of re-delivered messages, and — the headline — zero double-charges.
- **Timeline.** t0 steady, t_kill broker killed, t_rebalance consumer rebalance, t_recover produce latency normal.
- **Root cause.** "The redelivery is *expected* — it's at-least-once delivery doing its job after a rebalance. The reason it caused no double-charge is the idempotency-key dedup backed by the outbox, which made the duplicate effects no-ops."
- **The proof.** Paste the `SELECT idempotency_key, COUNT(*) FROM charges GROUP BY idempotency_key HAVING COUNT(*) > 1` returning **zero rows.** That empty result set is the deliverable.
- **Action items.** Even on a clean pass: "Add a metric counting deduplicated (skipped-duplicate) messages so we can *see* the redelivery happening in production, not just in the drill."

> **The thing that impresses a reviewer about Drill B is the empty result set.** Anyone can claim exactly-once; you *queried for the violation and found none*, under the exact failure that would produce it. That's the difference between asserting a property and proving it — the same difference the property tests drew last week, now at the system level.

---

## Part 2b — The "five whys" without the witch-hunt

Both postmortems reach a **root cause**, and the standard tool is the "five whys" — asking "why" repeatedly until you hit something systemic rather than proximate. The technique is useful and frequently abused, so use it deliberately.

Done well, it drives past the symptom:

> - The inventory write paused for 18 seconds during failover. **Why?**
> - Because the surviving region couldn't write the SKU until the dead region's lease expired. **Why did that take 18 seconds?**
> - Because the lease TTL is 30 seconds and ~18 had elapsed. **Why is the TTL 30 seconds?**
> - Because we copied a conservative default and never tuned it for the failover RTO target. **Why didn't we tune it?**
> - Because we never ran a failover drill until this week — there was no signal telling us the TTL was the failover bottleneck.

The fifth "why" lands on something *systemic* — "we didn't drill failover, so we never saw the bottleneck" — which produces a real action item ("drill failover regularly; treat the lease TTL as a failover parameter") rather than a proximate band-aid ("lower the TTL"). Both are worth doing, but the systemic one prevents the *next* unmeasured-parameter surprise.

The abuse to avoid: the "five whys" must never bottom out at a *person* ("why did the engineer set the TTL wrong"). That's the witch-hunt version, and it's worse than useless — it teaches people to hide problems instead of surfacing them, which is the opposite of what a postmortem is for. In a solo capstone there's no one else to blame, but the discipline still matters: every "why" points at the *system* and how to change it, never at a name. The blameless framing isn't politeness; it's what keeps the postmortem honest enough to be useful. A team that blames people in postmortems gets fewer postmortems and more hidden incidents; a team that blames the system gets the failure modes on the table where they can be fixed.

> **The reviewer reads the root-cause section to learn whether you think in systems or in symptoms.** "The region died" is a trigger, not a root cause. "We had no failover drill, so the lease-TTL-as-failover-bottleneck was invisible until now" is a root cause — it names the systemic gap and implies the fix. The difference is the entire signal of the section.

## Part 2c — The runbook that the drills feed

The two drills don't just produce postmortems — they produce *runbook entries*. The capstone's 6-page runbook covers five named failure modes, and two of them (region loss, broker loss) are exactly the drills you ran, which means you write those two entries from *measured experience* rather than speculation. That's the strongest possible runbook entry: "here's what happens, because I made it happen and watched."

A runbook entry has a fixed shape, and the load-bearing part is the **first diagnostic line** — the one a reviewer reads to judge whether your observability is real:

```
FAILURE MODE: Region loss
  SYMPTOM (what pages you): order-slo-fast-burn fires; error rate spikes briefly.
  FIRST LOOK: Open the order SLO dashboard. Is the whole region's backend unhealthy?
              Check the cluster status, not the application logs.
  IS IT A REGION EVENT?
    - Yes: failover is automatic (the LB/routed control plane shifts traffic).
           Confirm the surviving region is serving (trace one order), then WAIT.
           There is nothing to mitigate; the page is expected. Annotate the incident.
    - No: it's a service-level problem; go to the relevant service's runbook entry.
  RECOVERY: when the region returns, confirm the cart CONVERGES on heal (the OR-set
            merge reconciles divergent writes) and the Kafka backlog drained.
  DATA-LOSS WINDOW: zero (proven in Drill A) - reads interrupted, writes buffered.
```

Notice the first look is a *dashboard*, not "grep the logs." The whole point of the Week 17 observability work was to make "what's wrong" answerable in one glance; the runbook is where that pays off. An entry whose first step is "tail the logs and look around" tells a reviewer your observability is decorative — you instrumented the system but can't *use* the instrumentation to triage. An entry whose first step is "open this dashboard, which shows you which of the four signals is degraded" tells them you can operate it. The five entries — region loss, broker loss, Postgres primary failure, Temporal worker outage, certificate expiry — each get this shape, and the first two come straight from the drills.

The other three you reason through from the course material: **Postgres primary failure** is the Week 13 logical-replica promotion (promote a replica, repoint Debezium, name the small data-loss window of un-replicated commits); **Temporal worker outage** is the Week 12 durability property (workflows are durable history, workers resume, nothing's lost — the symptom is workflow latency, not data loss); **certificate expiry** is the Week 8/21 mesh-CA / SPIRE rotation (the symptom is mTLS handshake failures, the cause is istiod or SPIRE down longer than the cert lifetime, the fix is restoring the CA before the certs age out). Writing these five well is what turns "I built a system" into "I can hand someone the on-call pager for it."

## Part 3 — The 12-Minute Demo

### 3.1 The spec

The syllabus is exact about the demo's content: "a 12-minute recorded demo video covering: architecture walkthrough, a live deploy with weighted canary, a Grafana dashboard tour ending in a trace-to-log jump, and the cart-CRDT convergence demo across a simulated partition." So the demo is not freeform — it's four named segments, and you should time-box each:

1. **Architecture walkthrough (~3 min).** The C4 container diagram on screen. Walk the order through the system at the shape level — the same walk as the review's diagram-walk, condensed. Not every detail; the *flow*.
2. **Live deploy with weighted canary (~3 min).** Deploy a v2 of a service, shift the canary 10/90, show the `istioctl proxy-config routes` weights landing on the real proxy, then induce an SLO breach (a broken v2) and show the **automatic rollback** to weight 0. This is the Week 8 progressive-delivery story, live.
3. **Grafana dashboard tour ending in a trace-to-log jump (~3 min).** The RED dashboards, then the move: click an exemplar on a latency spike → the trace → a span → its logs. Metrics to traces to logs, correlated, in clicks. (Lecture 1 §1.5b.)
4. **Cart-CRDT convergence across a partition (~3 min).** Partition the two regions (chaos-mesh network-partition), make divergent cart writes in each, heal the partition, and show the carts *converge* to the same set. This is the Week 20 demo, and it's the visible proof of the eventual-consistency choice.

### 3.2 Recording it well

A few disciplines that make the recording a thirty-minute session instead of a thirty-take ordeal:

- **Rehearse the live parts three times** before recording. The canary deploy and the partition-heal involve a live system that can misbehave; rehearse until each is under three minutes of clicking.
- **Have a warm system.** Bring everything up and let it settle before you hit record. A cold start mid-demo is the most common avoidable disaster.
- **Narrate the mechanism, not the clicks.** "I'm clicking here" is dead air. "I'm shifting 10% of cart traffic to v2 — watch the proxy route weights update without a pod restart" is a demo. The narration is what reads as mastery.
- **Have a fallback recording of each live segment.** Networks fail during demos. A pre-recorded clip of a successful canary rollback you can cut to if the live one hiccups is completely acceptable and far better than freezing on camera.
- **Edit to time.** Twelve minutes is a constraint, not a suggestion — it forces you to show the *load-bearing* moments and cut the setup. A reviewer's attention is the scarce resource; respect it.

### 3.2b A narration script for the canary segment

The segments live or die on the narration. Here is the canary segment, scripted the way you'd actually say it, so you can hear what "narrate the mechanism" means in practice:

> "I'm going to deploy v2 of the cart service with a weighted canary. First I apply the v2 deployment — it's labeled `version: v2`, and my DestinationRule already has a v2 subset pointing at that label. Now I shift 10% of cart traffic to it by editing the VirtualService weights. Watch — I'm not restarting any pods; this is a config push. Let me confirm it landed on the *actual* proxy, not just the CRD: `istioctl proxy-config routes` shows the weighted clusters, 90 to v1, 10 to v2. Now here's the important part: this v2 is deliberately broken — it returns 5xx on 20% of requests. Watch the Grafana success-rate panel for the v2 subset… there, it's dropping below my 99% SLO. And because Flagger is watching that exact metric, it's now rolling the canary back automatically — there, the weight goes to 0, v2 gets no traffic, and the users on v1 never saw the broken version. That's progressive delivery: a bad deploy caught by the SLO and rolled back without a human, in seconds, with no redeploy."

Notice the moves: every action names *what it is and why* ("a config push, no restarts"), the proof is on the *real proxy* ("not just the CRD"), the failure is *induced deliberately* (so it's reliable on camera), and the payoff is the *automatic* rollback tied to the *SLO metric*. That's the Week 8 progressive-delivery story compressed into ninety seconds of narrated, observable action. A reviewer watching this sees that you didn't just configure a canary — you understand that the engineering is in the metric that drives the rollback, not the weight that does the shift.

### 3.2c The convergence segment: showing the invisible

The cart-CRDT convergence segment is the hardest to demo well, because convergence is an *absence* — the absence of disagreement — and showing an absence on camera takes care. The script:

> "I have the same customer's cart in both regions. I'm going to partition them — here's the chaos-mesh network-partition, the two regions can no longer talk. Now I add item A to the cart in us-east and item B in us-west, at the same time. The carts now *disagree*: us-east has A, us-west has B. That's expected — they're partitioned, eventual consistency means they can diverge temporarily. Now I heal the partition… and watch both carts. The OR-set anti-entropy runs, the merges exchange, and — there — both regions now show *both* A and B. They converged, and crucially, *neither add was lost*. That's why the cart is a CRDT: a partition can't lose a customer's add, it can only delay convergence. And I proved the merge is commutative, associative, and idempotent with property tests last week, so this convergence isn't luck on this one partition — it holds for any interleaving."

The discipline is to *show the divergence first* (so the convergence means something) and to *name the property-test backing* (so the reviewer knows it's not a one-off). Convergence shown without the prior divergence looks like nothing happened; convergence shown after a visible disagreement is the whole eventual-consistency story made tangible. This is the segment that proves the single deepest choice in the whole architecture — that the cart trades strong consistency for partition-survival — actually works.

### 3.3 What the demo proves that the document can't

The architecture document defends the *design*; the demo proves the *system runs*. The four segments are chosen to demonstrate the four properties a document can only *claim*: that progressive delivery actually rolls back (the canary), that the system is actually observable (the trace-to-log jump), that the cart actually converges (the partition-heal), and that the whole thing actually flows (the architecture walk). A reviewer who reads a great document but never sees the system run is right to be skeptical; the demo is what turns "this is a nice design" into "this is a system that works." That's why it's a required deliverable and not a nice-to-have — it's the proof that the document isn't fiction.

### 3.4 The demo as a portfolio artifact

The 12-minute recording outlives the defense. Long after Friday, it's the thing a hiring manager watches before a phone screen and the thing you link from your portfolio README. So record it as a portfolio artifact, not just a course requirement: clean audio, a readable terminal font, no dead air, and a narration that assumes the viewer is a skeptical senior engineer who'll close the tab the moment it gets boring. The four segments are chosen precisely because they're the four most impressive things a distributed system can show — automatic rollback, end-to-end observability, CRDT convergence, and a clean architecture — so a tight 12-minute version of them is a genuinely strong portfolio piece. Many graduates report the demo video does more for their job search than the repo itself, because a hiring manager can watch a system *work* in twelve minutes but won't read ten thousand lines of YAML. Treat the recording as the front door to everything you built.

The discipline that makes the recording good is the same as the live defense: rehearse, warm the system, narrate the mechanism, and have a fallback for each live segment. The difference is that the recording is *edited* — you can cut the dead air, retake a fumbled narration, and trim to time — which means the bar is higher, not lower. A live demo gets grace for a hiccup; a recorded one doesn't, because you had every chance to fix it. Spend the editing time; it's the most-watched twelve minutes of work you'll produce in the course.

---

## Part 4 — Running the drills safely (chaos discipline)

A word on doing this without turning the drill into the incident. Week 22 taught the four principles of chaos engineering; the capstone drills apply them, and the discipline is what separates a controlled experiment from a self-inflicted outage:

- **State the hypothesis first.** You've seen this twice now — it's the principle that makes a drill an *experiment*. Without it you're just breaking things and reacting.
- **Define steady state and the abort condition.** Before you inject the fault, know what "healthy" looks like (the steady-state metrics) and the line past which you *stop the drill* — if the system isn't recovering by some bound, you abort and reverse the fault rather than letting it cascade. Both drill drivers reverse the fault on Ctrl-C for exactly this reason.
- **Blast-radius control.** These drills run against your *capstone* clusters, not a shared environment. In a real org you'd scope the blast radius (a fraction of traffic, a single cell) so a drill that goes wrong doesn't take down production. The capstone's blast radius is "your own two clusters," which is the right scope to learn on.
- **Time-box and announce.** A drill has a start and an end. The most embarrassing failure mode is a drill nobody knew was running, paging the team about "elevated latency" that turns out to be the fault you injected. Announce it, time-box it, and have the reversal ready — the same discipline as Week 8's "delete the fault injection when you're done."

The capstone drills are the safe, rehearsed version of what Week 22's gameday threw at you for real: you control the fault, you know the hypothesis, you have the abort condition and the reversal, and you measure the result. That's chaos engineering as a *discipline* — curiosity with guardrails — rather than chaos as a synonym for recklessness. Done this way, the drills are the strongest evidence in your defense; done carelessly, the first drill is the defense's first incident.

## Part 4b — Why these two drills and not others

The syllabus mandates *these two* drills specifically, and it's worth understanding why they were chosen out of all the failures you could inject — because the choice itself is a lesson in what to test.

**Drill A (region failover)** tests the *availability* story of the multi-region active-active design. It's the drill that proves the entire Phase 4 thesis — that two regions give you survival of a region loss — is real and not aspirational. It exercises every failure-domain-isolation choice at once: the CRDT's partition tolerance, the lease's bounded TTL, Temporal's durable replay. If any of those choices was wrong, the failover drill exposes it. It's the single most comprehensive availability test you can run, which is why it's mandatory.

**Drill B (broker loss)** tests the *correctness* story of the event spine. It's the drill that proves the exactly-once design — outbox + idempotency keys — actually delivers exactly-once under the failure that would break it. A broker loss is chosen specifically because the consumer rebalance it triggers is the *exact* moment a redelivery happens, which is the *exact* moment a non-idempotent consumer double-processes. No other common failure targets the idempotency machinery so precisely. If your exactly-once is broken, this is the drill that finds it.

Together they cover the two properties a marketplace backbone must have and that are hardest to get right in a distributed system: it must *stay up* when a region dies (Drill A), and it must *not corrupt money* when the event spine hiccups (Drill B). A region-failover that's slow is an availability bug; a double-charge under broker loss is a correctness bug; and the capstone makes you prove neither exists, under the exact failures that would cause them. That's why these two and not, say, a CPU-stress drill — they target the design's two load-bearing claims, and a load-bearing claim you haven't drilled is a claim you're only hoping is true.

## Summary

The two chaos drills are mandatory, measured experiments with stated hypotheses. **Drill A (region failover)** kills the primary region under 1k RPS and proves a bounded RTO with zero data loss, walking the three failure domains (CRDT cart, leased inventory, Temporal payment) that fail differently by design. **Drill B (broker loss)** kills a Kafka broker mid-traffic and proves — with an empty `HAVING COUNT(*) > 1` result set — that the idempotent, outbox-backed consumers process exactly once despite the redelivery a rebalance causes. Each drill's blameless postmortem is the gap between hypothesis and measured reality, with timestamped timelines and owned action items. The **12-minute demo** is four timed segments — architecture walk, canary with automatic rollback, the trace-to-log jump, and the cart-convergence-across-a-partition — that prove the four properties the document can only claim. Rehearse the live parts; bring a warm system; narrate the mechanism.

A closing thought before the exercises. These two drills and this demo are the moment the whole course's "prove it, don't assert it" discipline pays off at the system level. All term you made the machinery prove things — `istioctl` proving mTLS, the property test proving convergence, `can-i-deploy` proving the boundary held. The drills are that same discipline applied to the system's two load-bearing claims: the empty double-charge query *proves* exactly-once under the failure that would break it, and the measured RTO *proves* the failover is real and not aspirational. The demo, in turn, proves the four properties a document can only claim. By the time you've run both drills and recorded the demo, you don't *believe* your system is correct and available — you've *measured* that it is, under the exact failures and shown live on camera. That shift, from belief to evidence, is the entire difference between an engineer who built a distributed system and one who can stand behind it. Go produce the evidence.

Next: the exercises walk you through tracing one order, running Drill A, and running Drill B. Continue to [the exercises](../03-exercises/00-overview.md).

---

## References

- *Google SRE — Postmortem culture*: <https://sre.google/sre-book/postmortem-culture/>
- *Google SRE — Example postmortem*: <https://sre.google/sre-book/example-postmortem/>
- *Principles of Chaos Engineering*: <https://principlesofchaos.org/>
- *chaos-mesh docs*: <https://chaos-mesh.org/docs/>
- *Kafka — replication and ISR*: <https://kafka.apache.org/documentation/#replication>
- *Temporal — workflow recovery / deterministic replay*: <https://docs.temporal.io/workflows>
- *Mermaid C4 diagrams*: <https://mermaid.js.org/syntax/c4.html>
- *PagerDuty postmortem guide*: <https://postmortems.pagerduty.com/>
- *OBS Studio (demo recording)*: <https://obsproject.com/>

---

*One last note as you head into the drills: the two postmortems and the demo are not the end of the work — they're the evidence the work was real. Treat them with the care you'd give a production incident review and a conference talk, because that is exactly what they are: the artifacts that will represent your judgment to people who weren't in the room. The system you built matters; the evidence that it works, and that you understand why, is what gets remembered.*
