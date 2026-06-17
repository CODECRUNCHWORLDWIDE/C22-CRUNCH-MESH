# Challenge 1 — Diagnose Three Determinism / Versioning Faults

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. After a deploy, a fleet of Temporal workflows is misbehaving: some throw `nondeterminism` errors on replay, one "takes a different branch every time the worker restarts," and a batch of in-flight workflows "started failing the moment we shipped a new workflow version." All three are determinism or versioning faults — each a *different* violation of the Lecture 1 §4.3 rule or the Lecture 2 §3 versioning discipline.

You will run a harness that reproduces all three, then **detect, diagnose, and prescribe the fix** for each, using only the Web UI's event history and the non-determinism errors. No reading the harness's fault comments until you've diagnosed all three from the outside — that's the whole point.

This mirrors the real skill: you rarely debug a determinism bug in workflow code you just wrote. You debug it on workflows someone else wrote, from the event history inward, after a deploy wedged them — while running executions pile up.

## The harness

Save this as `faulty_workflows.go`. It needs `temporal server start-dev` running. It registers three workflows, each with one planted fault, and starts an execution of each. Run the worker, start the workflows, and force replays (kill -9 the worker mid-execution, restart) to surface the faults. **Do not read the FAULT comments until you've diagnosed all three from the event history.**

```go
package main

import (
	"context"
	"flag"
	"log"
	"math/rand"
	"sort"
	"time"

	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"go.temporal.io/sdk/workflow"
)

const tq = "faulty-task-queue"

func NoopActivity(ctx context.Context, s string) (string, error) { return s, nil }

// --- Workflow 1: wall-clock in workflow code (planted fault #1) ---------------------
func ClockWorkflow(ctx workflow.Context) (string, error) {
	ctx = workflow.WithActivityOptions(ctx, workflow.ActivityOptions{StartToCloseTimeout: 10 * time.Second})
	// FAULT #1: time.Now() is non-deterministic. On replay it differs from the original
	// run, so the branch taken can change => nondeterminism error (or a silent wrong path).
	deadline := time.Now().Add(time.Hour) // <-- forbidden in workflow code
	_ = deadline
	workflow.Sleep(ctx, 30*time.Second) // sleep so a worker kill forces a replay
	var out string
	err := workflow.ExecuteActivity(ctx, NoopActivity, "clock").Get(ctx, &out)
	return out, err
}

// --- Workflow 2: map iteration order dependence (planted fault #2) -------------------
func MapWorkflow(ctx workflow.Context) (string, error) {
	ctx = workflow.WithActivityOptions(ctx, workflow.ActivityOptions{StartToCloseTimeout: 10 * time.Second})
	items := map[string]int{"a": 1, "b": 2, "c": 3, "d": 4}
	workflow.Sleep(ctx, 20*time.Second) // force a replay window
	// FAULT #2: ranging a Go map has RANDOM order. On replay the activities are scheduled
	// in a different order than the history records => nondeterminism error.
	for k := range items { // <-- non-deterministic iteration order
		var out string
		_ = workflow.ExecuteActivity(ctx, NoopActivity, k).Get(ctx, &out)
	}
	return "done", nil
	_ = sort.Strings // (sort imported for the fix; unused in the broken version)
}

// --- Workflow 3: code changed without versioning (planted fault #3) ------------------
// Run this file ONCE with -v=0 to start workflows on the "old" code (just the activity).
// Then re-run the worker with -v=1 (the "new" code adds a step BEFORE the activity)
// while the -v=0 workflows are still IN FLIGHT (sleeping). Their replay against the new
// code won't match history => nondeterminism error. This simulates a bad deploy.
func VersionWorkflow(ctx workflow.Context, newCode bool) (string, error) {
	ctx = workflow.WithActivityOptions(ctx, workflow.ActivityOptions{StartToCloseTimeout: 10 * time.Second})
	workflow.Sleep(ctx, 40*time.Second) // long sleep so it's in flight across a redeploy
	if newCode {
		// FAULT #3: this extra step was added without GetVersion gating. In-flight
		// workflows that started on the old code have no history event for it.
		var pre string
		_ = workflow.ExecuteActivity(ctx, NoopActivity, "new-pre-step").Get(ctx, &pre)
	}
	var out string
	err := workflow.ExecuteActivity(ctx, NoopActivity, "main").Get(ctx, &out)
	return out, err
}

func main() {
	mode := flag.String("mode", "worker", "worker | start")
	v := flag.Int("v", 0, "version: 0 = old code, 1 = new code (for fault #3)")
	flag.Parse()
	_ = rand.Int

	c, _ := client.Dial(client.Options{HostPort: "localhost:7233"})
	defer c.Close()

	if *mode == "worker" {
		w := worker.New(c, tq, worker.Options{})
		w.RegisterWorkflow(ClockWorkflow)
		w.RegisterWorkflow(MapWorkflow)
		w.RegisterWorkflowWithOptions(
			func(ctx workflow.Context) (string, error) { return VersionWorkflow(ctx, *v == 1) },
			workflow.RegisterOptions{Name: "VersionWorkflow"})
		w.RegisterActivity(NoopActivity)
		log.Printf("worker started (v=%d)", *v)
		_ = w.Run(worker.InterruptCh())
		return
	}

	for _, name := range []string{"ClockWorkflow", "MapWorkflow", "VersionWorkflow"} {
		_, err := c.ExecuteWorkflow(context.Background(),
			client.StartWorkflowOptions{ID: name + "-1", TaskQueue: tq}, name)
		if err != nil {
			log.Printf("start %s: %v", name, err)
		}
	}
	log.Println("started three workflows")
}
```

```bash
temporal server start-dev               # terminal 1
go run faulty_workflows.go -mode worker  # terminal 2
go run faulty_workflows.go -mode start   # terminal 3
# Then for each: kill -9 the worker mid-sleep and restart it to force a replay.
# For fault #3: restart the worker with -v=1 while VersionWorkflow is still sleeping.
```

Your diagnostic surface is the **Web UI event history** for each workflow, and the worker logs, which will show `nondeterminism` errors when replay fails.

## Your task

For **each of the three workflows**, produce a diagnosis with these four parts:

1. **Symptom** — what's observably wrong (the exact error in the worker log / Web UI; "different branch each restart"; "broke on deploy").
2. **Root cause** — the precise rule violated, named (wall-clock in workflow code §4.3; map iteration order §4.3; unversioned code change §3).
3. **How replay exposes it** — why the fault is invisible on the first run and only appears on replay (or only for in-flight executions across a deploy).
4. **Prescription** — the exact fix, with corrected code (`workflow.Now`; sort the keys then range; gate the new step with `GetVersion`).

You must reach each diagnosis using **at least two** independent signals — e.g., the non-determinism error *and* the event history showing the mismatch. One signal is a guess; two is a diagnosis.

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with a section per workflow, each containing all four parts above.
- [ ] You correctly identify the fault on each:
  - `ClockWorkflow` — **wall-clock in workflow code**: `time.Now()` is non-deterministic; replay differs from the recorded run. Fix: `workflow.Now(ctx)`.
  - `MapWorkflow` — **map iteration order**: Go randomizes map range order, so activities are scheduled in a different order on replay than in history. Fix: collect keys, `sort.Strings`, then range the sorted slice.
  - `VersionWorkflow` — **unversioned code change**: the new step has no history event for in-flight executions, so their replay mismatches. Fix: gate the new step behind `workflow.GetVersion(ctx, "add-pre-step", workflow.DefaultVersion, 1)`.
- [ ] For `ClockWorkflow` and `MapWorkflow` you captured the actual non-determinism error from the worker log/UI after forcing a replay.
- [ ] For `VersionWorkflow` you demonstrated that the *new* workflows (started on v=1) are fine but the *in-flight* ones (started on v=0) break on the v=1 redeploy — proving it's a versioning fault, not a code-logic fault.
- [ ] A `fixed_workflows.go` where all three replay cleanly (including in-flight ones across the version change).

## The trap (read after a first attempt)

`VersionWorkflow` is the subtle one and the most production-relevant, because the new code is **correct in isolation** — start a workflow fresh on v=1 and it runs perfectly. The fault only appears for workflows that were *already running* on the old code when you deployed the new one. This means it passes every test that starts a fresh workflow, ships green, and *then* wedges every in-flight execution the moment it deploys — a failure mode unique to durable execution that doesn't exist in stateless services. The tell is that the broken workflows are exactly the ones with `WorkflowExecutionStarted` timestamps *before* the deploy. **A workflow code change that is correct for new executions can still break every in-flight one; that's what `GetVersion` exists to prevent, and forgetting it is the single most common Temporal production incident.** Prescribing "the new code is fine" is wrong — it's fine for new workflows and catastrophic for running ones.

## Stretch

- Add a fourth fault: a raw `go func()` in workflow code (instead of `workflow.Go`). Show it produces non-deterministic behavior and fix it with the SDK's deterministic coroutine.
- Use the Temporal **replay test** API (`worker.NewWorkflowReplayer`) to replay a *recorded* history against changed code in a unit test — catching a determinism break *before* deploy. Write one for the `VersionWorkflow` change and show it fails without `GetVersion` and passes with it. This is the CI gate that prevents the production incident.
- Reproduce the whole challenge in Python (`temporalio`) and confirm the determinism rules and the `patched()`/versioning API are the same concepts in a different SDK.

## Why this matters

The midterm essay (due this week) may ask you to critique a system's reliability design, and durable-execution misuse is a rich target. More concretely: every team that adopts Temporal eventually ships a workflow-code change without versioning and wedges their in-flight executions — it is a rite of passage and a real incident. The engineer who can read an event history, spot the determinism or versioning violation, and prescribe the `workflow.Now` / sorted-iteration / `GetVersion` fix in five minutes is the one who turns that incident into a ten-minute fix instead of an afternoon outage. This challenge is that incident, rehearsed three ways.
