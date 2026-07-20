# Week 19 — Multi-Region: Active-Active, Active-Passive, and the Choices

Welcome to the week the system grows a second home. For eighteen weeks you have built and operated services in a single region — one Kubernetes cluster, one Postgres primary, one failure domain. That was a simplification, and a load-bearing one: a single region means a single source of truth, a single write path, and a single place for "the latest value" to live. This week you give that up. The moment you put the system in two regions you inherit the speed of light as a design constraint, a write path that may now span an ocean, and the oldest question in distributed systems made operational: **when the two regions disagree, who wins, and how fast can the survivor take over?**

We assume you finished Phase 3. You have a Postgres primary with logical replication (Week 13), a CDC pipeline (Week 14), observability that can show you replication lag (Week 17), and the SLI/SLO discipline to put a number on "down" (Week 18). That literacy is load-bearing this week, because **multi-region is not a feature you turn on — it is a set of tradeoffs you choose**, and every one of them is denominated in the budgets you learned to measure: latency, lag, RTO, RPO, and dollars.

The one sentence to internalize before you read another line: **two regions is harder than one region twice.** A second region does not double your reliability for free; it doubles your write-coordination problem, your data-gravity problem, and your operational surface, and it hands you a brand-new failure mode — the partition *between* your regions — that did not exist when there was only one. The active-active deployment that looks like "twice the capacity, twice the availability" on the architecture slide is, underneath, a distributed consensus problem you are now responsible for. The whole point of this week is to make you able to choose between active-active and active-passive *deliberately*, with the RTO/RPO numbers and the data-residency constraints written down, instead of reaching for active-active because it sounds stronger.

This week is where "the system is up" stops being a single bit and becomes a question of *which region, with what data, recovered in how long.*

## Learning objectives

By the end of this week, you will be able to:

- **Distinguish** active-active from active-passive precisely — what each costs, what each buys, and which failure modes each one actually protects against — and choose between them for a given workload with the tradeoffs written down.
- **Define and measure** RTO (recovery time objective) and RPO (recovery point objective) as the two numbers that drive every multi-region decision, and connect them to the replication mechanism (synchronous vs asynchronous) that determines what each one *can* be.
- **Reason about** cross-region replication latency as a budget: the speed-of-light floor between regions, why synchronous cross-region writes are usually a mistake, and how asynchronous replication trades RPO for write latency.
- **Design** a geo-routing layer — DNS-based (GeoDNS/latency-based records), anycast, and GSLB — and explain how health-checked failover actually redirects traffic, including the DNS-TTL tax on your effective RTO.
- **Confront** the data-gravity problem: why data is the hardest thing to make multi-region, why "route reads local, writes to the primary" is the pragmatic default, and how data-residency law (GDPR, data localization) turns geography into a correctness constraint rather than a latency one.
- **Stand up** a two-region topology on two Kind clusters with a routed control plane, replicate Postgres logically across the regions, route reads locally and writes to the primary, and **perform a controlled failover with a measured RTO**.
- **Measure** replication lag continuously and reason about what a non-zero lag means for RPO at the moment of failover — the data you lose is the data that hadn't replicated yet.
- **Write** the failover runbook: the named steps, the promote-the-replica decision, the split-brain guard, and the "is it actually safe to fail back" question that catches teams every time.

## Prerequisites

This week assumes you have completed **C22 weeks 1–18**, or have equivalent fluency. Specifically:

- Two **Kind** clusters you can run simultaneously (the two "regions"), each with enough headroom for Postgres and a couple of services. ~6 GB free total is comfortable; the lab is deliberately small.
- The **Postgres logical replication** literacy from Week 13: you can create a publication and a subscription, and you can read `pg_stat_replication` to see lag.
- The **`cart`/`inventory` services** from Phase 1, deployable to a cluster as gRPC servers with readiness/liveness probes (Week 6).
- The **observability** from Week 17: you can scrape a metric and graph it, because you will graph replication lag and the failover transient.
- The **SLI/SLO discipline** from Week 18: you can state an availability target and an error budget, because RTO and RPO are the multi-region expression of exactly that discipline.
- Comfort with **DNS fundamentals** — records, TTL, resolution — because geo-routing and failover live and die on DNS behavior.

You do **not** need a cloud account. Everything runs on two local Kind clusters; the multi-region *concepts* (the speed-of-light floor, the partition, the RTO/RPO tradeoff) are identical whether the second region is across the room or across an ocean, and the lab makes the latency explicit with a simulated cross-region delay.

## Topics covered

- **Active-active vs active-passive**: the two topologies, what each one means for the write path (active-active = writes accepted in multiple regions, hence conflict; active-passive = one region writes, the other waits), and the honest tradeoff — active-active buys capacity and lower write-RTO at the cost of a conflict-resolution problem; active-passive buys simplicity at the cost of idle standby capacity and a failover step.
- **RTO and RPO**: the two budgets. RTO = how long until service is restored after a failure; RPO = how much data you can afford to lose (the age of the last replicated write). Their relationship to synchronous vs asynchronous replication: synchronous can give RPO≈0 but pays the cross-region latency on every write; asynchronous gives a fast write but an RPO equal to the replication lag at the moment of failure.
- **Quorum across regions**: why a consensus group (Raft/Paxos, Week 2) spread across regions pays the inter-region round-trip on every commit, why an even number of regions is a split-brain trap, and why the three-region (or two-regions-plus-a-witness) layout exists.
- **Cross-region replication latency as a budget**: the speed-of-light floor (≈ tens of ms across a continent, ≈ 100+ ms across an ocean), why a synchronous cross-region write inherits that floor on every commit, and the design rule that follows — keep the write path inside one region and replicate asynchronously.
- **Geo-routing**: DNS-based routing (GeoDNS, latency-based / weighted records), anycast (one IP announced from many places, the network routes to the nearest), and GSLB (global server load balancing with health-checked failover). The DNS-TTL tax: a record cached for TTL seconds means clients keep hitting a dead region for up to TTL after you fail over, so TTL is a direct term in your effective RTO.
- **Session affinity and the data-gravity problem**: why a user's session and their data want to live in one region, why "stick the user to their home region" is the common pattern, and why data — not compute — is the thing that makes multi-region hard. Compute is stateless and cheap to replicate; data has gravity.
- **Data residency as a correctness constraint**: GDPR and data-localization laws that *require* certain data to stay in certain regions, turning geography from a latency optimization into a legal correctness requirement — the EU user's data must live in the EU region, full stop, and that constraint can forbid the active-active design you'd otherwise choose.
- **The controlled failover**: promoting a replica to primary, the split-brain guard (fencing the old primary so it can't accept writes after you've promoted its replica), the DNS/routing cutover, and the fail-back question — bringing the recovered region back as a replica before (carefully) handing writes back.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Active-active vs active-passive; RTO/RPO; the budgets   |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Two Kind regions; logical replication across regions    |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Geo-routing: DNS, anycast, GSLB; the TTL tax            |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Read-local/write-primary; measuring lag; data gravity   |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The controlled failover; split-brain; RTO measurement   |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                  |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, runbook polish                            |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The replication, geo-routing, and DR-pattern material worth your time |
| [lecture-notes/01-active-active-active-passive-rto-rpo.md](./lecture-notes/01-active-active-active-passive-rto-rpo.md) | The two topologies, RTO/RPO, replication sync-vs-async, quorum across regions |
| [lecture-notes/02-geo-routing-data-gravity-and-the-failover.md](./lecture-notes/02-geo-routing-data-gravity-and-the-failover.md) | DNS/anycast/GSLB, the data-gravity and residency problem, and the controlled failover |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-two-region-postgres-replication.md](./exercises/exercise-01-two-region-postgres-replication.md) | Stand up two Kind regions, replicate Postgres logically across them, measure lag |
| [exercises/exercise-02-geo-routing-failover.yaml](./exercises/exercise-02-geo-routing-failover.yaml) | A health-checked geo-routing + failover config: read-local/write-primary, the TTL tax made visible |
| [exercises/exercise-03-failover-rto.py](./exercises/exercise-03-failover-rto.py) | Drive a controlled failover under load and *measure the RTO and the RPO* — the data lost equals the lag at cutover |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-split-brain-double-write.md](./challenges/challenge-01-the-split-brain-double-write.md) | A failover that didn't fence the old primary produces split-brain double writes — diagnose and fix |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the active-active-vs-active-passive decision memo |
| [mini-project/README.md](./mini-project/README.md) | `cart-multiregion`: the cart topology across two regions with measured failover, an RTO/RPO budget, and a runbook |

## The "the failover actually worked" promise

C22 uses a recurring marker for every exercise that ends in the system actually doing what you declared. This week's canonical one is a *measured* failover — RTO and RPO are numbers you produce, not numbers you hope for:

```
$ python3 exercise-03-failover-rto.py --run
[t=0.0s]   region-a PRIMARY healthy, region-b REPLICA, lag=0.4s
[t=12.0s]  injecting region-a failure (kill primary)...
[t=12.3s]  health check failed; promoting region-b replica to primary
[t=18.7s]  region-b accepting writes; routing cut over
--------------------------------------------------------------------
MEASURED RTO: 6.7s  (failure detected -> writes accepted on new primary)
MEASURED RPO: 0.4s  (replication lag at moment of failure = data at risk)
WRITES LOST:  2     (the 2 writes that hadn't replicated when A died)
--------------------------------------------------------------------
```

If the script reports a measured RTO and RPO — and the writes-lost count matches the lag — your failover is real and budgeted, not assumed. The point of this week is to make these numbers *ordinary*: an RTO you measured under load and an RPO you can defend, the way you made `pg_stat_replication` lag ordinary in Week 13 — and to make a *silent* multi-region failure (a standby that was never actually replicating, discovered only at failover) something you catch in a drill, not in an incident.

## Stretch goals

If you finish the regular work early and want to push further:

- Run the failover with **synchronous replication** (`synchronous_commit = remote_apply` to the cross-region replica) and measure what it does to **write latency** — you'll see the cross-region round-trip land on every commit. Then explain, with your two numbers, why synchronous cross-region replication is usually the wrong default: you bought RPO≈0 at the cost of an ocean of latency on every write.
- Add a **witness/arbiter** node in a notional third location so a two-region split-brain can be broken by a tie-breaker. Reason about why an even number of voting members across regions is a split-brain trap.
- Model the **data-residency constraint**: declare that `eu-user` rows must never leave the EU region, and show how that constraint forbids a naive active-active design (which would replicate those rows everywhere) and forces a partitioned/sharded-by-region layout instead.
- Measure your **effective RTO including DNS TTL**: set a record TTL of 30s, fail over, and show that clients with the cached record keep hitting the dead region for up to TTL — so your *effective* user-visible RTO is the failover RTO *plus* the TTL, which is why low TTLs on failover-critical records are a real practice.

## Up next

Week 20 takes the two-region topology you build here and solves the problem active-active *creates*: when both regions accept writes, they will disagree, and last-write-wins quietly loses data. You'll promote the cart service to genuine active-active using a **CRDT** (the Week 3 theory, now in production), partition the regions, heal, and prove convergence — so the cart survives a partition with *no* lost updates, which is the thing a single primary with failover cannot give you. Everything you learn this week about the partition between regions is what makes next week's "both regions write, and it still converges" comprehensible. Push your `cart-multiregion` mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
