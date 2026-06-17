# Mini-Project — `idempotent-checkout`: Exactly-Once Effect, Proven Under Chaos

> Build a checkout pipeline that takes `order.placed.v1` events and charges each order **exactly once in effect** — using a transactional outbox on the producer side and an idempotent consumer on the consumer side — and **prove it with an automated chaos test** that kills the consumer mid-batch and verifies `double-charges: 0`. Then run the same pipeline against a second broker (NATS JetStream or Pulsar) and confirm the contract is broker-agnostic.

This is the artifact that turns "we use exactly-once" from a claim into a tested guarantee. After this week, when someone asks "how do you know you won't double-charge?", you don't point at a broker feature — you run `./chaos-test.sh` and show them `double-charges: 0` under a deliberate crash.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `idempotent-checkout` pipeline is the payment path of your **capstone Polyglot Marketplace**. The outbox is how `order-service` emits `order.placed.v1`; the idempotent consumer is how `payment-service` charges without double-charging. The chaos test becomes **Drill B** in the capstone (lose a Kafka broker mid-traffic, prove no double-process). Build it well now; you'll run the drill in the capstone defense.

**The one-sentence spec:** a producer that writes the order and its outbox row atomically, a relay that publishes the outbox at-least-once, and a consumer that charges idempotently — chaos-tested to zero double-charges and proven portable across two brokers. Everything below is the detail of those four clauses.

---

## What you will build

A repo `idempotent-checkout` with four deliverables:

1. **`producer/`** — an order service that, on checkout, writes the order row + an `outbox` row in one Postgres transaction (harden exercise 2), plus a relay that publishes the outbox to the broker at-least-once with `FOR UPDATE SKIP LOCKED`.
2. **`consumer/`** — a payment consumer that charges each order idempotently: a dedup table recording each `event_id` in the **same transaction** as the charge, plus a stable idempotency key on the (simulated) external charge call (harden exercise 3).
3. **`chaos-test.sh`** — the automated proof: produce N orders, start the consumer, kill it mid-batch, restart it (redelivery), drain, and assert `double-charges == 0` and `unique-orders-charged == N`. Exits non-zero on any double-charge or lost charge.
4. **A broker-portability proof** — run the *same* consumer logic against a second broker (JetStream or Pulsar) and show the chaos test still passes, demonstrating the guarantee lives in your code, not the broker.

By the end you have a public repo of ~500–700 lines (Go + Python + SQL + shell) plus a chaos test that *demonstrates* effectively-exactly-once under failure — the single most interview-relevant artifact in the course.

---

## Why a chaos test and not a unit test

You could unit-test the dedup logic with a mocked duplicate. Don't stop there. A unit test proves the code does what you *think* it does on the input you *imagined*. The chaos test proves it does the right thing under the failure it's *meant to survive* — a crash at an arbitrary, adversarial instant. The two questions a chaos test answers that a unit test cannot:

- **Is the dedup insert truly in the same transaction as the effect?** A unit test with a mocked DB can pass even if they're in separate transactions; only a real crash between two real transactions exposes the leak (challenge 1, flow-C).
- **Is the idempotency key truly stable across the redelivery?** A unit test feeds the same key twice on purpose. A chaos test feeds whatever the redelivery actually carries — which catches a per-attempt key that the unit test, by feeding the same key, hides (challenge 1, flow-B).

The chaos test is the senior-shop convention for correctness-under-failure in 2026: if you can't kill it and show it recovered clean, you haven't proven anything about production, where it *will* be killed.

---

## Repo layout

```
idempotent-checkout/
├── README.md
├── schema.sql                  # orders, outbox, charges, processed_events
├── producer/
│   ├── go.mod
│   └── main.go                 # atomic order+outbox writer; the relay
├── consumer/
│   ├── requirements.txt
│   └── consumer.py             # idempotent charge; dedup in same txn; stable key
├── chaos-test.sh               # the automated proof (the headline deliverable)
├── brokers/
│   ├── docker-compose.kafka.yml
│   ├── docker-compose.jetstream.yml   # or pulsar
│   └── README.md               # how to run the consumer against each
└── test/
    ├── test_idempotent_charge.py   # unit: duplicate event_id => one charge
    └── test_stable_key.py          # unit: the key is derived from the event, not random
```

---

## The reference schema

The whole pipeline rests on four tables. Get these right and the rest follows:

```sql
-- The business state + the outbox, written together in one transaction (producer side).
CREATE TABLE orders (
  id          text PRIMARY KEY,
  status      text NOT NULL,
  total_cents bigint NOT NULL
);
CREATE TABLE outbox (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  aggregate_id text NOT NULL,
  event_type   text NOT NULL,
  payload      jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  sent         boolean NOT NULL DEFAULT false,
  sent_at      timestamptz
);
CREATE INDEX outbox_unsent_idx ON outbox (created_at) WHERE NOT sent;

-- The dedup gate + the effect, written together in one transaction (consumer side).
CREATE TABLE processed_events (
  event_id     text PRIMARY KEY,           -- the idempotency gate
  processed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE charges (
  order_id     text PRIMARY KEY,           -- natural idempotency on the charge
  amount_cents bigint NOT NULL,
  charged_at   timestamptz NOT NULL DEFAULT now()
);
```

The two `PRIMARY KEY` choices are load-bearing: `processed_events(event_id)` is the dedup gate (a duplicate delivery is a conflicting insert), and `charges(order_id)` is the belt-and-suspenders second layer (even if two different events referenced the same order, the charge couldn't double). Both inserts happen in the *same* transaction as nothing-else, which is the entire correctness argument in two `ON CONFLICT DO NOTHING` clauses.

---

## Deliverable 1 — the producer (atomic outbox)

Harden exercise 2 into a checkout producer. It must:

- On each checkout, write the `orders` row and the `outbox` row in **one** transaction. The event can never disagree with the committed state (Lecture 2 §1.2).
- Run a relay that reads unsent outbox rows with `FOR UPDATE SKIP LOCKED`, publishes them with `acks=all`, and marks them sent — at-least-once, horizontally scalable.
- Carry a stable `event-id` header (the outbox row id) so the consumer has a reliable idempotency key.
- Include a `-fail-after-insert` mode that proves a mid-transaction crash rolls back *both* writes (no orphan order, no orphan event).

---

## Deliverable 2 — the consumer (idempotent charge)

Harden exercise 3. It must:

- For each event, run the dedup-table insert and the charge in **one** transaction. If the `event_id` is already present, skip — no double-charge (Lecture 2 §2.1).
- Use a **stable** idempotency key derived from the event (`order_id` / event id) for the simulated external charge call — never a per-attempt random key.
- Commit the Kafka offset (or ack the JetStream message) **only after** the DB transaction commits — at-least-once, so redelivery is safe rather than lossy.
- Maintain the `charges` ledger keyed by `order_id` so `--verify` can count double-charges.

---

## Deliverable 3 — the chaos test (the headline)

`chaos-test.sh` must, end to end:

1. Reset the DB (truncate `orders`, `outbox`, `charges`, `processed_events`) and the topic.
2. Run the producer to write N (e.g., 1000) orders + outbox rows; run the relay to publish them all.
3. Start the consumer; let it process a few hundred; `kill -9` it (a crash before commit).
4. Restart the consumer; Kafka redelivers the uncommitted records (genuine duplicates); let it drain to lag 0.
5. Run `--verify` and assert:
   - `unique orders charged == N` (nothing lost),
   - `double-charges == 0` (nothing double-effected),
   - exit non-zero if either assertion fails.

Expected output:

```
$ ./chaos-test.sh
[1/5] reset db + topic ... ok
[2/5] produced 1000 orders + outbox rows; relay drained outbox ... ok
[3/5] consumer processing ... killed at ~437 ... ok
[4/5] consumer restarted; redelivered 63 duplicates; drained to lag 0 ... ok
[5/5] verify:
   processed_events: 1000   charges: 1000   distinct orders: 1000   double-charges: 0
PASS: at-least-once delivery, exactly-once effect.  (exit 0)
```

> **A nonzero `double-charges` is a failing grade** — not because the idea is wrong, but because the *implementation* leaked. The three usual culprits (challenge 1): the dedup insert is in a separate transaction, the idempotency key is per-attempt, or the "effect" isn't actually idempotent. The chaos test exists to catch exactly these, deterministically, before a customer does.

---

## Deliverable 4 — the broker-portability proof

Run the consumer against a second broker (JetStream durable pull consumer with explicit ack, or Pulsar key-shared subscription) and show `chaos-test.sh` still reports `double-charges: 0`. The producer's outbox relay changes its publish call; the consumer's *idempotency logic does not change at all*. Document this in `brokers/README.md` with the actual passing output from both brokers. The point: **the exactly-once-effect guarantee lives in your outbox + dedup, not in the broker — so switching brokers doesn't change the contract, only the engine** (Lecture 2 §Part 4).

---

## Rules

- **You may** read the microservices.io patterns, the Debezium outbox docs, and the broker docs.
- **You must** put the dedup insert and the effect in **one** transaction. If `grep` finds two separate `connect`/`begin` calls around a single event's dedup-and-effect, you've reintroduced the dual write; fix it.
- **You must** derive every idempotency key from the event, not generate it per attempt. A random key inside the retry path is an automatic fail.
- **You must not** rely on a broker's EOS feature (Kafka transactions, JetStream dedup window) as the *only* defense — the chaos test must pass even with those features off, because the guarantee is yours.
- Go 1.23+, Python 3.12+, Postgres 16, Docker. The external charge is simulated (a row insert) but must use a stable idempotency key as if it were Stripe.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-11-idempotent-checkout-<yourhandle>`.
- [ ] The producer writes order + outbox atomically; `-fail-after-insert` rolls back both (proven in the README).
- [ ] The consumer's dedup insert and charge are in one transaction; the idempotency key is event-derived.
- [ ] `./chaos-test.sh` produces, kills mid-batch, restarts, drains, and asserts `double-charges == 0` and `unique == N`, exiting non-zero on failure.
- [ ] The chaos test passes against a **second broker** with unchanged consumer idempotency logic; both passing outputs are in the repo.
- [ ] Unit tests pass: duplicate `event_id` ⇒ one charge; the idempotency key is event-derived, not random.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Atomic outbox** | 20 | Order + outbox in one transaction; `-fail-after-insert` rolls back both; relay is at-least-once with `SKIP LOCKED`. |
| **Idempotent consumer** | 25 | Dedup insert + effect in one transaction; stable event-derived key; offset committed after the DB commit. |
| **Chaos test rigor** | 30 | Automated kill-mid-batch + restart + drain; asserts both no-loss and no-double-charge; exits non-zero on failure; deterministic. |
| **Broker portability** | 15 | Same idempotency logic passes on a second broker; documented with real output. |
| **Tests & hygiene** | 10 | Unit tests for dedup and key-stability; clean README; no `build/`/`.venv/` checked in. |

**90+** is portfolio-grade and becomes the capstone's payment path and Drill B. **70–89** works but the chaos test is soft (non-deterministic, or asserts only one of loss/duplication). **Below 70** means the chaos test doesn't actually prove the contract — fix that first; it's the whole point.

---

## How to make the chaos test deterministic (the hard part)

A chaos test that *sometimes* passes is worse than no test — it lulls you. The discipline that makes it deterministic:

- **Control the kill point, don't race it.** Don't `sleep 2 && kill` and hope you caught the consumer mid-batch. Instead, have the consumer emit a marker (a log line, a touch-file, a row count) when it has processed a known number of records, and have the drill script *wait for that marker* before killing. Now the kill lands at a known point every run.
- **Use a fixed input.** Produce exactly N events with known ids, not a random stream. Then the verification — "1000 unique orders, 0 double-charges" — is an exact equality, not an approximate one.
- **Make the verification an exact assertion, not eyeballing.** `--verify` must compute `double-charges` and exit non-zero if it's not exactly 0. A human reading "looks fine" is not a test.
- **Run it in a loop.** A correct idempotent consumer passes the drill 100 times in a row. Run `for i in $(seq 1 20); do ./chaos-test.sh || break; done` — if it ever fails, you have a real leak, not bad luck. A flaky pass is a real bug you haven't caught yet.

The payoff is a test you trust: when it's green, the contract holds, and when it's red, there's a real implementation leak (separate-transaction dedup, per-attempt key, non-idempotent effect). That trustworthiness is what makes it a *gate* — something you can put in CI and rely on — rather than a demo. Spend the time to make it deterministic; a flaky chaos test is a chaos test that will eventually let a double-charge through.

---

## Stretch goals

- **CDC relay.** Replace the polling outbox relay with Debezium tailing the Postgres WAL (previews Week 14). Show lower latency and no polling load, and that the consumer is unchanged.
- **Poison-message handling.** Add a deliberately malformed event and route it to a dead-letter topic after N failed deliveries, instead of looping forever — and prove the chaos test still passes for the good events.
- **Effect-once across two effects.** Make the consumer do *two* effects (charge + decrement inventory) atomically with the dedup gate, and chaos-test that neither double-applies. This is the saga seed for Week 12.
- **CI job.** A GitHub Actions workflow that stands up Postgres + single-node Redpanda in containers and runs `chaos-test.sh`, failing the build on any double-charge. Green check on every push is the strongest possible signal that the contract holds.

---

## What "done" feels like

You'll know this project landed not when the code compiles but when you can do the following, cold, in an interview: someone says "a customer was charged twice — how is that impossible in your system," and you answer without hesitation — "the producer writes the order and the outbox row in one Postgres transaction, so the event can't disagree with the state; the relay publishes at-least-once with `SKIP LOCKED`; the consumer charges with a stable `order_id` idempotency key and records the `event_id` in a dedup table in the *same* transaction as the charge, so a redelivery is a no-op; and I prove it with `./chaos-test.sh`, which kills the consumer mid-batch and asserts zero double-charges across a thousand events." That paragraph, delivered confidently and backed by a green chaos test, is the deliverable. The repo is just the evidence.

## How this connects to the rest of C22

- **Week 12 (Temporal)** replaces the hand-wired "charge then maybe compensate" choreography here with an orchestrated, durable workflow — and you'll see why orchestration makes the saga *readable* where this week's outbox-and-consumer made it *correct but scattered*.
- **Week 14 (CDC)** swaps the polling relay for Debezium, and feeds the same `order.placed.v1` — your idempotent consumer reads it unchanged.
- **Capstone** uses `idempotent-checkout` as the literal payment path, and `chaos-test.sh` becomes Drill B (Kafka broker loss, prove no double-process).

When you've finished, push the repo and take the [quiz](../05-quiz.md) with your notes closed.
