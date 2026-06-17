# Challenge 1 — The Split-Brain Double-Write

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. Last night the health checker declared `region-a` (your Postgres primary) unhealthy, and the automated failover promoted `region-b`'s replica to primary and repointed the write endpoint. The on-call who handled it marked the incident resolved: "failed over to B, service restored." This morning, the data team is escalating: **orders are missing, some order IDs exist twice with different contents, and the two regions' databases disagree about the current state of dozens of carts.**

Here's the twist that makes it a real incident: **`region-a` never actually went down.** It was *partitioned from the health checker* — a network issue between the monitoring system and region A — but region A's Postgres stayed up the whole time and *kept accepting writes from the clients that could still reach it.* So for the last eight hours you have had **two primaries**: region A (the "old" primary that was never fenced) and region B (the promoted "new" primary), both accepting writes, both diverging.

Your job: prove this is **split-brain** (not ordinary replication lag, not a one-region bug), name the exact step that was skipped, **reconcile the diverged data without silently dropping either region's writes**, and fix the failover procedure so it cannot happen again. "Just keep region B and throw away region A's writes" is *not* an acceptable answer — region A has real customer writes that were acknowledged; dropping them is data loss you'd have to explain to the customers who placed those orders.

This mirrors the most consequential real multi-region failover incident there is. A clean region death is easy: the region is gone, there's nothing to conflict with. The dangerous case is a region that's *unreachable from your monitoring* but *alive to its clients* — promote a new primary without fencing the old one, and you've manufactured two sources of truth.

## The harness

Reproduce it. Build the split-brain deliberately so you can diagnose it.

```bash
# Start from the Exercise 1 topology: region A primary, region B logical replica,
# the `writes(id, payload, ts)` table on both, replication streaming.

# 1. Drive some writes to A; confirm they replicate to B (normal operation).
for i in $(seq 1 50); do psql "$PGA" -c "INSERT INTO writes(payload) VALUES('A-normal-$i');"; done
psql "$PGB" -c "SELECT count(*) FROM writes;"   # ~50, B is caught up

# 2. PARTITION the health checker from A (simulate: just stop monitoring A) but
#    DO NOT actually stop A's Postgres. A is alive; the monitor just can't see it.

# 3. "Fail over": promote B WITHOUT fencing A (the bug).
psql "$PGB" -c "SELECT pg_promote();"           # B is now ALSO a primary
#    (and crucially: nobody made A read-only / stopped A / revoked its leadership)

# 4. Now BOTH accept writes — the split-brain. Drive writes to BOTH:
for i in $(seq 1 20); do psql "$PGA" -c "INSERT INTO writes(payload) VALUES('A-after-$i');"; done
for i in $(seq 1 20); do psql "$PGB" -c "INSERT INTO writes(payload) VALUES('B-after-$i');"; done
```

You now have the incident: two primaries, each with writes the other doesn't have, and (because both used the same `bigserial`) **colliding ids with different contents**. Diagnose it from the outside before reading the fix section.

## Your task

Produce a diagnosis and a remediation with these parts:

1. **Symptom** — exactly what you observe: the row counts on A vs B, the ids that exist on *both* with *different* `payload`, and the ids that exist on only one side. Show the divergence with queries, not prose.
2. **Proof it's split-brain, not lag** — the specific evidence that distinguishes "two primaries diverged" from "the replica is just behind." (Hint: replication lag is *one-directional and converges* — the replica is a strict prefix of the primary and catches up. Split-brain is *bidirectional and divergent* — each side has writes the other will *never* get, because the replication link is broken/promoted-away. Show that A has writes B lacks AND B has writes A lacks. A pure-lag scenario can never produce that.)
3. **The mechanism** — name it precisely: the failover promoted B to primary **without fencing A first**. Because A was only partitioned from the *monitor* (not actually down) and was never made read-only / stopped / stripped of leadership, it kept accepting writes. Two primaries = split-brain. Fencing (STONITH / making the old primary read-only / revoking its lease) *before* promotion is the missing step.
4. **The reconciliation** — merge the two divergent histories *without dropping either side's real writes*. You must: (a) stop the bleeding (fence A *now* — make it read-only so it stops accepting new writes), (b) identify the conflicting ids (same id, different payload) and the side-unique writes, (c) define a reconciliation rule that *preserves* both sides' real writes (e.g., re-key A's post-split writes onto fresh ids and replay them into B, the surviving primary — so no acknowledged write is lost), and (d) re-establish single-primary with B as primary and A re-synced as a replica.
5. **Procedure fix** — the change that makes this impossible: **fence before promote, always**, plus a guard that an automated failover cannot promote unless it has *positively fenced* the old primary (not merely failed to reach it). State the rule: "unreachable from the monitor" is NOT "safe to promote" — you must *prove the old primary cannot write* before you promote a new one.

You must reach the diagnosis with **at least two** independent signals — e.g., the bidirectional divergence (A-unique writes *and* B-unique writes) *and* the fact that A's Postgres was up and writable the whole time (`pg_is_in_recovery()` is `false` on A, and A's log shows accepted writes during the "outage"). One signal is a guess; two is a diagnosis.

## The fix, applied

Fence first, always. The corrected failover order (Lecture 2 §3.1):

```
detect -> decide -> FENCE the old primary -> promote the replica -> reroute -> verify
                     └─ make A read-only / stop A / revoke A's lease BEFORE promoting B ─┘
```

Fencing A in this lab (the step that was skipped):

```bash
# BEFORE promoting B, make A unable to accept writes. Any of these fences it:
psql "$PGA" -c "ALTER SYSTEM SET default_transaction_read_only = on; SELECT pg_reload_conf();"
# or stop it outright:
kubectl --context kind-region-a scale deploy/pg --replicas=0
# or, in a leader-lease system (Patroni/etcd): revoke A's leadership lease so it
# demotes itself when it can't renew. The point: A CANNOT write after this.
```

The automated-failover guard:

```
# An automated failover MUST satisfy this before promote:
#   fenced(old_primary) == TRUE
# where fenced() means "positively confirmed cannot write" (lease revoked, or
# write-fenced, or powered off) — NOT "health check timed out." A timed-out
# health check means UNKNOWN, and promoting on UNKNOWN is how you get two primaries.
```

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You show the **bidirectional divergence** with queries: ids unique to A, ids unique to B, and ids present on both with *different* payloads.
- [ ] You demonstrate A was **alive and writable** throughout (`pg_is_in_recovery()` = false on A; A accepted writes after the "failover") — proving it's split-brain, not lag.
- [ ] Your reconciliation **preserves both sides' real writes** (no acknowledged write silently dropped) and re-establishes a single primary (B) with A re-synced as a replica.
- [ ] Your procedure fix is **fence-before-promote** with the "unreachable ≠ safe to promote" guard — NOT "always keep B."
- [ ] A `failover-fixed.md` (or runbook section) with the corrected, fenced procedure, checked in.
- [ ] Committed to your Week 19 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The two wrong "fixes" you must NOT write:

- **"Keep region B, drop region A's post-split writes."** This makes the divergence disappear by *throwing away acknowledged customer writes*. Those `A-after-*` rows are real orders someone placed and got a confirmation for; silently dropping them is data loss you'd have to explain to those customers. Reconciliation that preserves both sides is harder and is the only correct answer. Picking a winner and dropping the loser's writes is not reconciliation; it's giving up and calling it a decision.
- **"Add a longer health-check timeout so we don't fail over so eagerly."** This *reduces the frequency* of the bug but doesn't *fix* it — a longer timeout still eventually promotes on a partition, and you're back to two primaries, just less often. The fix is structural: **fence before promote**, so even an eager (or wrong) failover decision cannot produce two writable primaries. A timeout is a probability tweak; fencing is a correctness guarantee.

A related real-world cousin worth naming in your writeup: the **even-member quorum split-brain** (Lecture 1 §4.2). Two regions with an even number of voting members partition, neither side has a majority, and a misconfigured system lets both sides act as authoritative. It's the same disease (two sources of truth) with a different cause (no quorum tie-breaker instead of no fencing), and the cure is related: a witness/arbiter to break the tie, plus fencing on the losing side.

## Stretch

- Build the **automated fence**: a tiny controller that, on failover, *first* revokes A's write capability (sets `default_transaction_read_only` or scales A to 0) and only *then* promotes B — and refuses to promote if it cannot confirm the fence. Demonstrate it prevents the split-brain even when you trigger an eager failover.
- Add a **witness node** so the failover decision requires a quorum (A + B + witness): show that with the witness, a partition that isolates A leaves B+witness with a majority (safe to promote, and A demotes itself because it *lost* the quorum), while a partition that isolates the *monitor* doesn't trigger a failover at all. This is the quorum-based prevention.
- Write the **reconciliation as a script**: detect colliding ids, re-key one side's post-split writes onto fresh ids, replay them into the surviving primary, and verify the merged result contains every acknowledged write from both sides. This is the "preserve both sides" rule made executable.

## Why this matters

Every multi-region system that does automated failover is one network partition away from this incident. The instinct — "we lost the primary, promote the replica" — is exactly right when the primary is *actually gone* and exactly catastrophic when the primary is merely *unreachable from your monitor*. The difference between a DR plan that survives a partition and one that corrupts data is a single step done in the right order: **fence the old primary before you promote a new one, and never treat "I can't reach it" as "it can't write."** When you defend your `cart-multiregion` mini-project at the Phase 4 review, "my failover fences before it promotes, and my runbook proves unreachable-isn't-dead" is the line that says you've operated a multi-region system, not just drawn one.
