# Exercise 1 — The Temporal Dev Server and Your First Workflow

**Goal:** Stand up a local Temporal dev server, open its Web UI, and run a trivial workflow that calls one activity — then *read the event history in the UI* to see, concretely, how Temporal records every step. You will train the single most important diagnostic habit of the week: reading the event history the way you read a stack trace, because it is the durable, authoritative record of what your workflow did.

**Estimated time:** 60 minutes. Guided.

---

## Setup

Install the `temporal` CLI (it bundles a single-binary dev server and the Web UI):

```bash
# macOS
brew install temporal
# Linux / other: see https://docs.temporal.io/cli#install
temporal --version
```

You also need Go 1.23+ for the worker:

```bash
go version
```

---

## Step 1 — Start the dev server

```bash
temporal server start-dev
# Starts the server on localhost:7233 and the Web UI on http://localhost:8233
```

Leave this running in its own terminal. Open `http://localhost:8233` in a browser — that's the Web UI, your primary diagnostic for the week. It's empty now; by the end of this exercise it will show your first workflow execution and its history.

---

## Step 2 — Write a trivial workflow and activity

Save this as `hello.go`. It's the smallest possible durable program: a workflow that calls one activity.

```go
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"time"

	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"go.temporal.io/sdk/workflow"
)

const taskQueue = "hello-task-queue"

// GreetActivity is an ACTIVITY: it does the "work" (here, just formats a string, but
// in a real activity this is where I/O lives). Activities can be retried, so keep them
// idempotent.
func GreetActivity(ctx context.Context, name string) (string, error) {
	return "Hello, " + name + "!", nil
}

// GreetWorkflow is a WORKFLOW: deterministic orchestration. It schedules the activity
// and returns its result. No I/O, no clocks, no randomness in here.
func GreetWorkflow(ctx workflow.Context, name string) (string, error) {
	ctx = workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Second,
	})
	var greeting string
	if err := workflow.ExecuteActivity(ctx, GreetActivity, name).Get(ctx, &greeting); err != nil {
		return "", err
	}
	return greeting, nil
}

func main() {
	mode := flag.String("mode", "worker", "worker | start")
	name := flag.String("name", "Crunch", "name to greet")
	flag.Parse()

	c, err := client.Dial(client.Options{HostPort: "localhost:7233"})
	if err != nil {
		log.Fatalln("dial:", err)
	}
	defer c.Close()

	switch *mode {
	case "worker":
		// A worker hosts the workflow + activity code and polls the task queue.
		w := worker.New(c, taskQueue, worker.Options{})
		w.RegisterWorkflow(GreetWorkflow)
		w.RegisterActivity(GreetActivity)
		log.Println("worker started; polling", taskQueue)
		if err := w.Run(worker.InterruptCh()); err != nil {
			log.Fatalln("worker:", err)
		}
	case "start":
		// Start a workflow execution and wait for its result.
		we, err := c.ExecuteWorkflow(context.Background(), client.StartWorkflowOptions{
			ID:        "greet-" + *name,
			TaskQueue: taskQueue,
		}, GreetWorkflow, *name)
		if err != nil {
			log.Fatalln("start:", err)
		}
		var result string
		if err := we.Get(context.Background(), &result); err != nil {
			log.Fatalln("get result:", err)
		}
		fmt.Printf("workflow %s result: %q\n", we.GetID(), result)
	}
}
```

```bash
go mod init hello
go get go.temporal.io/sdk
```

---

## Step 3 — Run the worker, then start a workflow

In one terminal, start the worker (it polls forever):

```bash
go run hello.go -mode worker
# worker started; polling hello-task-queue
```

In another terminal, start a workflow execution:

```bash
go run hello.go -mode start -name Crunch
# workflow greet-Crunch result: "Hello, Crunch!"
```

The result came back. Behind that one line, Temporal: persisted a `WorkflowExecutionStarted` event, dispatched a workflow task to your worker, your worker ran `GreetWorkflow` which scheduled `GreetActivity`, Temporal dispatched the activity task, your worker ran it, the result was recorded, and the workflow completed. All of it durable.

---

## Step 4 — Read the event history (the point of this exercise)

Open `http://localhost:8233`, click **Workflows**, and click `greet-Crunch`. You'll see the **event history** — the append-only log of everything that happened:

```
1   WorkflowExecutionStarted     input: "Crunch"
2   WorkflowTaskScheduled
3   WorkflowTaskStarted
4   WorkflowTaskCompleted
5   ActivityTaskScheduled        GreetActivity, input: "Crunch"
6   ActivityTaskStarted
7   ActivityTaskCompleted        result: "Hello, Crunch!"
8   WorkflowTaskScheduled
9   WorkflowTaskStarted
10  WorkflowTaskCompleted
11  WorkflowExecutionCompleted   result: "Hello, Crunch!"
```

**This history is the durable state of the workflow.** Read it: events 5–7 are the activity being scheduled, started, and completing with its result. That recorded result (event 7) is what makes replay work — if the worker had crashed after event 7, a new worker would replay the workflow code, read "Hello, Crunch!" from event 7 instead of re-running the activity, and continue. Sit with this: the history *is* the workflow's memory.

You can also see it from the CLI:

```bash
temporal workflow show --workflow-id greet-Crunch
```

---

## Step 5 — Inspect the task queue and the worker

```bash
temporal task-queue describe --task-queue hello-task-queue
# Shows your worker as a registered poller on the queue.
```

Stop your worker (Ctrl+C) and `temporal workflow start` a new execution. It will be *pending* — the workflow task sits in the queue with no worker to run it. Restart the worker and it picks up immediately. This is the matching service dispatching to workers (Lecture 1 §2), made visible: **work waits durably in the queue until a worker is available.**

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `temporal server start-dev` is running and the Web UI loads at `http://localhost:8233`.
- [ ] `go run hello.go -mode start` returns `"Hello, Crunch!"`.
- [ ] You found the workflow in the Web UI and can point to the `ActivityTaskScheduled` / `ActivityTaskCompleted` events and explain that the recorded result (not a re-run) is what makes replay work.
- [ ] `temporal task-queue describe` shows your worker as a poller.
- [ ] With the worker stopped, a started workflow is pending; restarting the worker completes it — proving work waits durably in the queue.
- [ ] You can state, in one sentence, the difference between the workflow (`GreetWorkflow`, deterministic, no I/O) and the activity (`GreetActivity`, does the work, retriable).

---

## Stretch

- Add a `workflow.Sleep(ctx, 30*time.Second)` before the activity. Start the workflow, watch a `TimerStarted` event appear in the history, kill the worker during the sleep, restart it, and confirm the workflow completes after the timer fires — the durable timer survived the worker death.
- Make `GreetActivity` fail on its first attempt (return an error if a counter is 0). Watch the history record `ActivityTaskFailed` then a retry, then success — the retry policy in action (Lecture 1 §5.2).
- Deliberately put `time.Now()` into `GreetWorkflow` and run it. You won't see an error on the *first* run (no replay happens), but read the Lecture 1 §4.3 forbidden list and predict what *would* break on a replay — then trigger a replay (kill the worker mid-sleep) and watch the non-determinism error appear.

---

When the event history feels like a readable record rather than a mystery, move to [Exercise 2 — The checkout saga](exercise-02-checkout-saga.go).
