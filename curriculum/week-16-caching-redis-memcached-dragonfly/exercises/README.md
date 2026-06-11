# Week 16 — Exercises

Three focused drills on a real cache in front of the `cart` read path. Each takes 45–90 minutes. Do them in order — exercise 1 (look-aside + coalescing) builds the cache; exercise 2 (the stampede) breaks and then hardens it; exercise 3 (cluster slots) is the sharding mechanics you need before you can scale it. Run everything against your **`cart`** service from Phase 1/3 with its Postgres read path (or, if your service isn't ready, the standalone stand-in each exercise names).

## Index

1. **[Exercise 1 — Look-aside with request coalescing](exercise-01-look-aside-and-coalescing.md)** — add a look-aside (cache-aside) cache to the cart read path with a TTL and invalidate-on-write, then add single-flight coalescing so N concurrent misses produce one backend load. Prove the cache agrees with Postgres after a write. (~75 min, guided)
2. **[Exercise 2 — The stampede, induced and fixed](exercise-02-stampede-cache-aside.py)** — a runnable cache-aside implementation. Induce a thundering herd with concurrency, count the backend queries, then turn on single-flight + probabilistic early expiration (XFetch) and watch the query count collapse from thousands to single digits. (~60 min, runnable)
3. **[Exercise 3 — Redis Cluster hash slots](exercise-03-cluster-hash-slots.go)** — compute `CRC16(key) mod 16384` yourself, prove your computation matches `CLUSTER KEYSLOT`, and demonstrate that a hash tag `{...}` forces related keys onto the same slot (so multi-key ops work). (~60 min, runnable)

## How to work the exercises

- Have a **Redis** (or Valkey) instance running — `docker run -p 6379:6379 redis:7` — and `redis-cli` on your path. Exercise 3 also needs a `redis-cli` that can talk to a cluster (or just uses `CLUSTER KEYSLOT` against a single node, which works).
- Have your **`cart`** service deployable with a Postgres read path. If it's not ready, each exercise names a self-contained stand-in (a fake "slow store" function) so the cache mechanics still work.
- **Read the cache *and* the store after every write.** The recurring discipline this week is proving the cache *agrees with the source of truth* — `redis-cli GET` the key, then confirm it matches (or correctly missed-then-reloaded) what Postgres holds. A cache you don't verify against the store is a cache you can't trust.
- When the cache "isn't helping," check the **hit rate** first (`redis-cli INFO stats | grep keyspace`), then the **TTL** (`redis-cli TTL <key>`), then the **query count** at the store. In that order.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match, you're not done.

## Running the exercises

The `.py` exercise is a standard Python script:

```bash
pip install redis
python3 exercise-02-stampede-cache-aside.py --mode naive    # watch the herd
python3 exercise-02-stampede-cache-aside.py --mode hardened  # watch it fixed
```

The `.go` exercise is a standard Go program:

```bash
go run exercise-03-cluster-hash-slots.go
# prints slots for sample keys, proves hash-tag co-location, and (if a cluster is
# reachable) cross-checks against CLUSTER KEYSLOT.
```

The header of each file lists the exact prerequisites. If your Phase 1/3 cart isn't wired to Postgres yet, the file's header points you at the minimal stand-in store.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-16` to compare.
