# Week 11 — Challenges

The exercises drill the mechanics. **The challenge makes you the on-call engineer.** You're handed a running pipeline that is double-charging customers (or losing events, or both) and you have to diagnose *why* without the luxury of having written the broken code yourself — the way it always happens in the real world, usually after a customer complaint.

## Index

1. **[Challenge 1 — Diagnose three delivery-semantics faults](challenge-01-diagnose-three-delivery-faults.md)** — a harness runs three event flows, each with a different planted fault: a dual-write that loses events on crash, a per-attempt idempotency key that double-charges, and a dedup gate in the wrong transaction that leaks under chaos. Use the `outbox`, `charges`, and `processed_events` tables plus a chaos kill to find all three, then prescribe the correct fix for each. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the Week 12 midterm, where you defend an event-driven design and must answer "how do you guarantee no double-charge?" under cross-examination. Do it. The skill — reading a ledger you didn't generate and naming why it double-charged in under five minutes — is exactly what separates an engineer who "knows about idempotency" from one who can stop a payments incident at 3 a.m.
