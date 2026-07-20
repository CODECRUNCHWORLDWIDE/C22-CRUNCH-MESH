# Mini-Project — `cart-multiregion`: The Cart Topology Across Two Regions, with a Measured Failover

> Put the cart system in two regions: `cart`/`inventory` deployed in `region-a` and `region-b`, a Postgres primary in A replicating logically to B, read-local/write-primary routing via a health-checked geo-router, and — the part that makes you dangerous — a **measured, rehearsed failover** with an RTO/RPO budget you wrote down and *hit*, plus a runbook for the region-loss failure mode.

This is the artifact that turns "we could go multi-region" into "we have a multi-region failover, here are its numbers, and here is the runbook." After this week, multi-region is a *defensible posture*: every region serves reads locally, writes go to one primary, and when that primary's region dies you fail over in a measured time, losing a measured (and budgeted) amount of data — and you can prove it because you ran the drill.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `cart-multiregion` is the two-region substrate for your **capstone Polyglot Marketplace Backbone** ("two-region active-active deployment"). Week 20 takes this exact topology and makes the cart *genuinely active-active* with a CRDT — so build the read-local/write-primary version cleanly, with the failover measured, because next week replaces the single-primary cart with a conflict-free one and you'll want this as the baseline you compare against. Week 22's gameday runs **Drill A — Region failover** on precisely this: a 1k-RPS load test with the primary region killed, graded by the postmortem. The failover you measure here is the rehearsal for that drill.

---

## What you will build

A repo `cart-multiregion` with five deliverables:

1. **`regions/`** — the two-region topology as reproducible manifests/scripts: `region-a` (primary) and `region-b` (replica), each running `cart`/`inventory` and a Postgres, with the cross-region replication (and a simulated cross-region latency) configured the same way every time.
2. **`routing/`** — the geo-routing layer (the Exercise-2 health-checked CoreDNS, or equivalent): `read.shop.internal` resolves to the local region's replica, `write.shop.internal` resolves to the primary region with a low TTL, and a health check that flips the write record to B on A's failure.
3. **`failover/`** — the **measured failover**: the promote-and-fence procedure (fence *before* promote — the Challenge's lesson) and the Exercise-3 driver that produces your **RTO and RPO numbers under load**.
4. **`budget.md`** — your declared **RTO/RPO budget** ("RTO < 60s, RPO < 5s") with the *measured* numbers from your drill next to the targets, and a one-paragraph justification of why those targets fit the cart workload.
5. **`runbook.md`** — the **region-loss runbook**: the named steps (detect, decide, fence, promote, reroute, verify), the split-brain guard, the fail-back procedure (re-sync A as a replica first), and the "unreachable ≠ dead" rule.

By the end you have a public repo of two-region manifests + a routing layer + a fenced failover procedure + a measured RTO/RPO budget + a runbook that any on-call engineer could execute.

---

## Why this and not "just deploy to two regions"

You could `kubectl apply` your services into a second cluster and call it "multi-region." Don't stop there — that's the gap this whole week is about. A defensible multi-region posture gives you:

- **A failover you measured, not one you hope for.** The default "we have a standby" is a wish; this project's drill produces a real RTO (recovery window under load) and a real RPO (lost writes = lag at failure). The difference is a DR plan that works versus one that discovers at 3 a.m. that the standby was never replicating.
- **Read-local/write-primary that respects data gravity**, not "everything everywhere" — reads are local and fast, writes go to one primary, one source of truth, no conflict to resolve (that's Week 20's job).
- **A fenced failover**, so a region that's *unreachable* (not dead) can't produce two primaries and split-brain (the Challenge's whole point).
- **A budget and a runbook**, so the failover is a documented, rehearsed procedure an on-call can run — which is exactly what Week 22's gameday grades.

The cloud providers' managed multi-region databases will eventually do much of this for you. Building it by hand first — promote, fence, reroute, measure — is what lets you read and trust what they do, and what lets you defend the RTO/RPO numbers when someone asks "are you sure?"

---

## Repo layout

```
cart-multiregion/
├── README.md
├── regions/
│   ├── region-a/                 # primary: cart, inventory, postgres (publication)
│   │   └── *.yaml
│   ├── region-b/                 # replica: cart, inventory, postgres (subscription)
│   │   └── *.yaml
│   └── setup.sh                  # creates both kind clusters, applies both regions, wires replication
├── routing/
│   ├── geo-router.yaml           # health-checked CoreDNS: read-local, write-primary, low-TTL failover record
│   └── healthcheck.sh            # the probe loop that flips the write record on primary failure
├── failover/
│   ├── failover.sh               # the FENCED procedure: fence A -> promote B -> reroute -> verify
│   └── measure.py                # Exercise-3 driver: drives writes, kills primary, prints RTO/RPO
├── budget.md                     # declared RTO/RPO targets + MEASURED numbers from the drill
└── runbook.md                    # region-loss runbook: detect/decide/fence/promote/reroute/verify + fail-back
```

---

## Deliverable 1 — `regions/` (the two-region topology)

A `setup.sh` that creates both Kind clusters, deploys `cart`/`inventory` and Postgres into each, configures the publication on A and the subscription on B, and injects the cross-region latency (Exercise 1). It must be idempotent — running it twice doesn't break a working topology. Capture the injected latency value; your RTO/RPO numbers only mean something next to the latency that produced them ("RPO 0.4s at 80ms cross-region RTT"). On localhost with no injected latency the lag is unrealistically near zero, which would make your RPO a lie — so the latency injection is not optional.

---

## Deliverable 2 — `routing/` (read-local, write-primary, failover)

The geo-routing layer from Exercise 2:

- **`geo-router.yaml`** — `read.shop.internal` → local replica (higher TTL, reads tolerate caching); `write.shop.internal` → primary region (low TTL, the failover knob). Document in a comment why the write record's TTL is low (the TTL tax: cached clients hit the dead region for up to TTL after cutover, so effective RTO = failover RTO + TTL).
- **`healthcheck.sh`** — the probe loop that detects A's failure and flips the write record to B. Document the detection cadence (probe interval + timeout) as the `detect` term in your RTO budget, and the tradeoff (too tight = flap on a blip; too loose = detection dominates RTO).

> **The rule the budget enforces:** your *effective* RTO includes the DNS TTL and the detection latency, not just the database promotion time. A budget that quotes only the promote time is optimistic fiction.

---

## Deliverable 3 — `failover/` (the FENCED, measured failover)

The heart of the project, building on Exercise 3 and the Challenge:

- **`failover.sh`** — the procedure in the correct order: **fence A first** (make it read-only / scale it to 0 / revoke its lease) **before** promoting B, then reroute and verify. Fencing-before-promote is non-negotiable — it's the one step that prevents split-brain (the Challenge), and a failover script that promotes before fencing fails this project's reason to exist.
- **`measure.py`** — drives writes under load, kills the primary, and prints the **measured RTO and RPO** with the lost-write count. Run it and capture the output.

Document the failover in the repo README with the `measure.py` output and a note on what each RTO term contributed (detection, promote, reroute, TTL).

---

## Deliverable 4 — `budget.md` (declared vs measured)

This is the deliverable that separates this project from a tutorial. State your **targets** and put your **measured** numbers next to them:

| Metric | Target | Measured (at <X>ms cross-region RTT) | Pass? |
|---|---|---|---|
| RTO | < 60s | 6.7s | yes |
| RPO | < 5s | 0.4s | yes |
| Writes lost at failover | < 100 | 4 | yes |

Then a paragraph: *why* these targets fit the cart workload (a cart can tolerate seconds of failover and losing a few in-flight cart updates is recoverable — the user re-adds the item; contrast with the payment ledger, where RPO must be ~0). The honest shape: read-local/write-primary with async replication gives you a small, measured RPO and a tens-of-seconds RTO cheaply; driving RPO to 0 would require synchronous cross-region replication and pay an ocean of write latency (Lecture 1 §3.2), which the cart doesn't need. "Our RTO is Xs and RPO is Ys, measured under load, and here's why that's the right target for this data" is the sentence that wins a DR-architecture review.

---

## Deliverable 5 — `runbook.md` (the region-loss runbook)

A runbook an on-call engineer could execute at 3 a.m. It must cover:

1. **Detect** — how you know region A is actually down (health checks, the symptoms), and the critical caveat: *unreachable from the monitor is not the same as dead.*
2. **Decide** — who/what triggers failover and the go/no-go criteria.
3. **Fence** — the exact command(s) to make A unable to write *before* promoting B. The split-brain guard.
4. **Promote** — promote B to primary.
5. **Reroute** — flip the write record; note the TTL-bounded propagation.
6. **Verify** — confirm writes land on B and the system is healthy; *this* is when the RTO clock stops.
7. **Fail-back** — the *harder* procedure: bring A back as a **replica** of B first (re-sync), reconcile or discard A's stranded unreplicated writes, and only then (carefully, as a planned failover) consider handing writes back. Name the unreplicated-writes reconciliation explicitly.

> **The rule the runbook enforces:** fence before promote, and treat "unreachable" as UNKNOWN (not dead) — you must *confirm* A cannot write before promoting B. A runbook that skips fencing is the Challenge's incident waiting to happen.

---

## Rules

- **You may** read the Postgres, CoreDNS, and DR-pattern docs, and the Patroni docs for how production fencing works.
- **You must not** declare a failover "working" without **measuring** RTO and RPO under load. A failover with no traffic measures nothing.
- **You must not** inject zero cross-region latency and report the resulting near-zero RPO as real — the latency injection is what makes the numbers honest.
- **You must not** promote without fencing (see the Challenge). A split-brain-capable failover fails the project.
- **You must not** report an RPO of 0 unless you actually ran synchronous replication and paid the write-latency cost — under async, RPO is your lag, full stop.
- Two Kind clusters, Postgres 16+, CoreDNS, `kubectl`/`psql`. Everything runs locally.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-19-cart-multiregion-<yourhandle>`.
- [ ] `regions/setup.sh` brings up two Kind regions with cart/inventory + Postgres and live cross-region replication idempotently; injected cross-region latency is captured.
- [ ] `pg_stat_replication` shows region B streaming from A, with a non-zero, monitored `replay_lag`.
- [ ] The geo-router routes reads local and writes to the primary, with a low TTL on the failover record; you demonstrated the TTL tax.
- [ ] `failover/failover.sh` **fences A before promoting B** and reroutes; `measure.py` produces a measured RTO and RPO under load with a lost-write count.
- [ ] `budget.md` states RTO/RPO targets, the measured numbers next to them (with the cross-region latency noted), and a justification tied to the cart workload.
- [ ] `runbook.md` covers detect/decide/**fence**/promote/reroute/verify *and* fail-back, with the "unreachable ≠ dead" rule.
- [ ] A `README.md` with the topology diagram, the failover sequence, the budget table, and a paragraph on when active-passive (this) suffices vs when you'd need active-active (Week 20).
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Two-region topology** | 15 | Both regions up, real cross-region replication with injected latency, reproducible setup. |
| **Read-local/write-primary routing** | 15 | Reads local, writes to primary, low-TTL failover record; TTL tax demonstrated. |
| **Fenced failover** | 25 | Fence-BEFORE-promote (not after); split-brain impossible; the procedure is correct and scripted. |
| **Measured RTO/RPO** | 25 | Real numbers under load; RPO = lag (identity shown); lost-write count; latency-context noted. |
| **Budget & runbook** | 15 | Targets vs measured; runbook covers fence + fail-back + "unreachable ≠ dead"; an on-call could run it. |
| **Docs & hygiene** | 5 | Clear README, topology diagram, sensible commits, no secrets/artifacts checked in. |

**90+** is portfolio-grade and ready to be the capstone's two-region substrate (and the Week 22 region-failover drill target). **70–89** works but likely reports an unmeasured or zero-latency RPO, or promotes before fencing. **Below 70** usually means the failover wasn't measured under load or could split-brain — fix those first; they're the two things this week exists to prevent.

---

## Stretch goals

- **Synchronous variant.** Run a synchronous-replication version and show RPO drops to ~0 *and* write latency rises by the cross-region RTT. Put both numbers in `budget.md` — the trade made measurable.
- **Automated, guarded failover.** A controller that fences-then-promotes and *refuses to promote unless the fence is confirmed* (the Challenge's guard). Trigger an eager failover and show it still can't split-brain.
- **Witness/arbiter.** Add a third notional location as a voting witness so a two-region partition is broken by quorum, and show the isolated region demotes itself.
- **Data-residency model.** Tag some rows `residency=eu` and show your replication *refuses* to copy them outside the EU region — and explain how that constraint would forbid a naive active-active (Lecture 2 §2.3).

---

## Common pitfalls (read before you start)

These are the mistakes that cost the most points and the most debugging time:

- **The zero-latency lie.** Running on localhost with no injected cross-region latency makes your replica lag near-zero, so your RPO looks artificially perfect. Inject the latency (Exercise 1) or your numbers are fiction.
- **The silent standby.** Setting up replication and never checking it actually streams. Monitor `pg_stat_replication` *continuously* — a standby that broke last week is discovered at failover, when it's too late.
- **Promote-before-fence.** Promoting region B before fencing region A. If A is only unreachable (not dead), you've made two primaries. Fence first, always (the Challenge).
- **Measuring only the promote time.** Reporting the database-promotion time as the RTO and ignoring detection latency and DNS TTL. Measure end-to-end: first failed request to first successful request.
- **No traffic during the drill.** A failover with no writes in flight measures nothing — you can't see what was lost. Drive load throughout.
- **Forgetting fail-back.** Rehearsing the failover but not the fail-back, then bricking the system re-syncing the recovered region the wrong direction. Fail-back is a failover-in-reverse plus reconciliation.

A submission that avoids all six is in 90+ territory; most of the lost points cluster on the first two (unmeasured/unrealistic numbers) and the third (split-brain-capable failover).

## How this connects to the rest of C22

- **Week 13 (Postgres replication)** is the single-region replication this builds on; here it crosses a (simulated) region boundary and gains a failover.
- **Week 18 (SLI/SLO)** is the discipline RTO/RPO are the multi-region expression of — your budget *is* an error-budget statement for region loss.
- **Week 20 (CRDTs in production)** replaces this single-primary cart with a genuinely active-active, conflict-free one — measured against the baseline you capture here.
- **Week 22 (gameday)** runs Drill A — Region failover on this exact topology, under 1k RPS, graded by the postmortem. This week's measured failover is that drill's rehearsal.

## A suggested order of work

If you're not sure where to start, this sequence keeps you from blocking yourself:

1. **Day 1 (Thursday):** stand up the two regions and replication (`regions/setup.sh`), inject the cross-region latency, and confirm `pg_stat_replication` shows a live, lagging stream. Don't move on until the lag is non-zero and visible.
2. **Day 1–2:** add the geo-router (`routing/`) and confirm read-local/write-primary resolution and the low-TTL failover record. Demonstrate the TTL tax once.
3. **Day 2 (Friday):** write the *fenced* failover (`failover/failover.sh`) — fence A, promote B, reroute, verify — and the measurement driver. Run it under load and capture the RTO/RPO.
4. **Day 2–3:** fill in `budget.md` (targets vs measured) and `runbook.md` (the full sequence + fail-back). These are quick once the numbers exist.
5. **Day 3 (Saturday):** the audit/automation polish, the stretch goals, and the README writeup.

The dependency that trips people: you can't measure a meaningful RTO/RPO until the latency is injected and the failover is fenced, so do those *first*. Everything else (the budget, the runbook, the docs) is fast once you have real numbers from a correct failover.

When you've finished, push the repo and take the [quiz](../quiz.md).
