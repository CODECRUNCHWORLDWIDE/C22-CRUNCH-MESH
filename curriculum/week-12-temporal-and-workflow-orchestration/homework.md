# Week 12 Homework

Six problems that revisit the week's topics and force the orchestration literacy into your fingers. The full set should take about **5 hours**. Work in your Week 12 Git repository (the same workspace as the exercises and the `checkout-orchestrator` mini-project) so every problem produces at least one commit you can point to at the midterm and the capstone.

The headline deliverable is **Problem 4 — the one-page orchestration-vs-choreography design memo**, the artifact a reviewer reads, not a journal entry. It also feeds directly into your midterm essay due this week.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have the **Temporal dev server** running (`temporal server start-dev`, UI on `http://localhost:8233`) and Go 1.23+. Problems 1, 2, 3, 5, and 6 run against it. If something is broken, the standalone workflows from the exercises are your fallback; say so in your writeup.

---

## Problem 1 — Read a real event history

**Problem statement.** Run the exercise-2 checkout saga (happy path and `-fail-ship` path). For each run, open the Web UI, find the workflow, and transcribe its **event history** into `notes/week-12/event-history.md`. Annotate each event group: which events are the activity being scheduled/completed, which are the compensations, where the workflow decided to compensate.

**Acceptance criteria.**

- `notes/week-12/event-history.md` contains the two histories (happy and compensated) with annotations.
- You correctly identify, on the compensated run, the events for `ShipOrder` failing and `RefundCharge` / `ReleaseInventory` running, and note they ran in reverse order.
- You state, in one sentence, why a recorded `ActivityTaskCompleted` event is what makes replay avoid re-running that activity.
- Committed.

**Hint.** `temporal workflow show --workflow-id checkout-B` dumps the history from the CLI if you prefer it to the UI. The point is to make the history a readable record, not a mystery — it's your primary diagnostic all week.

**Estimated time.** 40 minutes.

---

## Problem 2 — Prove durable execution with a worker kill

**Problem statement.** Run the exercise-2 worker and start a checkout workflow. Kill the worker (`Ctrl+C`, or `kill -9` the process) immediately after the worker logs `ChargePayment -> charged` but before `ShipOrder`. Restart the worker. Confirm the workflow completes (`ShipOrder` runs) and that `ChargePayment` did **not** run again on the restarted worker.

**Acceptance criteria.**

- `notes/week-12/durable-execution.md` records: the worker logs across both runs (showing `ChargePayment` only in the first), and the Web UI history showing a single `ActivityTaskCompleted` for the charge.
- You state, in one sentence, why the charge wasn't re-run (its result was replayed from the recorded history).
- Committed.

**Hint.** Add a `workflow.Sleep(ctx, 20*time.Second)` between charge and ship if the saga runs too fast to kill it at the right moment — the sleep gives you a window, and (bonus) proves the durable timer survives the kill too.

**Estimated time.** 45 minutes.

---

## Problem 3 — Break determinism on purpose, then fix it

**Problem statement.** Take a copy of the exercise-2 workflow and deliberately introduce a determinism violation: put `time.Now()` and a `rand.Intn` into the workflow code, using them to choose a branch. Add a `workflow.Sleep` so you can force a replay. Run it, kill and restart the worker mid-sleep to trigger a replay, and capture the **non-determinism error**. Then fix it with `workflow.Now(ctx)` and `workflow.SideEffect`, and show the replay now succeeds.

**Acceptance criteria.**

- `notes/week-12/determinism.md` captures the non-determinism error (from the worker log or Web UI) for the broken version, and a clean replay for the fixed version.
- You correctly explain *why* the broken version fails only on replay, not on the first run.
- The fixed code uses `workflow.Now` and `workflow.SideEffect` (or the deterministic random).
- Committed.

**Hint.** The error won't appear on the first run (no replay happens then) — you must force a replay by killing the worker mid-sleep and restarting. That "fine until replay" behavior is exactly why determinism bugs are insidious and why the challenge exists.

**Estimated time.** 1 hour.

---

## Problem 4 — The orchestration-vs-choreography design memo (headline deliverable)

**Problem statement.** This is the syllabus-style headline deliverable and a building block for your midterm essay. Using your Week-11 choreographed saga and your Week-12 orchestrated saga as concrete evidence, write a one-page memo at `notes/week-12/orchestration-vs-choreography.md` that decides, for the marketplace, which processes to orchestrate and which to choreograph. The memo must answer, explicitly:

1. **The two implementations** — a one-paragraph sketch each of the choreographed (Week 11) and orchestrated (Week 12) checkout saga, with a concrete complexity contrast (line counts, number of files/services, where compensation lives).
2. **What orchestration bought** — visibility, explicit reverse-order compensation, durable long waits, millisecond compensation testing, crash durability.
3. **What it cost** — a central engine to operate, the determinism discipline, the versioning tax.
4. **The decision rule** — when you'd orchestrate vs choreograph, stated as a rule a teammate could apply.
5. **A kept-choreography example** — one marketplace flow you'd deliberately leave choreographed (a broadcast event with many independent reactions), and why orchestrating it would be over-engineering.

**Acceptance criteria.**

- `notes/week-12/orchestration-vs-choreography.md` exists, fits roughly one page (400–600 words), and answers all five points.
- Point 1 cites a *concrete* contrast (not "orchestration is cleaner" but "one 60-line function vs five consumers across three services").
- Point 5 names a real flow and defends keeping it choreographed — showing you don't think orchestration is always right.
- Committed.

**Hint.** This memo is graded against the rubric below and becomes a section of your midterm essay and your capstone architecture document. The strongest memos refuse to crown a winner — they show orchestration winning for the compensating checkout saga *and* choreography winning for, say, the `order.placed.v1` fan-out to analytics, search, and notifications. Nuance beats dogma.

**Estimated time.** 1 hour.

---

## Problem 5 — Version a workflow without breaking in-flight executions

**Problem statement.** Take a workflow with a `workflow.Sleep` long enough to keep it in flight (e.g., 60s). Start it. While it's sleeping, change the workflow code to add an activity step *before* the sleep, **without** versioning, and restart the worker. Observe the in-flight execution break with a non-determinism error. Then fix it by gating the new step with `workflow.GetVersion`, restart, and show both the old (in-flight) and a new execution complete correctly.

**Acceptance criteria.**

- `notes/week-12/versioning.md` records: the non-determinism error from the unversioned change, and clean completion of both old and new executions after adding `GetVersion`.
- You explain, in one sentence, why the new code was correct for *new* workflows but broke *in-flight* ones, and why that's a failure mode unique to durable execution.
- Committed.

**Hint.** `workflow.GetVersion(ctx, "add-step", workflow.DefaultVersion, 1)` returns `DefaultVersion` for executions that started before the change (their history has no version marker) and `1` for new ones — so the old ones skip the new step on replay and don't mismatch. This is the single most common Temporal production incident; rehearsing it now is worth an afternoon later.

**Estimated time.** 40 minutes.

---

## Problem 6 — Test a saga's compensation in milliseconds

**Problem statement.** Write a Temporal workflow unit test (using `testsuite.NewTestWorkflowEnvironment`) for the exercise-2 saga that mocks the activities, forces `ShipOrder` to fail, and asserts that `RefundCharge` and `ReleaseInventory` are both called, in reverse order, exactly once. Run it and show it passes in milliseconds with no Temporal server running.

**Acceptance criteria.**

- A `checkout_test.go` (or equivalent) that mocks the activities, fails `ShipOrder`, and asserts the two compensations run in reverse order.
- The test passes and runs in milliseconds (no real server, no real sleeping).
- `notes/week-12/testing.md` notes, in one sentence, why this is a concrete advantage of orchestration over choreography (the whole saga, including compensation, is one deterministic function you can unit-test instantly).
- Committed.

**Hint.** `env.OnActivity(ShipOrder, ...).Return(errors.New("fail"))` injects the failure; `env.OnActivity(RefundCharge, ...).Return(nil).Once()` asserts it's called. `env.AssertExpectations(t)` checks the mocks. The test framework controls the clock, so even a workflow with a 3-day sleep tests instantly.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Read a real event history | 40 min |
| 2 — Prove durable execution (worker kill) | 45 min |
| 3 — Break and fix determinism | 1 h 0 min |
| 4 — Orchestration-vs-choreography memo (headline) | 1 h 0 min |
| 5 — Version without breaking in-flight | 40 min |
| 6 — Test compensation in milliseconds | 35 min |
| **Total** | **~5 h 0 min** |

---

## Grading rubric (for the headline Problem 4)

| Area | Points | What we look for |
|---|---:|---|
| **The two implementations** | 25 | Concrete complexity contrast (line counts / files / where compensation lives), not vague adjectives. |
| **What orchestration bought** | 20 | Visibility, explicit compensation, durable waits, testability, crash durability — each named. |
| **What it cost** | 20 | The central engine, determinism discipline, versioning tax — honestly stated. |
| **The decision rule** | 20 | A rule a teammate could apply, not "it depends." |
| **Kept-choreography example** | 15 | A real flow defended as deliberately choreographed — proving you don't think orchestration is always right. |

**90+** is portfolio-grade and drops straight into the midterm essay and the capstone architecture document. **70–89** decides the question but hand-waves the contrast. **Below 70** crowns one style as universally better — redo it with nuance and concrete evidence.

When you've finished all six, push your repo, make sure the `checkout-orchestrator` [mini-project](./mini-project/README.md) is in the same workspace, and **start your midterm architecture-review essay** — it's due at the end of this week and Phase 2 is now complete. Then take the [quiz](./quiz.md) with your notes closed.
