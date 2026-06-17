# Week 19 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 20. Answer key is at the bottom — don't peek.

---

**Q1.** What is the core difference between active-active and active-passive?

- A) Active-active is faster because it uses more CPU.
- B) Active-active has multiple regions accepting writes simultaneously (a conflict-resolution problem); active-passive has one region writing while others stand by ready to take over (a replication problem with a failover step).
- C) Active-passive has no replication.
- D) Active-active requires synchronous replication; active-passive forbids it.

---

**Q2.** What do RTO and RPO measure, respectively?

- A) RTO = requests per second; RPO = replicas per output.
- B) RTO = how long until service is restored after a failure (a recovery *time*); RPO = how much data you can afford to lose, measured as the age of the last replicated write (a recovery *point*).
- C) They're two names for the same downtime number.
- D) RTO = data lost; RPO = time down.

---

**Q3.** Your replica is 400 ms behind the primary when the primary dies and you fail over. What is your realized RPO?

- A) Zero — failover always preserves all data.
- B) About 400 ms — your RPO at failover equals the replication lag at the moment of failure; the ~400 ms of unreplicated writes are lost.
- C) Unbounded — you lose everything.
- D) Exactly the RTO, whatever that is.

---

**Q4.** Why is synchronous cross-region replication usually the wrong default?

- A) It loses data.
- B) It gives RPO≈0 but pays the cross-region round-trip (tens to 100+ ms) on *every* commit, crippling write latency — and adds a failure mode if the remote replica is unreachable. Async (fast writes, small monitored RPO) is the pragmatic default.
- C) It's not supported by Postgres.
- D) It only works within a single region.

---

**Q5.** What is the read-local/write-primary pattern, and why is it the pragmatic default?

- A) Read and write both go to the nearest region.
- B) Each region serves reads from its local async replica (fast, local) but all writes go to the single primary region — so reads are local, writes pay the cross-region trip but are a minority, there's one source of truth (no conflict), and RPO is the small monitored async lag. It respects data gravity.
- C) Writes go everywhere; reads go to one place.
- D) It requires active-active.

---

**Q6.** Why does spreading a consensus group (quorum) evenly across two regions create a split-brain trap?

- A) It doesn't; even is fine.
- B) A partition between the two regions leaves neither side with a majority (e.g., 2 of 4), so neither can make progress — or, if misconfigured, both act authoritative. The fix is three regions, or two-plus-a-witness, so the survivors retain a majority.
- C) Quorum requires exactly two members.
- D) Consensus doesn't work across regions at all.

---

**Q7.** What is the DNS TTL tax on failover?

- A) DNS costs money per query.
- B) A record cached for TTL seconds means clients keep hitting the dead region for up to TTL after you flip it — so effective RTO = failover RTO + TTL. This is why failover-critical records run low TTLs (and why anycast failover, with no DNS cache, can be faster).
- C) TTL is the time the database takes to promote.
- D) TTL only affects reads, never failover.

---

**Q8.** Why is multi-region described as "a data problem, not a compute problem"?

- A) Compute is more expensive than data.
- B) Stateless compute is trivial to replicate (run a copy per region); data has *gravity* — it attracts its services and resists being moved, and deciding how it lives in two places (one primary or two, sync or async, conflict handling) is the entire hard part.
- C) Data is always smaller than compute.
- D) Compute can't run in multiple regions.

---

**Q9.** How can a data-residency law (e.g. GDPR) change a multi-region architecture decision?

- A) It can't; residency is a latency optimization.
- B) It turns geography into a *correctness* constraint: if EU data must stay in the EU, that can forbid a naive active-active (which replicates data everywhere) and force a partitioned-by-region layout where regulated rows never leave their region. You ask the lawyers before the latency budget.
- C) It only affects backups.
- D) It requires synchronous replication.

---

**Q10.** What is the single step in a failover that prevents split-brain, and where does it go in the order?

- A) Promoting the replica, first.
- B) **Fencing the old primary** (making it unable to write) — and it must happen *before* promoting the replica. Skip it and an old primary that's merely unreachable (not dead) keeps accepting writes, giving you two primaries.
- C) Lowering the DNS TTL, last.
- D) There is no such step; split-brain is unavoidable.

---

**Q11.** During an incident, the health checker can't reach the primary region. Is it safe to promote the replica?

- A) Yes — unreachable means dead, so promote immediately.
- B) Not without fencing first. "Unreachable from the monitor" is UNKNOWN, not "dead" — the primary may be alive and writable to clients that *can* reach it. You must positively confirm it cannot write (fence it) before promoting, or you risk two primaries.
- C) Only if the TTL is low.
- D) Promotion is never safe.

---

**Q12.** Why is fail-back (bringing the recovered region back) often harder than the failover?

- A) It isn't; fail-back is trivial.
- B) The recovered region comes back as a stale former-primary, possibly holding unreplicated writes; turning it back on as a primary causes split-brain or stale-overwrites. The correct fail-back re-syncs it as a *replica* of the current primary first (reconciling/discarding its stranded writes), then optionally fails back as a planned, fenced failover.
- C) Fail-back requires a new region.
- D) Fail-back loses all data by definition.

---

**Q13.** What does it mean to "measure" an RTO and RPO, and why does it matter?

- A) Read them off the architecture diagram.
- B) Drive real write traffic, kill the primary, and measure end-to-end: RTO = first-failed-request to first-successful-request on the new primary (including detection and TTL), RPO = the count of acknowledged/in-flight writes absent from the new primary (= the lag). It matters because an unmeasured RTO/RPO is a hope, and the drill catches the silent failures (a standby that never replicated) before a real incident does.
- C) Estimate them from the cloud provider's SLA.
- D) They can't be measured locally.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Multiple write paths (conflict) vs one write path + failover (replication). The conflict problem is what makes active-active hard. (Lecture 1 §1.)
2. **B** — RTO = time to restore; RPO = data you can lose (age of last replicated write). (Lecture 1 §2.)
3. **B** — RPO at failover = replication lag at failure; the unreplicated writes are lost. (Lecture 1 §2.2.)
4. **B** — RPO≈0 but every commit pays the cross-region round-trip; async is the pragmatic default. (Lecture 1 §3.)
5. **B** — Reads local from a replica, writes to the one primary; one source of truth, small monitored RPO; respects data gravity. (Lecture 1 §3.3; Lecture 2 §2.1.)
6. **B** — Even members → a partition leaves neither side a majority → stall or split-brain; fix with odd members / a witness. (Lecture 1 §4.2.)
7. **B** — Cached clients hit the dead region for up to TTL; effective RTO = RTO + TTL; hence low TTLs / anycast. (Lecture 2 §1.3.)
8. **B** — Compute is stateless and cheap to replicate; data has gravity and is the whole hard part. (Lecture 2 §2.1.)
9. **B** — Residency makes geography a correctness constraint that can forbid active-active and force partition-by-region. (Lecture 2 §2.3.)
10. **B** — Fence the old primary *before* promoting the new one; it's the split-brain guard. (Lecture 2 §3.1; Challenge.)
11. **B** — Unreachable = UNKNOWN, not dead; fence (confirm it can't write) before promoting. (Lecture 2 §3.1; Challenge.)
12. **B** — Recovered region is a stale former-primary; re-sync as a replica first, reconcile stranded writes, then planned fail-back. (Lecture 2 §3.2.)
13. **B** — Drive traffic, kill the primary, measure end-to-end RTO and the lost-write RPO (= lag); the drill catches silent failures. (Lecture 2 §3.3; Exercise 3.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./06-homework.md).
