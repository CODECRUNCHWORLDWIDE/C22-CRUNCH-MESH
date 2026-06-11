#!/usr/bin/env python3
# Exercise 3 — Signals, queries, and the worker-crash drill
#
# Goal: Build a Python workflow that (1) waits durably (up to a timeout) for a `cancel`
#   SIGNAL or proceeds, (2) exposes its status via a QUERY, and (3) survives a worker
#   kill mid-execution with ZERO state loss. You will prove the defining property of
#   durable execution: kill -9 the worker mid-workflow, restart it, and the workflow
#   resumes from the exact step it was on, with completed activities NOT re-executed.
#
# Estimated time: 60 minutes. Runnable.
#
# SETUP
#   temporal server start-dev          # in its own terminal (UI on :8233)
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install temporalio
#
# HOW TO USE THIS FILE
#   python3 exercise-03-signals-and-worker-crash.py worker            # terminal 1
#   python3 exercise-03-signals-and-worker-crash.py start --order A   # terminal 2
#   python3 exercise-03-signals-and-worker-crash.py query  --order A  # read live status
#   python3 exercise-03-signals-and-worker-crash.py signal --order A  # send cancel
#
#   THE WORKER-CRASH DRILL (the point):
#     1. Start the worker.
#     2. Start a workflow (it does step1, then SLEEPS 60s durably, then step2).
#     3. While it's sleeping, kill -9 the worker terminal.
#     4. Restart the worker. The workflow RESUMES the sleep and finishes step2 —
#        step1 is NOT re-run (its result is replayed from history).
#     5. Confirm in the Web UI: the history shows step1 once, the timer, then step2.
#
# ACCEPTANCE CRITERIA
#   [ ] `query` returns the live status ("step1", "sleeping", "step2", "done").
#   [ ] `signal --order A` cancels a sleeping workflow; it ends as "cancelled" and
#       runs no further steps.
#   [ ] kill -9 the worker mid-sleep, restart: the workflow completes; step1 ran
#       exactly ONCE (check the worker logs across both runs and the Web UI history).
#   [ ] The event history shows the durable timer surviving the worker death.
#
# Expected output is at the bottom of the file.

import argparse
import asyncio
import sys
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

TASK_QUEUE = "crash-drill-task-queue"


# -------------------- Activities (the real work; idempotent) --------------------
@activity.defn
async def step1(order_id: str) -> str:
    activity.logger.info(f"  [activity] step1({order_id}) -> done")
    return f"step1-result-{order_id}"


@activity.defn
async def step2(order_id: str) -> str:
    activity.logger.info(f"  [activity] step2({order_id}) -> done")
    return f"step2-result-{order_id}"


# -------------------- The workflow (deterministic orchestration) --------------------
@workflow.defn
class CrashDrillWorkflow:
    def __init__(self) -> None:
        self._status = "started"
        self._cancelled = False

    @workflow.run
    async def run(self, order_id: str) -> str:
        opts = dict(start_to_close_timeout=timedelta(seconds=10))

        self._status = "step1"
        r1 = await workflow.execute_activity(step1, order_id, **opts)

        # A DURABLE sleep. The worker can be killed and restarted during this 60s and
        # the workflow resumes the sleep — the timer is recorded in the event history.
        # While sleeping, we also watch for a cancel SIGNAL (wait_condition).
        self._status = "sleeping"
        try:
            await workflow.wait_condition(lambda: self._cancelled, timeout=timedelta(seconds=60))
        except asyncio.TimeoutError:
            pass  # 60s elapsed with no cancel — proceed normally

        if self._cancelled:
            self._status = "cancelled"
            return f"cancelled after {r1}"

        self._status = "step2"
        r2 = await workflow.execute_activity(step2, order_id, **opts)

        self._status = "done"
        return f"{r1} + {r2}"

    @workflow.signal
    def cancel(self) -> None:
        # A SIGNAL: asynchronous input into the running workflow. Recorded in history,
        # so it survives replay like everything else.
        self._cancelled = True

    @workflow.query
    def status(self) -> str:
        # A QUERY: synchronous, read-only view of workflow state. No side effects.
        return self._status


# -------------------- main: worker / start / signal / query --------------------
async def run_worker() -> None:
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CrashDrillWorkflow],
        activities=[step1, step2],
    )
    print(f"worker started; polling {TASK_QUEUE}")
    await worker.run()


async def start_workflow(order_id: str) -> None:
    client = await Client.connect("localhost:7233")
    handle = await client.start_workflow(
        CrashDrillWorkflow.run,
        order_id,
        id=f"crash-drill-{order_id}",
        task_queue=TASK_QUEUE,
    )
    print(f"started crash-drill-{order_id}; waiting for result...")
    result = await handle.result()
    print(f"workflow crash-drill-{order_id} result: {result}")


async def send_signal(order_id: str) -> None:
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle(f"crash-drill-{order_id}")
    await handle.signal(CrashDrillWorkflow.cancel)
    print(f"sent cancel signal to crash-drill-{order_id}")


async def do_query(order_id: str) -> None:
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle(f"crash-drill-{order_id}")
    status = await handle.query(CrashDrillWorkflow.status)
    print(f"crash-drill-{order_id} status: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Temporal signals + worker-crash drill.")
    parser.add_argument("cmd", choices=["worker", "start", "signal", "query"])
    parser.add_argument("--order", default="A")
    args = parser.parse_args()

    if args.cmd == "worker":
        asyncio.run(run_worker())
    elif args.cmd == "start":
        asyncio.run(start_workflow(args.order))
    elif args.cmd == "signal":
        asyncio.run(send_signal(args.order))
    elif args.cmd == "query":
        asyncio.run(do_query(args.order))


if __name__ == "__main__":
    main()
    sys.exit(0)


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
# Happy path (worker terminal, after `start --order A`):
#   [activity] step1(A) -> done
#   ... (60s durable sleep) ...
#   [activity] step2(A) -> done
# Starter terminal:
#   workflow crash-drill-A result: step1-result-A + step2-result-A
#
# Query (during the sleep):
#   crash-drill-A status: sleeping
#
# Cancel (during the sleep, `signal --order A`):
#   sent cancel signal to crash-drill-A
# Starter terminal then prints:
#   workflow crash-drill-A result: cancelled after step1-result-A
#   (step2 NEVER ran — the signal short-circuited it)
#
# THE WORKER-CRASH DRILL:
#   1. start --order A   -> worker logs "step1(A) -> done", then sleeps.
#   2. kill -9 the worker while it's sleeping.
#   3. restart the worker.
#   4. After the original 60s elapses, the worker logs "step2(A) -> done" and the
#      workflow completes. step1 was NOT re-run on the restarted worker.
#
# Look at the Web UI history for crash-drill-A:
#   ActivityTaskCompleted (step1)   <-- recorded ONCE
#   TimerStarted / TimerFired       <-- the durable sleep, survived the worker death
#   ActivityTaskCompleted (step2)
# state lost: 0.  Completed activities re-executed: 0.  THAT is durable execution.
# -----------------------------------------------------------------------------
