# Challenge 1 — The Stale Cart That Wouldn't Die

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. A customer reports their cart is wrong: they removed an item an hour ago, but the app still shows it. Support escalates because it's not one customer — there's a trickle of "my cart is wrong" tickets, all the same shape. You check, and the *database is correct*: `SELECT * FROM carts WHERE id = 42` shows the item is gone. But the API returns the old cart with the item still in it. Someone on the team has already noticed that **restarting the cart service makes the complaints stop for a while**, and is now suggesting "let's just restart it on a cron" — which would make the symptom intermittent and the root cause permanent.

Your job: prove the **cache disagrees with the source of truth**, find *which* write path is updating Postgres without invalidating the cache, name the mechanism, and fix it correctly — *not* by lowering the TTL (which trades a correctness bug for a load problem and still serves stale data for the TTL window), and *not* by restarting on a cron (which hides the bug).

This mirrors the most common real caching on-call scenario there is. A read path caches correctly and invalidates on *its own* writes. Then a *second* writer — a batch job, an admin tool, another service, a DBA's manual `UPDATE` — changes the same rows directly and never touches the cache. The cache now holds a value the source of truth has moved past, and it serves that stale value until the TTL expires (which is why a restart "fixes" it: a restart cold-starts the cache, so the next read reloads fresh — temporarily).

## The harness

Reproduce it. You have the look-aside cart cache from Exercise 1: reads cache with a 1-hour TTL, the cart-service write path invalidates on write. Now introduce the second writer — a "promotions" job that removes discontinued items straight in Postgres and forgets the cache:

```python
# cart_service.py — the CORRECT read/write path (invalidates on its own writes).
def get_cart(cart_id):
    key = f"cart:{cart_id}"
    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)              # HIT
    cart = db.query_cart(cart_id)              # MISS -> source of truth
    r.set(key, json.dumps(cart), ex=3600)      # 1-HOUR TTL (the stale window)
    return cart

def cart_service_update(cart_id, items):
    db.update_cart(cart_id, items)
    r.delete(f"cart:{cart_id}")                # this path DOES invalidate

# promotions_job.py — the SECOND writer. Runs hourly. Updates Postgres DIRECTLY
# and NEVER invalidates the cache. THIS is the bug.
def remove_discontinued_items():
    for cart_id in db.carts_with_discontinued_items():
        db.remove_discontinued(cart_id)        # writes Postgres...
        # ...and never calls r.delete(f"cart:{cart_id}")  <-- the missing line
```

```bash
# Reproduce the stale read:
python3 -c "import cart_service; print(cart_service.get_cart('42'))"   # caches v7 (with item)
python3 -c "import promotions_job; promotions_job.remove_discontinued_items()"  # DB -> v8 (item gone)
python3 -c "import cart_service; print(cart_service.get_cart('42'))"   # STILL v7! cache is stale
redis-cli GET cart:42        # shows the stale v7 the promotions job didn't invalidate
```

You now have the bug. Diagnose it from the outside before reading the fix section.

## Your task

Produce a diagnosis and a fix with these parts:

1. **Symptom** — exactly what you observe: the API returns a cart that disagrees with Postgres, the TTL on the stale key (`redis-cli TTL cart:42` shows time remaining — so it's not expired, it's *wrong*), and the fact that a restart "fixes" it temporarily.
2. **Proof the cache disagrees with the source of truth** — the canonical check: `redis-cli GET cart:42` vs `SELECT … FROM carts WHERE id = 42`. They differ. The cached value is *older* than the database. (Quote both.)
3. **Find the writer that skipped invalidation** — the cart-service write path invalidates; the read path is correct. So *something else* wrote the database. Audit every code path (and human/operational path) that writes `carts`. The promotions job is the culprit: it writes Postgres and never deletes the cache key.
4. **The mechanism** — name it precisely: look-aside invalidation-on-write requires *every* writer to invalidate; a writer that bypasses the cache (a batch job, an admin tool, another service, a manual `UPDATE`) leaves the cache holding a value the source of truth has moved past, and the TTL is the only thing that eventually heals it.
5. **The fix** — the *correct* one, not the band-aid. The robust fix is **CDC-driven invalidation**: invalidate from the source of truth's own change log (the Week 14 Debezium stream), so *any* writer — including the promotions job and a DBA's manual `UPDATE` — produces a change event that invalidates the cache, with no writer needing to know the cache exists. (The narrow fix — "add `r.delete` to the promotions job" — is correct *for this writer* but doesn't survive the next forgetful writer; say so.)

You must reach the diagnosis with **at least two** independent signals — e.g., the `redis-cli GET` vs `SELECT` disagreement *and* the non-expired TTL proving it's stale-not-missing, or the disagreement *and* the audit finding the second writer. One signal is a guess; two is a diagnosis.

## The fix, applied

The narrow fix (correct for this writer, fragile against the next):

```python
def remove_discontinued_items():
    for cart_id in db.carts_with_discontinued_items():
        db.remove_discontinued(cart_id)
        r.delete(f"cart:{cart_id}")            # the missing invalidation, added
```

The robust fix (CDC-driven — survives ALL writers, the senior answer):

```python
# A consumer of the Debezium stream off Postgres (Week 14) invalidates the cache
# from the SOURCE OF TRUTH's change log. No writer has to know the cache exists.
for event in debezium_consumer:                # CDC stream off the carts table
    if event.table == "carts" and event.op in ("u", "d"):
        cart_id = (event.after or event.before)["id"]
        r.delete(f"cart:{cart_id}")            # any writer's change -> this fires
```

Re-run the harness with CDC invalidation running, and the promotions job's direct write now produces a change event that deletes the cache key — so the next read reloads v8:

```bash
python3 -c "import promotions_job; promotions_job.remove_discontinued_items()"
# ... the CDC consumer sees the carts UPDATE and DELETEs cart:42 ...
redis-cli GET cart:42        # (nil) -> invalidated from the change log
python3 -c "import cart_service; print(cart_service.get_cart('42')['v'])"   # 8 -> fresh
```

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You quote `redis-cli GET cart:42` AND the `SELECT … FROM carts WHERE id = 42` showing the cache holds an *older* value than Postgres (the cache-vs-source-of-truth disagreement).
- [ ] You quote `redis-cli TTL cart:42` showing time remaining — proving the value is *stale*, not *expired/missing* (it would heal on its own if it were expired).
- [ ] You identify the second writer (the promotions job) as the path that skipped invalidation, and explain why the cart-service write path being correct misled the team.
- [ ] Your fix is **CDC-driven invalidation** (with the narrow per-writer fix named as the fragile alternative), NOT lowering the TTL and NOT a restart cron. A `cdc-invalidator.py` (or equivalent) is checked in.
- [ ] Committed to your Week 16 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The two wrong "fixes" you must NOT write:

- **"Lower the TTL to 10 seconds."** This *masks* the bug by shrinking the stale window — but it still serves stale data for up to 10 seconds after every promotions-job write, it multiplies your cache-miss rate and database load (defeating the cache's purpose), and it does nothing about the *next* writer that forgets to invalidate. Shortening the TTL trades a correctness bug for a load problem and only *reduces* the correctness bug rather than fixing it. The TTL is a backstop, not the invalidation strategy.
- **"Restart the service on a cron."** This hides the symptom (a cold cache reloads fresh) while leaving the root cause — a writer that doesn't invalidate — fully in place. It's the caching equivalent of rebooting the server to clear a memory leak. The complaints come back the moment the cache re-warms with stale values, now on an unpredictable schedule that's *harder* to debug.

A related real-world cousin worth naming in your writeup: the **stale-set race** (Lecture 1 §3.4) — even a *correct* invalidate-on-write has a narrow window where a slow reader can repopulate the cache with a value it read just before a write. It's the same family — cache and source of truth disagreeing — and the same backstop (a TTL) plus versioned keys closes it. Naming it shows you understand that invalidation is leaky even when every writer cooperates.

## Stretch

- Wire the **real Week 14 Debezium stream** (if you have it running) so the invalidation is genuinely CDC-driven, not simulated. Confirm a *manual* `UPDATE carts SET … WHERE id = 42` in `psql` — a writer that no application code knows about — still invalidates the cache. That's the proof CDC invalidation survives writers you don't control.
- Add a **versioned-key** variant: cache under `cart:42:v<version>` where the version comes from a cheap counter. Show that a write that bumps the version makes the old key simply unreferenced (it TTLs out) with *no* invalidation race at all — the immutable-cache trick that sidesteps the whole problem.
- Add an **audit assertion** to a test suite: after any write path runs, assert `redis-cli GET` agrees with the database (or is `(nil)`). This is the "cache agrees with the source of truth" check turned into a regression test, so a future forgetful writer is caught in CI, not by a customer.

## Why this matters

Every system with a cache hits this wall: the read path caches correctly, and then a *second* writer — always there's a second writer — changes the data without telling the cache. The difference between a cache you can trust and a cache that quietly serves wrong answers is whether *someone* can stand in front of the room and say "the cache is stale because the promotions job writes the DB without invalidating; the fix is CDC-driven invalidation off the change log, not a shorter TTL." When you defend your `cart-cache` mini-project, "I invalidate from the source of truth's change log, so no writer can leave the cache stale" is the line that says you've operated a cache, not just installed one.
