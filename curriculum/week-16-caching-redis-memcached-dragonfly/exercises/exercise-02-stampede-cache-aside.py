#!/usr/bin/env python3
# Exercise 2 — The Cache Stampede, Induced and Fixed (runnable)
#
# Goal: A COMPLETE, runnable cache-aside implementation that demonstrates the
#       thundering-herd / cache-stampede failure mode AND its two fixes:
#         1. single-flight request coalescing (one loader per key)
#         2. probabilistic early expiration (XFetch) so the key is refreshed
#            BEFORE its hard TTL, staggered, so the herd never forms.
#
#       Run it in --mode naive and watch a hot key's expiry produce a burst of
#       identical backend loads. Run it in --mode hardened and watch that burst
#       collapse to single digits.
#
#       This is the syllabus lab: "Induce a stampede with k6; show the fix."
#       (We use Python threads to induce concurrency so the file is self-contained;
#        the mini-project drives the same thing with k6 against the live service.)
#
# Estimated time: 60 minutes. Runnable.
#
# PREREQUISITES
#   pip install redis
#   A Redis (or Valkey, or Dragonfly) on localhost:6379 — OR pass --no-redis to
#   use an in-process dict as the cache (the stampede logic is identical; only
#   the store-of-the-cache differs).
#
# HOW TO USE THIS FILE
#   # Watch the herd: a hot key expires, N concurrent requests all miss and all load.
#   python3 exercise-02-stampede-cache-aside.py --mode naive --concurrency 200
#
#   # Watch the fix: single-flight + XFetch keep the backend load count tiny.
#   python3 exercise-02-stampede-cache-aside.py --mode hardened --concurrency 200
#
#   # Compare the two side by side:
#   for m in naive hardened; do
#     python3 exercise-02-stampede-cache-aside.py --mode $m --concurrency 200
#   done

import argparse
import json
import math
import random
import sys
import threading
import time

try:
    import redis  # type: ignore
except ImportError:
    redis = None


# ---------------------------------------------------------------------------
# The backend "store" — an expensive load we are trying to protect. Every call
# is counted so we can SEE the stampede as a number.
# ---------------------------------------------------------------------------
class CountingStore:
    def __init__(self, latency_s: float = 0.030):
        self.latency_s = latency_s
        self.loads = 0
        self._lock = threading.Lock()

    def load(self, cart_id: str) -> dict:
        with self._lock:
            self.loads += 1                      # count EVERY backend hit
        time.sleep(self.latency_s)               # simulate an expensive query/join
        return {"id": cart_id, "items": [{"sku": "A1", "qty": 2}], "v": 7}


# ---------------------------------------------------------------------------
# A tiny cache interface so the same code runs against Redis or an in-process
# dict. Values are packed with the metadata XFetch needs: (json, delta, expiry).
# ---------------------------------------------------------------------------
class DictCache:
    """In-process cache with explicit TTL handling (for --no-redis)."""
    def __init__(self):
        self._d: dict[str, tuple[str, float]] = {}   # key -> (packed, hard_expiry)
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            entry = self._d.get(key)
            if entry is None:
                return None
            packed, hard_expiry = entry
            if time.time() >= hard_expiry:
                self._d.pop(key, None)               # hard-expired -> a real miss
                return None
            return packed

    def set(self, key: str, packed: str, ttl: float):
        with self._lock:
            self._d[key] = (packed, time.time() + ttl)

    def delete(self, key: str):
        with self._lock:
            self._d.pop(key, None)


class RedisCache:
    def __init__(self):
        self.r = redis.Redis(decode_responses=True)
        self.r.ping()

    def get(self, key: str):
        return self.r.get(key)

    def set(self, key: str, packed: str, ttl: float):
        # +10s margin so XFetch can refresh slightly past the logical expiry.
        self.r.set(key, packed, ex=int(ttl) + 10)

    def delete(self, key: str):
        self.r.delete(key)


def pack(value: dict, delta: float, expiry: float) -> str:
    return json.dumps({"v": value, "delta": delta, "expiry": expiry})


def unpack(packed: str) -> tuple[dict, float, float]:
    o = json.loads(packed)
    return o["v"], o["delta"], o["expiry"]


# ---------------------------------------------------------------------------
# NAIVE cache-aside: no coalescing, no early expiration. This is the stampede.
# ---------------------------------------------------------------------------
def get_naive(cache, store: CountingStore, key: str, ttl: float) -> dict:
    packed = cache.get(key)
    if packed is not None:
        value, _, _ = unpack(packed)
        return value                                 # HIT
    # MISS: every concurrent caller does this independently -> the herd.
    value = store.load(key)
    cache.set(key, pack(value, 0.0, time.time() + ttl), ttl)
    return value


# ---------------------------------------------------------------------------
# HARDENED cache-aside: single-flight coalescing + probabilistic early
# expiration (XFetch). The two fixes from Lecture 1 §3.2-3.3.
# ---------------------------------------------------------------------------
_sf_locks: dict[str, threading.Lock] = {}
_sf_guard = threading.Lock()


def _single_flight_lock(key: str) -> threading.Lock:
    with _sf_guard:
        return _sf_locks.setdefault(key, threading.Lock())


def get_hardened(cache, store: CountingStore, key: str, ttl: float, beta: float = 1.0) -> dict:
    packed = cache.get(key)
    if packed is not None:
        value, delta, expiry = unpack(packed)
        # XFetch test: as `now` approaches `expiry`, the chance of an early
        # recompute rises; the more expensive the load (delta large), the
        # earlier it starts. -ln(rand) is a positive, growing-for-small-draws term.
        if time.time() - delta * beta * math.log(random.random()) < expiry:
            return value                             # still fresh enough; serve it
        # else: probabilistic early refresh fired -> fall through to recompute,
        #       but coalesce so only ONE caller actually recomputes.

    # Either a real miss or an early-refresh trigger. Coalesce the recompute.
    lock = _single_flight_lock(key)
    if not lock.acquire(blocking=False):
        # Someone else is already recomputing. Serve the (possibly slightly stale)
        # current value if we have one, else briefly wait and re-read.
        if packed is not None:
            value, _, _ = unpack(packed)
            return value                             # serve stale while the leader refreshes
        with lock:                                    # real miss with no value: wait for the leader
            fresh = cache.get(key)
            if fresh is not None:
                value, _, _ = unpack(fresh)
                return value
            # leader hasn't finished; fall through and load (rare)
    try:
        # DOUBLE-CHECK under the lock: the leader may have just populated.
        fresh = cache.get(key)
        if fresh is not None:
            value, delta, expiry = unpack(fresh)
            # If it's genuinely fresh (not just an XFetch trigger), use it.
            if time.time() < expiry - delta:
                return value
        start = time.time()
        value = store.load(key)                       # the ONE recompute
        delta = time.time() - start
        cache.set(key, pack(value, delta, time.time() + ttl), ttl)
        return value
    finally:
        if lock.locked():
            lock.release()


# ---------------------------------------------------------------------------
# The harness: warm the key, let it (nearly) expire, then fire a concurrent herd.
# ---------------------------------------------------------------------------
def run(mode: str, concurrency: int, ttl: float, use_redis: bool) -> int:
    store = CountingStore(latency_s=0.030)
    cache = RedisCache() if use_redis else DictCache()
    key = "cart:trending"
    cache.delete(key)

    getter = get_naive if mode == "naive" else get_hardened

    # Warm the cache, then drive it past its logical expiry so the herd hits a
    # cold (naive) or XFetch-protected (hardened) key.
    getter(cache, store, key, ttl)                    # initial populate
    store.loads = 0                                   # reset the counter AFTER warm-up
    time.sleep(ttl + 0.05)                            # let it hard-expire (naive)
    # (For hardened/XFetch, the value would normally be refreshed BEFORE this in a
    #  steady read stream; we force a cold start here to compare worst cases fairly.)

    results: list[dict] = []
    res_lock = threading.Lock()
    # A barrier so EVERY worker arrives at the get() call together. Without this,
    # thread-start latency lets early threads populate the cache before later
    # threads even begin, masking the herd. The barrier makes the miss synchronized,
    # which is the realistic hot-key-expiry condition.
    gate = threading.Barrier(concurrency)

    def worker():
        gate.wait()                                   # release all workers at once
        v = getter(cache, store, key, ttl)
        with res_lock:
            results.append(v)

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - t0

    print(f"mode={mode:9s} concurrency={concurrency:4d}  "
          f"backend_loads={store.loads:4d}  "
          f"wall={elapsed*1000:6.1f}ms  answered={len(results)}")
    # A correct run answers EVERY request regardless of mode.
    assert len(results) == concurrency, "every request must be answered"
    return store.loads


def main() -> int:
    p = argparse.ArgumentParser(description="Cache stampede: induced and fixed.")
    p.add_argument("--mode", choices=["naive", "hardened"], default="naive")
    p.add_argument("--concurrency", type=int, default=200)
    p.add_argument("--ttl", type=float, default=0.5, help="seconds (small for a fast demo)")
    p.add_argument("--no-redis", action="store_true", help="use an in-process cache")
    args = p.parse_args()

    use_redis = (redis is not None) and (not args.no_redis)
    if not use_redis and not args.no_redis:
        print("(redis package not importable; falling back to in-process cache)", file=sys.stderr)

    loads = run(args.mode, args.concurrency, args.ttl, use_redis)
    return 0 if loads >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
#   $ python3 exercise-02-stampede-cache-aside.py --mode naive --concurrency 200
#   mode=naive     concurrency= 200  backend_loads= 200  wall=  35.x ms  answered=200
#                                     ^^^^^^^^^^^^^^^^^^^ THE HERD: 200 misses -> ~200 loads
#
#   $ python3 exercise-02-stampede-cache-aside.py --mode hardened --concurrency 200
#   mode=hardened  concurrency= 200  backend_loads=   1  wall=  3x.x ms  answered=200
#                                     ^^^^^^^^^^^^^^^^^^^ single-flight: ~200 misses -> 1 load
#
#   The naive backend_loads scales with concurrency (the stampede). The hardened
#   count stays ~1 (single-flight coalesces; XFetch would, in a live read stream,
#   keep the key from ever fully expiring so the herd never even forms).
#
# THE LESSON: A fixed TTL on a hot key synchronizes every concurrent miss into one
# burst of identical backend loads -- the cache becomes a load AMPLIFIER. Two
# fixes: single-flight (one loader per key per process; a distributed lock for one
# loader fleet-wide) and XFetch (probabilistic early refresh so the key is renewed
# before it hard-expires, staggered, so the synchronized miss never happens).
#
# ACCEPTANCE CRITERIA
#   [ ] --mode naive shows backend_loads roughly EQUAL to --concurrency (the herd).
#   [ ] --mode hardened shows backend_loads in the single digits regardless of
#       --concurrency (coalescing collapses the herd to ~1 load).
#   [ ] EVERY request is answered in both modes (answered == concurrency) -- the fix
#       must not drop requests, only deduplicate the backend loads.
#   [ ] You can explain why XFetch's recompute probability RISES as expiry nears and
#       why a more-expensive load (larger delta) starts refreshing EARLIER.
# -----------------------------------------------------------------------------
