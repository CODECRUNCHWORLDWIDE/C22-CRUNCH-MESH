# Week 12 — Challenges

The exercises drill the mechanics. **The challenge makes you the on-call engineer.** You're handed Temporal workflows that fail to replay — they throw non-determinism errors, or they broke when someone changed the code under in-flight executions — and you have to diagnose *why* without the luxury of having written the broken workflows yourself, the way it always happens when a deploy wedges a fleet of running workflows.

## Index

1. **[Challenge 1 — Diagnose three determinism / versioning faults](./challenge-01-diagnose-three-determinism-faults.md)** — a harness runs three workflows, each with a different planted fault: a wall-clock call in workflow code, a map-iteration-order dependence, and a code change deployed without versioning that breaks in-flight replays. Use the Web UI's event history and non-determinism errors to find all three, then prescribe the correct fix (a deterministic SDK call; sorted iteration; `GetVersion` gating). (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the **midterm architecture-review essay** due this week, where you may critique a system's use (or misuse) of durable execution. Do it. The skill — reading an event history you didn't generate and naming why a workflow won't replay in under five minutes — is exactly what separates an engineer who "uses Temporal" from one who can unwedge a fleet of stuck workflows at 3 a.m. after a bad deploy.
