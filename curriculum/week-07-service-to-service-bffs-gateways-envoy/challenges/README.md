# Week 7 — Challenges

The exercises drill the mechanics. **The challenge makes you the on-call engineer.** You're handed a running proxy chain that's amplifying an outage instead of containing it, and you have to diagnose *why* and stop it — from the outside, reading stats, the way it always happens at 3 a.m. when the dashboards are red and nobody can find the off switch.

## Index

1. **[Challenge 1 — Tame the retry storm](challenge-01-tame-the-retry-storm.md)** — a fault-injection harness stands up an Envoy with a *naive* retry policy in front of a backend that's hiccuping. The retries amplify the hiccup into a full outage. Using only the admin `/stats`, you must (a) prove the storm is retry-driven, (b) name the missing primitive, and (c) fix it with a retry budget and show the storm cannot re-form. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the gateway-vs-mesh memo (homework Problem 4) and for the kind of incident you *will* own once you run a real edge. The retry storm is the most common self-inflicted outage in distributed systems — a system that was *almost* fine turned catastrophic by its own resilience code. The engineer who can look at `upstream_rq_retry` climbing and say "the budget is missing" in two minutes is the one who shortens the incident from an hour to five minutes.
