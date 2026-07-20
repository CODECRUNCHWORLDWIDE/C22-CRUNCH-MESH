# Week 19 Homework

Six problems that revisit the week's topics and force the multi-region operational literacy into your fingers. The full set should take about **5 hours**. Work in your Week 19 Git repository (the same workspace as the exercises and the `cart-multiregion` mini-project) so every problem produces at least one commit you can point to at the Phase 4 review and the Week 22 gameday.

The headline deliverable is **Problem 4 — the active-active-vs-active-passive decision memo**, the artifact a platform lead reads before committing a workload to a multi-region topology. Treat it as an architecture decision document, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have your **two Kind regions** with cross-region Postgres replication up (Exercise 1). Problems 1, 2, 3, 5, and 6 run against the live topology.

---

## Problem 1 — The replication-lag-is-your-RPO dashboard

**Problem statement.** Bring up your two-region topology. Graph the **replication lag** (`replay_lag` from `pg_stat_replication`) continuously while you vary the write load, and annotate the graph with what each lag value *means as an RPO*. Show at least two regimes: steady-state (lag small) and overloaded (write rate exceeds the link's ship rate, lag climbing).

**Acceptance criteria.**

- `notes/week-19/lag-rpo.md` has the graph (or the raw time-series + a description) showing lag under at least two write-load regimes.
- You label, for each regime, "this lag = this much data lost if the primary died now."
- You show (or describe) the overloaded regime where lag climbs without bound, and state why that's a silent RPO regression.
- Committed.

**Hint.** `SELECT EXTRACT(EPOCH FROM replay_lag) FROM pg_stat_replication;` sampled every second gives you the series. Drive load with the Exercise-1 insert loop and crank the rate until the replica can't keep up — that's the moment lag stops being flat.

**Estimated time.** 40 minutes.

---

## Problem 2 — Measure RTO and RPO under load (and confirm the identity)

**Problem statement.** Run the Exercise-3 failover measurement twice: once with **low lag** (modest write rate) and once with **high lag** (cranked write rate). Capture the measured RTO and RPO and the lost-write count for each, and confirm the identity: more lag at failure → more data lost.

**Acceptance criteria.**

- `notes/week-19/rto-rpo.md` records both runs: measured RTO, measured RPO (lag at failure), and lost-write count for each.
- You demonstrate that the high-lag run lost more writes than the low-lag run, confirming RPO = lag.
- You note the cross-region latency you injected, so the numbers are interpretable.
- You state in one sentence why an RTO/RPO you didn't measure under load is a hope, not a number.
- Committed.

**Hint.** The lost-write count is the `measure.py` reconciliation: committed-on-old-primary minus present-on-new-primary. If you measure lag≈0 but lose writes, your standby wasn't actually caught up — that's a finding, not a bug in the script.

**Estimated time.** 50 minutes.

---

## Problem 3 — Fence-before-promote (prove split-brain is prevented)

**Problem statement.** Implement the **fenced** failover from the Challenge: fence region A (make it read-only or scale it to 0) *before* promoting region B. Then *deliberately* run the wrong order (promote B without fencing A, while A is still up) and show the split-brain (bidirectional divergence). Then show your fenced order prevents it.

**Acceptance criteria.**

- `notes/week-19/fencing.md` shows the WRONG order producing split-brain (A has writes B lacks AND B has writes A lacks — both directions).
- It shows the FENCED order: A is confirmed unable to write before B is promoted, so no divergence is possible.
- You state the rule: "unreachable from the monitor" is UNKNOWN, not "dead" — you must confirm the old primary can't write before promoting.
- Committed.

**Hint.** The bidirectional divergence is the proof it's split-brain: `SELECT id, payload FROM writes WHERE id IN (...)` on both sides showing the same id with different payloads, plus ids unique to each side. Replication lag can never produce writes-unique-to-the-replica.

**Estimated time.** 50 minutes.

---

## Problem 4 — The active-active-vs-active-passive decision memo (headline deliverable)

**Problem statement.** This is the syllabus skill ("active-active vs active-passive; the choices"). Write a one-to-two-page memo at `notes/week-19/topology-decision-memo.md` advising a platform team which topology to adopt for a specific workload, backed by the numbers *you measured* and the constraints you reason through. Pick **one** workload and state which:

- **Workload A — the cart:** a global user base; users tolerate seconds of failover and losing a few in-flight cart updates (the user re-adds the item). Write-heavy at peak but each write is low-stakes.
- **Workload B — the payment ledger:** every write is a financial fact; RPO must be ~0 (you cannot lose an acknowledged charge); strict residency on some data.

Your memo must hit these headings:

1. **Recommendation** — one sentence: active-active, active-passive, or read-local/write-primary-with-failover, for the chosen workload.
2. **The RTO/RPO budget** — the targets this workload needs and *why* (tie to the business: what does a minute of downtime / a lost write actually cost here?).
3. **The measured numbers** — your Exercise-3 RTO/RPO at your cross-region latency, and what they'd be under sync vs async.
4. **The conflict story (if active-active)** — if you recommend active-active, what resolves conflicts (CRDT / single-writer-per-key / partition-by-region)? If active-passive, state explicitly that you've *avoided* the conflict problem by having one write path.
5. **Residency / data-gravity constraints** — any constraint (legal or latency) that *forces* part of the decision, and how it interacts with the topology.
6. **The migration & operational cost** — idle standby capacity (active-passive) vs the conflict-resolution complexity (active-active); the drill/runbook you'd commit to.

**Acceptance criteria.**

- `notes/week-19/topology-decision-memo.md` exists, fits roughly one-to-two pages (600–1000 words), and hits all six headings.
- The **measured numbers** section uses real numbers from your own failover, not figures quoted from a blog.
- The recommendation commits to a position and ties it to the workload's actual RTO/RPO needs and constraints.
- For Workload B, you confront that RPO≈0 forces synchronous replication and its write-latency cost (or a different design); for Workload A, you justify why async + failover suffices.
- Committed.

**Hint.** The strongest memos pick the *cheapest correct* topology, not the strongest-sounding one. For the cart (A), read-local/write-primary with a measured fast failover is usually the right call — active-active is overkill *until* Week 20's CRDT makes it cheap. For the ledger (B), the honest tension is "RPO must be ~0, which means synchronous, which means slow cross-region writes — so maybe writes live in ONE region with sync local replicas, and cross-region is async DR with a documented small RPO and a manual-reconciliation tail." Address the tension; don't hand-wave it.

**Estimated time.** 1 hour.

---

## Problem 5 — The DNS TTL tax, measured

**Problem statement.** Using your geo-router (Exercise 2), demonstrate the DNS TTL tax. Set the failover record's TTL to a high value (e.g. 120s), fail over, and measure how long a *cached* resolver keeps hitting the old region. Then set it low (5s) and measure again. Show that effective RTO = failover RTO + TTL.

**Acceptance criteria.**

- `notes/week-19/ttl-tax.md` shows, for a high TTL and a low TTL, how long after cutover a cached resolver still returns the old region's address.
- You compute the *effective* RTO for each (your failover RTO + the observed TTL lag).
- You state why failover-critical records run low TTLs, and one tradeoff of doing so (more DNS query volume).
- Committed.

**Hint.** `dig` shows the remaining TTL on a cached answer (it counts down). Resolve the record, fail over, and keep resolving through the same caching resolver — the old answer persists until its TTL hits zero, then flips. That persistence window is the tax.

**Estimated time.** 35 minutes.

---

## Problem 6 — Diagnose a planted multi-region fault

**Problem statement.** Have a partner (or your future self) introduce ONE of these faults, then diagnose it from the outside before looking at what was changed: (a) the subscription on region B is broken/dropped so it silently stops replicating (a standby that isn't a standby), (b) the failover record's TTL is set absurdly high so failover "doesn't work" for cached clients, or (c) the failover promotes B without fencing A (split-brain-capable). For whichever fault, produce a diagnosis: symptom, the evidence (replication state / TTL / row divergence), root cause, and fix.

**Acceptance criteria.**

- `notes/week-19/planted-fault.md` records which fault, the diagnostic commands you ran, the evidence (quote `pg_stat_replication` / `dig` / the row divergence), the root cause, and the fix.
- You reach the diagnosis with at least two signals (e.g., an empty `pg_stat_replication` *and* a replica row-count that stopped advancing).
- Committed.

**Hint.** The "standby that isn't replicating" (a) is the scariest because it's *silent* — everything looks fine until failover, when you discover the standby is hours behind (huge RPO) or empty. Catch it the way you'd catch it in production: monitor `pg_stat_replication` being non-empty and the replica's row count advancing. The fault that produces "the failover works in psql but clients don't notice" is the TTL one (b).

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Lag-is-your-RPO dashboard | 40 min |
| 2 — Measure RTO/RPO under load | 50 min |
| 3 — Fence-before-promote | 50 min |
| 4 — Topology decision memo (headline) | 1 h 0 min |
| 5 — DNS TTL tax measured | 35 min |
| 6 — Diagnose a planted fault | 35 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `cart-multiregion` [mini-project](./mini-project/README.md) is in the same workspace — Week 20 makes this cart genuinely active-active with a CRDT, and Week 22's gameday runs a region-failover drill on this exact topology. Then take the [quiz](./quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Lag-as-RPO (P1)** | 15 | Lag graphed under load; the lag-means-data-lost interpretation; the overloaded regime shown. |
| **Measured RTO/RPO (P2)** | 20 | Real numbers under load; high-lag-loses-more demonstrated; RPO=lag identity confirmed. |
| **Fencing (P3)** | 15 | Split-brain reproduced (bidirectional divergence); fenced order prevents it; "unreachable ≠ dead" stated. |
| **Decision memo (P4)** | 25 | Measured numbers; committed recommendation tied to RTO/RPO needs; conflict + residency confronted. |
| **TTL tax (P5)** | 15 | Effective RTO = RTO + TTL measured for two TTLs; low-TTL tradeoff named. |
| **Planted fault (P6)** | 10 | Two-signal diagnosis; correct root cause and fix. |

**90+** is portfolio-grade. **70–89** is solid but the memo likely lacks measured numbers or hedges on the recommendation. **Below 70** usually means Problem 2 or 4 was treated as a formality — they're the two that prove you understand the multi-region *budgets* and the *topology choice*, which is the whole difference between deploying to two regions and operating a multi-region system.
