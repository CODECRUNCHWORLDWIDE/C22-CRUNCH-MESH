# Week 22 — Chaos Engineering and the Gameday

Welcome to the week you stop trusting your system and start *interrogating* it. For twenty-one weeks you built a polyglot marketplace backbone — a CRDT cart, a leased inventory writer, a Temporal payment workflow, a Kafka spine, mTLS on every hop, two regions. Every one of those pieces has a resilience story you *wrote*: "the outbox guarantees exactly-once," "the region fails over in under sixty seconds," "the consumer is idempotent." This week you find out whether those stories are *true*. The instrument is **chaos engineering**, and the ritual is the **gameday**.

The thing to internalize before you read another line: **chaos engineering is not "break things in production for fun." It is the disciplined, hypothesis-driven practice of injecting controlled failure to find the gap between the resilience you *designed* and the resilience you *have* — before a real incident finds it for you.** Netflix's four principles are the spine: build a hypothesis around steady-state behavior, vary real-world events, run experiments in production (or as close as you can get), and minimize the blast radius. A chaos experiment that doesn't start with "I believe the system will keep doing X while I do Y, and here's the metric that proves it" is not an experiment — it's vandalism with extra steps.

You will install **Chaos Mesh** (and meet **LitmusChaos** as the CNCF alternative) on both Kind regions, author six experiments that map directly to your capstone's failure modes — pod kill, network partition, packet loss, CPU stress, disk fill, Kafka broker loss — and then run a **90-minute gameday** with a real runbook: a hypothesis per experiment, a steady-state metric, an abort condition, a scribe, and a blameless postmortem for every non-trivial finding. By Friday you will have done the two things that separate an engineer who *operated* a distributed system from one who only *built* one: you will have deliberately broken your own system under a hypothesis and a stopwatch, and you will have written a postmortem good enough to publish.

This is the dress rehearsal for the capstone's two mandatory chaos drills (Week 24, Drills A and B). Run it like the real thing, because in two weeks it *is*.

## Learning objectives

By the end of this week, you will be able to:

- **State** Netflix's four principles of chaos engineering and turn each into an operational rule: a steady-state hypothesis, real-world event variation, run-in-production bias, and blast-radius minimization (the "minimum viable experiment").
- **Install and operate** Chaos Mesh on a Kind cluster — the controller manager, the chaos daemon (the per-node agent that does the injecting), and the dashboard — and explain how it injects faults at the kernel/network layer without touching your application code.
- **Author** the six canonical experiments as `*Chaos` CRDs: `PodChaos` (kill), `NetworkChaos` (partition, loss, delay), `StressChaos` (CPU/memory), `IOChaos`/disk-fill, and a Kafka broker-loss drill — each scoped with a `selector` and a `duration` so the blast radius is bounded.
- **Write a gameday runbook**: a hypothesis, a steady-state SLI, an abort/rollback condition, a named scribe and commander, and a timeline — and run a 90-minute gameday against it without losing the room.
- **Verify exactly-once survives chaos**: kill a Kafka broker mid-traffic and prove, with consumer-group offsets and an idempotency-key audit, that the outbox + idempotent consumer did *not* double-process.
- **Distinguish** a controlled chaos experiment (hypothesis, blast radius, abort condition, in a non-prod-first ladder) from reckless production breakage, and explain the "minimize blast radius" discipline that makes the former safe.
- **Write a blameless postmortem** that survives publication: timeline, impact, the gap between expected and actual, contributing factors (not a single root cause), and action items with owners — and articulate the "five whys" critique (why a single root cause is usually a fiction).

## Prerequisites

This week assumes you have completed **C22 weeks 1–21**, or have equivalent fluency. Specifically:

- Two **Kind** clusters representing two regions, with your capstone services (`cart`, `inventory`, `payment`, `order`) deployable and healthy, from Weeks 19–21. `kubectl get nodes` is Ready on both.
- The **Kafka spine** from Weeks 10–11 running (Strimzi on Kind is fine), with at least one outbox-driven, idempotent consumer you can point at.
- **Observability from Week 17**: Prometheus, Grafana, and a RED dashboard, because chaos without observability is just downtime. You cannot run a gameday without a steady-state metric to watch.
- **SLI/SLO literacy from Week 18**: you can name an SLI, state an SLO, and read an error budget. The gameday's abort condition *is* an SLO breach.
- `kubectl` fluency: apply a CRD, label a pod, read `kubectl describe` and pod events. Chaos Mesh experiments are CRDs you apply and delete.
- A load generator (`k6` or `fortio`) to hold the system at steady state while you inject faults — a fault with no load is a fault nobody feels.

You do **not** need prior chaos-engineering experience. We start at the principles and the install and build up to a full gameday with a publishable postmortem.

## Topics covered

- **Chaos engineering principles**: Netflix's four principles (steady-state hypothesis, vary real-world events, run in production, minimize blast radius); the "minimum viable experiment"; the non-prod → staging → prod ladder; why the hypothesis comes *first* and the metric comes *with* it.
- **The tooling landscape**: **Chaos Mesh** (CNCF, CRD-driven, the one you'll run) and **LitmusChaos** (CNCF, experiment-hub + workflow model) in depth; **Gremlin** (commercial SaaS) briefly, and the honest "when you'd pay for it" line. How a chaos agent injects at the kernel/network layer (`tc`, `iptables`, cgroups, a failpoint) without app changes.
- **The six experiments**: `PodChaos` (pod-kill, container-kill); `NetworkChaos` (partition, packet loss, delay, bandwidth); `StressChaos` (CPU and memory pressure); `IOChaos` and disk-fill (latency and ENOSPC on a volume); a **Kafka broker-loss** drill (delete a broker pod, watch ISR shrink, prove no double-process); the DNS/clock-skew experiments as stretch.
- **The gameday**: the runbook (hypothesis, steady-state SLI, abort condition, roles — commander, scribe, observer); the 90-minute structure; the "game master" who knows the injected fault and the "responders" who don't; how to keep the experiment safe (blast radius, abort, a clean rollback).
- **Blameless postmortems**: the structure (timeline, impact, detection, the expected-vs-actual gap, contributing factors, action items with owners); *blameless* as a property (you analyze systems and decisions-with-the-information-available, not people); the **"five whys" debate** — why a single linear root cause is usually a comforting fiction and contributing-factors analysis is more honest.
- **Verifying invariants under chaos**: using the steady-state SLI as the experiment's ground truth; proving exactly-once survives a broker loss via consumer-group offset inspection and an idempotency-key audit; the difference between "it recovered" and "it recovered *correctly*."

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Chaos principles; the hypothesis; tooling landscape        |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Install Chaos Mesh; PodChaos + NetworkChaos; steady state  |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | StressChaos, IOChaos; the broker-loss + exactly-once drill |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | The gameday runbook; roles; the postmortem template        |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Run the 90-minute gameday; write the postmortems           |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work (the gameday harness + writeups)     |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, postmortem polish                            |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                            | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Chaos Mesh / Litmus docs, the principles, the postmortem corpus worth reading |
| [lecture-notes/01-chaos-engineering-principles-and-the-experiment.md](./02-lecture-notes/01-chaos-engineering-principles-and-the-experiment.md) | The four principles, the hypothesis-first experiment, Chaos Mesh architecture, the six fault types |
| [lecture-notes/02-the-gameday-and-the-blameless-postmortem.md](./02-lecture-notes/02-the-gameday-and-the-blameless-postmortem.md) | The gameday runbook and roles, the broker-loss/exactly-once drill, the blameless postmortem, the five-whys debate |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-install-and-first-experiment.md](./03-exercises/exercise-01-install-and-first-experiment.md) | Install Chaos Mesh, run a hypothesis-driven `PodChaos`, watch steady state hold (or not) |
| [exercises/exercise-02-six-experiments.yaml](./03-exercises/exercise-02-six-experiments.yaml) | The six canonical experiments as applyable CRDs, each scoped and bounded |
| [exercises/exercise-03-broker-loss-eos-probe.py](./03-exercises/exercise-03-broker-loss-eos-probe.py) | Kill a Kafka broker mid-traffic; prove the exactly-once consumer did not double-process |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-gameday-that-found-the-bug.md](./04-challenges/challenge-01-the-gameday-that-found-the-bug.md) | Run a gameday that surfaces a real latent bug, diagnose it live, write the postmortem |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the publishable blameless postmortem |
| [mini-project/README.md](./07-mini-project/00-overview.md) | `marketplace-gameday`: the full gameday harness — six experiments, a runbook, a live drill, and postmortems |

## The "the system told you, not you assumed" promise

C22 uses a recurring marker for every exercise that ends in the system *proving* something rather than you asserting it. This week's canonical one is the **steady-state metric holding (or breaking) under a named fault** — the experiment's verdict comes from the dashboard, not your hope:

```
# Hypothesis: "killing one cart pod does not raise the cart-read error rate above the SLO."
# The verdict is this query, before vs during the fault — not your opinion:

$ kubectl apply -f pod-kill.yaml          # inject: kill one cart pod
$ # watch the steady-state SLI for the experiment's duration:
sum(rate(cart_read_errors_total[1m])) / sum(rate(cart_read_total[1m]))
# 0.001  -> 0.002 -> 0.001     STEADY: the SLI never crossed the 1% SLO. Hypothesis HELD.
# OR
# 0.001  -> 0.34  -> 0.34      BROKEN: a single pod kill blew the error budget. Hypothesis REFUTED.
#                              That refutation is a FINDING. Write the postmortem.
```

A refuted hypothesis is not a failure of the week — it is the *entire point*. The gameday that finds nothing either has no faults worth injecting or no metric sharp enough to see them. The gameday that finds the bug two weeks before the capstone demo is the one that earned its 90 minutes.

## Stretch goals

If you finish the regular work early and want to push further:

- Author a **`Schedule`** resource so an experiment runs on a cron — the "continuous chaos" posture where a small, safe fault fires every hour and you find regressions automatically.
- Build a **`Workflow`** (Chaos Mesh) or a **Litmus chaos workflow** that *chains* faults: partition, then heal, then kill a broker, then assert recovery — a scripted multi-stage gameday you can replay.
- Reproduce the same six experiments on **LitmusChaos** and write a one-paragraph honest comparison (the experiment-hub model vs Chaos Mesh's CRD-per-fault model; when each fits).
- Add an **`AbortCondition`/automatic halt**: wire a Prometheus alert so the experiment is *automatically* stopped when the steady-state SLI breaches — chaos with a real dead-man's switch, the safety property production chaos demands.

## Up next

Week 23 takes the resilience you *demonstrated* this week and asks the complementary question: **how do you catch the regression before the gameday?** Contract testing with Pact closes the polyglot integration gap; property-based testing hammers your CRDT-merge and idempotency invariants with thousands of generated cases; and capacity planning (Little's Law, the Universal Scalability Law, queueing) turns "it held under load" into a model you can defend on paper. Chaos finds the failure empirically; contract and property tests prevent whole classes of it, and the capacity model tells you *where the saturation point is* before chaos pushes you past it. Push your `marketplace-gameday` mini-project and its postmortems before you start — Week 24's capstone reuses both drills.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
