# Week 12 — Exercises

Three focused drills on a running Temporal. Each takes 45–75 minutes. Do them in order — exercise 2 builds the saga the mini-project extends, and exercise 3 reuses the worker pattern from exercise 1. Run everything against a local Temporal dev server (`temporal server start-dev`) with its bundled Web UI.

## Index

1. **[Exercise 1 — The Temporal dev server and your first workflow](./exercise-01-temporal-dev-server.md)** — install the `temporal` CLI, start the dev server, open the Web UI, and run a trivial workflow + activity end to end. Read the event history in the UI to *see* durable execution. (~60 min, guided)
2. **[Exercise 2 — The checkout saga](./exercise-02-checkout-saga.go)** — a Go workflow that reserves inventory, charges payment, and ships, with the compensation-stack pattern. Inject a failure in `ShipOrder` and prove the compensations run in reverse order. (~75 min, runnable)
3. **[Exercise 3 — Signals and the worker-crash drill](./exercise-03-signals-and-worker-crash.py)** — a Python workflow with a `cancel` signal, a `status` query, and a durable timer. Kill the worker mid-workflow and prove it resumes from the exact step with zero state loss. (~60 min, runnable)

## How to work the exercises

- Have the **Temporal dev server** running before you start exercise 2 or 3: `temporal server start-dev` (UI on `http://localhost:8233`). Keep it running in its own terminal.
- **Read the event history in the Web UI before and after every change.** The history is your ground truth, exactly as `ros2 topic info -v` and the Kafka lag table were in earlier weeks — it shows you precisely what the workflow did and where it is. Train the habit of reading it.
- When a workflow "behaves weirdly," check the Web UI for a **non-determinism error** before you touch code — it's almost always a determinism-rule violation (Lecture 1 §4.3).
- Each runnable exercise (`.go`, `.py`) ends with an **expected output** block. If your output doesn't match — especially if a completed activity re-executes on replay — you're not done.

## Running the Go saga

The Go exercise uses the Temporal Go SDK. From a fresh module directory:

```bash
go mod init checkout-saga
go get go.temporal.io/sdk
# Run the worker (hosts the workflow + activities) in one terminal:
go run exercise-02-checkout-saga.go -mode worker
# Start a workflow execution in another terminal:
go run exercise-02-checkout-saga.go -mode start -order order-A
# Force the ship step to fail and watch compensation:
go run exercise-02-checkout-saga.go -mode start -order order-A -fail-ship
```

## Running the Python workflow

The Python exercise uses the `temporalio` SDK:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install temporalio
# Worker in one terminal:
python3 exercise-03-signals-and-worker-crash.py worker
# Start a workflow in another:
python3 exercise-03-signals-and-worker-crash.py start --order order-A
# Send a cancel signal / query the status:
python3 exercise-03-signals-and-worker-crash.py signal --order order-A
python3 exercise-03-signals-and-worker-crash.py query  --order order-A
```

For the worker-crash drill: start the worker, start a workflow that sleeps mid-saga, `kill -9` the worker, restart it, and confirm in the Web UI that the workflow resumed from the recorded step with no activity re-execution.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-12` to compare.
