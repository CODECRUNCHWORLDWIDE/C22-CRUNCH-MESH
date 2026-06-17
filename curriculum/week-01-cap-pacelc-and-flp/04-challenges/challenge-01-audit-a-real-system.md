# Challenge 1 — Audit a Real System's Consistency Claims

**Time estimate:** ~90 minutes.

## Problem statement

You are the staff engineer in a design review. A team wants to adopt a data system and has written "it's strongly consistent and highly available" in the proposal. Your job is not to approve or reject — it is to **translate that sentence into the truth**: what consistency model does the system actually provide, in what configuration, what does it do under partition and on a healthy network, which of its guarantees are safety and which are liveness, and where does its own documentation quietly overstate the case?

You will pick one real system, read its *actual* documentation (not a blog summary), and write a one-and-a-half-page audit. This is the midterm architecture-review essay in miniature.

## Pick one system

Choose one you do **not** already understand deeply (the point is to read, not to recite):

- **Apache Cassandra** — tunable consistency levels; LWT (`SERIAL`); read-repair.
- **Amazon DynamoDB** — eventually vs strongly consistent reads; global tables.
- **MongoDB** — read/write concerns; `readPreference`; causal consistency sessions.
- **etcd** — linearizable vs serializable reads; the Raft guarantees.
- **CockroachDB** — serializable isolation; the Raft-per-range model; follower reads.
- **Apache Kafka** — per-partition log ordering; `acks`; ISR; the "exactly-once" claims.
- **Redis (Cluster + Sentinel)** — async replication; failover; the `WAIT` command.

## The audit (the deliverable)

Write `challenge-01-audit.md` with these six sections. Cite the specific documentation page or section for every claim — "the docs say X (link/section)" — so the audit is checkable.

### 1. Default consistency model

State the system's **default** single-object consistency model (linearizable / sequential / causal / eventual) and the exact configuration that produces it. If it is tunable, give the *default* and name the knob that moves it. Quote the doc.

### 2. The configuration sweep

Show how the consistency model **changes** across at least three configurations (e.g., Cassandra `ONE` vs `QUORUM` vs `SERIAL`; DynamoDB default vs `ConsistentRead`; Mongo `w:1` vs `w:majority` + `readConcern:majority` + causal session). For each, name the resulting model. This is the "brand is not the model" lesson made concrete.

### 3. PACELC corner

Assign the PACELC label (PA/EL, PC/EC, PA/EC, PC/EL) **for a named configuration**, and justify **both** branches: what it does under partition, and what it does on a healthy network. A label with only one branch justified does not count.

### 4. Safety vs liveness inventory

List at least **three** guarantees the system makes and classify each as **safety** ("nothing bad ever happens" — violable by a finite prefix) or **liveness** ("something good eventually happens" — violable only by an infinite execution). Example shape: "no acknowledged write is lost" (safety); "a write is eventually visible on all replicas" (liveness); "an election eventually completes" (liveness).

### 5. The overstatement

Find **at least one** place where the documentation or marketing **overstates** the guarantee, and name precisely what is missing. Classic finds: a "strongly consistent" badge that only applies to one read mode you must opt into; a "highly available" claim that is really PA/EL with a staleness window nobody quantifies; an "exactly-once" label that is really "effectively-once given an idempotent consumer and these four preconditions"; a durability claim that holds only with `fsync` settings the default disables. State the gap as a sentence a reviewer could act on.

### 6. The recommendation

In 3–5 sentences: for what workload is this system's true (audited) behavior a *good* fit, and for what workload would adopting it on the strength of the proposal's sentence be a mistake? Tie it to a consistency model and a PACELC corner, not to vibes.

## Acceptance criteria

- [ ] `challenge-01-audit.md` exists with all six sections.
- [ ] Every factual claim cites a specific documentation page/section (not a blog, not memory).
- [ ] Section 2 shows **at least three** configurations producing **at least two different** consistency models.
- [ ] Section 3's PACELC label justifies **both** the partition branch and the else branch.
- [ ] Section 4 classifies **at least three** guarantees, correctly split into safety vs liveness.
- [ ] Section 5 names a **specific** overstatement with the precise missing qualifier — not "the docs are vague."
- [ ] Committed to your Week 1 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The most common failure is auditing the *brand* instead of a *configuration*. "Cassandra is AP" is the kind of sentence this challenge exists to kill. Cassandra at `QUORUM`/`QUORUM` reads-your-writes; at `ONE` it's eventual; with `SERIAL` LWT it does Paxos and becomes (for that operation) linearizable-and-CP. The system is not one point on the grid — it is a *family* of points selected by configuration, and a real audit says which point a real deployment sits at. If your audit has no configuration in it, you audited a logo.

## Stretch

- Find the most recent **Jepsen report** for your chosen system (<https://jepsen.io/analyses>) and map every violation Kyle Kingsbury found back to a consistency-model name and a safety/liveness class. Note which violations were docs-vs-reality gaps (the system did less than it claimed) versus genuine bugs (the system did less than it intended).
- Write the **one paragraph** you would add to the team's proposal to make its consistency sentence true. This is the single most useful artifact you can produce in a real review: not "no," but "here is the sentence that is actually correct."

## Why this matters

At the Week 12 midterm you write a 2,500-word architecture review of a public distributed system. In the capstone you defend *your* system's consistency choices to external reviewers. In every staff-engineer interview loop, someone will draw a box and ask "what does this guarantee under partition?" This challenge is that conversation, rehearsed against a real system, with the receipts. The engineer who can produce this audit in 90 minutes is the one who gets to make the adoption decision instead of merely implementing someone else's.
