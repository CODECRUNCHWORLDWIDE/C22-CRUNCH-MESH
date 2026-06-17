# Mini-Project — `orders-cdc`: A CDC Pipeline That Survives Chaos

> Build the full change-data-capture pipeline from the syllabus lab: Debezium captures the `orders` table to Kafka, a read-model projector maintains a denormalized search view, and a second consumer writes the same events into an append-only event store. Then prove the whole thing is **idempotent under chaos** — kill consumers mid-batch, restart them, replay duplicates — and show the read model and event store come out byte-identical to a clean run.

This is the artifact that proves you can build an event-driven data pipeline that is *correct*, not just one that works in the happy path. After this week, "exactly-once" is not a checkbox you cross your fingers behind — it's a property you can demonstrate by deliberately injecting the failures that break naive consumers, and showing yours don't.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** The change stream you stand up here is the **same stream Week 15 routes into Iceberg** for the lakehouse — your second consumer (the one writing to an event store) is one rename away from being the Iceberg sink. The idempotency discipline is exactly what the Week 22 chaos gameday (Kafka broker loss) tests at the capstone level. Build it well now; you'll extend it next week and defend it at the capstone.

---

## What you will build

A repository `orders-cdc` with five deliverables:

1. **`infra/`** — a `compose.yml` (or Kind manifests) bringing up Postgres 16 (`wal_level=logical`), Kafka/Redpanda, and Kafka Connect with the Debezium Postgres connector; plus the connector registration JSON.
2. **`projector/`** — an idempotent read-model projector (Python or Rust; the syllabus suggests Rust, Python is accepted) that consumes the `orders` change stream and maintains a denormalized `order_search` read model. Survives duplicate delivery.
3. **`eventstore/`** — a second consumer (Go or Python) that writes every change event into an append-only `events` log, idempotently (dedup by the change's LSN), so the same event delivered twice produces exactly one stored event.
4. **`chaos/`** — scripts that run the pipeline two ways: a clean run, and a chaos run that kills each consumer mid-batch and restarts it (forcing redelivery). Plus a checksum/count comparison that asserts the two runs produce identical read models and event stores.
5. **`REPORT.md`** — the human deliverable: the pipeline diagram, the idempotency strategy for each consumer, and the chaos results proving exactly-once *processing*.

By the end you have a public repo of ~500–700 lines that demonstrates a production-shaped CDC pipeline with a *provable* correctness property — the kind of thing you put at the top of a portfolio.

---

## Why prove it under chaos and not just run it

You could build the three components, run them once on a quiet topic, see the read model populate, and call it done. Don't. A CDC pipeline that works on a quiet topic and corrupts itself on the first consumer restart is worse than no pipeline, because it *looks* correct. A real demonstration:

- **Injects the failure that actually happens.** Consumers restart constantly — deploys, rebalances, OOM-kills, node drains. Each restart can redeliver the last uncommitted batch. If your consumer isn't idempotent, *every restart* is a corruption event. You must test the restart, not avoid it.
- **Has a control.** The clean run is the baseline. "The read model has 41,023 rows" means nothing unless the chaos run *also* has 41,023 rows with the same checksum. The equality is the proof.
- **Distinguishes delivery from processing.** Kafka gives you at-least-once *delivery*. Your consumers must turn that into exactly-once *processing*. The chaos run is what forces that distinction from a claim into a demonstrated fact.

This is the senior-shop convention in 2026: an event-driven pipeline ships with a chaos test that proves idempotency, not a happy-path demo.

---

## Repository layout

```
orders-cdc/
├── README.md
├── infra/
│   ├── compose.yml               # postgres + kafka + connect
│   └── orders-connector.json     # the Debezium connector config
├── projector/
│   ├── main.py (or src/main.rs)  # idempotent read-model projector
│   └── schema.sql                # order_search read-model DDL
├── eventstore/
│   ├── main.go (or main.py)      # idempotent append-only event store consumer
│   └── schema.sql                # events log DDL (dedup by lsn)
├── chaos/
│   ├── reset-and-run.sh          # clean run -> emit checksums
│   ├── run-with-chaos.sh         # kill+restart consumers mid-batch -> emit checksums
│   └── compare.sh                # assert clean == chaos
├── load/
│   └── generate-changes.py       # drive N changes into orders (the workload)
└── REPORT.md
```

---

## Deliverable 1 — the infrastructure and connector

`infra/compose.yml` brings up the three services (reuse the Exercise 1 compose). `infra/orders-connector.json` registers the Debezium connector on `public.orders` with `topic.prefix=shop`, `plugin.name=pgoutput`, and a named slot. A `make up` (or a documented script) must:

1. Start the stack and wait for Connect to be healthy.
2. Create the `orders` table with `REPLICA IDENTITY FULL` (so consumers see full before/after).
3. Register the connector and confirm `RUNNING`.

The bring-up must be **one command** and idempotent (re-running doesn't duplicate the connector).

---

## Deliverable 2 — the idempotent projector

Consumes `shop.public.orders`, maintains `order_search` (denormalized: `order_id`, `customer_id`, `status`, `total_cents`, `updated_lsn`). Requirements:

- **Idempotent by construction.** Upsert by `order_id`, guarded by the change LSN so a duplicate or out-of-order older event is a no-op (the Exercise 2 pattern). Deletes (`op=d`) remove the row; tombstones are handled (skipped) without crashing.
- **Resumable.** On restart it resumes from its committed offset / consumer group; it does not re-scan from zero unless told to.
- **Observable.** Logs applied counts and current read-model size periodically.

The load-bearing property: replaying the entire stream a second time must leave `order_search` byte-identical.

---

## Deliverable 3 — the idempotent event store

A second, independent consumer of the same topic that appends every change into an `events` table:

```sql
CREATE TABLE events (
    global_seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lsn        bigint NOT NULL,        -- the change's WAL position
    op         text   NOT NULL,        -- c/u/d/r
    aggregate_id text NOT NULL,        -- order_id as text
    payload    jsonb  NOT NULL,        -- the full after (or before for deletes)
    UNIQUE (lsn, aggregate_id)         -- the idempotency guard: one event per change
);
```

Requirements:

- **Idempotent by construction.** `INSERT ... ON CONFLICT (lsn, aggregate_id) DO NOTHING` — the same change delivered twice stores exactly one event.
- **Append-only.** It never updates or deletes a stored event; a "delete" of an order is recorded as a `d` event, not a row removal.
- **Independent.** It's a separate consumer group from the projector, proving one stream feeds N consumers (the CQRS claim).

The load-bearing property: replaying the stream twice leaves the `events` table with the same row count and the same set of `(lsn, aggregate_id)` keys.

---

## Deliverable 4 — the chaos harness

Three scripts:

- **`reset-and-run.sh`** — truncate `order_search` and `events`, reset consumer offsets to earliest, drive a fixed workload (`generate-changes.py` makes the same N changes deterministically), let both consumers drain, then print `read_model_checksum`, `read_model_count`, `event_count`, and `event_keyset_checksum`. This is the **clean run** baseline.
- **`run-with-chaos.sh`** — same workload, but while the consumers are mid-drain, `kill -9` each consumer at least once and restart it (forcing Kafka to redeliver the last uncommitted batch). Then drain to completion and print the same four numbers. This is the **chaos run**.
- **`compare.sh`** — run both, diff the four numbers, exit non-zero if any differ.

```
$ ./chaos/compare.sh
clean : read_model=9f2c... count=41023  events=41023 keys=ab17...
chaos : read_model=9f2c... count=41023  events=41023 keys=ab17...
PASS  : pipeline is idempotent under consumer restart (exactly-once PROCESSING)
```

If the chaos numbers differ from clean, your consumers double-applied something — the harness must make that failure **loud** (non-zero exit, a diff), not silent.

---

## Deliverable 5 — the report

`REPORT.md` must contain:

- A **pipeline diagram**: Postgres → Debezium → Kafka topic → {projector → order_search, eventstore → events}.
- The **idempotency strategy** for each consumer, stated as the exact SQL/logic that makes re-application a no-op, and *why* it's correct.
- The **chaos results**: the clean vs chaos numbers side by side, proving equality, plus a note on what you killed and when.
- A short **"delivery vs processing"** paragraph: Kafka gave at-least-once delivery; your consumers achieved exactly-once processing; here's the line in each that did it.
- One **honest limitation**: e.g., "this is idempotent against duplicate delivery but assumes the connector's LSNs are monotonic; a connector re-snapshot would re-emit `op=r` events that the LSN guard handles by ___."

---

## Rules

- **You may** reuse the Exercise 1 compose, the Exercise 2 projector, and the Exercise 3 event-store mechanics as starting points.
- **You must** make both consumers idempotent *by construction* (upsert/dedup), not by a "have I seen this?" in-memory set that's lost on restart. The whole point is surviving restart.
- **You must** demonstrate the chaos run actually killed a consumer mid-batch (log the kill, or the harness proves redelivery happened).
- Postgres 16, Kafka or Redpanda, Debezium 2.x. Consumers in Python/Rust (projector) and Go/Python (event store).
- The pipeline must come up and the chaos comparison must run from **documented commands** (ideally `make up && make chaos`).

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-14-orders-cdc-<yourhandle>`.
- [ ] `make up` (or documented) brings up the stack and the connector reaches `RUNNING`.
- [ ] The projector maintains `order_search`; deletes remove rows; tombstones don't crash it.
- [ ] The event store appends idempotently; `UNIQUE (lsn, aggregate_id)` dedups duplicate delivery.
- [ ] `chaos/compare.sh` runs a clean run and a chaos run (with at least one mid-batch `kill -9` per consumer) and **passes** — identical read model and event store.
- [ ] Removing the idempotency guard from *either* consumer makes `compare.sh` **fail**, demonstrated in the README (this proves the guard is load-bearing, not decorative).
- [ ] `REPORT.md` has the diagram, the per-consumer idempotency strategy, the chaos numbers, and the delivery-vs-processing paragraph.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Pipeline correctness** | 20 | Debezium → Kafka → two consumers, all running from one bring-up; deletes/tombstones handled. |
| **Projector idempotency** | 20 | Upsert guarded by LSN; resumable from offset; replay leaves read model byte-identical. |
| **Event-store idempotency** | 20 | Append-only; `UNIQUE` dedup; replay leaves the keyset identical; truly independent consumer group. |
| **The chaos proof** | 25 | A real mid-batch kill+restart; clean == chaos asserted; removing the guard demonstrably **fails** the comparison. |
| **The report** | 10 | Diagram, per-consumer idempotency strategy, chaos numbers, delivery-vs-processing, one honest limitation. |
| **Docs & hygiene** | 5 | One-command bring-up; no secrets committed; sensible commits. |

**90+** is portfolio-grade and the base you extend in Week 15. **70–89** works but the chaos proof is weak (no real kill, or no control). **Below 70** means idempotency isn't actually demonstrated — the consumer is idempotent "by argument" but the chaos run doesn't prove it. Fix that first; an unproven idempotency claim is the exact thing this project exists to disprove.

---

## Stretch goals

- **Three read models, one stream.** Add a daily-revenue-rollup read model fed by the same topic, proving CQRS's one-write-model-feeds-N-read-models claim. The chaos test must cover all three.
- **Outbox variant.** Add an `outbox` table and the Debezium outbox event router, and run the pipeline off clean domain events instead of raw row changes. Compare the consumer code complexity.
- **Replay-to-rebuild.** A `rebuild.sh` that drops `order_search` and reconstructs it purely by replaying the `events` store (not the live Kafka topic), proving the read model is a pure function of the log.
- **Lag SLO.** Instrument CDC lag (`source.ts_ms` vs processed time) and the read-model staleness, and define an SLO on it (a preview of Week 18). Fail the report if median lag exceeds your target under the load workload.

---

## How this connects to the rest of C22

- **Week 13 (Postgres at scale)** is where the `orders` table and its WAL come from; your partition lifecycle keeps the CDC source healthy.
- **Week 15 (lakehouse)** routes this same change stream into Iceberg+Trino — your event-store consumer is the template for the Iceberg sink.
- **Week 22 (chaos gameday)** runs a Kafka-broker-loss drill against the capstone; the idempotency you proved here is exactly what stops that drill from double-processing.

## A note on what "byte-identical" really proves

The chaos comparison asserts the read model and event store are *identical* after a chaos run and a clean run. It's worth being precise about what that proves and what it doesn't, because a reviewer will press on it.

It **does** prove that your consumers turn at-least-once delivery into exactly-once processing for the workload you ran: every duplicate the restart caused Kafka to redeliver was absorbed with no additional effect. That is the property the whole week is about, and demonstrating it is far stronger than arguing it.

It **does not** prove your consumers are idempotent against *every* possible delivery anomaly — only against duplicate redelivery of recently-uncommitted messages, which is what a `kill -9` mid-batch produces. Out-of-order delivery across partitions, a connector re-snapshot that re-emits `op=r` events, or a consumer that commits offsets *before* applying (the classic bug) are separate hazards. The honest report names which anomalies your test covers and which it assumes away. The LSN-guarded upsert and the `UNIQUE (lsn, aggregate_id)` dedup are robust against most of these *by construction*, which is exactly why "idempotent by construction" beats "idempotent by an in-memory seen-set" — the construction survives a restart, the in-memory set does not.

The takeaway to carry to the capstone: idempotency is a property you *design in* (upsert by key, dedup by a stable change identifier, apply-and-record-atomically) and then *prove* with a chaos test, not a property you hope for and check by eye. The teams whose pipelines don't corrupt themselves are the ones who did both.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
