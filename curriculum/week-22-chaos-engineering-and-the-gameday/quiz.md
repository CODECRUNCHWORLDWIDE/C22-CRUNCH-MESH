# Week 22 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 23. Answer key is at the bottom — don't peek.

---

**Q1.** What are Netflix's four principles of chaos engineering?

- A) Move fast, break things, blame nobody, ship Friday.
- B) Build a hypothesis around steady-state behavior, vary real-world events, run experiments in production, and minimize the blast radius.
- C) Kill pods, partition networks, fill disks, and stress CPUs.
- D) Monitor, alert, page, and escalate.

---

**Q2.** Why must a chaos experiment's hypothesis and steady-state metric be chosen *before* the fault is injected?

- A) Because Chaos Mesh requires it in the CRD.
- B) Because deciding the verdict criterion after seeing the result lets you rationalize a bad outcome into "fine"; committing first makes a refutation unambiguous, and a refutation is the finding you ran the experiment to get.
- C) Because the metric changes after the fault.
- D) It doesn't matter; you can decide afterward.

---

**Q3.** What does "minimize the blast radius" mean operationally in Chaos Mesh?

- A) Run the experiment as fast as possible.
- B) Scope it with a `selector` (which targets), bound it with a `mode` (how many — `one`/`fixed`/`percent`), and time-box it with a `duration`, plus an abort condition — the smallest, shortest, most-bounded fault that still tests the hypothesis.
- C) Only run experiments in staging.
- D) Use the smallest cluster possible.

---

**Q4.** In Chaos Mesh's architecture, what does the `chaos-daemon` do, and how is it deployed?

- A) It's the control plane; one per cluster.
- B) It's the per-node DaemonSet (one per node) that does the actual injecting — entering target pods' namespaces and using `tc`/`netem`, `iptables`, cgroups, etc. — so faults are injected at the kernel layer without app changes.
- C) It schedules pods.
- D) It stores the experiment results.

---

**Q5.** "Run experiments in production" is one of the four principles. What is the responsible way to honor it?

- A) Start in production immediately; staging is a waste of time.
- B) Aim for production as the destination, but climb the non-prod → staging → prod ladder and never skip rungs; "run in prod" is where you end up after the small, bounded version holds, not where you start.
- C) Never run in production; it's too risky.
- D) Only run in production on weekends.

---

**Q6.** In the broker-loss drill, what is the actual verdict that the exactly-once invariant held?

- A) The Kafka dashboard returned to green and consumer lag drained.
- B) An audit of side effects: every business event applied exactly once (zero orders charged twice), AND redelivery was observed (more messages delivered/produced than processed) — proving the fault exercised at-least-once delivery and idempotency absorbed it.
- C) The broker came back up.
- D) The consumer group rebalanced successfully.

---

**Q7.** What is the difference between "it recovered" and "it recovered correctly," and why does it matter?

- A) There is no difference.
- B) "It recovered" means the system is available again (dashboard green); "it recovered correctly" means the invariants held (no double-charge, no lost data). A system can recover availability while having silently corrupted data — only an audit catches that, which is why you don't trust the green dashboard.
- C) "Correctly" means it recovered faster.
- D) "Recovered" is about CPU; "correctly" is about memory.

---

**Q8.** What does "blameless" mean in a blameless postmortem?

- A) The incident had no cause and nobody is responsible.
- B) You analyze the system and the decisions people made *with the information they had at the time*, never the people themselves — because blame destroys the honest timeline and near-miss information you need to fix the system.
- C) You don't write down what happened.
- D) Only managers are blamed, not engineers.

---

**Q9.** What is the central critique of "five whys" as a root-cause technique?

- A) It asks too few questions.
- B) Real incidents in complex systems rarely have a single linear root cause; they have multiple contributing factors each necessary but only jointly sufficient. Five-whys forces a tree of causes into one line, stops arbitrarily, often terminates in blame, and hides the systemic picture.
- C) It's too slow.
- D) It requires special software.

---

**Q10.** A chaos experiment runs but you have no live metric for the property you're testing. What is true?

- A) That's fine; you can check the logs afterward.
- B) You're not running an experiment — chaos without observability is just downtime. Every verdict is a metric; with no live SLI you can't tell "survived" from "limped," so the experiment manufactures false confidence. Build the metric or drop the experiment.
- C) The experiment is still valid if the pod came back.
- D) Chaos Mesh will judge it for you.

---

**Q11.** Why is a *refuted* hypothesis a good outcome of a gameday?

- A) It isn't; you want every hypothesis to hold.
- B) A refutation found a gap between designed and actual resilience in a controlled experiment, on a Tuesday, with a metric watching and a rollback ready — instead of at 3 a.m. in a real incident. The gameday that finds nothing either tested nothing interesting or had metrics too blunt to see the truth.
- C) It means the tooling is broken.
- D) It lets you loosen the SLO.

---

**Q12.** During a gameday, an experiment refutes its hypothesis and someone says "loosen the SLO so it passes." Why is that wrong?

- A) It's not wrong; passing the experiment is the goal.
- B) It makes the finding vanish by redefining "working" to include the broken behavior — the next incident is now *inside* your SLO and won't even page. Moving the goalposts to score institutionalizes the bug; the fix must make the *same* experiment pass by fixing the system.
- C) Loosening an SLO requires manager approval.
- D) SLOs can't be changed.

---

**Q13.** Which two of this week's experiments map directly onto the capstone's two mandatory chaos drills?

- A) CPU stress and I/O latency.
- B) The network partition / region kill (→ Drill A, region failover) and the Kafka broker loss with the exactly-once audit (→ Drill B, broker loss / no double-process).
- C) Pod kill and DNS chaos.
- D) None; the capstone drills are unrelated.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Steady-state hypothesis, vary real-world events, run in production, minimize blast radius. (Lecture 1 §1.)
2. **B** — Committing the verdict criterion first prevents rationalizing a refutation away; the refutation is the finding. (Lecture 1 §2.1.)
3. **B** — `selector` + `mode` + `duration` + abort condition = the minimum viable experiment. (Lecture 1 §1.4, §4.)
4. **B** — The per-node DaemonSet that injects at the kernel/namespace layer without app changes. (Lecture 1 §3.)
5. **B** — Aim for prod via the non-prod→staging→prod ladder; don't skip rungs. (Lecture 1 §1.3.)
6. **B** — The side-effect audit: exactly-once side effects AND observed redelivery. Not the dashboard. (Lecture 2 §2.3; Exercise 3.)
7. **B** — Availability (dashboard) vs invariants (audit); a system can recover availability while corrupting data. (Lecture 2 §2.3.)
8. **B** — Analyze systems + decisions-with-information-available, never people; blame destroys the honest timeline. (Lecture 2 §3.2.)
9. **B** — Single linear root cause is usually fiction; contributing-factors analysis is more honest. (Lecture 2 §4.)
10. **B** — Chaos without observability is just downtime; every verdict is a metric. (Lecture 1 §5.)
11. **B** — A refutation found the gap safely; the gameday that finds nothing tested nothing sharp. (Lecture 1 §2.1.)
12. **B** — Loosening the SLO institutionalizes the bug; fix the system so the same experiment passes. (Lecture 2; Challenge 1.)
13. **B** — Partition/region-kill → Drill A; broker-loss + EOS audit → Drill B. (Lecture 2 §5; mini-project.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
