# Week 12 — Temporal and Workflow Orchestration

Welcome to the week where the scattered, hard-won saga from Week 11 becomes a single readable program. By Friday you will be able to look at a long-running, multi-step business process — reserve inventory, charge payment, ship the order, compensate on any failure — and express it as **one workflow function** that reads top-to-bottom like ordinary code, yet survives process crashes, machine failures, and week-long sleeps with zero lost state. You will read a Temporal workflow the way you read a function, because that is exactly what it is — a function whose every step is durable.

We assume you finished Week 11 and built the `idempotent-checkout` pipeline: an outbox-emitting producer and an idempotent consumer, chaos-tested to zero double-charges. You also felt the discomfort the lecture promised — the saga's logic was *correct* but *scattered* across five consumers, its shape reconstructable only by reading all of them, its compensation logic smeared across services. This week removes that scatter. The same checkout-with-compensation becomes one Temporal workflow you can read in one screen, and the "what happens when the worker crashes mid-saga" question — which last week you answered with dedup tables and chaos tests — Temporal answers *for you*, by construction.

The one thing to internalize before you read another line: **a Temporal workflow is durable because it is deterministic and its every step is recorded in an event history that is replayed to reconstruct state after any failure.** The workflow code does not "run and hold state in memory" the way an ordinary program does. It runs, and every decision it makes — every activity it schedules, every timer it sets, every signal it receives — is written to a history. If the worker process dies mid-workflow, a new worker picks up the history, *replays* the workflow code against it to rebuild the exact in-memory state at the moment of the crash, and continues as if nothing happened. That replay is the magic, and it imposes one ironclad rule that this entire week orbits: **workflow code must be deterministic**, because non-deterministic code replays differently than it ran and corrupts the reconstruction. Master that rule and Temporal is a superpower; violate it and you get the subtlest bugs in distributed systems.

This week is where orchestration stops being a buzzword and becomes a tool you can defend.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** Temporal's architecture — the frontend, history, matching, and worker services, and the role of the persistence store — and how an event history makes a workflow durable.
- **Distinguish** a workflow from an activity: why workflow code must be deterministic and side-effect-free, why all I/O and non-determinism lives in activities, and exactly what "deterministic" forbids.
- **Author** a real Temporal workflow in Go: schedule activities, await their results, set timers, handle activity failures and retries, and structure a saga with compensation.
- **Reason** about deterministic replay: what the event history records, how a worker reconstructs state by replaying, and which code changes are safe versus history-incompatible (versioning).
- **Use** signals (asynchronous input into a running workflow), queries (synchronous read of workflow state), and child workflows, and explain when each is the right tool.
- **Design** a saga with compensation: reserve inventory, charge payment, ship — and on any step's failure, run the compensations for the steps that already succeeded, in reverse order, idempotently.
- **Compare** orchestration (a central workflow drives the steps) against choreography (services react to each other's events), and articulate precisely when a centralized workflow engine is the *simpler* answer.
- **Critique** the managed alternatives — AWS Step Functions, Azure Durable Functions — against Temporal, and place Cadence as Temporal's ancestor, choosing among them with evidence.

## Prerequisites

This week assumes you have completed **C22 weeks 1–11**, or have equivalent fluency. Specifically:

- The **`idempotent-checkout` pipeline** from Week 11: an outbox producer and an idempotent consumer. You'll re-implement its saga as a Temporal workflow, so having felt the choreographed version's scatter is the motivation. If it's broken, the standalone activities each exercise provides are your fallback.
- **Go 1.23+** installed; you can write a Go program with goroutines, channels, and `context.Context` from memory. The Temporal Go SDK is our primary SDK this week (with Python examples for contrast).
- A working **Docker** (for the Temporal dev server / `temporal server start-dev`) and `temporal` CLI.
- The **saga and compensation** intuition from Week 11 §2.7 — you can explain why a multi-step process needs to undo earlier steps when a later one fails.
- Comfort with **idempotency** from Week 11 — Temporal's at-least-once activity execution means activities must still be idempotent; Temporal reduces the burden but does not erase it.

You do **not** need prior Temporal experience. We start from the architecture and the workflow/activity split and build up to sagas, signals, and versioning. If you've used Step Functions or Durable Functions without understanding deterministic replay, this is the week that knowledge becomes load-bearing.

## Topics covered

- **Temporal architecture:** the **frontend** (the API gateway clients talk to), the **history** service (owns the event history and workflow state machine), the **matching** service (dispatches tasks to workers via task queues), the **worker** service (internal), the persistence store (Cassandra/Postgres/MySQL), and the **worker** *processes you write* that host workflow and activity code.
- **Workflow vs activity:** the workflow as deterministic orchestration code (no I/O, no clocks, no randomness, no direct network calls); the activity as the place all side effects, I/O, and non-determinism live. Why the split exists and what it buys.
- **Deterministic replay:** the event history (WorkflowExecutionStarted, ActivityTaskScheduled/Completed, TimerStarted/Fired, …), how a worker replays the workflow function against the history to reconstruct in-memory state, and the determinism rules (no `time.Now()`, no `rand`, no map iteration order dependence, no direct goroutines — use the SDK's deterministic equivalents).
- **Activities in depth:** at-least-once execution, retry policies (initial interval, backoff, max attempts, non-retryable errors), heartbeating for long activities, timeouts (schedule-to-start, start-to-close, schedule-to-close, heartbeat), and why activities must be idempotent.
- **Sagas and compensation:** the orchestrated saga — a workflow that runs steps and, on failure, executes compensations for completed steps in reverse order; why orchestration makes the saga's shape and compensation explicit and testable.
- **Signals, queries, child workflows:** signals (async input to a running workflow — e.g., "the customer cancelled"), queries (sync read of workflow state — e.g., "what's the order status"), child workflows (composing workflows), and the patterns each enables (the human-in-the-loop wait, the entity workflow).
- **Versioning and safe change:** why changing workflow code can break replay of in-flight executions, the `GetVersion`/patching API, and the discipline of evolving long-running workflows without corrupting history.
- **Orchestration vs choreography, and the alternatives:** the honest comparison of a central workflow engine against event choreography (Week 11); AWS Step Functions and Azure Durable Functions critiqued; Cadence as Temporal's ancestor; when each wins.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Temporal architecture; workflow vs activity; determinism    |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Activities, retries, timeouts; the first workflow           |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Sagas and compensation; deterministic replay deep-dive      |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Signals, queries, child workflows; the worker-crash demo    |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Versioning; orchestration vs choreography; the alternatives |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                      |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, postmortem polish                            |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                            | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The Temporal docs, the determinism deep-dives, the Step Functions/Durable Functions comparisons, and the talks |
| [lecture-notes/01-when-orchestration-wins.md](./lecture-notes/01-when-orchestration-wins.md) | Temporal architecture, workflow vs activity, deterministic replay, and activities in depth |
| [lecture-notes/02-sagas-signals-and-versioning.md](./lecture-notes/02-sagas-signals-and-versioning.md) | Sagas with compensation, signals/queries/child workflows, versioning, and orchestration vs choreography |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-temporal-dev-server.md](./exercises/exercise-01-temporal-dev-server.md) | Stand up the Temporal dev server, run the Web UI, and execute your first workflow + activity |
| [exercises/exercise-02-checkout-saga.go](./exercises/exercise-02-checkout-saga.go) | A Go checkout saga: reserve → charge → ship, with compensation on any failure, proven against an injected failure |
| [exercises/exercise-03-signals-and-worker-crash.py](./exercises/exercise-03-signals-and-worker-crash.py) | A Python workflow with a cancel signal and a query, demonstrating worker-crash recovery with zero state loss |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-diagnose-three-determinism-faults.md](./challenges/challenge-01-diagnose-three-determinism-faults.md) | Detect and fix three different non-determinism / versioning faults that corrupt workflow replay |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the one-page orchestration-vs-choreography design memo |
| [mini-project/README.md](./mini-project/README.md) | The `checkout-orchestrator`: the Week-11 saga re-built as a Temporal workflow, with a worker-crash drill |

## The "zero state loss" promise

C22 uses a recurring marker for every exercise that ends in a workflow surviving a crash with no lost progress:

```
$ ./worker-crash-drill.sh
starting checkout workflow for order-A...
  [activity] reserve_inventory      -> reserved
  [activity] charge_payment         -> charged
killing the worker process (kill -9) mid-workflow...
restarting the worker...
  [replay] reconstructed history: reserve_inventory=reserved, charge_payment=charged
  [activity] ship_order             -> shipped     <-- resumed exactly where it stopped
workflow completed: order-A confirmed.
  activities re-executed during replay: 0
  state lost:                          0      <-- the line that matters
PASS: durable execution survived a worker kill with zero state loss.
```

If `state lost` is anything but `0`, or completed activities re-execute on replay, you are not done. A workflow that loses progress on a worker crash has defeated the entire reason to use Temporal. The point of Week 12 is to make `state lost: 0` ordinary even under a deliberate `kill -9` — and to make any re-execution of an already-completed activity *loud* (it means a determinism bug) instead of silent.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **Temporal "deterministic constraints"** documentation until you can list, from memory, every operation forbidden in workflow code and its deterministic SDK replacement (`workflow.Now`, `workflow.Sleep`, `workflow.SideEffect`, `workflow.NewTimer`, the deterministic random).
- Use the **Temporal Web UI's "Stack Trace" and event-history view** to watch a running workflow's history accrete event by event as activities complete — then kill the worker and watch a new worker replay that history.
- Implement the **`ContinueAsNew`** pattern for a workflow that would otherwise accumulate an unbounded history (an entity workflow that runs for months), and explain why an unbounded history is a problem.
- Build the **same saga with `Step Functions` (ASL JSON) or `Durable Functions`** locally and write a paragraph contrasting the developer experience and the failure semantics with Temporal's code-first model.

## Up next

Week 12 closes Phase 2. You now have the full eventing-and-orchestration toolkit: Kafka/Redpanda for the log, NATS/Pulsar and the outbox for exactly-once effect, and Temporal for durable orchestration. **The midterm architecture-review essay is due at the end of this week** — a 2,500-word review of a public distributed system, where you'll apply everything from Phase 2. Phase 3 (weeks 13–18) turns to the data tier: Postgres at scale, CDC, the lakehouse, caching, observability, and reliability. Push your mini-project, write your midterm, and rest before week 13.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
