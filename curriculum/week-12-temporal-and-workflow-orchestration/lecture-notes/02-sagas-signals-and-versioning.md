# Lecture 2 — Sagas, Signals, and Versioning: Building Durable Processes That Last

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can structure a saga with clean compensation, use signals/queries/child workflows, version a long-running workflow without breaking replay, and argue precisely when orchestration beats choreography.

Lecture 1 gave you the architecture, the workflow/activity split, and the determinism rule. This lecture builds the patterns you actually ship: the **saga** with reverse-order compensation, the **signals and queries** that let the outside world interact with a running workflow, **child workflows** for composition, the **versioning** discipline that lets you change long-running workflows safely, and finally the honest **orchestration vs choreography** decision that this whole week has been building toward.

---

## Part 1 — The saga with compensation, done cleanly

### 1.1 The problem with inline compensation

Lecture 1 ended with a checkout workflow whose compensation was inlined into each error branch:

```go
if err := workflow.ExecuteActivity(ctx, ShipOrder, order).Get(ctx, nil); err != nil {
	_ = workflow.ExecuteActivity(ctx, RefundCharge, charge).Get(ctx, nil)
	_ = workflow.ExecuteActivity(ctx, ReleaseInventory, res).Get(ctx, nil)
	return Result{}, err
}
```

This works but it doesn't scale: with five steps, each error branch must remember to compensate *all* the prior steps in the right order, and you will eventually forget one. The compensation logic is duplicated and fragile.

### 1.2 The compensation-stack pattern

The clean structure: maintain a **stack of compensations**, push one after each successful step, and on any failure run the stack in reverse (LIFO) order. In Go, `defer` plus a slice expresses this beautifully:

```go
func CheckoutSaga(ctx workflow.Context, order Order) (err error) {
	ctx = workflow.WithActivityOptions(ctx, defaultActivityOptions())

	// The compensation stack. Each entry undoes one completed step.
	var compensations []func()
	defer func() {
		if err != nil { // only compensate if the saga failed
			// Run compensations in REVERSE order (LIFO): undo the most recent first.
			for i := len(compensations) - 1; i >= 0; i-- {
				compensations[i]()
			}
		}
	}()

	// Step 1: reserve inventory
	var res Reservation
	if err = workflow.ExecuteActivity(ctx, ReserveInventory, order).Get(ctx, &res); err != nil {
		return err // nothing pushed yet; nothing to compensate
	}
	compensations = append(compensations, func() {
		_ = workflow.ExecuteActivity(ctx, ReleaseInventory, res).Get(ctx, nil)
	})

	// Step 2: charge payment
	var charge Charge
	if err = workflow.ExecuteActivity(ctx, ChargePayment, order).Get(ctx, &charge); err != nil {
		return err // defer runs ReleaseInventory
	}
	compensations = append(compensations, func() {
		_ = workflow.ExecuteActivity(ctx, RefundCharge, charge).Get(ctx, nil)
	})

	// Step 3: ship
	if err = workflow.ExecuteActivity(ctx, ShipOrder, order).Get(ctx, nil); err != nil {
		return err // defer runs RefundCharge then ReleaseInventory, in that order
	}

	return nil // success: defer sees err == nil, compensates nothing
}
```

Now each step does exactly two things: run its activity, and push its compensation. The `defer` guarantees that *whatever* step fails, the compensations for all completed steps run, in reverse order, exactly once. Adding a fourth step is two lines and no risk of forgetting a compensation. This is the canonical Temporal saga, and it is what you'll build in the exercises.

### 1.3 Compensations must be idempotent too

A subtlety: compensations are activities, so they're at-least-once and must be idempotent. `RefundCharge` keyed by the charge id, `ReleaseInventory` keyed by the reservation id — re-running a compensation must be safe, because a worker can crash *during* compensation and the saga's defer will re-run it on replay. The Week-11 idempotency discipline applies to the undo path as much as the forward path. A non-idempotent compensation (a blind `stock += 1`) double-releases on a retry and corrupts inventory.

### 1.4 Why orchestrated compensation beats choreographed compensation

Compare to last week's choreographed saga, where compensation was scattered: the shipping consumer, on failure, emitted a `shipping.failed` event; the payment consumer listened for it and refunded; the inventory consumer listened for *that* and released. The compensation graph lived in no single place, the ordering was implicit in who-listens-to-what, and reasoning about "does this saga always fully compensate" required tracing events across services. The orchestrated version above puts the *entire* compensation logic in one readable function with explicit reverse order. **That visibility — the saga's success path and failure path both readable in one place — is the single biggest reason to reach for orchestration**, and it's the heart of the Part 4 comparison.

### 1.5 Why a saga and not a distributed transaction

A reasonable question: why compensate at all — why not a distributed transaction (two-phase commit) that atomically reserves, charges, and ships, rolling back automatically on any failure? Because **2PC across independent services does not work at scale**, for reasons you studied in Phase 1:

- It requires every participant to hold locks for the duration of the transaction (the prepare phase), which kills throughput and availability — a slow shipping service stalls every checkout's inventory and payment locks.
- It requires a coordinator that, if it fails between prepare and commit, leaves participants blocked indefinitely (the blocking problem of 2PC).
- External services (Stripe, a shipping carrier) simply don't expose a two-phase prepare/commit interface; you cannot "prepare" a credit-card charge.

The saga is the pragmatic answer: instead of one atomic transaction, run a sequence of *local* transactions (each service commits its own step immediately) and, if a later step fails, *compensate* the earlier ones with explicit undo actions. You give up atomicity (there's a window where inventory is reserved but payment hasn't charged) and isolation (a concurrent reader can see the intermediate state) in exchange for availability and the ability to span services that don't support 2PC. Temporal makes the saga *reliable* (the workflow durably drives every step and every compensation), which is exactly the part that's hard to get right by hand — and impossible to get right with scattered consumers and no coordinator. The saga-with-compensation is the correct shape for cross-service business processes; Temporal is the tool that makes it trustworthy.

---

## Part 2 — Signals, queries, and child workflows

A workflow is not a sealed box. The outside world interacts with a running workflow through three mechanisms.

### 2.1 Signals — asynchronous input into a running workflow

A **signal** delivers data *into* a running workflow asynchronously. The canonical use: a human or another service influences an in-flight process. "The customer cancelled their order while it was waiting for payment confirmation" is a signal.

```go
func CheckoutWorkflow(ctx workflow.Context, order Order) error {
	// A channel that receives the "cancel" signal.
	cancelCh := workflow.GetSignalChannel(ctx, "cancel")

	var cancelled bool
	// Wait for EITHER the payment-confirmation timer OR a cancel signal.
	selector := workflow.NewSelector(ctx)
	selector.AddReceive(cancelCh, func(c workflow.ReceiveChannel, more bool) {
		c.Receive(ctx, nil)
		cancelled = true
	})
	selector.AddFuture(workflow.NewTimer(ctx, 72*time.Hour), func(workflow.Future) {
		// 72h elapsed with no cancel — proceed.
	})
	selector.Select(ctx) // blocks (durably!) until one fires

	if cancelled {
		return workflow.ExecuteActivity(ctx, ReleaseInventory, order).Get(ctx, nil)
	}
	return workflow.ExecuteActivity(ctx, FinalizeOrder, order).Get(ctx, nil)
}
```

Signals are recorded in the history (a `WorkflowExecutionSignaled` event), so they survive replay like everything else. The `Select` here *durably* waits up to 72 hours for a cancel; the worker can be redeployed any number of times during that wait and the workflow resumes correctly, because the wait is a recorded timer plus a recorded signal channel, not an in-memory `select` that dies with the process. A client sends the signal with `client.SignalWorkflow(ctx, workflowID, runID, "cancel", nil)`.

### 2.2 Queries — synchronous, side-effect-free reads

A **query** reads a running workflow's current state synchronously, without affecting it. "What's the status of order A's checkout?" is a query. Queries must be **read-only and deterministic** (they run against the replayed state):

```go
func CheckoutWorkflow(ctx workflow.Context, order Order) error {
	status := "started"
	// Register a query handler that returns the current status.
	_ = workflow.SetQueryHandler(ctx, "status", func() (string, error) {
		return status, nil // read-only; no side effects
	})

	status = "reserving"
	// ... reserve ...
	status = "charging"
	// ... charge ...
	status = "shipping"
	// ... ship ...
	status = "confirmed"
	return nil
}
```

A client queries with `client.QueryWorkflow(ctx, workflowID, runID, "status")` and gets the live value. Queries never appear in the history (they don't change state), so they're cheap and can be called frequently — they're how a UI shows real-time workflow progress.

> **Signals vs queries vs updates (the 2026 trio).** Signals are *write, async, no return* — fire data in, don't wait. Queries are *read, sync, no side effects* — read state out. Temporal added a third primitive, **Updates**, that is *write, sync, with a return value* — send input in, let the workflow validate and process it, and get a result back synchronously. An Update is the right tool when the caller needs to know the outcome of their input (e.g., "add this item to the cart and tell me the new total, or reject it if out of stock"). The mental model: signal when you don't need an answer, update when you do, query when you only read. For this week's exercises, signals and queries cover the cases; know that Update exists for the "synchronous mutation with validation" need.

### 2.3 Child workflows — composition

A workflow can start **child workflows**, composing durable execution. Use a child workflow when a sub-process is independently meaningful (its own history, its own retries, its own lifecycle) — e.g., the checkout workflow spawns a child `FulfillmentWorkflow` that runs for days handling shipping and delivery while the parent completes the purchase quickly.

```go
cwo := workflow.ChildWorkflowOptions{WorkflowID: "fulfillment-" + order.ID}
ctx = workflow.WithChildOptions(ctx, cwo)
var fulfillment FulfillmentResult
err := workflow.ExecuteChildWorkflow(ctx, FulfillmentWorkflow, order).Get(ctx, &fulfillment)
```

Use a child workflow (vs an activity) when the sub-process is itself a multi-step orchestration that benefits from its own durability and history, or when it has a very different lifetime than the parent. Use an activity for a single unit of work. Over-using child workflows adds history overhead; under-using them buries independent processes inside one giant history. The judgment is "is this its own durable process or just a step."

### 2.4 Two patterns these primitives unlock

Putting signals, queries, and durable timers together gives you two patterns that are painful without Temporal and trivial with it:

- **Human-in-the-loop.** A process that must wait for a human decision — approve a refund, confirm a high-value order — is a durable `Select` on a signal channel and a timeout timer. The workflow sleeps (durably, for days) until the human signals approval or the timer fires and it auto-rejects. No timer table, no poller, no "where was this approval request" state to manage — the workflow *is* the state, and it survives every deploy during the wait.

  ```go
  approvalCh := workflow.GetSignalChannel(ctx, "approval")
  var decision string
  s := workflow.NewSelector(ctx)
  s.AddReceive(approvalCh, func(c workflow.ReceiveChannel, _ bool) {
      c.Receive(ctx, &decision) // "approved" or "rejected"
  })
  s.AddFuture(workflow.NewTimer(ctx, 48*time.Hour), func(workflow.Future) {
      decision = "auto-rejected" // no human responded in 48h
  })
  s.Select(ctx) // durably waits up to 48 hours
  ```

- **The entity workflow.** A long-lived workflow that *is* an entity — a shopping cart, a subscription, a user's session — that lives for months, holds the entity's state, processes signals (add item, cancel), answers queries (current contents), and uses `ContinueAsNew` to bound its history. This replaces a row in a database plus a pile of update endpoints with a single durable object that has built-in consistency and history. It's a powerful pattern, and the one most teams reach for second (after sagas) once Temporal clicks.

### 2.5 Testing workflows

Because workflows are deterministic code, they are *unusually* testable: the SDK ships a test framework that runs a workflow in a simulated environment with mocked activities and a controllable clock. You can advance time by days instantly (no real sleeping), assert which activities were called with which arguments, and inject activity failures to test your compensation:

```go
func TestCheckoutSaga_CompensatesOnShipFailure(t *testing.T) {
	env := testsuite.NewTestWorkflowEnvironment(t)
	env.OnActivity(ReserveInventory, mock.Anything, mock.Anything).Return(Reservation{ID: "r1"}, nil)
	env.OnActivity(ChargePayment, mock.Anything, mock.Anything).Return(Charge{ID: "c1"}, nil)
	env.OnActivity(ShipOrder, mock.Anything, mock.Anything).Return(errors.New("carrier down"))
	// Assert the compensations run, in reverse order:
	env.OnActivity(RefundCharge, mock.Anything, mock.Anything).Return(nil).Once()
	env.OnActivity(ReleaseInventory, mock.Anything, mock.Anything).Return(nil).Once()

	env.ExecuteWorkflow(CheckoutSaga, Order{ID: "A"})
	require.True(t, env.IsWorkflowCompleted())
	require.Error(t, env.GetWorkflowError()) // the saga failed (ship failed)
	env.AssertExpectations(t)                 // RefundCharge and ReleaseInventory were called
}
```

This is a genuine advantage of orchestration over choreography: the *whole* saga, including its compensation path, is unit-testable in milliseconds with no infrastructure, because it's one deterministic function. Testing a choreographed saga's compensation requires standing up the brokers and several consumers and inducing a real failure. The mini-project requires exactly this kind of compensation test.

---

## Part 3 — Versioning: changing workflows without breaking replay

### 3.1 Why changing workflow code is dangerous

Here is a problem unique to durable execution. Suppose a checkout workflow is *in flight* — it reserved inventory yesterday and is sleeping 72 hours waiting for payment confirmation. Today you deploy a new version of the workflow code that adds a step between reserve and charge. When the worker replays that in-flight workflow's history against the *new* code, the new code's decisions won't match the recorded history (the history has no event for the new step), and Temporal raises a **non-determinism error**. **You broke a running workflow by changing its code** — a failure mode that doesn't exist in stateless services, where a new deploy just handles new requests.

### 3.2 The `GetVersion` / patching API

The fix is **versioning**: gate the changed code behind a version marker so old (in-flight) executions take the old path and new executions take the new path. The Go SDK's `GetVersion`:

```go
func CheckoutWorkflow(ctx workflow.Context, order Order) error {
	// reserve ... (unchanged)

	// We want to add a fraud-check step, but only for workflows that STARTED after
	// this deploy. GetVersion records the chosen version in history the first time it
	// runs, so a replay of an old workflow returns DefaultVersion and skips the new code.
	v := workflow.GetVersion(ctx, "add-fraud-check", workflow.DefaultVersion, 1)
	if v == 1 {
		// new code path — only taken by workflows that recorded version 1
		if err := workflow.ExecuteActivity(ctx, FraudCheck, order).Get(ctx, nil); err != nil {
			return err
		}
	}
	// (workflows started before this deploy recorded DefaultVersion and skip the block)

	// charge ... (unchanged)
	return nil
}
```

`GetVersion` writes a marker to the history the first time it executes for a given workflow. On replay, an old workflow's history has no such marker (or has `DefaultVersion`), so `GetVersion` returns `DefaultVersion` and the old path runs — replay matches, no error. New workflows record version `1` and take the new path. Both old and new in-flight executions replay correctly. Once *all* old executions have drained, you can remove the `GetVersion` and the old branch.

> **The versioning discipline:** any change to workflow code that alters its *sequence of commands* (adding/removing/reordering activities, timers, signals) must be gated with `GetVersion` (or a patch) if there are in-flight executions on the old code. Changes that *don't* alter the command sequence — refactoring an activity's internals, fixing a typo in a log — are safe, because activities are replayed from recorded results, not re-run. Learn to ask, before every workflow-code change: "does this change what the workflow *does*, in what order? If yes, version it." This is the operational tax of durable execution, and it is well worth the durability.

### 3.3 `ContinueAsNew` for unbounded histories

A workflow that runs forever (an entity workflow modeling a customer that lives for years, processing a signal now and then) accumulates an unbounded history, which eventually becomes too large to replay efficiently. The fix is **`ContinueAsNew`**: the workflow completes and atomically starts a *fresh* execution of itself with carried-over state and an empty history. It's the durable-execution analog of a tail-recursive loop — same logical workflow, bounded history. Reach for it whenever a workflow's history would otherwise grow without bound.

---

## Part 4 — Orchestration vs choreography (the decision this week was building toward)

Now the central comparison. You've built the same saga both ways: choreographed (Week 11, events + idempotent consumers) and orchestrated (this week, a Temporal workflow). When is each right?

### 4.1 The two styles

- **Choreography:** services react to each other's events. No central coordinator; the process emerges from who-listens-to-what. The order's lifecycle is distributed across the services that participate in it.
- **Orchestration:** a central workflow drives the steps, calling each service in turn and handling failures and compensation explicitly. The process *is* the workflow; its shape lives in one place.

### 4.2 The honest comparison

| Dimension | Choreography (events) | Orchestration (Temporal) |
|---|---|---|
| Process visibility | Implicit; reconstruct from who-listens-to-what | Explicit; the workflow *is* the process, readable in one file |
| Coupling | Loose; services don't know the orchestrator | A central workflow knows all the steps (logical coupling) |
| Compensation | Scattered across consumers; ordering implicit | Explicit, reverse-order, in one place |
| Adding a step | Add a consumer + wire events | Add lines to the workflow |
| Debugging "where is order A" | Query several services | One workflow, one history, one query |
| Failure of the coordinator | No single coordinator to fail | The workflow engine must be available (but it's durable) |
| Extreme decoupling / scale | Excellent; fully decentralized | A central engine, though horizontally scalable |
| Best for | Many teams, loose coupling, simple flows | Complex multi-step processes with compensation, long waits, visibility needs |

### 4.3 When orchestration wins (the lecture title)

Orchestration is the **simpler** answer — counterintuitively — when the process is **complex, long-running, requires compensation, or needs visibility**. The choreographed saga's "loose coupling" is a real benefit for simple flows, but for a multi-step process with compensation it becomes a liability: the loose coupling means the process's correctness is an emergent property of many independent consumers, impossible to read in one place and hard to reason about. Orchestration trades a little coupling (the workflow knows the steps) for enormous gains in visibility, explicit compensation, durable long waits, and debuggability. **When someone asks "isn't a central orchestrator an anti-pattern," the answer is: for a simple two-service flow, maybe; for a checkout saga with compensation and a 72-hour human-confirmation wait, the orchestrator is the simplest correct design, and choreographing it would be the over-engineering.**

The senior heuristic for 2026: **choreograph simple, broadcast-style flows (one event, many independent reactions) where loose coupling is the point; orchestrate complex, multi-step, compensating processes where visibility and explicit failure handling are the point.** Most real systems use both — events for the loose-coupling spine (Week 10–11) and Temporal for the complex processes that ride on it. They're complementary, not rivals.

### 4.4 The alternatives, briefly

- **AWS Step Functions** — a managed state machine defined in Amazon States Language (JSON). Great if you're all-in on AWS and your process fits a state-machine shape; the trade-offs are vendor lock-in, JSON-not-code authoring, and weaker local testing. It's replay-free (the service holds state), so no determinism rule — but also less expressive than code.
- **Azure Durable Functions** — orchestrator functions with replay semantics *very* similar to Temporal (it's the same durable-execution idea), tied to the Azure Functions runtime. If you're on Azure, it's the natural choice; off Azure, Temporal is more portable.
- **Cadence** — Temporal's direct ancestor (Temporal was forked from Cadence by its original creators at Uber). Conceptually nearly identical; Temporal has the larger community and momentum in 2026. If you see Cadence in a codebase, everything you learned this week transfers.

The summary: **Temporal is the portable, code-first, open-source durable-execution engine; Step Functions and Durable Functions are the managed, cloud-tied equivalents.** Choose Temporal for portability and code-first authoring; choose the managed option if you're committed to one cloud and want zero ops. The *concepts* — durable execution, the workflow/activity split, compensation — are the same across all of them, which is why this week's skills transfer.

The decision matrix in one table:

| Engine | Authoring | Hosting | Determinism rule? | Best when |
|---|---|---|---|---|
| **Temporal** | Code (Go/Java/Python/TS) | Self-host or Temporal Cloud | Yes (replay-based) | Portability, code-first, multi-cloud or on-prem |
| **AWS Step Functions** | ASL (JSON) | Managed AWS | No (service holds state) | All-in on AWS; state-machine-shaped flows |
| **Azure Durable Functions** | Code (in Functions runtime) | Managed Azure | Yes (replay-based) | All-in on Azure; serverless orchestration |
| **Cadence** | Code (Go/Java) | Self-host | Yes (replay-based) | Legacy; migrate to Temporal for momentum |

The thing to carry out of this comparison: the *vendor* differs, but the *idea* — a long-running process expressed as durable code (or a durable state machine) that survives failures — is one idea with several implementations. Learn it once, here, with Temporal, and you can pick up any of the others in a day.

> **One last framing for the midterm.** Phase 2 gave you a layered toolkit: a **log** (Kafka/Redpanda) for the durable event spine, **exactly-once effect** (outbox + idempotency) for correctness across the broker boundary, and **durable orchestration** (Temporal) for the complex processes that ride on top. They compose: the order service emits to the log, a consumer drives a Temporal workflow, the workflow's activities are idempotent against redelivery, and the whole thing survives broker loss and worker crashes. When you write the midterm essay, the strongest analyses will show *which layer solves which problem* in the system you review — and will notice when a system reaches for the wrong layer (orchestrating a simple fan-out, or choreographing a complex compensating saga). That layered judgment is the Phase 2 capstone skill.

---

## 5. Recap

You should now be able to:

- Structure a saga with the compensation-stack pattern (push a compensation per step, run them reverse-order on failure via `defer`), and explain why compensations must be idempotent.
- Use signals (async input, durable waits), queries (sync read-only state), and child workflows (composition), and choose the right one for a given need.
- Version a workflow with `GetVersion` so changing code doesn't break in-flight executions, and use `ContinueAsNew` to bound an unbounded history.
- Compare orchestration and choreography honestly, and argue when a central workflow engine is the *simpler* answer (complex, long-running, compensating, visibility-needing processes).
- Place Step Functions, Durable Functions, and Cadence relative to Temporal and choose among them with evidence.
- Explain why a saga (local transactions + compensation) is the right shape for cross-service business processes where 2PC's locking, blocking, and lack of prepare/commit support make it untenable.
- Unit-test a whole saga — including its compensation path — in milliseconds with the SDK's test framework, mocking activities and controlling the clock.

Next: the exercises put all of this on a running Temporal — a checkout saga with compensation, a signal-driven cancel, and a worker-crash drill proving zero state loss. Continue to [the exercises](../exercises/README.md).

---

## References

- *Temporal — saga pattern*: <https://docs.temporal.io/develop/go/saga>
- *Temporal — message passing (signals, queries, updates)*: <https://docs.temporal.io/develop/go/message-passing>
- *Temporal — child workflows*: <https://docs.temporal.io/develop/go/child-workflows>
- *Temporal — versioning*: <https://docs.temporal.io/develop/go/versioning>
- *Temporal — ContinueAsNew*: <https://docs.temporal.io/develop/go/continue-as-new>
- *Saga pattern — microservices.io*: <https://microservices.io/patterns/data/saga.html>
- *AWS Step Functions*: <https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html>
- *Azure Durable Functions*: <https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview>
