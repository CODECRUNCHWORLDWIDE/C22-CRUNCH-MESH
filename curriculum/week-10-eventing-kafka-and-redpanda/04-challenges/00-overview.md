# Week 10 — Challenges

The exercises drill the mechanics. **The challenge makes you the on-call engineer.** You're handed a running cluster whose consumers are falling behind, and you have to diagnose *why* without the luxury of having written the broken producers and consumers yourself — the way it always happens in the real world.

## Index

1. **[Challenge 1 — Diagnose three consumer-lag faults on a live cluster](./challenge-01-diagnose-three-lag-faults.md)** — a harness spins up three topics, each with a different planted fault: a hot-partition key, a stop-the-world rebalance storm, and a too-short retention that silently drops unread records. Use `kafka-consumer-groups.sh --describe`, the rebalance logs, and the retention horizon to find all three, then prescribe the correct fix for each. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the midterm architecture-review essay at the end of Week 12, where you defend an event-driven design under cross-examination. Do it. The skill — reading a lag table you didn't generate and naming what's wrong in under five minutes — is exactly what separates an engineer who "knows Kafka" from one who can debug an event pipeline at 3 a.m.
