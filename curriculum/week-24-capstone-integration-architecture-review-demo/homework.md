# Week 24 Homework — The Capstone Deliverables

This week the homework *is* the capstone. The six problems below are the six required deliverables from the syllabus capstone spec, each scoped as a homework problem with acceptance criteria and a rubric. The full set is the bulk of your week — budget the **~5 hours** of "homework" time for the writing-and-polish of the deliverables, on top of the mini-project's integration time and the exercises' drills.

Work in your capstone repository (`marketplace-backbone`). Every problem produces a committed artifact you point a reviewer at on Friday.

The headline deliverables are **Problem 3 (the two chaos-drill postmortems)** and **Problem 1 (the architecture document)** — the two that most distinguish an engineer who has *operated* a system from one who has only *built* one. Treat them as the artifacts a staff engineer reads before deciding whether to trust your design.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time** (for the writeup/polish, beyond the integration and drill time).

Have the **two-region system running** (the mini-project) and the **two drills executed** (Exercises 2 and 3) before you write the deliverables that report them.

---

## Problem 1 — The 2,000-word C4 architecture document

**Problem statement.** Write `docs/ARCHITECTURE.md`: a 2,000-word architecture document with C4-style diagrams (system context, container, and component for two key services) that defends the design and its tradeoffs. The prose must answer *why*: why a CRDT for the cart and a lease for inventory (the per-field CAP choice), why Temporal orchestration over choreography, why a mesh over a library for mTLS, and the cost each carries.

**Acceptance criteria.**

- Three diagram levels: system context, container (every arrow labeled with protocol + rough throughput), and component for two services with interesting internals.
- ~2,000 words defending the per-field consistency model and the major architectural tradeoffs.
- At least three tradeoffs defended on the *requirement*, not on taste.
- Committed.

**Hint.** Use Mermaid C4 (`C4Context`/`C4Container`) so the diagrams diff in git. The strongest documents have a "consistency model" table: one row per data type, its consistency level, and the one-sentence reason. That table answers the review's hardest question before it's asked.

**Estimated time.** 1 hour 30 minutes (writeup; the system already exists).

---

## Problem 2 — The 12-minute demo

**Problem statement.** Record the 12-minute demo covering the four required segments: architecture walkthrough, a live weighted-canary deploy with automatic rollback, a Grafana tour ending in a trace-to-log jump, and the cart-CRDT convergence across a simulated partition. Write `demo/demo-script.md` with the timed segments and link the recording in the README.

**Acceptance criteria.**

- All four segments present, edited to roughly 12 minutes.
- The canary segment shows an *induced* SLO breach and the automatic rollback to weight 0.
- The Grafana segment ends in a one-click jump from a span to its logs.
- The CRDT segment shows divergent writes during a partition and convergence on heal.
- The recording is linked; `demo/demo-script.md` is committed.

**Hint.** Rehearse the live parts three times and have a fallback recording of each. Narrate the mechanism, not the clicks. The canary rollback is the segment most likely to need a fallback — induce the breach with a deliberately-broken v2 that returns 5xx so the SLO burn-rate alert fires reliably.

**Estimated time.** 1 hour (recording + edit; rehearsal is in the mini-project time).

---

## Problem 3 — The two chaos-drill postmortems (headline)

**Problem statement.** Write `postmortems/POSTMORTEM-drill-A.md` (region failover) and `postmortems/POSTMORTEM-drill-B.md` (Kafka broker loss) from the *executed* drills (Exercises 2 and 3). Each is a blameless, SRE-format postmortem with a stated hypothesis, a timestamped timeline, the measured result, the root cause, and owned action items.

**Acceptance criteria.**

- Drill A: the measured RTO, zero orders lost, zero double-charges, cart converges on heal. The three failure domains walked (CRDT cart, leased inventory, Temporal payment).
- Drill B: the empty `HAVING COUNT(*) > 1` query result pasted as the integrity proof; the DLQ stayed empty; the explanation of *why* exactly-once held (idempotency key + outbox + DB unique constraint).
- Both are blameless (fix the system, not a person) with timestamped timelines and owned action items.
- Committed.

**Hint.** The single most impressive line in Drill B is the empty result set — paste the literal query and the "0 rows" result. For Drill A, the strongest paragraph is the per-domain walk: name how each of the three failure domains behaved and tie it to the consistency choice you made for that data type. These two postmortems are the difference between "I built it" and "I operated it."

**Estimated time.** 1 hour (writeups; the drills are run in the exercises).

---

## Problem 4 — The 6-page runbook

**Problem statement.** Write `RUNBOOK.md` covering five named failure modes — region loss, broker loss, Postgres primary failure, Temporal worker outage, certificate expiry — each with the symptom (what pages you), the first diagnostic step (a dashboard or command, *not* "grep the logs"), the mitigation, and the recovery.

**Acceptance criteria.**

- All five failure modes, each with a one-look first diagnostic step.
- The region-loss and broker-loss entries cross-reference the two drills' findings.
- The certificate-expiry entry references the mesh CA / SPIRE rotation (Weeks 8, 21).
- Roughly 6 pages; committed.

**Hint.** A reviewer reads the *first line* of each entry. If it's "open the order SLO dashboard, which tells me which signal is degraded," that's an operable system; if it's "look at the logs," that's too vague and the reviewer says so. Make every first step a single dashboard or command that answers "what's wrong" in one look.

**Estimated time.** 45 minutes.

---

## Problem 5 — The green Pact broker and the consistency-model defense

**Problem statement.** Confirm the in-cluster Pact broker (from Week 23) is green for the named boundaries and `can-i-deploy` passes; capture the URL in the README. Then write `docs/consistency-model.md`: a one-page table of every data type, its consistency level (CRDT eventual / lease strong / Temporal exactly-once), and the requirement-based reason — the artifact you defend when a reviewer asks "why eventual here and strong there."

**Acceptance criteria.**

- The broker URL is in the README; `can-i-deploy` passes for the three boundaries.
- `docs/consistency-model.md` has one row per data type with its consistency level and the one-sentence reason.
- You can defend each choice on the requirement (e.g., "cart adds must not be lost across a partition → CRDT; stock must not oversell → lease; charges must not duplicate → Temporal exactly-once").
- Committed.

**Hint.** This table is the spine of the architecture review. Reviewers almost always ask the consistency question, and a candidate who has the table ready — and can defend each row on its requirement — reads as someone who designed the system on purpose. Rehearse defending the three hardest rows out loud.

**Estimated time.** 30 minutes.

---

## Problem 6 — The defense retrospective

**Problem statement.** After the live defense (the challenge), write `challenge-01-defense-notes.md`: the questions you were asked, the two you answered well, the one you fumbled, and what you'd say differently. Then turn the review's risk list into the README's "Known limitations and next steps" section — each item with its priority and the cost to fix.

**Acceptance criteria.**

- `challenge-01-defense-notes.md` with the questions, your two strong answers, the fumble, and the better answer.
- The README's "Known limitations and next steps" section, populated from the risk list, each item with a priority and a fix-cost.
- Committed.

**Hint.** The fumble is the valuable part. An engineer who can name their own weak answer and articulate the better one has the metacognition that makes the *next* defense (or interview) go better. And the limitations section is a *feature* — hiring managers read it first, because it's where they learn whether you can think honestly about your own system.

**Estimated time.** 15 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Architecture document (headline) | 1 h 30 min |
| 2 — The 12-minute demo | 1 h 0 min |
| 3 — Two chaos-drill postmortems (headline) | 1 h 0 min |
| 4 — The 6-page runbook | 45 min |
| 5 — Broker + consistency-model defense | 30 min |
| 6 — Defense retrospective | 15 min |
| **Total** | **~5 h 0 min** |

This is the last homework of C22. When you've finished all six, you have all six syllabus capstone deliverables. Push the repo, deliver the defense (the [challenge](./challenges/challenge-01-deliver-the-capstone-defense-live.md)), and take the [quiz](./quiz.md). Then you're done.

---

## Grading rubric (mapped to the syllabus capstone weighting)

| Area | Weight | What we look for |
|---|---:|---|
| **Functional correctness (P2, P5)** | 25% | The system runs two-region active-active; one order traces end to end; the broker is green. |
| **Architectural defensibility (P1, P5)** | 25% | The C4 document and consistency-model table defend the per-field choices; the live defense survives the question bank. |
| **Observability quality (P2)** | 15% | One cross-service trace per order; the trace-to-log jump in the demo; burn-rate alerts that fire in the drill. |
| **Chaos-drill postmortems (P3)** | 15% | Drill A RTO + zero-loss + convergence; Drill B's empty double-charge query — both mandatory, blameless, measured. |
| **Runbook (P4)** | 10% | Five failure modes, each with a one-look first diagnostic step. |
| **Demo and writeup (P2, P6)** | 10% | The 12-minute demo's four segments; the retrospective and the known-limitations section. |

**Passing requires ≥60% on each deliverable and ≥70% overall**, with the two chaos drills mandatory. **90+** is portfolio-grade — a system you defend in a staff interview and link from your portfolio. **70–89** passes but likely claims an unmeasured number, runs a cold-standby region instead of active-active, or doesn't defend the consistency model per data type. **Below 70** usually means a drill wasn't executed or the system doesn't trace end to end — and those are the two things that, fixed, turn a description into a defense. Welcome to the end of C22. Go own a platform.
