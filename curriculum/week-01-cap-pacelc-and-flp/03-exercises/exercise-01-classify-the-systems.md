# Exercise 1 — Classify the Systems

**Goal:** Take ten real systems and place each one on the **consistency lattice** (linearizable / sequential / causal / eventual) and the **PACELC grid** (PA/EL, PC/EC, PA/EC, PC/EL), with a one-sentence justification each. This is the single most important reasoning drill of the week: the code in Exercises 2 and 3 only makes sense once you can name a tradeoff out loud.

**Estimated time:** 60 minutes. Written.

---

## Setup

Create `notes/week-01/classification.md` in your Week 1 repo. You will fill in two tables and answer three follow-up questions. Use the lectures and the linked docs — this is open-book. The point is not to memorize a vendor's marketing; it is to read the *actual* default behavior and name it.

A reminder of the rules you are applying (Lecture 1 §3, Lecture 2 §1):

- **Consistency model** is for a *single key/object* at the system's **default** configuration. If a system is tunable, classify its default and note the knob.
- **PACELC**: the **P** branch is the partition behavior (CAP); the **E** branch is the *healthy-network* behavior (latency vs consistency).
- The brand is not the model. Read what the default actually does.

---

## Part A — The consistency lattice

For each system, give the default single-key consistency model and one sentence of justification.

| # | System | Default consistency model | Justification (one sentence) |
|---|---|---|---|
| 1 | etcd (linearizable reads) | | |
| 2 | ZooKeeper | | |
| 3 | Single-leader Postgres, read from an **async replica** | | |
| 4 | Single-leader Postgres, read from the **primary** | | |
| 5 | DynamoDB, default reads | | |
| 6 | DynamoDB, `ConsistentRead=true` | | |
| 7 | Cassandra, `ONE`/`ONE` | | |
| 8 | Cassandra, `QUORUM`/`QUORUM` | | |
| 9 | Riak (no CRDT) | | |
| 10 | Google Spanner | | |

## Part B — The PACELC grid

For each system, give its PACELC label and one sentence on *why*, separating the partition branch from the else branch.

| # | System | PACELC label | Justification (partition branch + else branch) |
|---|---|---|---|
| 1 | etcd | | |
| 2 | DynamoDB (default) | | |
| 3 | Cassandra (`ONE`) | | |
| 4 | Spanner | | |
| 5 | PNUTS | | |
| 6 | A single-node Redis (no replica) | | |
| 7 | Redis with async replica + failover | | |
| 8 | MongoDB, `w:majority` writes, primary reads | | |
| 9 | CockroachDB | | |
| 10 | Kafka (a partition's log, default `acks=all`) | | |

## Part C — Follow-up questions

Answer each in 2–4 sentences in the same file.

1. **The replica trap.** Items A3 and A4 are the *same database*, yet you classified them differently. Explain why "Postgres is strongly consistent" is a dangerous half-truth, and name the consistency model an async-replica read actually provides.

2. **The brand is not the model.** Items A5/A6 and A7/A8 show systems that change consistency model *per request* or *per configuration*. Pick one pair and explain what an engineer must read (which API field, which config) to know which model they're actually getting.

3. **The CA temptation.** B6 (single-node Redis) is the only system here for which "CA" is an honest label. Explain why, and why the moment you add B7 (a replica + failover) the honest label changes — and to which one.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] Both tables are filled, every cell with a model/label **and** a justification.
- [ ] A3 and A4 are classified **differently** (eventual vs linearizable), and you can say why in one sentence.
- [ ] A5/A6 differ (eventual vs linearizable) and A7/A8 differ (eventual-ish vs strong-ish), reflecting the per-request/per-config nature.
- [ ] Every PACELC label has **both** branches justified — the partition behavior *and* the else behavior. A label with only one branch justified is incomplete.
- [ ] All three follow-up questions are answered.

---

## Answer sketch (read only after you've attempted it)

These are defensible answers; minor disagreements that you can justify are fine — the justification matters more than matching this exactly.

**Part A.**
1. etcd — **linearizable** (Raft; linearizable reads go through the leader/quorum).
2. ZooKeeper — **linearizable writes, sequential reads** (Zab orders writes; reads from a follower can be stale → sequential, with a `sync` to force linearizable).
3. Postgres async replica — **eventual** (replication lag is the staleness window; no read-your-writes).
4. Postgres primary — **linearizable** (single copy of truth, serialized through the leader).
5. DynamoDB default — **eventual** (default reads are eventually consistent).
6. DynamoDB `ConsistentRead=true` — **linearizable** (strongly consistent read, opt-in, costs more and is partition-sensitive).
7. Cassandra `ONE`/`ONE` — **eventual** (one replica answers; no overlap guarantee).
8. Cassandra `QUORUM`/`QUORUM` — **strong-ish** (read and write quorums overlap → you read your writes; not full linearizability without `SERIAL`/LWT, so call it "quorum-strong, not linearizable").
9. Riak (no CRDT) — **eventual** (AP design; conflicts surface as siblings).
10. Spanner — **linearizable / externally consistent** (TrueTime gives a global real-time order).

**Part B.**
1. etcd — **PC/EC** (minority refuses under partition; coordinates through quorum when healthy).
2. DynamoDB default — **PA/EL** (available under partition; nearest-replica fast reads when healthy).
3. Cassandra `ONE` — **PA/EL** (same shape).
4. Spanner — **PC/EC** (consistent under partition; pays the TrueTime wait as latency when healthy).
5. PNUTS — **PC/EL** (consistent under partition for its record master; latency-optimized when healthy — the textbook PC/EL).
6. Single-node Redis — **"CA"** honestly, because there is no network between replicas to partition; it's one node.
7. Redis + async replica + failover — **PA/EL** in practice, and notably **not safe**: async failover can lose acknowledged writes (a *safety* violation, the dangerous kind).
8. MongoDB `w:majority`, primary reads — **PC/EC**-leaning (majority write coordination; primary reads are strong).
9. CockroachDB — **PC/EC** (Raft per range; serializable isolation; minority unavailable under partition).
10. Kafka partition, `acks=all` — **PC/EC** for that partition's log (ISR-based; loses availability for the partition if it can't form an in-sync quorum, preserving log integrity).

**Part C.**
1. The same database is linearizable on the primary and only eventual on an async replica; the model depends on *where you read*, so "Postgres is strongly consistent" silently assumes primary reads. An async-replica read provides **eventual** consistency with a lag-sized staleness window.
2. For DynamoDB you must read the `ConsistentRead` request flag; for Cassandra you must read the per-statement consistency level (`ONE` vs `QUORUM` vs `SERIAL`). The model is a *request/config property*, not a database property.
3. Single-node Redis is "CA" honestly because there is no inter-node network to partition — it's one machine, so partition tolerance is vacuous. Add a replica and failover and the network reappears; the honest label becomes **AP** (and an *unsafe* one, since async failover can drop acknowledged writes).

---

## Stretch

- Add three systems you operate at work and classify them. The hardest and most valuable ones are the systems your team *believes* are strongly consistent but configured into an EL corner for latency.
- For any one PA/EL system, write down the **staleness budget** you'd be willing to accept (e.g., "reads may be up to 200 ms stale") and how you'd *measure* whether reality stays inside it. That number is the EL choice made explicit.

When this feels comfortable, move to [Exercise 2 — The partitioned register](./exercise-02-partitioned-register.go).
