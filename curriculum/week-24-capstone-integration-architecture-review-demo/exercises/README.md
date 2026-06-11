# Week 24 — Exercises

Three drills that *are* the capstone proof. Unlike earlier weeks, these don't teach a new mechanic — they exercise the running system and produce the artifacts you defend on Friday. Do them in order: exercise 1 (trace one order) is the demo's heart and confirms the system is wired end to end; exercise 2 (Drill A) and exercise 3 (Drill B) are the two **mandatory** chaos drills, each producing a postmortem the syllabus requires.

## Index

1. **[Exercise 1 — Trace one order end to end](exercise-01-trace-one-order-end-to-end.md)** — place a single order with a known idempotency key and follow it through every hop (BFF → order → cart → inventory → payment → Kafka → search), ending in a trace-to-log jump. This is the demo's architecture-walk segment and the proof the backbone is wired. (~60 min, guided)
2. **[Exercise 2 — Region failover drill (Drill A)](exercise-02-region-failover-drill.py)** — drive the mandatory region-failover drill: kill the primary region under 1k RPS, measure the RTO, prove zero orders lost and zero double-charges, confirm the cart converges on heal, and emit the postmortem skeleton. (~90 min, runnable)
3. **[Exercise 3 — Broker loss, no double-process (Drill B)](exercise-03-broker-loss-no-double-process.py)** — drive the mandatory Kafka-broker-loss drill: kill a broker mid-traffic, let the consumers rebalance and re-deliver, and assert with a SQL count that every idempotency key was charged exactly once. The empty `HAVING COUNT(*) > 1` result set is the proof. (~90 min, runnable)

## How to work the exercises

- Have the **full backbone running** in two Kind clusters (the two-region active-active topology from Weeks 19/20): the services, the Kafka spine, the Temporal cluster, Postgres + Debezium, the Istio mesh, and the OpenTelemetry pipeline (Tempo/Prometheus/Loki/Grafana). If part of the system isn't ready, each exercise names what it minimally needs.
- Have **`k6`** (the load generator), **`chaos-mesh`** (the fault injector from Week 22), **`otel-cli`** (to pull traces), **`grpcurl`**, and the **`pact-broker`** CLI installed.
- **These exercises ARE deliverables.** Exercise 1 becomes the demo's first segment; Exercise 2 and 3 become the two mandatory postmortems. Treat the output as portfolio material, not scratch work.
- **A drill without a stated hypothesis is an accident.** Before you inject each fault, write down what you expect to happen. The postmortem is the gap between that and what did happen.
- Each runnable exercise ends with an **expected output** block and an **acceptance criteria** list mapped to the capstone rubric. If your output doesn't match — especially a non-empty double-charge query — you're not done.

## Running the exercises

The `.py` drills run directly and drive the live system:

```bash
pip install requests psycopg2-binary kafka-python
python3 exercises/exercise-02-region-failover-drill.py --duration 300 --rps 1000
python3 exercises/exercise-03-broker-loss-no-double-process.py --duration 180
```

The trace exercise is guided markdown — you place an order and walk the trace, with every command given.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-24` to compare. But the real artifact is *your* running system, traced, drilled, and defended.
