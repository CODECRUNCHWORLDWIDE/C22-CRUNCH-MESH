# Week 22 Homework

Six problems that revisit the week's topics and force the gameday discipline into your fingers. The full set should take about **5 hours**. Work in your Week 22 Git repository (the same workspace as the exercises and the `marketplace-gameday` mini-project) so every problem produces at least one commit you can point to at the capstone review in Week 24.

The headline deliverable is **Problem 4 — the publishable blameless postmortem**, the artifact a capstone reviewer reads and a hiring panel asks you to walk through. Treat it as a published incident review, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Chaos Mesh** installed on Kind and your **capstone services + Kafka** running (Exercise 1). Problems 1, 2, 3, 5, and 6 run against the live system.

---

## Problem 1 — The experiment design table

**Problem statement.** Before running anything, design all six experiments on paper. Build a markdown table in `notes/week-22/experiment-design.md` with one row per experiment and these columns:

| Experiment | Real-world event it models | Hypothesis (with reason) | Steady-state SLI (query) | Abort condition (number) | Rollback |
|---|---|---|---|---|---|

The **reason** in the hypothesis column is mandatory — "because the Service load-balances to survivors," not just "stays under 1%." If you can't name the reason, you don't understand the resilience claim you're testing.

**Acceptance criteria.**

- `notes/week-22/experiment-design.md` exists with one row per experiment (all six).
- Every hypothesis includes the *reason* you believe it.
- Every steady-state SLI is a concrete Prometheus query, not a vague metric name.
- Every abort condition is a concrete number with a duration ("error > 5% for 60 s").
- Committed.

**Hint.** Map each experiment to a *specific* failure mode in your architecture (broker dies, region partitions, primary fails) — principle 1.2, "vary real-world events." The SLI is almost always a RED metric from Week 17.

**Estimated time.** 45 minutes.

---

## Problem 2 — Run two experiments and record verdicts

**Problem statement.** Run experiments #1 (pod-kill) and #3 (the inventory degrade) against your live system at steady load. For each, capture the baseline, the metric during the fault, and the recovery — and record a verdict (HELD or REFUTED) from the metric.

**Acceptance criteria.**

- `notes/week-22/verdicts.md` shows, per experiment: the baseline SLI value, the value during the fault, the recovery value, and the verdict.
- You include a timeline (inject → peak → recover timestamps) for each.
- At least one verdict is a REFUTED (a finding) OR you argue why both held with a metric sharp enough to have caught a failure.
- You confirm `kubectl get podchaos,networkchaos -A` is empty afterward (cleanup).
- Committed.

**Hint.** Hold load with `k6` the whole time — a fault on an idle system is unfelt. The degrade experiment (#3) is the most likely to refute if your retry/timeout budget isn't tuned (Lecture 2 §3.3).

**Estimated time.** 50 minutes.

---

## Problem 3 — The exactly-once audit under broker loss

**Problem statement.** Run the broker-loss drill (Exercise 3). Snapshot before, drive a known order load, kill a broker mid-traffic, recover, snapshot after, and run the audit. Prove redelivery happened AND was absorbed.

**Acceptance criteria.**

- `notes/week-22/eos-audit.md` records the before/after snapshots, the ISR change during the fault, and the audit verdict.
- You demonstrate `delivered/produced > processed` (redelivery happened) AND zero orders charged more than once (it was absorbed).
- If the broker loss caused *no* redelivery, you escalate to a harder fault (kill the consumer mid-batch too) until you observe one, then prove absorption.
- You state in one sentence why "the dashboard recovered" is not the verdict.
- Committed.

**Hint.** The redelivery is the gap between produced and processed. If you can't make redelivery happen, kill the broker that's the *leader* of the partition the consumer is reading, mid-batch — that forces the rebalance + re-poll that re-delivers.

**Estimated time.** 50 minutes.

---

## Problem 4 — The publishable blameless postmortem (headline deliverable)

**Problem statement.** This is the syllabus skill ("writing a publishable postmortem"). Take your most interesting finding from the week — a refuted hypothesis, the broker-loss recovery, or a planted bug from the challenge — and write a blameless postmortem at `notes/week-22/postmortem.md` good enough to publish. It must hit the SRE structure:

1. **Title / date / authors / status.**
2. **Summary** — what happened, impact, resolution, in 2–3 sentences.
3. **Impact** — quantified and *extrapolated to production scale* ("6% of order requests breached the SLO; at 1k RPS that's ~3,600 slow requests, exhausting the error budget in under an hour").
4. **Timeline** — the scribe's record: inject → observe → act → recover, with timestamps.
5. **Detection** — how you found out (and whether that's a good detection story).
6. **Contributing factors (plural)** — all the conditions that had to align, reached via why-laddering-then-branching. NOT a single root cause.
7. **What went well / poorly / where we got lucky** — the "got lucky" section is mandatory.
8. **Action items** — each with an owner and a type (prevent/detect/mitigate).

**Acceptance criteria.**

- `notes/week-22/postmortem.md` exists and hits all eight sections.
- It is **blameless** — analyzes systems and decisions-with-information-available, never a person.
- Impact is quantified and extrapolated to production scale.
- The cause is stated as contributing factors (plural), not a single root cause.
- Every action item has an owner and a type.
- Committed.

**Hint.** The strongest postmortems quantify, extrapolate, and admit luck. Re-read Lecture 2 §3.3's worked example — it's the bar. The "where we got lucky" section is what separates a mature writeup from a defensive one: name the thing that *didn't* go wrong this time but easily could have.

**Estimated time.** 1 hour.

---

## Problem 5 — The five-whys-vs-contributing-factors rewrite

**Problem statement.** Take the finding from Problem 4 and write it up *twice*: once as a strict five-whys single root cause, and once as a contributing-factors set. Then write a paragraph on what the five-whys version *hid*.

**Acceptance criteria.**

- `notes/week-22/five-whys-critique.md` has both versions and the comparison paragraph.
- The five-whys version terminates in a single "root cause"; the contributing-factors version lists the plural conditions.
- The comparison names at least one real contributing factor the five-whys chain hid (or the blame it terminated in).
- You state the balanced position: why-laddering is a fine *prompt* to dig past symptoms, but its single-cause *output* is the trap.
- Committed.

**Hint.** Run the five-whys honestly — it really does produce a single chain — then notice that at one of the "why?" steps there was a *parallel* answer you didn't follow. That parallel answer is the hidden contributing factor.

**Estimated time.** 35 minutes.

---

## Problem 6 — Verify the blast radius and cleanup discipline

**Problem statement.** Audit your own gameday for safety. For each experiment file, confirm it is bounded (selector + mode + duration). Then deliberately weaken one (remove the `duration`), confirm your `verify_gameday.sh` catches it, and restore it. Finally confirm no chaos resources are left running anywhere.

**Acceptance criteria.**

- `notes/week-22/safety-audit.md` records the boundedness check per experiment.
- You demonstrate `verify_gameday.sh` exiting non-zero when an experiment is unbounded (no `duration`) and zero when restored.
- You confirm `kubectl get podchaos,networkchaos,stresschaos,iochaos -A` is empty.
- You state in one sentence why an unbounded fault (no `duration`, `mode: all`) is the difference between an experiment and an outage.
- Committed.

**Hint.** The `duration` is the time-box; without it, a fault runs until you remember to delete it — which, during a busy gameday, you won't. The audit script grepping for `duration:` in every experiment file is the cheap guard that prevents a self-inflicted outage.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Experiment design table | 45 min |
| 2 — Run two experiments + verdicts | 50 min |
| 3 — Exactly-once audit under broker loss | 50 min |
| 4 — Publishable blameless postmortem (headline) | 1 h 0 min |
| 5 — Five-whys vs contributing-factors rewrite | 35 min |
| 6 — Blast-radius + cleanup audit | 30 min |
| **Total** | **~4 h 50 min** |

When you've finished all six, push your repo and make sure the `marketplace-gameday` [mini-project](./mini-project/README.md) is in the same workspace — Week 24's capstone reuses both drills and their postmortems. Then take the [quiz](./quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Experiment design (P1)** | 15 | Six experiments mapped to real failure modes; reasoned hypotheses; concrete SLI queries and numeric abort conditions. |
| **Experiments + verdicts (P2)** | 15 | Baseline/during/recovery captured; verdicts from the metric; a real finding or a credible "all held." |
| **Exactly-once audit (P3)** | 20 | Redelivery observed AND absorbed; zero double-charges; the verdict is the audit, not the dashboard. |
| **Postmortem (P4)** | 25 | Blameless; quantified + extrapolated; contributing factors plural; owned+typed action items; a "where we got lucky" section. |
| **Five-whys critique (P5)** | 15 | Both versions written; a hidden contributing factor named; the balanced position stated. |
| **Safety audit (P6)** | 10 | Boundedness checked; `verify_gameday.sh` catches an unbounded experiment; no chaos left running. |

**90+** is portfolio-grade. **70–89** is solid but the postmortem likely lacks the extrapolation or writes a single root cause. **Below 70** usually means Problem 3 or 4 was treated as a formality — they're the two that prove you can verify an invariant under chaos and turn a finding into a published fix, which is the whole difference between reading about chaos engineering and doing it.
