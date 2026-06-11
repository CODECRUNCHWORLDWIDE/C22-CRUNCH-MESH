# Lecture 1 — When Orchestration Wins: Temporal Architecture, Determinism, and Activities

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain Temporal's architecture and how an event history makes a workflow durable, state precisely why workflow code must be deterministic and what that forbids, and author activities with correct retry policies and timeouts.

If you remember one sentence from this entire week, remember this one:

> **A Temporal workflow is durable because it is deterministic and its every step is recorded in an event history that is replayed to reconstruct state after any failure. The workflow doesn't hold state in memory and hope the process survives — it records its decisions, and a new worker rebuilds the state by replaying the code against the history.**

Last week you built a saga out of idempotent consumers and outbox tables. It was correct, and it was *scattered*: the order's lifecycle lived in no single place. This week the entire saga becomes one function that reads top-to-bottom, and Temporal makes that function survive crashes for you — but only if you obey the determinism rule, which is the price of admission and the subject of half this lecture.

---

## 1. The problem Temporal solves

Consider checkout: reserve inventory, charge payment, ship the order. Three steps, each a call to a different service, each able to fail, and a requirement that if shipping fails you refund the charge and release the inventory. Last week you choreographed this as a chain of events and idempotent consumers. The pain points you felt:

- **The process's shape is invisible.** To know "what does checkout do," you read five consumers and reconstruct the graph in your head. There is no single artifact that *is* the process.
- **State lives in scattered tables.** "Where is order A in its lifecycle" is a query across several services' databases.
- **Crash recovery is hand-built.** Every consumer needs its dedup table and its chaos test, and the compensation logic is smeared across services.
- **Long waits are awkward.** "Wait 3 days for the customer to confirm, then expire the order" requires a scheduler, a timer table, and a poller — infrastructure you build and operate.

Temporal's pitch is **durable execution**: write the process as one ordinary-looking function — `reserve(); charge(); ship();` — and Temporal guarantees that function runs to completion *exactly as written*, surviving process crashes, machine failures, deploys, and sleeps of arbitrary length, with its local variables and position intact across all of them. The five scattered consumers become one readable workflow; the crash recovery becomes automatic; the 3-day wait becomes a single line, `workflow.Sleep(3 * 24 * time.Hour)`, that survives the worker being redeployed twelve times in those three days.

That is a genuinely large simplification, and the rest of this lecture is *how* it works and *what it costs you* (determinism).

---

## 2. The architecture

Temporal is a server (a cluster of services) plus **workers that you write and run**. Keep the two straight: the server orchestrates and persists; your workers execute your code.

### 2.1 The server services

- **Frontend** — the API gateway. Your client SDK and your workers all talk to the frontend. It routes requests, handles rate limiting, and is the only service clients touch.
- **History** — the heart. It owns each workflow's **event history** and the workflow state machine. When an activity completes, the history service records the event and decides what the workflow should do next. It is the durable, authoritative record of every workflow's progress.
- **Matching** — the dispatcher. It owns **task queues** and matches workflow tasks and activity tasks to the workers polling those queues. This is how work gets handed to your worker processes.
- **Worker** (internal) — a system service for background tasks (timers firing, retries). Do not confuse it with the worker *processes you write*.
- **Persistence** — the backing store (Cassandra, PostgreSQL, or MySQL) where histories and state live. Everything durable bottoms out here.

### 2.2 The workers you write

A **worker** is a process *you* deploy that hosts your workflow and activity code and polls a task queue. The flow:

```
client                 frontend/history          matching            YOUR worker
  │  StartWorkflow        │                          │                   │
  ├──────────────────────►│ persist WorkflowStarted  │                   │
  │                       ├─ enqueue WorkflowTask ───►│                   │
  │                       │                           ├─ dispatch ───────►│ run workflow code
  │                       │                           │                   │   schedule activity
  │                       │◄── ScheduleActivity ──────┤◄──────────────────┤
  │                       ├─ enqueue ActivityTask ───►│                   │
  │                       │                           ├─ dispatch ───────►│ run activity (real I/O)
  │                       │◄── ActivityCompleted ─────┤◄──────────────────┤
  │                       ├─ persist + resume workflow│                   │
```

The key insight: **the workflow code runs on your worker, but its *decisions* (schedule this activity, set this timer) are sent back to the server and recorded in the history.** Your worker is stateless about any individual workflow — if it dies, another worker picks up the task, replays the history, and continues. The durable state is on the server; your workers are interchangeable executors.

A worker is a small program: connect to the frontend, register your workflows and activities on a task queue, and poll:

```go
func main() {
	c, _ := client.Dial(client.Options{HostPort: "localhost:7233"})
	defer c.Close()

	// A worker polls one task queue and hosts the code registered on it.
	w := worker.New(c, "checkout-task-queue", worker.Options{})
	w.RegisterWorkflow(CheckoutWorkflow)        // the deterministic orchestration
	w.RegisterActivity(ReserveInventory)        // the side-effecting work
	w.RegisterActivity(ChargePayment)
	w.RegisterActivity(ShipOrder)

	w.Run(worker.InterruptCh())                  // poll forever; survives restarts
}
```

Run many copies of this for horizontal scale and high availability; any of them can pick up any workflow's next task. Killing one and starting another loses nothing — that's the property the whole week proves.

---

## 3. Workflow vs activity — the central distinction

This is the distinction the entire framework rests on. Get it wrong and nothing works; get it right and everything follows.

- A **workflow** is **deterministic orchestration code**. It decides *what* to do and *in what order* — schedule this activity, wait for its result, then schedule that one, set a timer, react to a signal. It does **no I/O**: no database calls, no HTTP requests, no reading the clock, no random numbers, no direct file access. It is pure coordination logic over the results activities give it.
- An **activity** is **a unit of work that does the actual side effects** — call the payment API, write to Postgres, send the email, read a file. Activities are where all I/O and all non-determinism live. An activity runs **at-least-once** (Temporal retries it on failure), so it must be **idempotent** (Week 11's lesson, still required).

Here is the same checkout, sketched, to make the split concrete:

```go
// WORKFLOW: deterministic orchestration. No I/O. Just decides and waits.
func CheckoutWorkflow(ctx workflow.Context, order Order) error {
	ao := workflow.ActivityOptions{StartToCloseTimeout: 30 * time.Second}
	ctx = workflow.WithActivityOptions(ctx, ao)

	// Schedule activities and await results. The workflow doesn't DO the work;
	// it orchestrates activities that do.
	var reservation Reservation
	if err := workflow.ExecuteActivity(ctx, ReserveInventory, order).Get(ctx, &reservation); err != nil {
		return err
	}
	var charge Charge
	if err := workflow.ExecuteActivity(ctx, ChargePayment, order).Get(ctx, &charge); err != nil {
		return err
	}
	return workflow.ExecuteActivity(ctx, ShipOrder, order).Get(ctx, nil)
}

// ACTIVITY: the real work. Does I/O. Must be idempotent (it can be retried).
func ChargePayment(ctx context.Context, order Order) (Charge, error) {
	// REAL network call to the payment provider, with a stable idempotency key
	// (Week 11) because Temporal may retry this activity.
	return stripe.Charge(order.TotalCents, idempotencyKey("charge-"+order.ID))
}
```

The workflow reads like a synchronous program — reserve, then charge, then ship — but each step is a durable activity execution. The workflow function might be *suspended for days* between two lines (waiting on a slow activity or a timer) and the worker hosting it might be killed and replaced ten times in between; the code resumes at the exact next line with `reservation` and `charge` still populated. That is durable execution.

> **Why the split exists:** the workflow must be **replayable** (re-runnable against its history to rebuild state), which requires determinism. I/O is inherently non-deterministic (the network can fail, return different data, take different time), so it *cannot* live in workflow code — it is quarantined into activities, whose *results* are recorded in the history. On replay, the workflow doesn't re-call the activity; it reads the recorded result from the history. The split is precisely what makes replay possible.

---

## 4. Deterministic replay — the magic and the rule

### 4.1 What the history records

Every workflow has an **event history**: an append-only log (yes, another log — Phase 2's theme) of everything that happened. A simplified history for our checkout:

```
1  WorkflowExecutionStarted        (input: order A)
2  WorkflowTaskScheduled
3  WorkflowTaskCompleted
4  ActivityTaskScheduled           (ReserveInventory)
5  ActivityTaskCompleted           (result: reservation R)
6  WorkflowTaskScheduled
7  WorkflowTaskCompleted
8  ActivityTaskScheduled           (ChargePayment)
9  ActivityTaskCompleted           (result: charge C)
10 ... and so on
```

Each time the workflow makes progress (schedules an activity, an activity completes, a timer fires), an event is appended. The history *is* the durable state of the workflow.

### 4.2 How replay reconstructs state

Here is the mechanism. When a worker needs to run a workflow — because it just started, or because the previous worker died, or because an activity just completed and the workflow must decide what's next — it **replays the workflow function from the beginning against the recorded history**:

- It runs `CheckoutWorkflow` from line 1.
- When the code calls `ExecuteActivity(ctx, ReserveInventory, ...)`, the worker does **not** actually schedule a new activity — it looks at the history, sees event 4/5 already recorded `ReserveInventory` completed with result R, and **returns R immediately** from the recorded history.
- The code continues to `ChargePayment`; again, the worker reads the recorded result C from events 8/9.
- The code reaches `ShipOrder`; this time the history has *no* recorded result yet (this is where the previous worker died), so the worker *actually schedules* the activity for real.

The result: replaying the deterministic code against the history rebuilds the exact in-memory state (`reservation = R`, `charge = C`) at the moment of the crash, and execution continues from there. **The completed activities are not re-executed** — their results come from the history. This is why a worker crash loses nothing: the durable history plus the deterministic code reconstruct everything.

### 4.3 The determinism rule, stated precisely

For replay to reconstruct state correctly, the workflow code must make **the same decisions in the same order** every time it runs against the same history. If it doesn't — if it would schedule a *different* activity on replay than the history records — Temporal detects the mismatch and raises a **non-determinism error**, because the reconstruction is now corrupt. So workflow code is forbidden from anything that could vary between runs:

- **No `time.Now()` / `time.Sleep()`** — the wall clock differs every run. Use `workflow.Now(ctx)` (deterministic; returns the recorded time) and `workflow.Sleep(ctx, d)` (a durable timer, recorded in history).
- **No `rand`** — random differs every run. Use `workflow.SideEffect` or the SDK's deterministic random, which records the value in history so replay returns the same one.
- **No direct I/O** — network/DB/file calls differ and have side effects. Put them in activities.
- **No iterating a Go `map` and depending on order** — Go randomizes map iteration order; two runs differ. Sort keys first, or use ordered structures.
- **No spawning raw goroutines / `go func()`** — the scheduler is non-deterministic. Use `workflow.Go` (the SDK's deterministic coroutine).
- **No reading mutable global state, env vars, config at runtime** — these can change between the original run and the replay.

> **The rule in one line:** *workflow code may only get non-deterministic values through Temporal-mediated mechanisms (activity results, `workflow.Now`, `workflow.SideEffect`, signals), never directly.* Everything that varies between runs must be recorded in the history so replay reproduces it. Internalize the list above; violating it is the single most common Temporal bug, and you'll diagnose three flavors of it in this week's challenge.

The forbidden-vs-allowed table, to tape next to your editor:

| You want... | FORBIDDEN in workflow code | ALLOWED (deterministic SDK) |
|---|---|---|
| The current time | `time.Now()` | `workflow.Now(ctx)` |
| To sleep / wait | `time.Sleep(d)` | `workflow.Sleep(ctx, d)` (a durable timer) |
| A random number / UUID | `rand.Int()`, `uuid.New()` | `workflow.SideEffect(ctx, ...)` |
| To do I/O (DB, HTTP) | a direct call | put it in an **activity** |
| Concurrency | `go func(){}` | `workflow.Go(ctx, ...)` |
| A map iteration | range over `map` (random order) | sort keys, then range |
| Read config/env | `os.Getenv` at runtime | pass it in as workflow input, or via an activity |

And the contrast in code, because it's so easy to slip:

```go
// WRONG: non-deterministic. On replay, time.Now() and rand differ from the original
// run, the workflow makes a different decision, and Temporal raises a non-determinism
// error (or worse, silently corrupts state in older SDKs).
func BadWorkflow(ctx workflow.Context) error {
	deadline := time.Now().Add(time.Hour)   // <-- wall clock; differs every replay
	if rand.Intn(100) < 50 {                 // <-- random; differs every replay
		return workflow.ExecuteActivity(ctx, PathA).Get(ctx, nil)
	}
	return workflow.ExecuteActivity(ctx, PathB).Get(ctx, nil)
}

// RIGHT: every non-deterministic value comes through a Temporal-mediated API, so it's
// recorded in history and reproduced exactly on replay.
func GoodWorkflow(ctx workflow.Context) error {
	deadline := workflow.Now(ctx).Add(time.Hour)            // recorded time
	var coin int
	workflow.SideEffect(ctx, func(workflow.Context) interface{} {
		return rand.Intn(100)                               // recorded in history
	}).Get(&coin)
	if coin < 50 {
		return workflow.ExecuteActivity(ctx, PathA).Get(ctx, nil)
	}
	return workflow.ExecuteActivity(ctx, PathB).Get(ctx, nil)
}
```

### 4.4 Why this is worth it

The payoff for obeying the rule is enormous: you write `reserve(); charge(); ship()` as plain sequential code, with `if`s and loops and local variables, and it becomes a crash-proof, infinitely-resumable durable process *for free*. No state machine to hand-code, no "where was I" table, no resumption logic. The determinism constraint feels alien for a day and then becomes second nature, because the SDK gives you a deterministic replacement for every forbidden operation. You trade a small, learnable discipline for automatic durability — the best trade in this part of the course.

---

## 5. Activities in depth

Activities are where the real work happens, and Temporal gives you rich control over their execution.

### 5.1 At-least-once and idempotency

An activity runs **at-least-once**: if it fails or times out, Temporal retries it per its retry policy. So — exactly as in Week 11 — **activities must be idempotent.** The `ChargePayment` activity uses a stable idempotency key derived from the order so a retry doesn't double-charge. Temporal *reduces* the idempotency burden (it won't re-run a *completed* activity on workflow replay, because the result is in the history) but does not *eliminate* it (a single activity execution can still be retried after a partial failure). Keep your Week-11 reflexes.

### 5.2 Retry policy

Every activity has a retry policy. The knobs:

```go
ao := workflow.ActivityOptions{
	StartToCloseTimeout: 30 * time.Second,
	RetryPolicy: &temporal.RetryPolicy{
		InitialInterval:    time.Second,       // first retry after 1s
		BackoffCoefficient: 2.0,               // then 2s, 4s, 8s, ... (exponential)
		MaximumInterval:    100 * time.Second, // cap the backoff
		MaximumAttempts:    5,                  // give up after 5 tries (0 = unlimited)
		NonRetryableErrorTypes: []string{"InvalidCardError"}, // never retry these
	},
}
```

The `NonRetryableErrorTypes` is important: some failures are permanent (an invalid card, a malformed request) and retrying them just wastes time and money. Mark them non-retryable so the activity fails fast and the workflow can compensate. Transient failures (a timeout, a 503) *should* retry with backoff. Getting this classification right is the activity-level analog of the data-loss matrix — knowing which failures are recoverable.

### 5.3 The four timeouts

Activities have four timeouts, and confusing them is a classic bug:

| Timeout | Clock starts | Measures | Typical use |
|---|---|---|---|
| **ScheduleToStart** | when scheduled | time waiting in the queue before a worker picks it up | detect "no workers available" |
| **StartToClose** | when a worker starts it | the activity's own execution time | the main one — bound how long the work may take |
| **ScheduleToClose** | when scheduled | total time including all retries | bound the whole activity end-to-end |
| **Heartbeat** | each heartbeat | max gap between heartbeats for long activities | detect a stuck long-running activity |

**StartToClose** is the one you set on almost every activity (how long may this one execution take). **Heartbeat** matters for long activities: a 10-minute video transcode should heartbeat every few seconds so Temporal can detect a stuck worker quickly instead of waiting 10 minutes.

### 5.4 Heartbeating

A long activity calls `activity.RecordHeartbeat(ctx, progress)` periodically. Two payoffs: Temporal detects a dead worker fast (no heartbeat within the heartbeat timeout → retry on another worker), and the heartbeat can carry **progress** so a retry resumes from where the last attempt got to instead of restarting:

```go
func TranscodeVideo(ctx context.Context, job Job) error {
	startFrame := 0
	if activity.HasHeartbeatDetails(ctx) {
		activity.GetHeartbeatDetails(ctx, &startFrame) // resume from last reported frame
	}
	for f := startFrame; f < job.TotalFrames; f++ {
		transcodeFrame(f)
		if f%100 == 0 {
			activity.RecordHeartbeat(ctx, f) // report progress; enables fast-fail + resume
		}
	}
	return nil
}
```

This combines with idempotency: a retried activity that resumes from its last heartbeat does less re-work, but must still be safe to re-run from that point.

---

## 6. A worked example: the marketplace checkout

On the services you've been building, here is the shape of what you'll implement in the exercises. The checkout workflow orchestrates three activities, each backed by a real service:

```go
func CheckoutWorkflow(ctx workflow.Context, order Order) (Result, error) {
	ctx = workflow.WithActivityOptions(ctx, defaultActivityOptions())

	// Step 1: reserve inventory (inventory-service)
	var res Reservation
	if err := workflow.ExecuteActivity(ctx, ReserveInventory, order).Get(ctx, &res); err != nil {
		return Result{}, err // nothing to compensate yet
	}

	// Step 2: charge payment (payment-service) — idempotent activity
	var charge Charge
	if err := workflow.ExecuteActivity(ctx, ChargePayment, order).Get(ctx, &charge); err != nil {
		// compensate step 1 before returning
		_ = workflow.ExecuteActivity(ctx, ReleaseInventory, res).Get(ctx, nil)
		return Result{}, err
	}

	// Step 3: ship (shipping-service)
	if err := workflow.ExecuteActivity(ctx, ShipOrder, order).Get(ctx, nil); err != nil {
		// compensate steps 2 and 1, in reverse order
		_ = workflow.ExecuteActivity(ctx, RefundCharge, charge).Get(ctx, nil)
		_ = workflow.ExecuteActivity(ctx, ReleaseInventory, res).Get(ctx, nil)
		return Result{}, err
	}

	return Result{OrderID: order.ID, Status: "confirmed"}, nil
}
```

Read it: the *entire* saga — the happy path *and* the compensation — is one function you can read top to bottom. Compare that to last week's five scattered consumers. And it is durable: kill the worker after `ChargePayment` succeeds, and a new worker replays, sees the charge recorded in history, and continues to `ShipOrder` without re-charging. Lecture 2 refines the compensation structure (a defer-based saga helper) and adds signals, queries, and versioning. For now, sit with how much complexity collapsed into readable code.

---

## 7. Recap

You should now be able to:

- Explain the four Temporal server services (frontend, history, matching, worker) and how the workers *you* write host workflow/activity code and poll task queues.
- State the workflow/activity split: deterministic orchestration with no I/O vs at-least-once side-effecting work, and why the split is what makes replay possible.
- Explain deterministic replay — the event history, how a worker reconstructs state by replaying code against it, and why completed activities aren't re-executed.
- Recite the determinism rule and its forbidden operations (`time.Now`, `rand`, direct I/O, map order, raw goroutines) and their deterministic SDK replacements.
- Author activities with retry policies (backoff, max attempts, non-retryable errors), the four timeouts, and heartbeating for long work.

Next: structuring the saga's compensation cleanly, signals and queries and child workflows, versioning long-running workflows safely, and the honest comparison of orchestration against choreography. Continue to [Lecture 2 — Sagas, Signals, and Versioning](./02-sagas-signals-and-versioning.md).

---

## References

- *Temporal — workflows*: <https://docs.temporal.io/workflows>
- *Temporal — activities*: <https://docs.temporal.io/activities>
- *Temporal — deterministic constraints*: <https://docs.temporal.io/workflow-definition#deterministic-constraints>
- *Temporal — workers and task queues*: <https://docs.temporal.io/workers>
- *Temporal — Go SDK developer guide*: <https://docs.temporal.io/develop/go>
- *Temporal — why durable execution*: <https://docs.temporal.io/evaluate/why-temporal>
