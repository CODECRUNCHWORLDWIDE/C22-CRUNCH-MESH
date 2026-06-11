# Week 22 — Exercises

Three focused drills on a running Chaos Mesh install. Each takes 45–90 minutes. Do them in order — exercise 1 installs Chaos Mesh and runs your first hypothesis-driven experiment, exercise 2 gives you the full six-experiment CRD set the gameday runs, and exercise 3 is the broker-loss/exactly-once drill that becomes capstone Drill B. Run everything against your **capstone services** (`cart`, `inventory`, `order`, `payment`) and your **Kafka spine** on Kind. If a service isn't ready, each exercise names a stand-in.

## Index

1. **[Exercise 1 — Install Chaos Mesh and run your first experiment](exercise-01-install-and-first-experiment.md)** — install Chaos Mesh on Kind, write a hypothesis with a steady-state metric, inject a scoped `PodChaos`, and let the dashboard — not your hope — render the verdict. (~75 min, guided)
2. **[Exercise 2 — The six canonical experiments](exercise-02-six-experiments.yaml)** — a complete, applyable set of `*Chaos` CRDs (pod-kill, partition, packet loss, CPU stress, I/O latency, broker loss), each scoped with `selector`/`mode`/`duration`. The gameday's experiment library. (~60 min, runnable)
3. **[Exercise 3 — The broker-loss exactly-once probe](exercise-03-broker-loss-eos-probe.py)** — kill a Kafka broker mid-traffic and prove, with offsets and an idempotency-key audit, that the exactly-once consumer did NOT double-process. (~75 min, runnable)

## How to work the exercises

- Have **Chaos Mesh 2.6+** installed (Exercise 1 walks the Helm install) and a **Kind** cluster with your services + Kafka. `kubectl get pods -n chaos-mesh` shows the controller and daemon.
- **Have a steady-state metric open before every experiment.** Prometheus + Grafana from Week 17 is a hard prerequisite — chaos without observability is just downtime. If you can't see the SLI live, you're not running an experiment.
- **Hold the system at load.** Run `k6` (or `fortio`) at a steady RPS so a fault is something a user would feel. A fault on an idle system teaches you nothing.
- **Write the hypothesis and the abort condition first.** Before you `kubectl apply` any chaos CRD, write down the claim and the number that aborts the experiment. Decide the verdict criterion before you can see the result.
- Each runnable exercise ends with an **expected output** block and **acceptance criteria**. If your output doesn't match, you're not done.

## Running the exercises

The `.yaml` exercise is applied (and crucially, *deleted*) with `kubectl`:

```bash
kubectl apply -f exercise-02-six-experiments.yaml   # applies ONE experiment at a time (read the header)
# observe the steady-state metric, then ALWAYS clean up:
kubectl delete -f exercise-02-six-experiments.yaml
```

The `.py` exercise drives the broker-loss drill and runs the idempotency audit:

```bash
pip install kafka-python psycopg2-binary
python3 exercise-03-broker-loss-eos-probe.py --audit
```

The header of each file lists the exact prerequisites and the stand-in if your capstone services aren't ready.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-22` to compare.

> **The one rule that overrides all others:** every chaos CRD you `apply`, you `delete`. A chaos experiment left running in a namespace is a self-inflicted outage. The mini-project's audit script checks that no chaos resources are left behind.
