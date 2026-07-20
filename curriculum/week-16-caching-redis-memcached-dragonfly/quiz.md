# Week 16 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 17. Answer key is at the bottom — don't peek.

---

**Q1.** In a look-aside (cache-aside) cache, what does the application do on a *write*?

- A) Update the cached value with the new data.
- B) Write to the store, then *invalidate* (delete) the cached key, so the next read reloads the fresh value.
- C) Nothing — the cache updates itself.
- D) Write only to the cache; the store is updated lazily.

---

**Q2.** Why does look-aside *delete* the cache key on a write rather than *updating* it with the new value?

- A) Deleting is faster than setting.
- B) Updating from the write path re-introduces a race (two concurrent writes can populate the cache in the opposite order they hit the store, leaving a permanently-stale value); deleting is idempotent — the worst case is an extra miss, never a wrong value.
- C) Redis doesn't support updates.
- D) There's no difference; both are equivalent.

---

**Q3.** Which cache pattern has the highest durability risk, and why?

- A) Look-aside — because it can miss.
- B) Read-through — because the cache loads on miss.
- C) Write-back (write-behind) — writes hit the cache and flush to the store asynchronously, so if the cache dies before a flush, those writes are lost.
- D) Write-through — because it writes twice.

---

**Q4.** What is a cache stampede (thundering herd)?

- A) Too many keys in the cache at once.
- B) A hot key expires and N concurrent requests all miss simultaneously and all run the load from the store at once, batching a burst of identical expensive queries onto the backend — the cache becomes a load *amplifier*.
- C) The cache running out of memory.
- D) A network partition between the app and the cache.

---

**Q5.** What does request coalescing (single-flight) do, and what's the essential detail that makes it correct?

- A) It caches more keys; the detail is the TTL.
- B) When N concurrent requests miss the same key, only *one* runs the load and the rest share its result; the essential detail is the **double-check inside the lock** (re-read the cache after acquiring the lock, since the leader may have just populated it).
- C) It shards the key across nodes.
- D) It retries failed loads.

---

**Q6.** What does probabilistic early expiration (XFetch) do that single-flight alone does not?

- A) It encrypts the cached values.
- B) It recomputes a hot key *before* its hard TTL with a probability that rises as expiry nears (and earlier for more-expensive loads), staggering the refresh so the key is (almost) never fully absent — so the synchronized miss never even forms.
- C) It replicates the key to other nodes.
- D) It compresses the value to save memory.

---

**Q7.** A system has many writers you don't all control (a service, a batch job, a DBA's manual `UPDATE`). Which invalidation strategy is the right one, and why?

- A) TTL-only — it needs no writer cooperation.
- B) Invalidate-on-write — every writer should remember.
- C) CDC / event-driven invalidation — invalidate from the source of truth's own change log (e.g., a Debezium stream), so *no writer* has to know the cache exists; any change produces an event that invalidates.
- D) Versioned keys only.

---

**Q8.** What is the defining architectural difference between Redis and Dragonfly?

- A) Dragonfly has no persistence.
- B) Redis's command-execution core is single-threaded (one CPU core per instance, shard to scale); Dragonfly is shared-nothing multi-threaded (scales vertically across all cores on one box, often eliminating the need for a cluster).
- C) Redis is multi-threaded; Dragonfly is single-threaded.
- D) Dragonfly uses a different wire protocol that Redis clients can't speak.

---

**Q9.** In Redis Cluster, how does a key map to a node?

- A) The key is hashed directly to a node by `hash(key) mod num_nodes`.
- B) `slot = CRC16(key) mod 16384`; slots are distributed across shards, so you hash the key to a slot, then look up which node owns that slot. Resharding moves *slots*, not keys.
- C) The client picks a node at random.
- D) All keys go to one primary; replicas are read-only copies.

---

**Q10.** Why do related keys sometimes need a hash tag `{...}` in Redis Cluster?

- A) To make them expire together.
- B) Multi-key operations (`MGET`, `MSET`, transactions) only work if all keys are in the same slot; a hash tag forces only the `{...}` substring to be hashed, so `{42}:cart` and `{42}:wishlist` land on the same slot and can be operated on together (otherwise: `CROSSSLOT` error).
- C) To compress the key names.
- D) Hash tags are required for all keys in a cluster.

---

**Q11.** Redis replication is asynchronous. What is the consequence on failover?

- A) None — replicas are always in sync.
- B) A write is acked before it reaches the replicas, so if the primary fails in that window and a replica is promoted, the un-replicated writes are *lost* (the lost-write window). For a cache this is usually fine because the source of truth heals it on the next miss.
- C) Writes are rejected during failover.
- D) The cluster refuses to fail over until all replicas catch up.

---

**Q12.** What changed with the Redis license in 2024–2025, and what are the open-source-clean alternatives?

- A) Nothing changed; Redis is still BSD.
- B) Redis moved from BSD to dual RSALv2/SSPL (source-available) in 2024, prompting the Linux Foundation's **Valkey** fork (BSD, drop-in OSS); Redis later added an AGPLv3 option (2025). For open-source-first, Valkey (BSD) and Dragonfly (BSL→Apache) are the clean choices.
- C) Redis became fully proprietary with no open option.
- D) Memcached was relicensed; Redis was unaffected.

---

**Q13.** Why must a cache be "optional" (the read path must survive the cache being down)?

- A) It doesn't — if the cache is down, the service should return errors.
- B) If the service *cannot answer* when the cache is down, you didn't add a cache — you added a second database with worse durability. Look-aside gives optionality for free: a dead cache means every read misses to the store (slow, but correct). You also cap the cold-cache stampede onto the store.
- C) Because caches are unreliable and should never be trusted.
- D) To save memory.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Write the store, then invalidate the key; the next read reloads. (Lecture 1 §1.1.)
2. **B** — Delete is race-tolerant (worst case an extra miss); update re-introduces an ordering race that can leave a permanently-stale value. (Lecture 1 §1.1.)
3. **C** — Write-back flushes asynchronously, so a cache death before flush loses writes. Never write-back the source of truth for money. (Lecture 1 §1.4.)
4. **B** — A hot key's synchronized expiry batches a herd of identical loads onto the backend; the cache amplifies load instead of shielding it. (Lecture 1 §3.1.)
5. **B** — One loader per key; the double-check-inside-the-lock is what stops the other waiters from re-loading after the leader populates. (Lecture 1 §3.2; Exercise 1.)
6. **B** — XFetch refreshes *before* the hard TTL, probability rising as expiry nears and earlier for costlier loads, so the key never fully expires and the herd never forms. (Lecture 1 §3.3.)
7. **C** — CDC/event-driven invalidation decouples invalidation from writers; the change log is the authoritative trigger. The only strategy that survives uncontrolled writers. (Lecture 1 §2.3.)
8. **B** — Redis single-threaded core (shard to scale) vs Dragonfly shared-nothing multi-threaded (vertical scale, often no cluster). (Lecture 2 §1.1, §1.3.)
9. **B** — `CRC16(key) mod 16384` → slot → node; resharding moves slot ranges (online), never rehashes keys. (Lecture 2 §2.1.)
10. **B** — Multi-key ops need one slot; the hash tag forces co-location; otherwise `CROSSSLOT`. (Lecture 2 §2.2.)
11. **B** — Async replication → a lost-write window on failover; tolerable for a cache because the source of truth heals it. (Lecture 2 §3.4.)
12. **B** — BSD → RSALv2/SSPL (2024) → Valkey fork (BSD) → AGPL option (2025); Valkey and Dragonfly are the OSS-clean picks. (Lecture 2 §4.)
13. **B** — A required cache is a second database with worse durability; look-aside degrades to slow-but-correct, and you cap the cold-cache stampede. (Lecture 1 §4.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
