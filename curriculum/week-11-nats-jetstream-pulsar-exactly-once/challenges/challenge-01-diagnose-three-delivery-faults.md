# Challenge 1 — Diagnose Three Delivery-Semantics Faults

**Time estimate:** ~90 minutes.

## Problem statement

You are on call for a payments-adjacent service. Three event flows are misbehaving in ways that produced real incidents: `flow-A` "loses confirmations whenever the service restarts," `flow-B` "charges some customers twice during retries," and `flow-C` "double-charges only when we redeploy under load." All three are delivery-semantics faults, each a *different* mistake from Lecture 2.

You will run a fault-injection harness that reproduces all three, then **detect, diagnose, and prescribe the fix** for each, using only the tables and the chaos kill from this week. No reading the harness's fault choices until you've diagnosed all three from the outside — that's the whole point.

This mirrors the real skill: you rarely debug a double-charge in code you just wrote. You debug it on a service someone else built, from the ledger inward, with `psql` and a clear head, while a customer-support escalation ticks.

## The harness

Save this as `faulty_flows.py`. It needs Postgres and a Kafka/Redpanda on `localhost:9092` (your exercise setup). It runs three independent flows, each with one planted fault. Run it, drive load, and chaos-kill it while diagnosing from `psql`. **Do not read the fault comments until you've diagnosed all three from the outside.**

```python
#!/usr/bin/env python3
"""Three event flows, three planted delivery-semantics faults. Do NOT read the FAULT
comments until you've diagnosed all three from the outside (the ledger + a chaos kill)."""
import json
import os
import sys
import time
import uuid

import psycopg
from confluent_kafka import Consumer, Producer

DSN = os.environ.get("DSN", "postgres://crunch:crunch@localhost:5432/crunch")
BOOTSTRAP = "localhost:9092"


def setup_schema() -> None:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("""
          CREATE TABLE IF NOT EXISTS orders_a (id text PRIMARY KEY, status text);
          CREATE TABLE IF NOT EXISTS charges_b (charge_id uuid PRIMARY KEY,
              order_id text, amount bigint);
          CREATE TABLE IF NOT EXISTS charges_c (order_id text, amount bigint);
          CREATE TABLE IF NOT EXISTS processed_c (event_id text PRIMARY KEY);
        """)


# --- flow-A: confirm an order, then publish — a DUAL WRITE (planted fault #1) --------
def flow_a_confirm(order_id: str) -> None:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("INSERT INTO orders_a VALUES (%s,'confirmed') "
                  "ON CONFLICT (id) DO UPDATE SET status='confirmed'", (order_id,))
    # FAULT #1: separate step. If the process dies HERE (between the DB write and the
    # publish), the order is confirmed but no event is ever published. Dual write.
    p = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    p.produce("flow.a.confirmed", key=order_id, value=json.dumps({"order_id": order_id}))
    p.flush()


# --- flow-B: charge with a PER-ATTEMPT idempotency key (planted fault #2) ------------
def flow_b_charge(order_id: str, amount: int) -> None:
    # FAULT #2: the "idempotency key" is generated fresh each call (uuid4), so a retry
    # gets a DIFFERENT key and the dedup never matches — every retry charges again.
    charge_id = uuid.uuid4()                  # <-- NOT derived from the event!
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("INSERT INTO charges_b VALUES (%s,%s,%s) "
                  "ON CONFLICT (charge_id) DO NOTHING", (charge_id, order_id, amount))


# --- flow-C: dedup gate in a SEPARATE transaction from the charge (planted fault #3) -
def flow_c_charge(order_id: str, event_id: str, amount: int) -> None:
    with psycopg.connect(DSN, autocommit=True) as c1:
        cur = c1.execute("INSERT INTO processed_c VALUES (%s) "
                         "ON CONFLICT (event_id) DO NOTHING", (event_id,))
        if cur.rowcount == 0:
            return
    # FAULT #3: a SECOND, separate connection/transaction for the effect. A crash
    # between "record processed" and "charge" lets a redelivery charge again, because
    # the redelivery sees event_id already processed... no wait — it sees it processed
    # and SKIPS, so the FIRST charge never happened. Either way the two-transaction
    # split breaks the guarantee. (Diagnose which direction it breaks!)
    with psycopg.connect(DSN, autocommit=True) as c2:
        c2.execute("INSERT INTO charges_c VALUES (%s,%s)", (order_id, amount))


def driver() -> None:
    setup_schema()
    i = 0
    while True:
        oid = f"o{i}"
        flow_a_confirm(oid)
        flow_b_charge(oid, 100 + i)           # called twice to simulate a retry:
        flow_b_charge(oid, 100 + i)           # <-- the retry that double-charges
        flow_c_charge(oid, f"evt-{i}", 200 + i)
        i += 1
        time.sleep(0.01)


if __name__ == "__main__":
    driver()
```

```bash
pip install "psycopg[binary]" confluent-kafka
DSN=postgres://crunch:crunch@localhost:5432/crunch python3 faulty_flows.py
# let it run ~30s, then kill -9 it, then inspect the tables.
```

Your diagnostic surfaces:

```bash
# flow-A: are there confirmed orders with no published event? (consume flow.a.confirmed
#   into a set, compare against orders_a.)
# flow-B: SELECT order_id, count(*) FROM charges_b GROUP BY order_id HAVING count(*) > 1;
# flow-C: compare count(processed_c) vs count(charges_c) — they should match; a gap is the bug.
```

## Your task

For **each of the three flows**, produce a diagnosis with these four parts:

1. **Symptom** — what's observably wrong in the ledger (orders confirmed but no event; duplicate charge rows; processed-vs-charged count mismatch).
2. **Root cause** — the precise mechanism and the Lecture 2 concept it violates (dual write §1.1; per-attempt idempotency key §2.1; dedup gate not in the effect's transaction §2.1).
3. **Why it's silent / intermittent** — why the fault only shows under crash/retry/redeploy, not in a happy-path test.
4. **Prescription** — the exact fix, with the corrected code (the outbox for A; a stable event-derived key for B; one transaction spanning dedup + effect for C).

You must reach each diagnosis using **at least two** independent signals — e.g., the ledger query *and* a chaos kill that makes the count diverge. One signal is a guess; two is a diagnosis.

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with a section per flow, each containing all four parts above.
- [ ] You correctly identify the fault on each flow:
  - `flow-A` — **dual write**: the DB write and the publish are separate steps; a crash between them confirms the order without publishing the event. Fix: the transactional outbox (§1.2).
  - `flow-B` — **per-attempt idempotency key**: the `charge_id` is `uuid4()` generated fresh each call, so a retry never matches the dedup and charges again. Fix: derive the key from the event (`order_id` or the event id), stable across retries (§2.1).
  - `flow-C` — **dedup gate in a separate transaction from the effect**: a crash between the two transactions breaks atomicity (the event is marked processed but the charge never happens, *or* the reverse). Fix: one transaction spanning both (§2.1).
- [ ] For each, you captured the divergence by *inducing a crash* (kill the harness mid-run) and showing the ledger gap that the happy path hides.
- [ ] A `fixed_flows.py` — your corrected harness where, after the same chaos kill, flow-A loses no events, flow-B charges each order once, and flow-C's processed-count equals its charged-count.

## The trap (read after a first attempt)

`flow-C` is the subtle one and the most realistic, because it *looks* idempotent — there is a dedup table, there is an `ON CONFLICT`, the code reads correctly at a glance. The bug is invisible in the source and only appears under a crash at the exact wrong instant, which is why it survives code review and ships. The tell is the **count mismatch**: `count(processed_c) != count(charges_c)` after a chaos kill. If processed > charged, a crash after recording-processed-but-before-charging *lost* a charge (the redelivery skips because it's "processed"). The lesson — **a dedup table in a different transaction than the effect is not idempotent, it's two dual-writes** — is the single most important and most missed point of the week. "There's a dedup table" is not "it's idempotent"; the transaction boundary is.

## Stretch

- Add a fourth flow that does the effect correctly (outbox + same-transaction dedup) and show that the *same* chaos kill produces zero loss and zero double-charge — the contrast that proves the fixes work.
- Re-run `flow-A`'s fix against **NATS JetStream** instead of Kafka and confirm the outbox pattern is broker-agnostic — only the publish call changes (§Part 4).
- Write a `ledger-check.sh` that runs all three diagnostic queries and exits non-zero if any flow shows loss or duplication — a CI gate you could run after every deploy.

## Why this matters

At the Week 12 midterm a reviewer will ask, pointing at your event-driven design, "a customer says they were charged twice — walk me through how that's impossible in your system." This challenge *is* that conversation, rehearsed against three real ways it goes wrong. Every payments-adjacent on-call rotation eventually hands you a double-charge ticket with a cause you can't see in the code. The engineer who can name it from the ledger in five minutes — and who knows that a dedup table in the wrong transaction is worse than none — is the one who stops the incident instead of extending it.
