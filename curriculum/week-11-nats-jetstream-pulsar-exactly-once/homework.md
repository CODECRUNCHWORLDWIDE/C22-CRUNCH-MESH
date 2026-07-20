# Week 11 Homework

Six problems that revisit the week's topics and force the exactly-once literacy into your fingers. The full set should take about **5 hours**. Work in your Week 11 Git repository (the same workspace as the exercises and the `idempotent-checkout` mini-project) so every problem produces at least one commit you can point to at the Week 12 midterm.

The headline deliverable is **Problem 4 — the one-page exactly-once-boundary design memo**, the artifact a reviewer reads, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Postgres** and a **broker** reachable (your exercise Docker setup). Problems 1, 2, 3, and 6 run against them. If something is broken, the standalone containers from the exercises are your fallback; say so in your writeup.

---

## Problem 1 — The dual-write demonstration

**Problem statement.** Write the *broken* version on purpose: a small program that confirms an order in Postgres and then publishes `order.confirmed` to the broker as two separate steps. Add a `--crash` flag that exits hard between the two. Run it with `--crash` a few times, then compare the set of confirmed orders in Postgres against the set of events actually on the topic.

**Acceptance criteria.**

- `notes/week-11/dual-write.md` shows the divergence: at least one order confirmed in Postgres with no corresponding event on the topic (or vice versa, depending on your ordering).
- You state, in one sentence, why retrying or reordering the two steps does not fix it (the problem is structural — no transaction spans the two systems).
- Committed.

**Hint.** Consume the topic into a set with `kafka-console-consumer.sh --from-beginning` (or your exercise consumer), `SELECT id FROM orders` into another set, and diff them. The gap is the dual write. This is the bug Problem 4's memo and the mini-project exist to eliminate.

**Estimated time.** 40 minutes.

---

## Problem 2 — The outbox fix, proven atomic

**Problem statement.** Take Problem 1's broken program and fix it with the transactional outbox (reuse exercise 2): write the order row and the outbox row in one transaction, and a relay publishes the outbox. Add the same `--crash` flag, but now crash *inside* the transaction (before COMMIT). Show that the crash leaves *neither* the order row nor the outbox row — both rolled back — and that no run ever produces a confirmed order without its event.

**Acceptance criteria.**

- `notes/week-11/outbox-fix.md` shows: a mid-transaction crash leaves no order and no outbox row; and after a clean run + relay, every confirmed order has exactly one published event.
- You contrast this with Problem 1's divergence in one sentence.
- Committed.

**Hint.** The atomicity proof is `SELECT count(*) FROM orders WHERE id=$crashed_id` → 0 and the same for `outbox`. The exercise-2 `-fail-after-insert` flag is exactly this; adapt it. The whole point: one write, one system, atomic — the event can't exist without the state.

**Estimated time.** 45 minutes.

---

## Problem 3 — Three flavors of idempotent consumer

**Problem statement.** Implement the *same* "charge an order" effect three ways from Lecture 2 §2: (A) a dedup table in the same transaction as the charge; (B) a natural unique constraint on `charges(order_id)`; (C) an idempotent upsert into an `order_read_model`. For each, deliver the same event twice and show the effect happened once. Then write a paragraph on when each is the right tool.

**Acceptance criteria.**

- `notes/week-11/idempotency-three-ways.md` shows all three patterns with a duplicate delivery and a single resulting effect each.
- The paragraph correctly distinguishes when each fits: dedup table is the most general; unique constraint when the effect is a keyed insert; upsert when the event carries full new state (not a delta).
- You note the one case where the upsert is *wrong* (a delta like `stock = stock - 1`, which needs A or B).
- Committed.

**Hint.** For (C), remember the upsert is only idempotent if the event carries the full new value (`status = 'shipped'`), not a delta. That distinction is the trap and the thing the reviewer will probe.

**Estimated time.** 1 hour.

---

## Problem 4 — The exactly-once-boundary design memo (headline deliverable)

**Problem statement.** This is the syllabus-style headline deliverable. For the capstone's checkout-and-charge flow, write a one-page memo at `notes/week-11/exactly-once-boundary.md` that **draws the boundary** between what the broker guarantees and what your application must guarantee, and specifies the mechanism at each hop. The memo must answer, explicitly:

1. **The flow** — name each hop from `order.placed.v1` to a charged card to `order.confirmed.v1`, and the delivery semantic at each (at-least-once everywhere, justified).
2. **Where the broker's guarantee ends** — for your chosen broker (Kafka, JetStream, or Pulsar), state precisely what its EOS feature covers and the exact point it stops (the DB write, the external charge).
3. **The producer-side guarantee** — the outbox, and why it makes the emit atomic with the state.
4. **The consumer-side guarantee** — the idempotency key (which field, why stable) and the dedup table (in the same transaction as the effect), and the external-API idempotency key for the charge.
5. **The proof** — how you would demonstrate `double-charges: 0` under a deliberate crash (the chaos test), and what a failure of it would tell you.

**Acceptance criteria.**

- `notes/week-11/exactly-once-boundary.md` exists, fits roughly one page (400–600 words), and answers all five points.
- Point 2 names the *exact* boundary where the broker stops, not a vague "Kafka handles it."
- Points 3–4 specify concrete mechanisms (outbox table, dedup table in the same transaction, event-derived key), not "we'll be careful."
- Point 5 describes a *testable* proof, not an assertion.
- Committed.

**Hint.** This memo becomes the exactly-once section of your capstone architecture document and the script for the Week 12 midterm question "how is a double-charge impossible?" The strongest memos draw a literal diagram with a labeled line: "everything left of here is the broker's job; everything right is ours." Vague memos ("we use exactly-once") fail.

**Estimated time.** 1 hour.

---

## Problem 5 — The dedup window's blind spot

**Problem statement.** On NATS JetStream, create a stream with a short dedup window (e.g., 5 s). Publish a message with a `Nats-Msg-Id`, confirm a re-publish *within* the window is dropped, then publish the *same* id *after* the window and confirm it is *accepted*. Write up why this means the dedup window cannot be your only defense against duplicates.

**Acceptance criteria.**

- `notes/week-11/dedup-window.md` shows the stream message count: unchanged by an in-window duplicate, incremented by a post-window duplicate.
- You explain, in two sentences, the real-world scenario the window misses (a consumer replaying old data hours later, a delayed redelivery) and why an idempotent consumer with a permanent dedup table covers it.
- Committed.

**Hint.** `nats stream info <STREAM> | grep Messages` before and after each publish is your measurement. The lesson is Lecture 1 §3.3: the window protects fast retries, not late duplicates — it's an optimization, not the guarantee.

**Estimated time.** 40 minutes.

---

## Problem 6 — Broker portability of the guarantee

**Problem statement.** Take your idempotent consumer (exercise 3 or the mini-project consumer) and run it against **two** brokers: Kafka and one of {NATS JetStream, Pulsar}. Deliver duplicates on each and show the effect happened once on both. The consumer's *idempotency logic* must not change between brokers — only the subscribe/ack call.

**Acceptance criteria.**

- `notes/week-11/broker-portability.md` shows the idempotent consumer absorbing duplicates with zero double-effects on both brokers.
- You diff the consumer code between the two broker versions and confirm the only changes are the client/subscribe/ack calls — the dedup-table logic is byte-for-byte identical.
- You state, in one sentence, why this proves the exactly-once-effect guarantee lives in your code, not the broker.
- Committed.

**Hint.** Abstract the broker behind a tiny interface (a `next()` that returns the next message and an `ack()` that acks/commits it) so the idempotency code is shared. The whole point: switching brokers changes the engine, not the contract (Lecture 2 §Part 4).

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Dual-write demonstration | 40 min |
| 2 — Outbox fix, proven atomic | 45 min |
| 3 — Three flavors of idempotent consumer | 1 h 0 min |
| 4 — Exactly-once-boundary memo (headline) | 1 h 0 min |
| 5 — Dedup window's blind spot | 40 min |
| 6 — Broker portability of the guarantee | 35 min |
| **Total** | **~5 h 0 min** |

---

## Grading rubric (for the headline Problem 4)

| Area | Points | What we look for |
|---|---:|---|
| **The flow & semantics** | 20 | Each hop named with its delivery semantic; at-least-once justified, not assumed. |
| **The broker boundary** | 25 | The exact point the broker's EOS stops is named precisely for the chosen broker. |
| **Producer guarantee** | 20 | The outbox, and a correct explanation of why it makes the emit atomic with the state. |
| **Consumer guarantee** | 25 | Idempotency key (field + why stable), dedup table in the effect's transaction, external-API key. |
| **The proof** | 10 | A testable chaos-test description and what a failure would diagnose. |

**90+** is portfolio-grade and drops into the capstone architecture document. **70–89** draws the boundary but hand-waves a mechanism. **Below 70** asserts exactly-once without locating the boundary — redo it with the line drawn explicitly.

When you've finished all six, push your repo and make sure the `idempotent-checkout` [mini-project](./mini-project/README.md) is in the same workspace — Week 12 builds the orchestrated saga on top of this idempotency foundation. Then take the [quiz](./quiz.md) with your notes closed.
