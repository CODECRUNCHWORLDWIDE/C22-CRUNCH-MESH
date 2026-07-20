# Mini-Project — `checkout-orchestrator`: The Week-11 Saga, Made Durable

> Re-build the Week-11 choreographed checkout saga as a **single Temporal workflow** with reverse-order compensation, a cancel signal, a status query, and a worker-crash drill that proves `state lost: 0`. Then write a one-page memo arguing, with this concrete before/after in hand, when orchestration beats the choreography you built last week.

This is the artifact that makes the whole phase land: last week you built checkout as scattered idempotent consumers and an outbox; this week you rebuild the *same* process as one readable, durable, testable workflow. After this week, "orchestration vs choreography" is not an abstract debate — you've implemented the identical saga both ways and can show the diff.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `checkout-orchestrator` becomes the **payment workflow of your capstone Polyglot Marketplace** — the syllabus literally specifies "`payment-service` (Go): Temporal workflow for charge / refund / reversal, with idempotency." The worker-crash drill becomes part of the capstone's reliability story. The orchestration-vs-choreography memo becomes a section of your midterm essay and your capstone architecture document. Build it well now; you'll defend it twice.

---

## What you will build

A repo `checkout-orchestrator` with four deliverables:

1. **`workflow/`** — the `CheckoutSaga` Go workflow (harden exercise 2) with the compensation-stack pattern: reserve → charge → ship, compensating in reverse order on any failure, plus a `cancel` signal (cancel before shipping releases and refunds) and a `status` query.
2. **`activities/`** — the four activities (reserve, charge, ship) and their compensations (release, refund), each idempotent on a stable id, wired to a real-ish backend (Postgres rows are fine; the capstone wires real services).
3. **`worker-crash-drill.sh`** — the automated proof: start a workflow, kill the worker mid-saga (after charge, before ship), restart it, and assert the workflow completes with the charge **not** re-executed and **zero** state lost.
4. **A decision memo** (`ORCHESTRATION.md`, ~1 page) that, using the concrete Week-11-vs-Week-12 diff, argues when orchestration beats choreography and when it doesn't — defended with the two implementations in front of you.

By the end you have a public repo of ~500–700 lines (Go + shell + a workflow test) plus a memo grounded in a real before/after — the most defensible "I understand orchestration" artifact you can bring to an interview.

---

## Why rebuild the same saga instead of building something new

You could build a fresh workflow. Don't — rebuild *last week's* saga, deliberately, because the *contrast* is the lesson:

- **You'll see the code collapse.** Five scattered consumers (Week 11) become one function you read top to bottom. That collapse is the single most persuasive argument for orchestration, and you can only make it if you built both.
- **You'll see the compensation move.** Last week's compensation was smeared across consumers reacting to failure events; this week it's a reverse-order stack in one place. Showing the diff *is* the memo.
- **You'll see the testability change.** Last week, testing the compensation path meant standing up brokers and inducing a real failure; this week it's a millisecond unit test with mocked activities. That's a concrete, demonstrable win.

A from-scratch workflow teaches the API. Rebuilding the known saga teaches the *judgment* — which is the actual learning objective and the thing the memo defends.

---

## Repo layout

```
checkout-orchestrator/
├── README.md
├── ORCHESTRATION.md            # the 1-page memo (the headline deliverable)
├── go.mod
├── workflow/
│   └── checkout.go             # CheckoutSaga: saga + signal + query
├── activities/
│   └── activities.go           # reserve/charge/ship + release/refund (idempotent)
├── cmd/
│   ├── worker/main.go          # the worker process
│   └── starter/main.go         # start / signal / query a workflow
├── worker-crash-drill.sh       # the durable-execution proof (headline)
├── schema.sql                  # orders, charges, inventory (verifiable activity state)
└── workflow/checkout_test.go   # the saga unit test (incl. compensation path)
```

The activities back onto a tiny Postgres schema so the worker-crash drill can *verify* the effect happened exactly once (rather than trusting logs):

```sql
CREATE TABLE orders    (id text PRIMARY KEY, status text NOT NULL);
CREATE TABLE charges   (order_id text PRIMARY KEY, amount_cents bigint NOT NULL);
CREATE TABLE inventory (sku text PRIMARY KEY, reserved int NOT NULL DEFAULT 0);
```

The `charges(order_id)` primary key is what makes "charged exactly once" a query (`SELECT count(*) FROM charges WHERE order_id='A'` must be 1) rather than a guess. The drill asserts against it.

---

## Deliverable 1 — the workflow

Harden exercise 2 into the production saga. It must:

- Implement reserve → charge → ship with the **compensation-stack pattern** (push a compensation per successful step; `defer` runs them reverse-order on failure).
- Handle a **`cancel` signal**: a cancel received before shipping aborts the saga and runs the compensations (release inventory, refund charge if charged).
- Expose a **`status` query** returning the current step ("reserving", "charging", "shipping", "confirmed", "compensating", "cancelled").
- Use correct activity options: `StartToCloseTimeout`, a retry policy with backoff, and `NonRetryableErrorTypes` for permanent failures (an invalid card shouldn't retry).
- Be fully deterministic — no `time.Now`, no `rand`, no I/O in the workflow (a `worker.NewWorkflowReplayer` test, stretch, proves it).

---

## Deliverable 2 — the activities

The four activities and two compensations, each:

- **Idempotent** on a stable id (charge by `charge-<order_id>`, refund by the charge id, reserve/release by the reservation id) — Temporal runs activities at-least-once, so a retry must be safe.
- Backed by real state (Postgres rows: an `orders` table, a `charges` table, an `inventory` table) so the worker-crash drill can *verify* the effect happened once.
- Classifying failures correctly: transient (timeout, 503) → retryable; permanent (invalid card) → `NonRetryableApplicationError` so the saga compensates fast.

---

## Deliverable 3 — the worker-crash drill (the headline)

`worker-crash-drill.sh` must, end to end:

1. Reset the DB and start the worker and the Temporal dev server.
2. Start a checkout workflow for `order-A`.
3. Wait until the worker logs that `ChargePayment` completed (charge is done, ship not yet).
4. `kill -9` the worker process.
5. Restart the worker.
6. Wait for the workflow to complete, then assert from the DB and the event history:
   - `ShipOrder` completed (the workflow resumed),
   - `ChargePayment` ran **exactly once** (the `charges` table has one row for `order-A`; the event history shows one `ActivityTaskCompleted` for charge),
   - exit non-zero if the charge ran twice or the workflow lost progress.

Expected output:

```
$ ./worker-crash-drill.sh
[1/6] reset db + start temporal + worker ... ok
[2/6] started checkout workflow for order-A
[3/6] charge completed; killing worker (kill -9) ... ok
[4/6] restarted worker ...
[5/6] workflow resumed: ship completed
[6/6] verify:
   charges rows for order-A:                1   (exactly once)
   charge activity executions in history:   1   (not re-run on replay)
   workflow status:                         confirmed
   state lost:                              0
PASS: durable execution survived a kill -9 with zero state loss, zero double-charge.
```

> **A re-executed charge or lost progress is a failing grade.** If the charge ran twice on replay, you have a determinism bug (something in the workflow varied between runs) or an activity that isn't actually idempotent. If progress was lost, the workflow isn't structured durably. The drill exists to catch exactly these, deterministically, before the capstone reliability review does.

---

## Deliverable 4 — the orchestration-vs-choreography memo

`ORCHESTRATION.md`, roughly one page, must:

1. Show the **before/after**: a sketch of the Week-11 choreographed saga (consumers + outbox + scattered compensation) next to the Week-12 workflow (one function), with line counts or a complexity comparison.
2. State **what orchestration bought**: process visibility, explicit reverse-order compensation, durable long waits, the millisecond compensation unit test, the worker-crash durability.
3. State **what it cost**: a central engine to operate, the determinism discipline, the versioning tax on code changes.
4. **Recommend** when to orchestrate vs choreograph — and, the senior move, name a flow in the marketplace where you'd *keep* choreography (a broadcast event with many independent reactions) and why.
5. Acknowledge that **most systems use both** — events for the loose-coupling spine, Temporal for the complex compensating processes — and that they're complementary.

---

## Rules

- **You may** read the Temporal docs, the samples-go repo, and your Week-11 code.
- **You must** keep all I/O, clocks, and randomness in **activities**; the workflow must be deterministic. A `worker.NewWorkflowReplayer` test (stretch) or a clean `kill -9` drill proves it.
- **You must** make every activity *and* every compensation idempotent on a stable id. A non-idempotent compensation (blind `stock += 1`) is an automatic fail.
- **You must** structure compensation with the stack/defer pattern, not inline per-branch duplication.
- Go 1.23+, Temporal Go SDK, Postgres (for verifiable state), Docker for the dev server.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-12-checkout-orchestrator-<yourhandle>`.
- [ ] The workflow implements reserve → charge → ship with reverse-order compensation, a `cancel` signal, and a `status` query.
- [ ] `worker-crash-drill.sh` kills the worker mid-saga, restarts it, and asserts the charge ran exactly once and the workflow completed — exiting non-zero on any double-charge or lost progress.
- [ ] A `checkout_test.go` unit test proves the compensation path: mock `ShipOrder` to fail and assert `RefundCharge` then `ReleaseInventory` are called in reverse order.
- [ ] `ORCHESTRATION.md` exists, shows the before/after, states the trade-offs, recommends with a kept-choreography example, and fits ~one page.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Saga structure** | 25 | Compensation-stack pattern; reverse-order compensation; clean, readable one-function saga. |
| **Determinism & idempotency** | 20 | No I/O/clock/rand in the workflow; every activity and compensation idempotent on a stable id. |
| **Worker-crash drill** | 25 | Automated kill-mid-saga + restart; asserts charge-once and no lost progress; exits non-zero on failure. |
| **Signal/query & test** | 15 | Cancel signal and status query work; the compensation-path unit test passes. |
| **Memo** | 15 | Concrete before/after; honest trade-offs; recommendation with a kept-choreography example. |

**90+** is portfolio-grade and becomes the capstone's `payment-service` workflow. **70–89** works but the drill is soft or the memo is abstract. **Below 70** means the saga isn't durably structured or the compensation isn't idempotent — fix that first.

---

## Common pitfalls (read before you start, save yourself hours)

The mistakes that consume most of the debugging time on this project, and how to avoid them:

- **Doing I/O in the workflow.** The single most common error: calling a database or HTTP client directly from the workflow function instead of from an activity. It "works" on the first run and explodes on the first replay with a non-determinism error. Rule: if it touches the outside world, it's an activity. The workflow only orchestrates.
- **A non-idempotent compensation.** It's easy to make the forward activities idempotent and forget the compensations. A `ReleaseInventory` that blindly does `stock += reserved` double-releases when a worker crashes during compensation and the defer re-runs it. Key compensations by the reservation/charge id, exactly like the forward path.
- **Catching the workflow's own errors too broadly.** If you `recover()` or swallow errors inside the workflow, the `defer`-based compensation never sees the error and doesn't run. Let errors propagate to the defer; that's what triggers compensation.
- **Racing the worker kill in the drill.** As in Week 11, don't `sleep && kill` and hope. Wait for a marker (the worker logs "charge completed") before killing, so the kill lands at a known point every run and the drill is deterministic.
- **Forgetting that activities run at-least-once even with Temporal.** Temporal won't re-run a *completed* activity on workflow replay, but it *will* retry a *failed* one. So the idempotency discipline from Week 11 is not optional — it's the floor. A retried `ChargePayment` without a stable idempotency key double-charges, and the drill will catch it.

If your drill double-charges, it is almost always one of the first two: I/O in the workflow (a determinism bug that re-runs the charge) or a non-idempotent activity/compensation. Check those before anything else.

---

## Stretch goals

- **Replay test as a CI gate.** Record a workflow history, then use `worker.NewWorkflowReplayer` to replay it against your current code in a unit test — catching any future determinism break before deploy. Add it to CI. This is the gate that prevents the Challenge-1 versioning incident.
- **Versioned change.** Add a fraud-check step gated with `GetVersion`, deploy it while a workflow is in flight, and prove the in-flight one finishes on the old path while a new one takes the new path — versioning done right.
- **Human-in-the-loop.** Add a "manual review" branch for high-value orders: the workflow durably waits (up to 48h) for an `approve`/`reject` signal, auto-rejecting on timeout. Prove the wait survives a worker redeploy.
- **`ContinueAsNew`.** Convert the order into a long-lived entity workflow (handles cancel, refund, return signals over its lifetime) and use `ContinueAsNew` to bound its history.

---

## What "done" feels like

You'll know this project landed when you can show someone the *same* checkout saga twice — last week's choreographed version (five consumers, an outbox, compensation reacting to failure events across three services) and this week's orchestrated version (one `CheckoutSaga` function you read top to bottom, compensation as a reverse-order stack) — and articulate, without notes, exactly what the orchestrated version bought (visibility, explicit compensation, durable waits, a millisecond compensation test, crash durability) and what it cost (a central engine, the determinism discipline, the versioning tax). That before/after, plus a green `worker-crash-drill.sh` printing `state lost: 0`, is the deliverable. The repo is the evidence; the judgment is the point — and the judgment is what the midterm and the capstone defense will probe.

## How this connects to the rest of C22

- **Week 11 (exactly-once)** built this saga's idempotency primitives; this week composes them into durable orchestration. The outbox still emits `order.placed.v1`; the workflow consumes it and drives the rest.
- **The midterm essay (this week)** can use the orchestration-vs-choreography memo as a worked example of a reliability/architecture trade-off.
- **Capstone** uses `checkout-orchestrator` as the literal `payment-service` Temporal workflow (charge / refund / reversal with idempotency), and the worker-crash drill as part of the reliability story.

When you've finished, push the repo and take the [quiz](../quiz.md) with your notes closed.
