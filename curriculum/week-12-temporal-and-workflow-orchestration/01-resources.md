# Week 12 — Resources

Every resource here is **free** and pinned to a current version (Temporal 1.2x / SDKs 2026) wherever the docs are versioned. The Temporal docs and SDK references are open. The Step Functions and Durable Functions docs are public. No paywalled books are linked.

When a link is versioned, the current URL is given. The deterministic-replay and saga concepts are stable across versions; only the SDK-reference URLs move.

## Required reading (work it into your week)

- **Temporal — "Temporal Platform" / core concepts** (workflows, activities, workers, task queues, the event history — read this Monday, twice):
  <https://docs.temporal.io/temporal>
  <https://docs.temporal.io/workflows>
  <https://docs.temporal.io/activities>
- **Temporal — Deterministic constraints** (the rules workflow code must obey, and why — the single most important page of the week):
  <https://docs.temporal.io/workflow-definition#deterministic-constraints>
- **Temporal — Workers and task queues** (how a worker hosts workflow/activity code and polls task queues):
  <https://docs.temporal.io/workers>
- **Temporal — Go SDK developer guide** (our primary SDK; the foundations and the workflow/activity APIs):
  <https://docs.temporal.io/develop/go>
- **"Saga pattern" — microservices.io** (the compensation pattern you'll orchestrate; reread from Week 11):
  <https://microservices.io/patterns/data/saga.html>

## The deeper writeups (skim, don't memorize)

- **Temporal — "Why Temporal? Durable execution explained"** (the conceptual pitch and the replay mechanism):
  <https://docs.temporal.io/evaluate/why-temporal>
- **Temporal — Versioning workflows** (the `GetVersion`/patching API and history compatibility — read before the versioning lecture):
  <https://docs.temporal.io/develop/go/versioning>
- **Temporal — Signals, Queries, and Updates** (async input, sync reads, and the newer Update API):
  <https://docs.temporal.io/develop/go/message-passing>
- **Cadence (Uber) — the ancestor** (Temporal forked from Cadence; the original durable-execution engine):
  <https://cadenceworkflow.io/docs/>

## API references (the ones you'll have open all week)

- **Temporal Go SDK** (`go.temporal.io/sdk`): `workflow`, `activity`, `client`, `worker` packages:
  <https://pkg.go.dev/go.temporal.io/sdk>
- **Temporal Python SDK** (`temporalio`): the `@workflow.defn`, `@activity.defn`, `Client`, `Worker` APIs:
  <https://python.temporal.io/>
- **`temporal` CLI** (start-dev server, workflow start/describe/show, task-queue inspection):
  <https://docs.temporal.io/cli>

## Operating docs (the practical ones)

- **Temporal — Run a dev server** (`temporal server start-dev`, the bundled Web UI):
  <https://docs.temporal.io/cli/server#start-dev>
- **Temporal — Self-hosting and the service split** (frontend/history/matching/worker, persistence):
  <https://docs.temporal.io/self-hosted-guide>
- **Temporal — Web UI** (event history, stack traces, workflow search):
  <https://docs.temporal.io/web-ui>

## The alternatives (for the comparison)

- **AWS Step Functions — developer guide** (Amazon States Language, the state-machine model):
  <https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html>
- **Azure Durable Functions — overview** (the orchestrator-functions model, replay-based like Temporal):
  <https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview>
- **Temporal vs the alternatives — community comparisons** (read with a critical eye; verify against the docs):
  <https://docs.temporal.io/evaluate/comparison>

## Temporal in real stacks (read the source of code that gets it right)

- **Temporal samples — Go** (the saga, signals, child-workflow, and money-transfer samples — runnable, canonical):
  <https://github.com/temporalio/samples-go>
- **Temporal samples — Python**:
  <https://github.com/temporalio/samples-python>
- **The money-transfer demo** (the canonical "durable execution survives a crash" example):
  <https://learn.temporal.io/getting_started/go/first_program_in_go/>

## Talks and deep dives worth your time (free, no signup)

- **"Designing a Workflow Engine from First Principles" — Temporal/Maxim Fateev** (the founder on why durable execution works the way it does):
  <https://www.youtube.com/@Temporalio>
- **Replay (the Temporal conference) talks** — sagas, versioning, scale stories, all posted free:
  <https://replay.temporal.io/>
- **"Event sourcing vs durable execution"** — search the conference archives; the conceptual bridge from Week 11's logs to this week's histories:
  <https://www.youtube.com/results?search_query=temporal+durable+execution+talk>

## Books (optional, not required, not paywalled-linked)

- **Sam Newman, *Building Microservices* (2nd ed.)** — the saga and orchestration-vs-choreography chapters frame this week's central decision.
- **Martin Kleppmann, *Designing Data-Intensive Applications*** — Chapter 11 (stream processing) and the "exactly-once" material connect Week 10–11's logs to this week's event histories; an event history *is* a log.

## Tools you'll use this week

- **`temporal server start-dev`** — a single-binary local Temporal with a Web UI on `localhost:8233`. Your dev environment.
- **`temporal` CLI** — `temporal workflow start/describe/show/list`, `temporal task-queue describe`. Inspect running workflows and their histories.
- **The Temporal Web UI** — your primary diagnostic. The event-history view is the `ros2 topic info -v` / lag-table of this week: it shows you exactly what the workflow did and where it is.
- **The Go and Python Temporal SDKs** — `go.temporal.io/sdk` and `temporalio`.
- **A `worker-crash-drill.sh`** — the script that kills the worker mid-workflow and proves zero state loss; you write it in the mini-project.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Workflow** | Deterministic orchestration code; its execution is durable via replay. No direct I/O. |
| **Activity** | A unit of work that does I/O / side effects; runs at-least-once; must be idempotent. |
| **Worker** | A process *you* run that hosts workflow and activity code and polls task queues. |
| **Task queue** | The named queue the matching service uses to dispatch workflow/activity tasks to workers. |
| **Event history** | The append-only log of everything a workflow did; replayed to reconstruct state. |
| **Deterministic replay** | Re-running workflow code against its history to rebuild in-memory state after a failure. |
| **Determinism rule** | Workflow code must produce the same decisions on replay — no `time.Now()`, `rand`, real I/O, etc. |
| **Activity retry policy** | Initial interval, backoff, max attempts, non-retryable error types for an activity. |
| **Timeout (activity)** | schedule-to-start, start-to-close, schedule-to-close, heartbeat — the four activity timeouts. |
| **Heartbeat** | An activity periodically reporting liveness for long-running work, enabling fast failure detection. |
| **Saga** | A sequence of steps with compensations that undo completed steps on a later failure. |
| **Compensation** | The "undo" action for a completed saga step (release inventory, refund a charge). |
| **Signal** | Asynchronous input delivered into a running workflow (e.g., "cancel"). |
| **Query** | A synchronous, side-effect-free read of a running workflow's state. |
| **Child workflow** | A workflow started by another workflow; composes durable execution. |
| **`ContinueAsNew`** | Restart a workflow with fresh history to bound an otherwise-unbounded history. |
| **Versioning / patching** | `GetVersion` / patch APIs to change workflow code without breaking in-flight replays. |
| **Determinism / non-determinism error** | A replay mismatch caused by workflow code behaving differently than its recorded history. |

---

*If a link 404s, please open an issue so we can replace it.*
