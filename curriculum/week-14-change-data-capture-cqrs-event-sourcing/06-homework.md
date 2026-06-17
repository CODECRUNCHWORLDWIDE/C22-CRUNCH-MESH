# Week 14 Homework

Six problems that revisit the week's topics and force the CDC, CQRS, and event-sourcing literacy into your fingers. The full set should take about **5 hours**. Work in your Week 14 Git repository (the same workspace as the exercises and the `orders-cdc` mini-project) so every problem produces at least one commit you can point to at the Phase 3 architecture review.

The headline deliverable is **Problem 4 — the CDC-vs-event-sourcing taxonomy memo**. Treat it as the artifact a staff engineer reads to decide which event architecture a new system should use, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Run everything against the Postgres 16 (`wal_level=logical`), Kafka/Redpanda, and Debezium you stood up in Exercise 1. Have `kcat`/`jq` available — Problems 1, 2, and 5 read the change stream by hand.

---

## Problem 1 — Annotate a change event

**Problem statement.** Capture one of each Debezium event type for the `orders` table — an insert (`c`), an update (`u`), a delete (`d`), the delete's tombstone, and a snapshot read (`r`) — and write a fully annotated reference. For each, paste the raw `payload` and label every field (`op`, `before`, `after`, `source.lsn`, `source.ts_ms`, top-level `ts_ms`). Then set `REPLICA IDENTITY FULL` and capture an update whose `before` is now populated, contrasting it with the `before: null` version.

**Acceptance criteria.**

- `notes/week-14/change-events.md` contains all five event types with the raw payload and a labeled explanation of each field.
- The before/after contrast for `REPLICA IDENTITY DEFAULT` vs `FULL` is shown with both update payloads side by side.
- You state which field you'd use as an idempotency key (the LSN) and why.
- Committed.

**Hint.** To force a snapshot `r` event, drop and re-register the connector with a fresh slot so it re-snapshots, or add a new table to the include list. `kcat -b localhost:9092 -t shop.public.orders -C -o beginning -c 5 | jq '.payload'` dumps the first five.

**Estimated time.** 40 minutes.

---

## Problem 2 — Build a second read model with a different shape

**Problem statement.** Your projector from Exercise 2 maintains `order_search`. Now build a **second** projector — a separate consumer group — that consumes the *same* `orders` stream and maintains a completely different read model: a `daily_revenue` rollup table (`day date, order_count bigint, revenue_cents bigint`). It must be idempotent: replaying the stream twice must not double-count revenue. Demonstrate both read models updating from one stream.

**Acceptance criteria.**

- `notes/week-14/second-read-model/` has the second projector and its `daily_revenue` DDL.
- Both projectors run against the same topic in different consumer groups; `order_search` and `daily_revenue` both update as you change orders.
- You prove the rollup is idempotent: replaying the stream leaves `daily_revenue` numbers unchanged (the tricky part — a naive `revenue += total` double-counts on replay).
- A one-paragraph note on *how* you made the aggregate idempotent (e.g., recompute from a per-order applied-set, or dedup by LSN so each change counts once).
- Committed.

**Hint.** Idempotent aggregation is harder than idempotent upsert. The clean approach: keep a `processed (order_id, lsn)` dedup so each change is counted exactly once, and apply the *delta* (new total − old total) only for un-processed changes. This proves the CQRS claim — one write model, N independently-shaped read models — and the subtle point that aggregate projections need more care than key-upsert projections.

**Estimated time.** 1 hour.

---

## Problem 3 — Implement snapshots in the event store

**Problem statement.** Extend the Exercise 3 Go event store (or a Python port) with **snapshotting**. After every 100 events for an aggregate, write a snapshot row (`aggregate_id, version, state_json`). Change `loadState` to start from the latest snapshot and replay only events *after* it. Build an aggregate with 5,000 events and measure load time with and without snapshots.

**Acceptance criteria.**

- `notes/week-14/snapshots/` has the snapshot-enabled event store and a small benchmark driver.
- A `snapshots` table exists; loading uses the latest snapshot + subsequent events.
- `notes/week-14/snapshots/RESULTS.md` shows load time for a 5,000-event aggregate with snapshots off vs on, with the speedup.
- You correctly state that snapshots are an optimization, never the source of truth — deleting all snapshots and rebuilding from events must yield the same state.
- Committed.

**Hint.** Prove the "never the source of truth" property: after building snapshots, `DELETE FROM snapshots`, reload purely from events, and assert the state matches. If it doesn't, your snapshot logic diverged from your fold — a real and dangerous bug.

**Estimated time.** 1 hour.

---

## Problem 4 — The CDC-vs-event-sourcing taxonomy memo (headline deliverable)

**Problem statement.** This is the staff-review artifact. You're advising three new internal systems on their event architecture: (1) a **product-catalog search** that needs fast faceted search over data owned by a catalog service; (2) a **payments ledger** that must retain the full history of every money movement for audit and support "what was this balance on date X?"; (3) a **notification service** that emails users when their order ships. For *each*, recommend an architecture — event-driven service, CDC-fed CQRS, or event sourcing — and justify it against the taxonomy. Write the memo at `notes/week-14/taxonomy-memo.md`.

For each system, your memo must state:

1. **Classification & recommendation** — which of the three architectures, named explicitly.
2. **Where the source of truth lives** and where events come from, in your design.
3. **The dual-write check** — how your design avoids a dual write (outbox/CDC), explicitly.
4. **The cost you're accepting** — for the event-sourced one, the upcasting/erasure costs; for the CQRS one, the eventual-consistency / read-your-writes caveat.

**Acceptance criteria.**

- `notes/week-14/taxonomy-memo.md` exists, fits one-to-two pages, and covers all three systems with parts 1–4.
- Your recommendations are defensible: catalog-search → **CDC-fed CQRS**; payments ledger → **event sourcing** (history is the asset); notifications → **event-driven service** (with outbox/CDC, not a dual write).
- You explicitly call out that event sourcing is the *right* call for the ledger *despite* usually being overkill — and *why*.
- Each recommendation names the dual-write avoidance mechanism, not "we'll be careful."
- It reads like a memo to a staff engineer, not a tutorial.
- Committed.

**Hint.** The calibration this memo tests: don't reflexively reject event sourcing (it's right for the ledger) and don't reflexively reach for it (it's wrong for the other two). The strongest memos state, for each, "what would have to be true to change this recommendation" — e.g., "if catalog-search needed full audit history, I'd revisit event sourcing."

**Estimated time.** 1 hour.

---

## Problem 5 — Break and fix a dual write

**Problem statement.** Implement a deliberately-broken dual-writer: a tiny service that, on a request, does `INSERT INTO inventory_reservations ...` (commit) and then `kafka.produce("InventoryReserved", ...)`. Inject a failure (a `kill -9` or a forced exception) in the window *between* the commit and the produce. Show the database now has a reservation with no corresponding event, and a downstream consumer that's now out of sync. Then fix it with the transactional outbox pattern and show the failure can no longer desync the two.

**Acceptance criteria.**

- `notes/week-14/dual-write/` has the broken version, the failure injection, and the outbox-fixed version.
- `notes/week-14/dual-write/POSTMORTEM.md` documents: the exact failure window, the observed desync (DB row without event), the fix, and proof the fix holds (kill in the same window, no desync).
- You correctly explain *why* the outbox fix works (the business write and the outbox row commit atomically; the relay is at-least-once but a downstream idempotent consumer absorbs duplicates).
- Committed.

**Hint.** The clean way to hit the window deterministically is to put a `panic()` / `sys.exit(1)` immediately after the commit and before the produce, run it, then inspect both the DB and the topic. For the fix, the relay can be a simple loop that drains an `outbox` table — or you can let Debezium's outbox router do it and just show the outbox row committed atomically with the reservation.

**Estimated time.** 50 minutes.

---

## Problem 6 — Read-your-writes across eventual consistency

**Problem statement.** Demonstrate the read-your-writes problem and two fixes. With your `order_search` read model running, write a small flow: place an order (writes the `orders` write model), then immediately query "my orders" from the `order_search` *read* model. Show that under load the just-placed order is sometimes **missing** (the read model hasn't caught up). Then implement two fixes and show each working: (a) route the read-your-writes query to the *write* model, and (b) carry the write's LSN forward and have the read wait until the read model's `updated_lsn` has caught up to it.

**Acceptance criteria.**

- `notes/week-14/read-your-writes/` has the demo and both fixes.
- You reproduce the missing-just-placed-order symptom (at least intermittently under load).
- Both fixes are shown working, with a one-paragraph tradeoff comparison (write-model read is always correct but doesn't scale; LSN-wait is scalable but adds latency).
- You state the general rule: reads that *tolerate* staleness use the read model; reads where staleness is a correctness bug use the write model or an LSN-wait.
- Committed.

**Hint.** To reliably reproduce the symptom, add artificial lag (a small sleep in the projector, or run it under a heavy backlog) so the read model is visibly behind. The LSN-wait fix needs the read model to expose its high-water `updated_lsn` and the writer to know its commit LSN (`pg_current_wal_lsn()` right after commit).

**Estimated time.** 50 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Annotate a change event | 40 min |
| 2 — Second read model | 1 h 0 min |
| 3 — Event-store snapshots | 1 h 0 min |
| 4 — Taxonomy memo (headline) | 1 h 0 min |
| 5 — Break and fix a dual write | 50 min |
| 6 — Read-your-writes | 50 min |
| **Total** | **~5 h 20 min** |

When you've finished all six, push your repo and make sure the `orders-cdc` [mini-project](./07-mini-project/00-overview.md) is in the same workspace — Week 15 routes that same change stream into Iceberg. Then take the [quiz](./05-quiz.md) with your notes closed.

---

## Grading rubric (for the headline memo, Problem 4)

| Criterion | Weight | What earns full marks |
|---|---:|---|
| **Correct classification** | 25% | All three systems classified correctly (catalog→CQRS, ledger→event sourcing, notifications→event-driven). |
| **Source-of-truth clarity** | 20% | Each design states where truth lives and where events come from, unambiguously. |
| **Dual-write avoidance** | 25% | Each design names a concrete outbox/CDC mechanism; no "be careful" hand-waving. |
| **Calibration on event sourcing** | 20% | Event sourcing chosen for the ledger *with* a stated reason, and *rejected* for the other two — the both-directions discipline. |
| **Memo quality** | 10% | Reads like a staff-review memo; includes a "what would change this" for at least one system. |

A memo that reflexively recommends event sourcing everywhere, or that rejects it for the ledger, caps at 60%. The whole skill is calibrated judgment, not a favorite pattern.
