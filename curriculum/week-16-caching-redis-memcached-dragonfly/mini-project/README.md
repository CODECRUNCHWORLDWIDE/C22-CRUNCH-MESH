# Mini-Project — `cart-cache`: A Hardened Look-Aside Cache with Stampede Protection, CDC Invalidation, and a Dragonfly Benchmark

> Put a cache in front of the cart read path and make it *trustworthy*: look-aside with a TTL and CDC-driven invalidation so no writer can leave it stale, single-flight coalescing and probabilistic early expiration so a hot key can't stampede the database, and — the part that makes you dangerous — a measured benchmark of Redis vs Dragonfly on your own workload, so the engine choice is evidence, not a default.

This is the artifact that turns "I added Redis and it's faster" into "I operate a cache I can defend." After this week, the cache is a *correctness-and-load posture* you can stand behind: every cached value agrees with the source of truth (or is provably invalidated), a hot key cannot topple Postgres, and you have hard numbers for what each engine costs on *your* read path — so when someone asks "Redis, Valkey, or Dragonfly," you answer with a benchmark instead of an opinion.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `cart-cache` is the hot read tier of your **capstone Polyglot Marketplace Backbone**. The Week 13 Postgres read path is the source of truth; this cache sits in front of it. Week 17 instruments this cache end-to-end (hit rate, miss latency, exemplars from a slow miss straight to its trace), and Week 18 wires the cache's failure into the reliability story (a dead cache must degrade the system to *slow*, then *shed load*, not topple it). Build it cleanly, with the benchmark captured, because next week's observability and the week-after's reliability patterns are layered on exactly this.

---

## What you will build

A repo `cart-cache` with five deliverables:

1. **`cache/`** — the look-aside cache layer over the cart read path: a TTL, invalidate-on-write, single-flight request coalescing (in-process *and* a distributed Redis lock), and probabilistic early expiration (XFetch).
2. **`invalidation/`** — **CDC-driven invalidation**: a consumer of the Week 14 Debezium stream (or a simulated change stream) that invalidates cache keys from the source of truth's own change log, so *no writer* — including batch jobs and manual `UPDATE`s — can leave the cache stale.
3. **`stampede/`** — the **stampede test**: a `k6` script (or equivalent) that drives a hot key past expiry under concurrency, plus a before/after showing the database query count collapsing from thousands (naive) to single digits (hardened).
4. **`bench/`** — the **engine benchmark**: identical workload run against Redis, Valkey, and Dragonfly, measuring hit-path latency (p50/p99), throughput, and memory efficiency, with the numbers and a short analysis and a license note.
5. **`audit/verify_cache.sh`** — a script that proves the posture is real: it asserts the cache *agrees with Postgres* after a write (the canonical check), that a hot-key stampede does not exceed a small backend-load bound, and that the cache is *optional* (kill it and the read path still answers correctly). Exits non-zero if any claim is false.

By the end you have a public repo of a cache layer + a stampede test + an engine benchmark + an audit script that any future read path can adopt.

---

## Why this and not "just add Redis"

You could `SET`/`GET` and call your read path "cached." Don't stop there — that's the gap this whole week is about. A defensible cache posture gives you:

- **Correctness you can prove**, not assume. The default "add a cache" leaves you with a second copy that silently drifts from the source of truth the first time a writer forgets to invalidate. This project's audit *demonstrates the cache agrees with Postgres after a write*. The difference is a trustworthy read tier versus a generator of "my cart is wrong" tickets.
- **A cache that protects the database instead of amplifying load onto it.** Naive TTL caching turns a hot key's expiry into a synchronized assault on Postgres; this project's single-flight + XFetch bounds the backend load no matter the concurrency.
- **Invalidation that survives writers you don't control.** CDC-driven invalidation means a batch job, an admin tool, another service, or a DBA's manual `UPDATE` all invalidate the cache automatically — the only strategy that holds in a polyglot, multi-writer system.
- **A real answer to "which engine,"** measured on *your* workload, so the Redis-vs-Valkey-vs-Dragonfly choice (and the license that comes with it) is evidence-based.

The managed cache services will eventually run much of this for you. Building it by hand first is what lets you read and trust what they do — the senior-shop convention in 2026.

---

## Repo layout

```
cart-cache/
├── README.md
├── cache/
│   ├── lookaside.py            # TTL + invalidate-on-write + single-flight + XFetch
│   └── distlock.py             # the distributed-lock coalescing (one loader fleet-wide)
├── invalidation/
│   └── cdc_invalidator.py      # Debezium-stream consumer -> targeted cache DELETEs
├── stampede/
│   ├── hot_key.js              # k6 script: drive a hot key past expiry under load
│   └── RESULTS.md              # naive vs hardened backend-query counts
├── bench/
│   ├── run.sh                  # identical workload vs Redis / Valkey / Dragonfly
│   └── RESULTS.md              # latency + throughput + memory + LICENSE note
├── audit/
│   └── verify_cache.sh         # asserts cache==source-of-truth, stampede bounded, cache optional
└── deploy/
    └── docker-compose.yaml     # Postgres + Redis + Valkey + Dragonfly side by side
```

---

## Deliverable 1 — `cache/` (the hardened look-aside layer)

The cache layer over the cart read path, building on Exercises 1 and 2:

- **Look-aside** with a TTL and **invalidate-on-write** (delete, not update — document why).
- **Single-flight coalescing**: in-process so a herd within one instance produces one load; plus a **distributed Redis lock** (`SET lock:cart:<id> <token> NX EX 5`, released with a check-and-delete Lua script) so a herd across *all* instances produces one load fleet-wide.
- **Probabilistic early expiration (XFetch)**: store the recompute cost alongside the value and refresh probabilistically before the hard TTL.

Document the stale-set race (Lecture 1 §3.4) and your backstop (a TTL, and optionally versioned keys).

---

## Deliverable 2 — `invalidation/` (CDC-driven)

The robust invalidation strategy: a consumer of the change stream off Postgres that turns `carts` row changes into targeted `DEL`s.

> **The rule the audit enforces:** the cache must invalidate when *any* writer changes the source of truth — including a writer your application code doesn't know about. A posture that only invalidates on the cart-service write path (and trusts every other writer to remember) fails the audit. Invalidate from the change log, not from the writers.

If you have the Week 14 Debezium stream running, consume it for real. If not, a small simulated change stream (a process that tails a Postgres `LISTEN/NOTIFY` channel or polls a change table) stands in — the point is that the invalidation trigger is the *source of truth's change*, not a writer remembering.

---

## Deliverable 3 — `stampede/` (the herd, bounded)

The stampede test, building on Exercise 2 but driven against the live service with `k6`:

- A `k6` script that warms a hot key, lets it expire, and fires high concurrency at the instant of expiry.
- A **before** run (naive TTL caching) showing the backend query count spike with concurrency — the herd.
- An **after** run (single-flight + XFetch) showing the backend query count stay bounded (single digits) regardless of concurrency.

`RESULTS.md` records both, with the query counts and a sentence on why the fix works.

---

## Deliverable 4 — `bench/` (the engine benchmark)

This is the deliverable that separates this project from a tutorial. Run the *identical* cart-cache workload against three engines and measure:

1. **Redis** (community) — your baseline.
2. **Valkey** (the BSD fork) — the licenses-clean drop-in. Confirm your code runs unchanged.
3. **Dragonfly** — the shared-nothing multi-threaded engine. Confirm your code runs unchanged.

Measure, on the cart read path under a fixed load: **hit-path latency (p50/p99)**, **throughput (ops/sec)**, and **memory for the working set** (`INFO memory` / container RSS). For Dragonfly, also note whether one vertically-scaled instance keeps up with what would otherwise need a Redis Cluster.

Write `RESULTS.md`: a table across the three engines, a paragraph of analysis, and a **license note** — because for an open-source-first platform the license (Valkey BSD vs Redis source-available/AGPL vs Dragonfly BSL→Apache) is part of the decision. The honest shape you'll find: Valkey ≈ Redis on a single-core workload (it's the same architecture); Dragonfly pulls ahead when you give it cores. Put real numbers on it. "Dragonfly does X ops/sec on 8 cores where one Redis does Y; here's the license trade" is the sentence that wins an engine-choice argument.

---

## Deliverable 5 — `audit/verify_cache.sh`

A script that makes the posture *verifiable*, not claimed. Against the running stack it must:

1. **Cache agrees with the source of truth:** write a change to Postgres, confirm the cache key is invalidated (`redis-cli GET` returns `(nil)`), and confirm the next read reloads the fresh value matching Postgres.
2. **Stampede is bounded:** drive a hot-key herd and assert the backend query count stays under a small bound (e.g., < 10), not proportional to concurrency.
3. **Cache is optional:** stop the cache and confirm the read path still returns correct carts (degrades to slow, not down).
4. Exit **0** when every assertion passes; exit **non-zero** naming the first failure.

Sketch:

```bash
#!/usr/bin/env bash
set -euo pipefail
fail() { echo "CACHE AUDIT FAIL: $1" >&2; exit 1; }
ID=42

# 1. cache agrees with the source of truth after a write?
psql -c "UPDATE carts SET version = version + 1 WHERE id = $ID;"
sleep 1                                              # allow CDC invalidation to fire
[ "$(redis-cli GET cart:$ID)" = "" ] || fail "cache not invalidated after a Postgres write"
DBV=$(psql -tAc "SELECT version FROM carts WHERE id = $ID;")
APIV=$(curl -s localhost:8080/cart/$ID | jq .version)
[ "$DBV" = "$APIV" ] || fail "reloaded cache ($APIV) disagrees with Postgres ($DBV)"

# 2. stampede bounded? (drive the k6 hot-key test, assert backend loads < 10)
LOADS=$(./stampede/measure_backend_loads.sh)
[ "$LOADS" -lt 10 ] || fail "stampede produced $LOADS backend loads (expected < 10)"

# 3. cache optional? (stop it, the read path must still answer correctly)
docker stop cart-cache-redis
curl -sf localhost:8080/cart/$ID >/dev/null || fail "read path FAILED with the cache down"
docker start cart-cache-redis

echo "CACHE AUDIT PASS: cache==source-of-truth, stampede bounded, cache optional."
```

---

## Rules

- **You may** read the Redis/Valkey/Dragonfly docs, the lecture notes, and the XFetch paper.
- **You must not** declare the cache "correct" without demonstrating it *agrees with Postgres after a write*. The audit enforces this; a cache that drifts from the source of truth has broken the project's reason to exist.
- **You must not** "fix" a stampede by lowering the TTL (see the challenge). Single-flight + XFetch bound the herd; a short TTL just trades correctness for load.
- **You must not** report an engine-benchmark number you didn't measure. The benchmark must be reproducible from `bench/run.sh`.
- Redis 7.4+ / Valkey 8+ / Dragonfly v1.x, Docker/Kind, `redis-cli`, `k6`. Everything runs locally.
- The audit must exit non-zero on any failed assertion so it can gate a deploy or CI.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-16-cart-cache-<yourhandle>`.
- [ ] The look-aside cache caches reads, invalidates on write, coalesces concurrent misses (in-process *and* distributed), and uses XFetch.
- [ ] CDC-driven invalidation invalidates the cache when *any* writer changes Postgres — demonstrated with a write that the application code didn't perform (a manual `UPDATE` or a batch job).
- [ ] The stampede test shows the backend query count bounded (single digits) regardless of concurrency, with before/after numbers.
- [ ] `bench/RESULTS.md` has measured latency + throughput + memory across Redis, Valkey, and Dragonfly, with analysis and a license note.
- [ ] `audit/verify_cache.sh` exits **0** against the correct cache and **non-zero** when you weaken the posture (e.g., disable CDC invalidation so the cache goes stale) — demonstrated in the README.
- [ ] A `README.md` with the cache flow diagram, the invalidation strategy, the stampede before/after, the benchmark table, and a paragraph on which engine you'd pick and why (engineering *and* license).
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Correctness (cache == source of truth)** | 20 | Invalidate-on-write AND CDC invalidation; the audit demonstrates the cache agrees with Postgres after a write, including from an uncontrolled writer. |
| **Stampede protection** | 20 | Single-flight (in-process + distributed) and XFetch; backend load bounded under concurrency, proven with before/after numbers. |
| **Invalidation strategy** | 15 | CDC-driven (not just write-path); a writer the app doesn't control still invalidates; stale-set race named and backstopped. |
| **Engine benchmark** | 20 | Real, reproducible latency/throughput/memory across Redis/Valkey/Dragonfly; honest analysis; license note. |
| **Resilience (cache optional)** | 15 | Killing the cache degrades the read path to slow, not down; the audit proves it. |
| **Docs & hygiene** | 10 | Clear README, cache-flow diagram, sensible commits, no secrets/build artifacts checked in. |

**90+** is portfolio-grade and ready to be the capstone's hot read tier. **70–89** works but likely claims correctness it doesn't prove, or reports an unmeasured benchmark, or leaves the cache able to take the service down. **Below 70** usually means the cache can drift from the source of truth or a stampede isn't bounded — fix that first; those are the two things this week exists to prevent.

---

## Stretch goals

- **Versioned-key read path.** Cache under `cart:<id>:v<version>` so a change writes a new key and the old one TTLs out — no invalidation race at all. Prove the audit's cache-vs-source-of-truth check passes with *zero* explicit invalidation.
- **Redis Cluster.** Stand up a 3-shard cluster, hash-tag the cart's related keys so multi-key ops work, and reshard a slot range live while the service serves traffic — confirm no key is lost.
- **Negative caching.** Cache "this cart does not exist" (a miss) with a short TTL so a flood of requests for a non-existent cart doesn't hammer Postgres — and reason about the staleness risk (a cart created right after a negative-cache entry).
- **CI gate.** A GitHub Actions workflow that boots the stack in containers, runs the stampede test and `verify_cache.sh`, and goes green only if the cache is correct, the stampede is bounded, and the cache is optional.

---

## How this connects to the rest of C22

- **Week 13 (Postgres at scale)** is the source of truth this cache sits in front of; the cache relieves the read load you measured there.
- **Week 14 (CDC)** is the change stream your invalidation consumes — the cache invalidates from the same Debezium pipeline you built two weeks ago.
- **Week 17 (observability)** instruments this cache: hit rate, miss latency, and exemplars that jump from a slow-p99 metric straight to the trace of the offending cache miss.
- **Week 18 (reliability)** wires the cache's failure into the reliability patterns: a dead cache must degrade to slow, then shed load via the circuit breaker and load shedder, never topple Postgres.
- **Phase 4 (capstone)** deploys `cart-cache` as the real hot read tier in front of the multi-region Postgres.

When you've finished, push the repo and take the [quiz](../quiz.md).
