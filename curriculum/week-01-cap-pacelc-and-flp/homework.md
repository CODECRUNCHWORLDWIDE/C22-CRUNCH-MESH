# Week 1 Homework

Six problems that drive the theory into your fingers. The full set should take about **5 hours**. Work in your Week 1 Git repository (the same workspace as the exercises and the `regime-register` mini-project) so every problem produces at least one commit you can point to at the midterm architecture review in Week 12.

The headline deliverable is **Problem 4 — the consistency-audit memo**, the miniature of the midterm essay. Treat it as the artifact a reviewer reads, not a journal entry.

Each problem includes a short **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — Reproduce the Gilbert–Lynch proof on paper

**Problem statement.** Without looking at the lecture, draw and write the two-node CAP proof from scratch in `notes/week-01/cap-proof.md`: two nodes G₁ and G₂ each holding `v0`, a partition that drops all messages between them, a write of `v1` to G₁, a read from G₂, and the contradiction. State, in one sentence each, exactly where availability forces G₁ to ack the write and where availability forces G₂ to answer the read, and why the read returning `v0` violates linearizability.

**Acceptance criteria.**
- `notes/week-01/cap-proof.md` contains the diagram (ASCII or an embedded image) and the four-step argument.
- The write step explicitly invokes *availability* as the reason G₁ cannot wait for G₂.
- The contradiction names *linearizability* as the violated property.
- Committed.

**Hint.** The whole proof is four sentences (Lecture 1 §2.4). If yours is a page long, you're padding; if it skips why G₁ can't wait, you've missed the load-bearing step.

**Estimated time.** 30 minutes.

---

## Problem 2 — Drive the partitioned register through both regimes

**Problem statement.** Run Exercise 2's `exercise-02-partitioned-register.go` (or your mini-project register). Capture the full CP and AP traces into `notes/week-01/register-runs.md`. Then **change the AP reconcile** from last-writer-wins to "report the conflict instead of discarding a write" (print both candidate values on heal rather than picking one) and capture the new output. Write two sentences on why LWW is a footgun and what reporting the conflict buys you.

**Acceptance criteria.**
- `notes/week-01/register-runs.md` contains the unmodified CP and AP traces.
- A modified run shows the heal step *reporting* the divergent values (`v2` vs `v3`) instead of silently choosing one.
- Two sentences explain the LWW data-loss problem and how conflict-reporting surfaces it.
- Committed (with your modified `.go` file).

**Hint.** The footgun is *silent data loss*: LWW throws away a concurrent write with no signal. Reporting the conflict is the first step toward the CRDT thinking in Week 3 — you can't merge well what you didn't notice diverged.

**Estimated time.** 45 minutes.

---

## Problem 3 — Hand-check three histories for linearizability

**Problem statement.** Write three single-register histories (as `[invoke, return, op]` triples) by hand in `notes/week-01/histories.md`: one linearizable with concurrency, one non-linearizable due to a real-time violation, and one non-linearizable due to an impossible read. For each, give your verdict and a one-sentence justification **before** running it through Exercise 3's checker. Then run all three through the checker and confirm your hand-verdicts match.

**Acceptance criteria.**
- Three histories with your *predicted* verdict and justification.
- The checker's verdict for all three is recorded and matches your prediction (or you explain where your intuition was wrong and why).
- The real-time-violation history names the specific precedence edge that fails.
- Committed.

**Hint.** To force a real-time violation, make a write *complete* (return) strictly before a read is *invoked*, then have the read return the old value — the checker's `precedes()` edge makes that unsatisfiable (Exercise 3, H4).

**Estimated time.** 45 minutes.

---

## Problem 4 — The consistency-audit memo (headline deliverable)

**Problem statement.** This is the syllabus-style deliverable and the midterm in miniature. Pick one real data system (Cassandra, DynamoDB, etcd, MongoDB, CockroachDB, Kafka, or Redis Cluster). Write a one-page memo at `notes/week-01/consistency-audit.md` that:

1. **States the default consistency model** for a single object, with the configuration that produces it, citing the docs.
2. **Shows the configuration sweep** — at least three configs producing at least two different models.
3. **Assigns the PACELC corner** for one named configuration, justifying *both* branches.
4. **Inventories three guarantees** split into safety vs liveness.
5. **Names one overstatement** in the docs/marketing with the precise missing qualifier.

**Acceptance criteria.**
- `notes/week-01/consistency-audit.md` exists, fits roughly one page (400–700 words), and hits all five points.
- Every factual claim cites a specific documentation page/section.
- The PACELC label justifies both the partition branch and the else branch.
- The overstatement is *specific* (an opt-in mode, a default `fsync` setting, an unquantified staleness window), not "the docs are vague."
- Committed.

**Hint.** This overlaps the Challenge but is shorter and required. The strongest memos cite the exact config knob (Cassandra's per-statement consistency level; DynamoDB's `ConsistentRead`; Mongo's `readConcern`/`writeConcern`) — the "brand is not the model" lesson, with receipts.

**Estimated time.** 1 hour 15 minutes.

---

## Problem 5 — Map a Jepsen finding to the vocabulary

**Problem statement.** Read one Jepsen report (<https://jepsen.io/analyses>) for a system you use or want to. In `notes/week-01/jepsen-mapping.md`, pick **two** findings from the report and for each: (a) name the consistency model that was violated, (b) classify the violation as a safety or liveness failure, and (c) state whether it was a docs-vs-reality gap (the system did less than it *claimed*) or a genuine bug (less than it *intended*).

**Acceptance criteria.**
- Two findings, each with consistency-model name, safety/liveness class, and gap-vs-bug classification.
- A one-sentence link from each finding back to a lecture concept (e.g., "this is a read-your-writes violation — a session guarantee — under their default config").
- The report is cited by name and date.
- Committed.

**Hint.** Jepsen reports are dense; you don't need to understand the whole report, just two concrete violations. "Lost updates," "stale reads," "split-brain," and "G2 anomaly" all map cleanly onto this week's models — look them up if a term is new.

**Estimated time.** 50 minutes.

---

## Problem 6 — Classify your own production system

**Problem statement.** Pick a data system your team actually runs (or, if you can't name one, the storage layer of any open-source project you've used). In `notes/week-01/our-system.md`, write its honest consistency model, its PACELC corner *as configured* (not as branded), and one place where your team's *belief* about its consistency diverges from its *configuration*. If you genuinely don't know the config, say so and write down the exact question you'd ask to find out.

**Acceptance criteria.**
- `notes/week-01/our-system.md` names a real system and its configured consistency model.
- The PACELC corner reflects the *actual configuration*, with a one-line reason.
- One belief-vs-configuration gap is named (or an explicit "I don't know — here's the question I'd ask").
- Committed.

**Hint.** The highest-value finding is almost always a system your team *believes* is strongly consistent but has configured into an EL corner (an async replica, a `ONE` read level, a `w:1` write) for latency. That gap is exactly where the next incident comes from.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Reproduce the CAP proof | 30 min |
| 2 — Drive the register through both regimes | 45 min |
| 3 — Hand-check three histories | 45 min |
| 4 — Consistency-audit memo (headline) | 1 h 15 min |
| 5 — Map a Jepsen finding | 50 min |
| 6 — Classify your own system | 35 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `regime-register` [mini-project](./mini-project/README.md) is in the same workspace — Week 2 grafts Raft onto it. Then take the [quiz](./quiz.md) with your notes closed.
