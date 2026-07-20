# Week 16 — Resources

Every resource here is **free** and **open**. Redis (community), Valkey, Memcached, and Dragonfly all publish their docs openly; the foundational papers are freely available. No paywalled books are linked.

A note on versions and licenses, because this week is partly *about* them: **Redis** community is on the dual RSALv2/SSPL source-available license as of 2024 (with an AGPL option added in 2025); **Valkey** is the Linux Foundation's BSD-licensed fork and the drop-in OSS continuation; **Dragonfly** is BSL-1.1 (source-available, converts to Apache 2.0 after a delay). When this matters for an "open-source-first" choice — and it does — the docs below say so. Pin examples to **Redis 7.4+ / Valkey 8+ / Dragonfly v1.x**; the protocol is stable, only occasional command flags move.

## Required reading (work it into your week)

- **Redis — Client-side caching & caching patterns** — the canonical description of look-aside and the tracking-based invalidation:
  <https://redis.io/docs/latest/develop/reference/client-side-caching/>
- **"Caching at Scale With Redis"-style patterns / AWS caching strategies** — look-aside vs write-through vs write-behind, stated cleanly:
  <https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Strategies.html>
- **Vattani, Chierichetti & Lowenstein — "Optimal Probabilistic Cache Stampede Prevention"** (VLDB 2015) — the XFetch algorithm; read it for the stampede fix:
  <https://www.vldb.org/pvldb/vol8/p886-vattani.pdf>
- **Redis — Cluster specification** — the 16384 hash slots, CRC16, redirection, resharding:
  <https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/>
- **Dragonfly — Architecture / "Redis vs Dragonfly"** — why a multi-threaded, shared-nothing engine exists:
  <https://www.dragonflydb.io/docs/managing-dragonfly/architecture>

## The patterns and invalidation (skim, then refer back)

- **Redis — Keyspace notifications** — event-driven invalidation from Redis's own key-event stream:
  <https://redis.io/docs/latest/develop/use/keyspace-notifications/>
- **Redis — `SET` with `EX`/`NX`/`GET`** — the building blocks of TTL caching and lock-based coalescing:
  <https://redis.io/docs/latest/commands/set/>
- **Go `singleflight`** — the canonical request-coalescing primitive (`golang.org/x/sync/singleflight`):
  <https://pkg.go.dev/golang.org/x/sync/singleflight>
- **"Thundering herd problem"** — the failure mode named, with the mitigations catalogued:
  <https://en.wikipedia.org/wiki/Thundering_herd_problem>

## The engines

- **Redis — Documentation home** — data types, persistence, replication, eviction policies:
  <https://redis.io/docs/latest/>
- **Valkey — Documentation** — the BSD fork; commands and topology are Redis-compatible:
  <https://valkey.io/docs/>
- **Memcached — Wiki / "ProgrammingFAQ" and "ServerMaint"** — slab allocation, LRU, threading:
  <https://github.com/memcached/memcached/wiki>
- **Dragonfly — Documentation** — getting started, supported commands, the snapshotting model:
  <https://www.dragonflydb.io/docs>

## The licensing saga (read it once, understand the landscape)

- **Redis — "Redis Adopts Dual Source-Available Licensing" (2024)** — the move off BSD:
  <https://redis.io/blog/redis-adopts-dual-source-available-licensing/>
- **Valkey — "Why Valkey" / Linux Foundation announcement** — the BSD fork and its backers (AWS, Google, Oracle):
  <https://valkey.io/blog/>
- **Redis — "Redis is open source again" (AGPLv3, 2025)** — Redis adding an AGPL option:
  <https://redis.io/blog/agplv3/>
- **The operational takeaway**: for "open-source-first," Valkey (BSD) and Dragonfly (BSL→Apache) are the clean choices; Redis community is now source-available-or-AGPL. The *protocol* is the same; the *license* is the decision.

## Cluster, HA, and consistency

- **Redis — Cluster tutorial** — setting up, resharding, hash tags in practice:
  <https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/>
- **Redis — Sentinel** — monitored failover for HA (non-sharded):
  <https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/>
- **Redis — Replication** — asynchronous replication and the lost-write window on failover:
  <https://redis.io/docs/latest/operate/oss_and_stack/management/replication/>
- **Kyle Kingsbury (aphyr) — "Call me maybe: Redis"** — the classic Jepsen-style analysis of Redis failover consistency. Dated but conceptually essential for *why* a cache is not a database:
  <https://aphyr.com/posts/283-jepsen-redis>

## Tools you'll use this week

- **`redis-cli`** — `GET`/`SET`/`SETEX`/`TTL`/`DEL`, plus `INFO`, `SLOWLOG GET`, `CLUSTER NODES`, `CLUSTER KEYSLOT`, `-c` for cluster-following.
- **`k6`** — the load generator for the stampede exercise; drives the concurrency that makes a hot-key expiry hurt.
- **`redis-benchmark` / `memtier_benchmark`** — throughput/latency benchmarking for the engine comparison.
- **Docker / Kind** — run Redis, Valkey, Memcached, and Dragonfly side by side locally.
- **`go run` / `python3`** — the exercises are runnable in Go and Python.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Look-aside (cache-aside)** | The app checks the cache, on miss loads from the store and populates the cache, and on write invalidates the key. The app owns the cache logic. |
| **Read-through** | The cache itself loads from the store on a miss, behind a uniform read interface. The app just reads the cache. |
| **Write-through** | Writes go through the cache to the store synchronously; the cache is always fresh, writes are slower. |
| **Write-back (write-behind)** | Writes hit the cache and are flushed to the store asynchronously; fastest writes, real durability risk if the cache dies before flush. |
| **Cache stampede / thundering herd** | A hot key expires and N concurrent requests all miss and all hit the backend at once, possibly toppling it. |
| **Request coalescing (single-flight)** | N concurrent misses for the same key share *one* backend load; the rest wait for that result. |
| **Probabilistic early expiration (XFetch)** | Recompute a hot key *before* its hard TTL with a probability that rises as expiry nears, staggering the refresh so it never all-misses at once. |
| **TTL** | Time-to-live: how long a cached value is served before it expires. The blunt-instrument invalidation. |
| **Invalidation** | Removing or refreshing a cached value because the source of truth changed. The hard problem. |
| **Versioned key** | Encoding a version into the key (`cart:42:v8`) so a change writes a *new* key instead of invalidating the old — the "immutable cache" trick. |
| **Hash slot** | One of Redis Cluster's 16384 slots; `CRC16(key) mod 16384` decides which slot (and thus which shard) a key lives in. |
| **Hash tag** | The `{...}` substring in a key; only it is hashed, so `{user:42}:cart` and `{user:42}:wish` land on the same slot — required for multi-key ops. |
| **MOVED / ASK** | Cluster redirections: `MOVED` = this slot lives on another node permanently; `ASK` = it's migrating, ask the target this once. |
| **Sentinel** | Redis's HA system: monitors a primary, elects a replica on failure. HA without sharding. |
| **Slab allocator** | Memcached's memory model: fixed-size chunk classes to avoid fragmentation; the reason it's simple and predictable. |
| **Shared-nothing** | Dragonfly's model: each thread owns a slice of the keyspace with no shared locks, so it scales across cores where Redis is single-core-bound. |

---

*If a link 404s, please open an issue so we can replace it.*
