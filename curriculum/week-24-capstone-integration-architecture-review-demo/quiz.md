# Week 24 — Quiz

Thirteen questions. Take it with your notes closed. This is the last quiz of C22 — it tests the *defense* skills, not new mechanics. Aim for 11/13. Answer key is at the bottom — don't peek.

---

**Q1.** What is an architecture review actually for?

- A) To show off what you built and get applause.
- B) To surface, in one hour, the risks that would otherwise take six months to find in production — producing a risk list tagged accept/mitigate-now/mitigate-later with owners.
- C) To get sign-off on a budget.
- D) To compare your design against the reviewer's preferred design.

---

**Q2.** A reviewer asks "which parts of your system are strongly consistent and which are eventually consistent?" Why is "everything is strongly consistent" the wrong answer?

- A) Because strong consistency is impossible.
- B) Because it shows you didn't reason about the CAP/PACELC tradeoff per data type — the cart is a CRDT (eventually consistent, so adds aren't lost) and inventory/payment are strongly consistent (no oversell, no double-charge), each by design.
- C) Because eventual consistency is always better.
- D) Because the question is a trap with no good answer.

---

**Q3.** What is the single most effective thing you do in a live architecture review?

- A) Read every box on the diagram aloud.
- B) Trace one real request through the live system using your own observability, ending in a trace-to-log jump — proving the system is observable enough to operate.
- C) Show the most complex diagram you have.
- D) Quote the documentation for each tool you used.

---

**Q4.** In Drill A (region failover), why is it important to walk the three failure domains separately?

- A) It isn't; a region loss is one failure.
- B) Because a region loss hits the CRDT cart, the leased inventory, and the Temporal payment differently — each was given its consistency model for a reason, and showing how each behaves proves you made those choices deliberately.
- C) Because Kubernetes requires it.
- D) To make the postmortem longer.

---

**Q5.** In Drill B (Kafka broker loss), what is the load-bearing proof that exactly-once held?

- A) The system didn't crash.
- B) A SQL query `SELECT idempotency_key, COUNT(*) ... HAVING COUNT(*) > 1` returning **zero rows** — you queried for the double-charge under the exact failure that would cause it, and found none.
- C) The logs looked normal.
- D) The CPU stayed under 80%.

---

**Q6.** Why does a Kafka broker loss specifically risk a double-charge if idempotency is broken?

- A) Brokers corrupt data when they die.
- B) The broker loss triggers a leader failover and a consumer rebalance; a consumer that pulled a batch but hadn't committed its offset re-pulls it after the rebalance — at-least-once redelivery — which is exactly when a non-idempotent consumer double-processes.
- C) Kafka deletes the topic on broker loss.
- D) It doesn't; broker loss is always safe.

---

**Q7.** What makes a postmortem "blameless," and why does it matter?

- A) It names who caused the incident.
- B) It fixes the *system*, not the person — asking "what about the system let this happen and how do we change it," which makes the postmortem a learning artifact instead of a punishment.
- C) It assigns no action items.
- D) It is kept secret from the team.

---

**Q8.** The four required segments of the 12-minute demo are:

- A) Intro, body, conclusion, Q&A.
- B) Architecture walkthrough, a live weighted-canary deploy (with automatic rollback), a Grafana tour ending in a trace-to-log jump, and the cart-CRDT convergence across a simulated partition.
- C) Slides, code, tests, and a summary.
- D) Whatever you have time for.

---

**Q9.** What is the highest-leverage move a presenter makes in a review?

- A) Defending every choice as obviously correct.
- B) Naming their own biggest risk before anyone asks — it shows they understand the system's weaknesses and sets the agenda on the risk they already know about.
- C) Avoiding any mention of weaknesses.
- D) Using the most advanced terminology possible.

---

**Q10.** A reviewer asks "what does one order cost you?" What's the senior insight to state?

- A) "I don't track cost."
- B) "Most of the cost is *fixed* — the always-on replicas and the substrate (Kafka, Temporal, Postgres, the mesh) — not per-order, so doubling traffic barely moves the bill and the optimization lever is 'is the floor justified,' not 'make each order cheaper.'"
- C) "Each order costs whatever the cloud charges."
- D) "Cost isn't an engineering concern."

---

**Q11.** Why is "it works on my machine" not a valid capstone defense?

- A) Because machines vary.
- B) Because a system you can't bring up reproducibly on demand is a pet, not a system — the review (and a grader) will ask you to stand it up from scratch, and reproducibility is itself a deliverable.
- C) Because the reviewers don't trust you.
- D) It is valid if the machine is powerful enough.

---

**Q12.** A reviewer says "your failover is about a minute, right?" and you can't show a measurement. What's the consequence?

- A) Nothing; estimates are fine.
- B) Every other number you stated becomes suspect — the fix is to run the drill (Exercise 2) and answer from the measured postmortem, not an estimate.
- C) The reviewer accepts the estimate.
- D) You get partial credit for the guess.

---

**Q13.** What does the capstone's risk list become after the review?

- A) Nothing; it's discarded.
- B) The README's "Known limitations and next steps" section — a *feature* that reads as credible, because a portfolio that names the three things you'd fix first (with costs) is more trustworthy than one pretending the system is perfect.
- C) A list of reasons the project failed.
- D) A private document never shared.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — A one-hour risk search producing an owned risk list. (Lecture 1 §1.1.)
2. **B** — The per-field CAP choice; "all strong" means you didn't reason about it. (Lecture 1 §1.4.)
3. **B** — Trace one real request live, ending in a trace-to-log jump. (Lecture 1 §1.5, §1.5b.)
4. **B** — Three failure domains fail differently by design; showing each proves deliberate choices. (Lecture 2 §1.2.)
5. **B** — The empty `HAVING COUNT(*) > 1` result set under the broker loss. (Lecture 2 §2.3, §2.4.)
6. **B** — Rebalance → re-pull of an uncommitted batch → at-least-once redelivery, the double-charge moment. (Lecture 2 §2.2.)
7. **B** — Fix the system not the person; a learning artifact, not punishment. (Lecture 2 §1.4.)
8. **B** — The four named segments from the syllabus demo spec. (Lecture 2 §3.1.)
9. **B** — Name your own biggest risk first. (Lecture 1 §1.6.)
10. **B** — Most cost is fixed (substrate + always-on replicas), not per-order. (Lecture 1 §1.4 cost.)
11. **B** — A non-reproducible system is a pet; reproducibility is a deliverable. (Lecture 1 §1.8; mini-project.)
12. **B** — Unmeasured numbers make every number suspect; run the drill. (Lecture 1 §1.8.)
13. **B** — The README's known-limitations section, a credibility feature. (Lecture 1 §1.9.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready to defend. Then take the [homework](./homework.md) — which is the capstone itself.
