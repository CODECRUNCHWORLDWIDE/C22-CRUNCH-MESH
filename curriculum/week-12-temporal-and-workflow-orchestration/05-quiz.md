# Week 12 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Phase 3. Answer key is at the bottom — don't peek.

---

**Q1.** Why is a Temporal workflow durable — what makes it survive a worker crash with no lost state?

- A) It writes its variables to a file on disk after every line.
- B) Its decisions are recorded in an event history; a new worker replays the workflow code against that history to reconstruct the exact in-memory state at the crash, then continues.
- C) It runs on three machines simultaneously and votes.
- D) Temporal pauses the world when a worker dies.

---

**Q2.** What is the core distinction between a workflow and an activity?

- A) Workflows are faster; activities are slower.
- B) A workflow is deterministic orchestration code with no I/O; an activity does the actual side effects (I/O, network, DB) and runs at-least-once.
- C) Activities are deterministic; workflows do I/O.
- D) There is no difference; they're interchangeable.

---

**Q3.** Which of these is FORBIDDEN in workflow code?

- A) Calling `workflow.ExecuteActivity`.
- B) `time.Now()` — the wall clock is non-deterministic and differs on replay. Use `workflow.Now(ctx)`.
- C) An `if` statement.
- D) A `for` loop over a slice.

---

**Q4.** On replay, what happens when the workflow code reaches an activity call whose result is already in the history?

- A) The activity is re-executed from scratch.
- B) The worker returns the recorded result from the history immediately, without re-running the activity.
- C) The workflow fails with an error.
- D) The activity runs but its result is discarded.

---

**Q5.** Why must activities be idempotent even though Temporal won't re-run a *completed* activity on replay?

- A) They don't need to be; Temporal handles all duplication.
- B) Because a single activity execution can still be retried after a partial failure or timeout (activities run at-least-once), so a retry must be safe.
- C) Because workflows are non-deterministic.
- D) Because queries change state.

---

**Q6.** In the compensation-stack saga pattern, in what order do compensations run on failure?

- A) The same order the steps ran (FIFO).
- B) Reverse order (LIFO) — undo the most recently completed step first.
- C) Random order.
- D) All at once, in parallel.

---

**Q7.** What is a signal in Temporal?

- A) A synchronous read of workflow state.
- B) Asynchronous input delivered into a running workflow (e.g., "cancel"), recorded in the history so it survives replay.
- C) A way to kill a workflow.
- D) A retry policy setting.

---

**Q8.** What is a query in Temporal?

- A) A way to start a workflow.
- B) A synchronous, read-only, side-effect-free read of a running workflow's current state; it doesn't appear in the history.
- C) An asynchronous input.
- D) A database call inside the workflow.

---

**Q9.** You deploy a new version of a workflow that adds a step, while old executions are still in flight. What happens, and how do you prevent it?

- A) Nothing; new code always works.
- B) The in-flight executions' replay against the new code mismatches their history → non-determinism error. Prevent it by gating the new step with `workflow.GetVersion` (or patching).
- C) Temporal automatically migrates the old executions.
- D) The old executions silently skip the new step.

---

**Q10.** Why use `ContinueAsNew`?

- A) To speed up a slow workflow.
- B) To bound an otherwise-unbounded event history: the workflow completes and atomically restarts itself with carried-over state and a fresh, empty history.
- C) To retry a failed activity.
- D) To send a signal.

---

**Q11.** When is orchestration (Temporal) the *simpler* answer than choreography (events)?

- A) Always.
- B) For complex, multi-step, compensating, long-running processes where visibility and explicit failure handling matter — there the choreographed version's scattered logic becomes a liability.
- C) Never; choreography is always simpler.
- D) Only for single-step processes.

---

**Q12.** Why use a saga (with compensation) instead of a distributed transaction (2PC) across services?

- A) 2PC is faster.
- B) 2PC requires participants to hold locks and a coordinator that can block indefinitely, and external services (Stripe, carriers) don't expose prepare/commit — so a saga of local transactions with explicit compensation is the pragmatic, available alternative.
- C) Sagas are atomic and isolated.
- D) There's no difference.

---

**Q13.** How does Temporal compare to AWS Step Functions and Azure Durable Functions?

- A) They are completely unrelated technologies.
- B) Temporal is the portable, code-first, open-source durable-execution engine; Step Functions is a managed AWS state machine (ASL JSON, no determinism rule); Durable Functions is Azure's replay-based equivalent. The durable-execution concepts transfer across all three.
- C) Step Functions and Durable Functions are faster in every case.
- D) Only Temporal supports compensation.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — The event history plus deterministic replay reconstructs state after a crash. (Lecture 1 §4.)
2. **B** — Deterministic orchestration (no I/O) vs at-least-once side-effecting work. The split makes replay possible. (Lecture 1 §3.)
3. **B** — `time.Now()` is non-deterministic; use `workflow.Now(ctx)`. (Lecture 1 §4.3.)
4. **B** — The recorded result is returned from history; the activity is not re-executed. (Lecture 1 §4.2.)
5. **B** — Activities run at-least-once; a single execution can be retried, so it must be idempotent. (Lecture 1 §5.1.)
6. **B** — Reverse order (LIFO): undo the most recent completed step first. (Lecture 2 §1.2.)
7. **B** — Async input into a running workflow, recorded in history. (Lecture 2 §2.1.)
8. **B** — Sync, read-only state read; not recorded in history. (Lecture 2 §2.2.)
9. **B** — Unversioned changes break in-flight replays; gate with `GetVersion`. (Lecture 2 §3.)
10. **B** — Bounds an unbounded history by restarting with fresh history. (Lecture 2 §3.3.)
11. **B** — For complex compensating long-running processes, orchestration's visibility makes it the simpler correct design. (Lecture 2 §4.3.)
12. **B** — 2PC's locking/blocking and the lack of prepare/commit in external services make the saga the pragmatic choice. (Lecture 2 §1.5.)
13. **B** — Temporal = portable/code-first/open-source; Step Functions = managed AWS state machine; Durable Functions = Azure replay-based. Concepts transfer. (Lecture 2 §4.4.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./06-homework.md).
