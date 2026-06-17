# Exercise 1 — Look-aside with Request Coalescing

**Goal:** Put a correct look-aside (cache-aside) cache in front of the `cart` read path: a TTL on cached values, invalidate-on-write, and single-flight request coalescing so that a herd of concurrent misses for the same key produces *one* database load, not N. You will train the single most important caching habit of the week: proving the cache *agrees with Postgres* after a write, instead of assuming the invalidation fired.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need a Redis (or Valkey) instance and your `cart` service with a Postgres read path.

```bash
docker run -d --name redis -p 6379:6379 redis:7    # or valkey/valkey:8
redis-cli ping                                      # PONG
```

**Fallback if your Phase 1/3 cart isn't wired to Postgres yet.** Use a stand-in "slow store" — a function that sleeps 20 ms (simulating a Postgres query) and returns a cart dict. Wherever this exercise says "load from Postgres," call the stand-in. The cache mechanics are identical.

```python
import time
def slow_store_load(cart_id: str) -> dict:
    time.sleep(0.020)                               # simulate a 20ms DB query
    return {"id": cart_id, "items": [{"sku": "A1", "qty": 2}], "v": 7}
```

---

## Step 1 — The naive look-aside read

Implement the read: check the cache, on miss load from the store and populate with a TTL.

```python
import json, redis
r = redis.Redis(decode_responses=True)

def get_cart(cart_id: str) -> dict:
    key = f"cart:{cart_id}"
    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)                   # HIT
    cart = slow_store_load(cart_id)                 # MISS -> load from source of truth
    r.set(key, json.dumps(cart), ex=300)            # populate, 5-minute TTL
    return cart
```

Verify a miss then a hit:

```bash
redis-cli DEL cart:42
python3 -c "import yourmodule; print(yourmodule.get_cart('42'))"   # MISS (slow, ~20ms)
redis-cli GET cart:42        # the value is now cached
redis-cli TTL cart:42        # ~300, counting down
python3 -c "import yourmodule; print(yourmodule.get_cart('42'))"   # HIT (fast, <1ms)
```

---

## Step 2 — Invalidate on write (delete, don't update)

The write path updates the store, then *deletes* the cache key. Deleting (not updating) is the race-tolerant choice — the worst case is an extra miss, never a wrong value.

```python
def update_cart(cart_id: str, items: list) -> None:
    store_update(cart_id, items)                     # Postgres (or stand-in) first
    r.delete(f"cart:{cart_id}")                       # invalidate; next read reloads fresh
```

Prove the invalidation is *real* — the canonical "cache agrees with the source of truth" check:

```bash
redis-cli GET cart:42        # serves v7
# ... call update_cart('42', new_items) which bumps the store to v8 ...
redis-cli GET cart:42        # (nil)  <-- the invalidation fired
python3 -c "import yourmodule; print(yourmodule.get_cart('42')['v'])"   # 8 -> reloaded fresh
```

If the key is `(nil)` after the write and the next read returns v8, your invalidation works. If `GET` still returns v7, your write path didn't invalidate — that's the bug the challenge is built around.

---

## Step 3 — Induce the herd (the problem coalescing solves)

Fire many concurrent reads for the *same* key right after deleting it, and count the store loads. Without coalescing, every concurrent miss runs its own load.

```python
import threading
load_count = 0
def slow_store_load_counted(cart_id):
    global load_count
    load_count += 1                                  # count every backend load
    time.sleep(0.020)
    return {"id": cart_id, "v": 7}

r.delete("cart:42")
threads = [threading.Thread(target=lambda: get_cart("42")) for _ in range(50)]
for t in threads: t.start()
for t in threads: t.join()
print("backend loads:", load_count)                  # WITHOUT coalescing: ~50 (the herd!)
```

50 concurrent misses → ~50 identical database queries. On a hot key under real load that's thousands. That is the stampede in miniature.

---

## Step 4 — Add single-flight coalescing

Coalesce concurrent misses so the loader runs **once** per key. A per-key lock (or a single-flight library) makes the first misser load while the rest wait and then read the just-populated value.

```python
import threading
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

def _key_lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())

def get_cart_coalesced(cart_id: str) -> dict:
    key = f"cart:{cart_id}"
    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)                    # HIT, no lock needed
    with _key_lock(key):                             # only one loader per key at a time
        cached = r.get(key)                          # DOUBLE-CHECK: someone may have just loaded
        if cached is not None:
            return json.loads(cached)
        cart = slow_store_load_counted(cart_id)      # the ONE load
        r.set(key, json.dumps(cart), ex=300)
        return cart
```

Re-run the 50-thread herd against `get_cart_coalesced`:

```python
load_count = 0
r.delete("cart:42")
threads = [threading.Thread(target=lambda: get_cart_coalesced("42")) for _ in range(50)]
for t in threads: t.start()
for t in threads: t.join()
print("backend loads:", load_count)                  # WITH coalescing: 1
```

The **double-check inside the lock** is essential: the first thread loads and populates; every other thread, on acquiring the lock, finds the value already there and skips the load. 50 misses → **1** backend query.

> **The lock here is per-process.** For a fleet of cart pods, each pod coalesces its own herd (10 pods → 10 loads, not 5,000). To get to *one* load across the whole fleet, you add a *distributed* lock in Redis (`SET lock:cart:42 <token> NX EX 5`) so only one pod loads. The exercise stays in-process; the mini-project adds the distributed version. Name the distinction in your writeup.

---

## Step 5 — Prove the cache is optional (degrade, don't die)

A cache must be optional: if Redis is down, reads should get *slower* (every read misses to the store), not *fail*. Stop Redis and confirm the read path still returns correct carts.

```bash
docker stop redis
python3 -c "import yourmodule; print(yourmodule.get_cart('42'))"
# Should still return a cart (loaded straight from the store) — slow, but correct.
docker start redis
```

If your read path *throws* when Redis is unreachable, wrap the cache calls so a cache error falls through to the store. A cache that takes the service down when it fails is not a cache — it's a second database with worse durability.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] A cache miss is slow (loads from the store) and a subsequent hit is fast (served from Redis), confirmed with timing and `redis-cli GET`/`TTL`.
- [ ] A write invalidates the key: `redis-cli GET` returns `(nil)` after the write, and the next read reloads the fresh version (the cache *agrees with the store*).
- [ ] Without coalescing, 50 concurrent misses produce ~50 backend loads; **with** coalescing they produce **1** (the double-check-inside-lock is present).
- [ ] With Redis stopped, the read path still returns correct carts (degrades to slow, not down).
- [ ] You can state, in one sentence, why look-aside *deletes* (not updates) the cache on write.

---

## Stretch

- Replace the per-process lock with a **distributed lock** in Redis (`SET lock:cart:<id> <token> NX EX 5`, release with a check-and-delete Lua script) so the herd is coalesced across *all* pods, not just within one. Confirm 10 simulated pods produce 1 load, not 10.
- Add a **hit-rate metric**: count hits and misses, print the ratio. This is the number Week 17 turns into a first-class Prometheus metric with an exemplar to the trace of a slow miss.
- Switch the backing store from Redis to **Dragonfly** (`docker run -p 6379:6379 docker.dragonflydb.io/dragonflydb/dragonfly`) with *no code change* and confirm every step still passes — the protocol compatibility that makes the Friday migration a benchmark, not a rewrite.

---

When this feels comfortable, move to [Exercise 2 — The stampede, induced and fixed](./exercise-02-stampede-cache-aside.py).
