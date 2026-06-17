# Week 16 — Caching: Redis, Memcached, Dragonfly

Welcome to the week you put a cache in front of the read path — and learn that the cache is the part of the system most likely to take you down. Last week you built the lakehouse: Iceberg tables on object storage queried by Trino, the cold analytical tier. This week you go the other direction, to the hottest tier there is: an in-memory store that answers a read in tens of microseconds instead of the milliseconds Postgres needs. That store is a **cache**, and the headline truth of the week is that **a cache is a correctness liability you accept in exchange for latency and load relief — and the engineering is entirely in managing that liability.**

We assume you finished the data-tier weeks. You have a `cart` read path that hits Postgres (Week 13), a Debezium CDC stream off that Postgres (Week 14), and the observability instinct to measure before you optimize. That literacy is load-bearing: a cache you add without a latency baseline is a cache you can't justify, and a cache you add without an *invalidation* story is a cache that serves stale carts to real users. This week you add Redis to the `cart` read path, do it *correctly* (look-aside with request coalescing and stampede protection), break it on purpose with a thundering herd under `k6`, show the fix, and then migrate to **Dragonfly** — the multi-threaded, vertically-scaling Redis-protocol-compatible engine that exists because Redis's licensing changed and its single-threaded core became a ceiling.

The one sentence to internalize before you read another line: **the two hardest problems in computer science are cache invalidation and naming things, and this week is about the first one — because the cache is a *second copy* of your data, and a second copy is always at risk of disagreeing with the first.** Every pattern you learn — look-aside, read-through, write-through, write-back — is a different answer to "when and how does the copy get refreshed or thrown away." Get that wrong and you ship a system that is fast and confidently wrong, which is worse than slow and right.

This week is where you stop treating the cache as a magic speed-up and start treating it as a distributed-systems component with its own failure modes, consistency model, and operational budget.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the four canonical cache patterns — **look-aside (cache-aside)**, **read-through**, **write-through**, and **write-back (write-behind)** — by what each guarantees, what each costs, and which failure mode each one trades for which.
- **Implement** a correct look-aside read path with **request coalescing** (single-flight) so that N concurrent misses for the same key produce *one* backend load, not N.
- **Diagnose and fix a cache stampede** (thundering herd): reproduce it with `k6`, then defend against it with single-flight coalescing and **probabilistic early expiration** (XFetch), and explain why a naive TTL is a synchronized-failure generator.
- **Reason about invalidation strategies** — TTL-only, write-through-on-change, event-driven (CDC) invalidation, and versioned keys — and pick the right one for a given read/write ratio and staleness budget.
- **Compare** Redis, Memcached, and Dragonfly precisely: the single-threaded event-loop of Redis vs Memcached's slab allocator and threading vs Dragonfly's shared-nothing multi-threaded architecture — and articulate the **Redis licensing change saga** (RSALv2/SSPL, the Valkey fork) and what it changed operationally.
- **Operate Redis Cluster**: explain the **16384 hash slots**, how keys map to slots via CRC16, why multi-key operations need **hash tags** (`{...}`), and how `MOVED`/`ASK` redirection and resharding work.
- **Choose a deployment topology** — standalone, Sentinel (HA failover), or Cluster (sharded) — and reason about the consistency cost of asynchronous replication and failover (the lost-write window).
- **Benchmark a cache** honestly — hit rate, p50/p99 latency, throughput, memory efficiency — and migrate the `cart` cache from Redis to Dragonfly with numbers that justify (or reject) the move.

## Prerequisites

This week assumes you have completed **C22 weeks 1–15**, or have equivalent fluency. Specifically:

- A working **Kind** cluster, or local Docker, with headroom to run Redis, Memcached, Dragonfly, and a load generator.
- The **`cart`** service from Phase 1/3 with a Postgres-backed read path (Week 13), deployable and instrumented with the OpenTelemetry basics from Week 6.
- Comfort with **a backend language** (the examples are Go and Python; the patterns translate). You can write an HTTP/gRPC handler, talk to Postgres, and add a client library dependency.
- **`redis-cli`** literacy at the level of `GET`/`SET`/`SETEX`/`TTL`/`DEL` — and the willingness to read `INFO`, `SLOWLOG`, and `CLUSTER NODES`.
- A load generator: **`k6`** (the examples use it) or `wrk`/`hey`. You will induce a stampede, so you need to drive real concurrency.
- The **measurement instinct** from across the course: you baseline before you optimize, and a cache without a before/after latency number is undefended.

You do **not** need prior Redis Cluster or Dragonfly experience. We start at the look-aside pattern and build up to stampede protection, cluster sharding, and the migration benchmark.

## Topics covered

- **The four cache patterns**: look-aside/cache-aside (the app owns the cache, reads miss-then-load, writes invalidate), read-through (the cache loads on miss behind a uniform interface), write-through (writes go through the cache to the store synchronously, cache always fresh), write-back/write-behind (writes hit the cache and are flushed to the store asynchronously — fastest writes, real durability risk).
- **Stampede / thundering herd**: what happens when a hot key expires and N concurrent requests all miss and all hammer the backend at once; the two defenses — **request coalescing (single-flight)** so concurrent misses share one load, and **probabilistic early expiration (XFetch)** so the recompute is staggered before the hard TTL — and why a fixed TTL on a hot key is a self-synchronizing outage.
- **Invalidation strategies**: TTL-only (simple, bounded staleness, but a tuning problem), write-through-on-change (consistent, but couples writes to the cache), **event-driven invalidation via CDC** (the Debezium stream from Week 14 invalidates cache keys — decoupled, eventually consistent), and **versioned/namespaced keys** (change the key, never invalidate — the "immutable cache" trick).
- **Redis vs Memcached vs Dragonfly**: Redis (single-threaded event loop, rich data structures, persistence, replication, Cluster); Memcached (multi-threaded, slab allocator, pure LRU key-value, no persistence — simpler and sometimes faster for the plain-blob case); **Dragonfly** (a from-scratch, shared-nothing multi-threaded engine speaking the Redis and Memcached protocols, built to scale *vertically* on many cores where Redis is single-core-bound).
- **The Redis licensing saga**: Redis's 2024 move from BSD to the dual **RSALv2 / SSPL** source-available license, the Linux Foundation's **Valkey** fork (BSD, the drop-in OSS continuation), and what this means for "open-source-first" infra choices — plus Redis's 2025 return to adding an AGPL option. The operational takeaway: Valkey and Dragonfly are the licenses-clean, Redis-protocol-compatible options.
- **Redis Cluster**: the **16384 hash slots**, `CRC16(key) mod 16384` slot assignment, slots-to-shards mapping, **hash tags** (`{user:42}`) to force multi-key ops onto one slot, `MOVED`/`ASK` client redirection, and resharding/migration.
- **Deployment topology and consistency**: standalone, **Sentinel** (monitored failover for HA), **Cluster** (sharded for scale); asynchronous replication and the **lost-write window** on failover; why a cache "loses" the strong-consistency argument and that's usually fine — but you must know *how* stale and *how* lossy.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | The four patterns; invalidation; the leaky abstraction     |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Add look-aside to cart; coalescing; the engines compared   |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Stampede: induce with k6, fix with single-flight + XFetch  |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Redis Cluster hash slots; Sentinel; topology choice        |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Dragonfly migration + benchmark; the licensing saga        |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                      |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, benchmark write-up polish                    |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                            | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Redis/Valkey/Dragonfly docs, the patterns papers, the licensing-saga references |
| [lecture-notes/01-cache-patterns-invalidation-and-the-stampede.md](./02-lecture-notes/01-cache-patterns-invalidation-and-the-stampede.md) | The four patterns, invalidation strategies, and stampede protection (coalescing + XFetch) |
| [lecture-notes/02-engines-cluster-and-the-licensing-saga.md](./02-lecture-notes/02-engines-cluster-and-the-licensing-saga.md) | Redis vs Memcached vs Dragonfly, Redis Cluster hash slots, topology, and the licensing change |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-look-aside-and-coalescing.md](./03-exercises/exercise-01-look-aside-and-coalescing.md) | Add look-aside caching to the cart read path with single-flight request coalescing |
| [exercises/exercise-02-stampede-cache-aside.py](./03-exercises/exercise-02-stampede-cache-aside.py) | A runnable cache-aside implementation with single-flight + probabilistic early expiration |
| [exercises/exercise-03-cluster-hash-slots.go](./03-exercises/exercise-03-cluster-hash-slots.go) | Compute Redis Cluster slots (CRC16) and demonstrate hash tags forcing keys onto one slot |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-stale-cart-that-wouldnt-die.md](./04-challenges/challenge-01-the-stale-cart-that-wouldnt-die.md) | Diagnose a stale-read bug caused by a write path that updates the DB but not the cache |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the Redis-vs-Dragonfly benchmark memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | `cart-cache`: a hardened look-aside cache with stampede protection, CDC invalidation, and a Dragonfly benchmark |

## The "the cache is actually correct" promise

C22 uses a recurring marker for every exercise that ends in the system actually doing what you declared. This week's canonical one is proving the cache *agrees with the source of truth* after a write — that an invalidation actually happened, not that you hoped it did:

```
$ redis-cli GET cart:42
"{\"items\":[...],\"v\":7}"          # cached cart, version 7

# ... a write bumps the cart to version 8 in Postgres ...

$ redis-cli GET cart:42
(nil)                                 # the invalidation fired; the next read reloads v8

$ curl -s localhost:8080/cart/42 | jq .v
8                                     # reload pulled the fresh version. Cache == source of truth.
```

If the cache returns `(nil)` after the write and the next read serves version 8, your invalidation is *real*, not assumed. The point of this week is to make these "does the cache agree with Postgres" checks ordinary — the same way you made `istioctl proxy-config` ordinary in Week 8 — and to make a *silently stale* cache (a write path that forgot to invalidate) something you catch in a test, not in a customer's "my cart is wrong" ticket.

## Stretch goals

If you finish the regular work early and want to push further:

- Implement **probabilistic early expiration (XFetch)** from the Vattani–Chierichetti–Lowenstein paper and measure that it eliminates the stampede *without* the recompute being centralized through a lock — compare it against single-flight on a hot key.
- Stand up a **3-shard Redis Cluster** on Kind, write a key with and without a hash tag, and watch `redis-cli -c` follow the `MOVED` redirection across shards. Then reshard a slot range live and confirm no key is lost.
- Run the **identical benchmark on Valkey** (the BSD Redis fork) alongside Redis and Dragonfly. The point: Valkey is the licenses-clean drop-in; Dragonfly is the architecturally different bet. Numbers make the choice concrete.
- Wire **event-driven invalidation** off the Week 14 Debezium stream: a consumer that turns `orders`/`cart` change events into targeted `DEL`s, so the cache invalidates from the source of truth's own change log rather than from the write path guessing.

## Up next

Week 17 takes the cache you instrumented here and folds it into a full observability story: **OpenTelemetry, Prometheus + Thanos, Tempo, and Loki**. The cache hit-rate and latency metrics you eyeballed this week become first-class RED metrics with exemplars that jump straight to the trace of a slow miss — so when the p99 spikes, you can see *which* cache miss, on *which* key, in *which* request, caused it. Everything you measured by hand this week is what next week teaches you to measure continuously and correlate. Push your `cart-cache` mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
