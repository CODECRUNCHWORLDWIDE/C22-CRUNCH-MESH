# Challenge 1 — The Contract That Passed But Prod Broke

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. The marketplace is double-charging customers. Support has three tickets this morning: a customer placed one order and was charged twice. The finance team is escalating. And here is what makes it maddening: **every contract test is green.** The Pact broker is a wall of checkmarks. `order → inventory` verified. `order → payment` verified. `can-i-deploy` said yes for every service deployed this week. The build that shipped the bug was green on every gate you built last week.

A colleague is already drafting a message that says "contract testing doesn't work, it gave us false confidence, let's rip it out." That message is wrong, and you have to explain *why* it's wrong — not to defend Pact, but because the team is about to throw away a tool that's doing exactly its job and blame it for a bug it was never designed to catch.

Your job: prove the double-charge is real, explain precisely *why* the green pacts could not catch it, and write the test that *does* catch it — a property-based test of the idempotency semantics. "The contracts are wrong" is not the answer. The contracts are *correct and insufficient*, and the difference is the whole point.

## The setup

The relevant boundary is `order → payment`. The `order` service, on receiving an order, calls `payment.Charge(order_id, amount, idempotency_key)`. The contract — the pact `order` published and `payment` verified — looks like this:

```json
{
  "consumer": { "name": "order-service" },
  "provider": { "name": "payment-service" },
  "interactions": [
    {
      "description": "charge an order",
      "providerState": "the order ord-1 has not been charged",
      "request": {
        "method": "POST", "path": "/v1/charge",
        "body": { "order_id": "ord-1", "amount": 100, "idempotency_key": "idem-1" }
      },
      "response": {
        "status": 200,
        "body": { "charge_id": "ch-1", "status": "charged", "amount": 100 }
      }
    }
  ]
}
```

That pact is green. `payment` verifies it: given an uncharged order, a `POST /v1/charge` returns a `charged` response with the right shape. Perfect.

Here is the `payment` provider's *actual* charge handler (the bug is in here — it is not in the pact, and that is the lesson):

```python
# payment_service.py — the REAL provider behind the green pact
charges = {}            # charge_id -> record
seen_keys = set()       # idempotency keys we've processed

def charge(order_id: str, amount: int, idempotency_key: str) -> dict:
    # Intent: idempotent. If we've seen this key, return the existing charge.
    if idempotency_key in seen_keys:
        existing = next(c for c in charges.values() if c["key"] == idempotency_key)
        return {"charge_id": existing["id"], "status": "charged", "amount": amount}

    charge_id = f"ch-{len(charges) + 1}"
    charges[charge_id] = {"id": charge_id, "order_id": order_id,
                          "amount": amount, "key": idempotency_key}
    # BUG IS LURKING HERE — find it. (Hint: think about the ORDER of these two lines,
    # and what happens if the same key arrives twice CONCURRENTLY, or if the process
    # restarts between them. The pact sends each key exactly once, sequentially.)
    seen_keys.add(idempotency_key)
    return {"charge_id": charge_id, "status": "charged", "amount": amount}
```

And the `order` service retries on timeout (Week 7/8 discipline — gRPC `retryOn: unavailable`), so under load `payment.Charge` is sometimes called *twice with the same idempotency key*, concurrently, when the first call is slow.

## Your task

Produce a diagnosis and a fix with these parts:

1. **Prove the break is real.** Reproduce the double-charge: call `charge("ord-1", 100, "idem-1")` *twice concurrently* (two threads) and show that *two* charge records are created — the customer is charged twice for one idempotency key. Quote the resulting `charges` dict showing two `ch-*` records with the same `key`.

2. **Explain why the pact couldn't catch it.** State precisely what the pact verified and why that's orthogonal to the bug. The pact sends each idempotency key **once, sequentially**, and checks the **response shape**. The bug only manifests on a **duplicate, concurrent** delivery — an input the pact never sends and a property (idempotency-under-duplication) the pact never asserts. The pact proved the *shape of one charge*; the bug is in the *semantics of two*. Name the gap: contract testing verifies the agreed interactions' shape; it does not verify business invariants over inputs no consumer declared.

3. **Write the property test that catches it.** A Hypothesis (or proptest/gopter) property: *for any sequence of charge calls that includes duplicates and interleavings of the same idempotency key, exactly one charge record exists per key.* Generate sequences of `["charge", "charge-duplicate", "concurrent-duplicate"]`, run them against the handler, and assert the invariant. Show it **fails** on the buggy handler with a shrunk counterexample, then **passes** on your fix.

4. **The fix.** Make `charge` actually idempotent under concurrency: check-and-insert the idempotency key **atomically** (a unique constraint on the key in the real Postgres `payment` table, or a lock/compare-and-swap in this toy), so a second concurrent call with the same key cannot create a second charge. In the capstone's real `payment` (Temporal workflow + Postgres), this is a unique index on `idempotency_key` and an `ON CONFLICT DO NOTHING` — the database enforces the invariant the application code raced on.

5. **Where each test belongs.** State the division of labor you'll defend in the review: the **pact** locks the charge *boundary shape* (order and payment agree on the request/response), the **property test** proves the idempotency *semantic* (no double-charge under duplication), and the **Week 22 chaos drill** proves it survives a real broker-loss-and-redeliver in-cluster. Three tests, three guarantees, no one of them sufficient alone.

You must reach the diagnosis with **at least two** independent signals — e.g., the reproduced double-charge in the `charges` dict *and* the property test's shrunk failing sequence. One is an anecdote; two is a diagnosis.

## The fix, sketched

```python
import threading
_lock = threading.Lock()

def charge(order_id, amount, idempotency_key):
    with _lock:                          # atomic check-and-insert (toy version)
        if idempotency_key in seen_keys: # real version: DB unique constraint + ON CONFLICT
            existing = next(c for c in charges.values() if c["key"] == idempotency_key)
            return {"charge_id": existing["id"], "status": "charged", "amount": amount}
        charge_id = f"ch-{len(charges) + 1}"
        seen_keys.add(idempotency_key)   # insert key BEFORE releasing the lock
        charges[charge_id] = {"id": charge_id, "order_id": order_id,
                              "amount": amount, "key": idempotency_key}
        return {"charge_id": charge_id, "status": "charged", "amount": amount}
```

The real fix is the database, not a process lock: a `UNIQUE` index on `idempotency_key` makes the second insert fail at the storage layer, which is the only place the invariant can be enforced across replicas. The lock above only works in one process; the capstone's `payment` runs multiple replicas, so the constraint must live where all replicas meet — the row.

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You reproduce the double-charge under concurrent duplicate delivery and quote the two charge records with the same idempotency key.
- [ ] You explain — in two or three sentences — exactly why the green pact is orthogonal to this bug (shape-of-one vs semantics-of-two; sequential single delivery vs concurrent duplicate).
- [ ] A property-based test (`challenge-01-idempotency-property.py`) that fails on the buggy handler with a shrunk counterexample and passes on the fixed one.
- [ ] The fix makes the check-and-insert atomic, and your writeup names the *real* fix (a DB unique constraint) for the multi-replica capstone.
- [ ] The "where each test belongs" division of labor (pact = shape, property = semantics, chaos = in-cluster survival).
- [ ] Committed to your Week 23 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The two wrong conclusions you must NOT write:

- **"Contract testing is broken / gives false confidence, remove it."** This throws away a tool that did exactly its job — it proved order and payment agree on the charge *boundary shape*, which is a real and common source of polyglot breaks. The bug is a *semantic* one (idempotency under duplication) that no shape-checking tool was ever going to catch. Removing the pact wouldn't have caught this bug; it would only have *un*-caught all the boundary-shape bugs the pact is preventing. The lesson is "add the property test," not "remove the contract."
- **"Add another pact interaction for the duplicate case."** Tempting, but wrong-shaped: a pact verifies that a *given request produces a given response*, one interaction at a time. The double-charge is an emergent property of *two concurrent calls* and the *handler's internal state* — there is no single request/response pair that expresses "exactly once across duplicates." That invariant lives in a property test (over sequences) or a chaos drill (in-cluster), not in a contract (over single interactions). Trying to force it into a pact misunderstands what a pact is.

A related real-world cousin worth naming in your writeup: this is the *same* bug class as the Week 11 idempotent-consumer drill and the Week 22 "kill the consumer mid-batch" chaos test — the double-process under at-least-once delivery. You've now seen it tested three ways at three costs: a property test (cheap, in-process, this week), a chaos drill (expensive, in-cluster, Week 22), and — the one that does NOT catch it — a contract test. Knowing which tool catches which bug is the literacy.

## Stretch

- Reproduce the bug against the **real capstone `payment`** (Temporal + Postgres) by removing the `UNIQUE` constraint on `idempotency_key`, driving a concurrent duplicate, and showing the double-charge — then restoring the constraint and showing the property test pass. This is the bug in its real habitat.
- Add a **stateful property test** (Hypothesis `RuleBasedStateMachine`) that models the full order→payment flow with retries and asserts the ledger invariant (sum of charges == sum of order amounts) over any generated sequence. This is the property version of the capstone's "Drill B: Kafka broker loss — show no double-process."
- Write the **message pact** for `order.placed.v1` and show that it *also* can't catch this — the event-schema contract proves the message shape, not the consumer's idempotency. Three contracts, same blind spot, one property test that sees it.

## Why this matters

The most dangerous failure mode of a mature test suite is the false sense of completeness: green everywhere, and a bug in the gap between what the green tests prove and what you assumed they proved. Contract testing is uniquely prone to this because it's *so good* at the boundary-shape problem that teams forget it's *only* the boundary-shape problem. The engineer who can stand in a postmortem, point at a wall of green checkmarks, and say "these prove the shapes match — here's the semantic invariant they were never testing, and here's the property test that does" is the one who actually understands their tools. When you present your capstone's green Pact broker next week and a reviewer asks "what could be broken even though this is green," *that question is this challenge*, and you'll have the answer ready: "the semantics behind the shape — which is why I also property-tested the CRDT merge and the payment idempotency, and chaos-drilled the redelivery."
