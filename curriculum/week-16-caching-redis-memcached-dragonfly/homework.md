# Week 16 Homework

Six problems that revisit the week's topics and force the caching literacy into your fingers. The full set should take about **5 hours**. Work in your Week 16 Git repository (the same workspace as the exercises and the `cart-cache` mini-project) so every problem produces at least one commit you can point to at the Phase 3 review.

The headline deliverable is **Problem 4 — the Redis-vs-Dragonfly benchmark memo**, the artifact a platform lead reads before choosing a cache engine for a fleet. Treat it as a funding/architecture decision document, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Redis** (or Valkey) running and your **`cart`** read path cacheable (Exercise 1). Problems 1, 2, 3, 5, and 6 run against the live cache.

---

## Problem 1 — The cache-vs-source-of-truth audit

**Problem statement.** Bring up your cached `cart` read path. For a set of cart ids, capture — from `redis-cli` and from Postgres (or your stand-in store) — whether the cache *agrees with the source of truth* across three states: (a) freshly cached, (b) immediately after a write through the cart-service path, and (c) immediately after a write through a *second* path that does not invalidate. Build a markdown table in `notes/week-16/cache-audit.md` with one row per state and these columns:

| State | `redis-cli GET cart:X` | Store value | Agree? | Why |
|---|---|---|---|---|

**Acceptance criteria.**

- `notes/week-16/cache-audit.md` exists with one row per state.
- The "agree?" column comes from comparing `redis-cli GET` to the store, not from your assumptions.
- State (c) shows a *disagreement* (the second writer left the cache stale), with a one-line reason — the exact failure the challenge is about.
- Committed.

**Hint.** `redis-cli GET cart:42` then `SELECT … FROM carts WHERE id = 42`. After a non-invalidating write, the cache holds the *older* value — that's the row that proves "we have a cache" doesn't imply "the cache is correct."

**Estimated time.** 40 minutes.

---

## Problem 2 — Induce and bound a stampede

**Problem statement.** Demonstrate the cache-stampede failure mode and its fix. With naive TTL caching, drive a hot key past its expiry under concurrency (Exercise 2 or a `k6` script against the live service) and capture the backend query count spiking with concurrency. Then enable single-flight + XFetch and capture the query count staying bounded (single digits) at the same concurrency.

**Acceptance criteria.**

- `notes/week-16/stampede.md` shows the backend query count for naive caching (scales with concurrency) and hardened caching (bounded), at the same concurrency level.
- You state in one sentence why a fixed TTL on a hot key is a self-synchronizing outage.
- You note the difference between in-process single-flight (one load per pod) and a distributed lock (one load fleet-wide).
- Committed.

**Hint.** Count the loads at the store, not the responses to the client (every client still gets answered — the fix deduplicates *backend* loads, not requests). The naive count ≈ concurrency; the hardened count ≈ 1.

**Estimated time.** 45 minutes.

---

## Problem 3 — CDC-driven invalidation

**Problem statement.** Build invalidation that survives a writer your application code doesn't control. Wire a change-stream consumer (the Week 14 Debezium stream, or a simulated `LISTEN/NOTIFY`/change-table tail) that invalidates cache keys from the source of truth's change log. Then prove it: change a `carts` row with a *manual* `UPDATE` in `psql` (a writer no app code knows about) and show the cache invalidates anyway.

**Acceptance criteria.**

- `notes/week-16/cdc-invalidation.md` records the consumer, and a demonstration that a manual `psql` `UPDATE` invalidates the cache (the key goes `(nil)`, the next read reloads fresh).
- You contrast this with write-path invalidation and explain why CDC is the only strategy that holds when you don't control every writer.
- Committed.

**Hint.** The proof that matters is the *manual* `UPDATE`: if a `psql` write that no application code performed still invalidates the cache, your invalidation is genuinely driven by the source of truth's change log, not by writers remembering.

**Estimated time.** 50 minutes.

---

## Problem 4 — The Redis-vs-Dragonfly benchmark memo (headline deliverable)

**Problem statement.** This is the syllabus skill ("benchmarking caches; reasoning about invalidation; the licensing change saga"). Write a one-to-two-page memo at `notes/week-16/engine-benchmark-memo.md` advising a platform team which cache engine to adopt, backed by numbers *you measured* on your cart workload. Pick **one** org and state which:

- **Org A:** an open-source-first shop with a strict "must be permissively licensed" policy, running a moderate cache workload that fits comfortably on one node.
- **Org B:** a high-throughput shop currently running a multi-node Redis Cluster purely for the throughput, paying the cluster's operational complexity (hash tags, resharding, multi-key constraints).

Your memo must hit these headings:

1. **Recommendation** — one sentence: Redis, Valkey, or Dragonfly, for the chosen org.
2. **The measured numbers** — your benchmark: hit-path p50/p99 latency, throughput (ops/sec), and working-set memory for Redis vs Valkey vs Dragonfly on the cart read path.
3. **The architecture fit** — single-core-shard (Redis/Valkey) vs vertical-scale-one-instance (Dragonfly), mapped to the org's actual scale needs.
4. **The license** — Valkey BSD vs Redis source-available/AGPL vs Dragonfly BSL→Apache, mapped to the org's licensing policy. For an open-source-first shop, this is often the deciding factor.
5. **The operational trade** — for Org B specifically: does one vertically-scaled Dragonfly remove the Redis Cluster's complexity (no hash tags, no resharding, no CROSSSLOT)? Quantify what that's worth.
6. **The migration path** — how you'd move from the current engine to the recommended one with minimal risk (the protocol compatibility makes this a config change, but call out the gotchas).

**Acceptance criteria.**

- `notes/week-16/engine-benchmark-memo.md` exists, fits on roughly one-to-two pages (600–1000 words), and hits all six headings.
- The **measured numbers** section uses real figures from your own benchmark, not numbers quoted from a vendor blog.
- The recommendation commits to a position and ties it to *both* the measured numbers and the license.
- The license analysis is correct (the 2024–2025 saga: BSD → RSALv2/SSPL → Valkey → AGPL).
- Committed.

**Hint.** The strongest memos separate the *engineering* decision from the *license* decision and then recombine them. For Org A, Valkey often wins on license alone (BSD, drop-in) even if Dragonfly is faster — because the policy is a hard constraint. For Org B, the honest pitch for Dragonfly is "one box replaces your cluster; here's the throughput and here's the complexity you delete." Address the counter (Dragonfly is younger, smaller ecosystem) instead of ignoring it.

**Estimated time.** 1 hour.

---

## Problem 5 — Hash slots and hash tags

**Problem statement.** Using Exercise 3 (or `redis-cli CLUSTER KEYSLOT`), demonstrate the Redis Cluster slot mechanics for your cart's key schema. Show that the cart's related keys (cart, wishlist, recent) scatter across slots by default, then design a hash-tag scheme that co-locates the keys that must be operated on together, and prove they land on one slot.

**Acceptance criteria.**

- `notes/week-16/hash-slots.md` shows the slots for at least three related keys *without* a hash tag (different slots) and *with* a hash tag (same slot).
- You verify at least one slot against `redis-cli CLUSTER KEYSLOT` (it must match your computed value).
- You state which of your cart's operations need the keys co-located (and which don't), justifying the tag choice.
- Committed.

**Hint.** Choose the hash tag to be the entity all the related keys share — usually the cart/user id: `{42}:cart`, `{42}:wishlist`. Only `42` is hashed, so they share a slot. Don't over-tag: keys that are never operated on together don't need co-location, and over-co-location creates hot slots.

**Estimated time.** 35 minutes.

---

## Problem 6 — The cache is optional (degrade, don't die)

**Problem statement.** Prove your cached read path survives the cache being down. Under a steady load, kill the cache (`docker stop`) and capture that the read path still returns correct carts (degraded to slow, every read missing to the store) rather than failing. Then reason about the *cold-start stampede*: when the cache comes back empty, every key misses at once — what protects Postgres from that burst?

**Acceptance criteria.**

- `notes/week-16/cache-optional.md` shows the read path returning correct results with the cache stopped (slower, but no errors).
- You measure or describe the latency degradation (cache up vs cache down).
- You name the cold-start stampede risk and the defense (single-flight/XFetch on warm-up, plus the load shedding/circuit breaking that Week 18 formalizes).
- Committed.

**Hint.** If your read path *throws* when Redis is unreachable, wrap the cache calls so a cache error falls through to the store. The test: `docker stop redis`, hit the endpoint, get a correct (slow) cart. A cache that takes the service down when it fails is a liability, not an optimization.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Cache-vs-source-of-truth audit | 40 min |
| 2 — Induce and bound a stampede | 45 min |
| 3 — CDC-driven invalidation | 50 min |
| 4 — Redis-vs-Dragonfly memo (headline) | 1 h 0 min |
| 5 — Hash slots and hash tags | 35 min |
| 6 — Cache is optional | 35 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `cart-cache` [mini-project](./mini-project/README.md) is in the same workspace — Week 17 instruments this cache end-to-end and Week 18 wires its failure into the reliability story. Then take the [quiz](./quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Cache correctness audit (P1)** | 15 | Real `redis-cli` vs store evidence; the non-invalidating writer's stale read correctly flagged. |
| **Stampede (P2)** | 15 | Naive count scales with concurrency, hardened count bounded; in-process vs distributed distinction stated. |
| **CDC invalidation (P3)** | 20 | A manual `UPDATE` (uncontrolled writer) invalidates the cache; CDC justified over write-path invalidation. |
| **Engine benchmark memo (P4)** | 25 | Measured numbers; engineering *and* license analysis; committed recommendation; counter-argument addressed. |
| **Hash slots (P5)** | 15 | Slots verified against `CLUSTER KEYSLOT`; tag scheme co-locates the right keys; over-tagging avoided. |
| **Cache optional (P6)** | 10 | Read path survives a dead cache; cold-start stampede named with its defense. |

**90+** is portfolio-grade. **70–89** is solid but the memo likely lacks measured numbers or hedges on the recommendation. **Below 70** usually means Problem 1 or 3 was treated as a formality — they're the two that prove you understand the cache's *correctness* and how to keep it agreeing with the source of truth, which is the whole difference between adding Redis and operating a cache.
