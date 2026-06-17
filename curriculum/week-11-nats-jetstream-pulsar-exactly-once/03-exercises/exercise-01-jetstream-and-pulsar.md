# Exercise 1 — JetStream and Pulsar Up Close

**Goal:** Stand up NATS JetStream and Apache Pulsar in Docker, create durable streams/topics, and *observe* the two features that distinguish them from plain Kafka: JetStream's **dedup window** (a repeated `Nats-Msg-Id` is silently dropped within the window, accepted after it) and Pulsar's **subscription modes** (key-shared preserves per-key order; shared maximizes parallelism with no ordering). You will train the habit of reaching for the right broker primitive instead of bolting one on.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need Docker. We run NATS and Pulsar in standalone single-node mode — enough to see the semantics, not production topology.

```bash
docker --version
```

Install the two CLIs (they make the semantics visible without writing code):

```bash
# nats CLI (https://github.com/nats-io/natscli) — brew, apt, or the release binary
brew install nats-io/nats-tools/nats        # macOS; see the repo for Linux
# pulsar-admin ships inside the pulsar image; we'll exec into the container.
```

---

## Part A — NATS JetStream and the dedup window

### Step 1 — Run a JetStream server

```bash
docker run -d --name nats-js -p 4222:4222 nats:2.10 -js
# -js enables JetStream (persistence). Without it you get core NATS (at-most-once).
```

### Step 2 — Create a stream with a 2-minute dedup window

```bash
nats stream add ORDERS \
  --subjects "order.>" \
  --storage file \
  --replicas 1 \
  --retention limits \
  --dupe-window 2m \
  --max-age 1h \
  --defaults
```

`--subjects "order.>"` captures every subject under `order` (the wildcard from Lecture 1 §3.1). `--dupe-window 2m` is the load-bearing flag: JetStream will drop a repeated `Nats-Msg-Id` seen within 2 minutes. Confirm:

```bash
nats stream info ORDERS
# Look for "Duplicate Window: 2m0s" in the output.
```

### Step 3 — Publish with a `Nats-Msg-Id` and watch the dedup

Publish the *same* message id twice in quick succession:

```bash
nats pub order.placed '{"order_id":"A","total":4200}' -H "Nats-Msg-Id:evt-A-001"
nats pub order.placed '{"order_id":"A","total":4200}' -H "Nats-Msg-Id:evt-A-001"   # DUPLICATE id
nats pub order.placed '{"order_id":"B","total":1999}' -H "Nats-Msg-Id:evt-B-001"
```

Check how many messages the stream actually stored:

```bash
nats stream info ORDERS | grep Messages
# Messages: 2     <-- NOT 3! The duplicate evt-A-001 was dropped by the dedup window.
```

**Two messages, not three.** The second `evt-A-001` was deduplicated at the broker because it arrived within the 2-minute window. This dedups *producer retries* — exactly the network-blip-resend case from Lecture 1.

### Step 4 — Prove the window is bounded (the critical limitation)

The dedup is time-bounded, and you must internalize that it is *not* a permanent guarantee. If you wait out the window and republish the same id, it is **accepted as new**:

```bash
# (For a fast demo, recreate the stream with --dupe-window 5s, then:)
nats pub order.placed '{"order_id":"C"}' -H "Nats-Msg-Id:evt-C-001"
sleep 6                                    # wait past the 5s window
nats pub order.placed '{"order_id":"C"}' -H "Nats-Msg-Id:evt-C-001"   # SAME id, after window
nats stream info ORDERS | grep Messages
# The count went UP by 2, not 1 — the post-window duplicate was NOT deduped.
```

> **The lesson (Lecture 1 §3.3):** the dedup window protects against fast retries, not against a duplicate that arrives hours later (a consumer replay, a delayed redelivery). It is a *weaker* guarantee than an idempotent consumer with a permanent dedup table. Use it as a cheap first line of defense; never as your only defense. The outbox + idempotent consumer (exercises 2–3) is the durable guarantee.

### Step 5 — A durable pull consumer (at-least-once)

```bash
nats consumer add ORDERS fulfillment \
  --pull --ack explicit --deliver all --max-deliver 5 --defaults
nats consumer next ORDERS fulfillment --count 2
# Pulls and acks 2 messages. Durable: the position survives a reconnect. Explicit ack:
# crash before ack and JetStream redelivers — at-least-once, exactly like Kafka.
```

---

## Part B — Pulsar subscription modes

### Step 6 — Run Pulsar standalone

```bash
docker run -d --name pulsar -p 6650:6650 -p 8080:8080 \
  apachepulsar/pulsar:3.3.0 bin/pulsar standalone
# Wait ~30s for it to start; check: docker logs pulsar 2>&1 | grep "messaging service is ready"
```

### Step 7 — Key-shared: per-key ordering with parallelism

Open two consumer terminals on the **same** subscription in **key-shared** mode:

```bash
# Terminal 1 and Terminal 2, both:
docker exec -it pulsar bin/pulsar-client consume \
  persistent://public/default/orders -s checkout-sub \
  --subscription-type Key_Shared -n 0
```

Produce keyed messages:

```bash
docker exec -it pulsar bin/pulsar-client produce \
  persistent://public/default/orders --key order-A -m "A1" -m "A2" -m "A3"
docker exec -it pulsar bin/pulsar-client produce \
  persistent://public/default/orders --key order-B -m "B1" -m "B2"
```

**Observe:** all `order-A` messages land on *one* consumer (in order A1, A2, A3); all `order-B` on (possibly) the other. Same key → same consumer → per-key order preserved, with parallelism across keys. This is Kafka's keyed-partition model without a fixed partition count (Lecture 1 §4.3).

### Step 8 — Shared: maximum parallelism, no ordering

Restart both consumers in **shared** mode (`--subscription-type Shared`, a fresh subscription name `worker-sub`), produce the same messages, and **observe:** messages round-robin across both consumers regardless of key — A1 might go to consumer 1, A2 to consumer 2. No ordering, maximum throughput. This is a classic work queue, which a Kafka partition cannot do (one partition, one consumer).

> **The lesson (Lecture 1 §4.3):** Pulsar lets you pick the ordering/parallelism trade-off *per subscription*. Key-shared for ordered-per-entity processing; shared for an order-independent work queue. Kafka forces this decision at the partition level; Pulsar makes it a subscription flag.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `nats stream info ORDERS` shows `Messages: 2` after publishing `evt-A-001` twice and `evt-B-001` once — proving the dedup window dropped the in-window duplicate.
- [ ] You demonstrated that a repeat `Nats-Msg-Id` published *after* the window expires is *accepted* (count goes up) — proving the window is time-bounded, not permanent.
- [ ] A durable pull consumer on JetStream pulls and acks with `--ack explicit` (at-least-once).
- [ ] In Pulsar **key-shared**, all messages for one key reached one consumer in order.
- [ ] In Pulsar **shared**, messages round-robined across consumers regardless of key.
- [ ] You can state, in one sentence, why the JetStream dedup window is a *weaker* guarantee than an idempotent consumer (it's time-bounded; a late duplicate slips through).

---

## Stretch

- Set up **Pulsar tiered storage** to a local MinIO (S3-compatible), produce enough to roll a ledger, offload it with `pulsar-admin topics offload`, delete the local copy, and read the offloaded data back transparently. You just kept history at object-storage prices (Lecture 1 §4.2).
- Subscribe a JetStream consumer to `*.placed.us-east` and another to `order.>`, publish a mix of subjects, and confirm each consumer receives exactly the subjects its wildcard matches (Lecture 1 §3.1).
- Run a JetStream stream with `--replicas 3` on a 3-node NATS cluster and kill the stream leader; watch Raft elect a new one and the stream stay available — the Week 2 Raft you studied, doing JetStream's replication.

---

When the dedup window and the subscription modes feel concrete, move to [Exercise 2 — The transactional outbox relay](./exercise-02-outbox-relay.go).
