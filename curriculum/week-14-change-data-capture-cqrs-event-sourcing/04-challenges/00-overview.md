# Week 14 — Challenges

The exercises drill the mechanics. **The challenge makes you the reviewer.** You're handed four real-world designs and you have to classify each one correctly in the taxonomy — event-driven, CDC-fed CQRS, or event-sourced — and find the one that is *secretly dual-writing* and will corrupt itself in production.

## Index

1. **[Challenge 1 — Classify and fix four designs](./challenge-01-classify-and-fix-four-designs.md)** — four architecture descriptions, each using events differently. Place each in the taxonomy, identify the dual-write time bomb hiding in one of them, and rewrite that one with an outbox or CDC. Then defend, for each design, whether it picked the right tool for its problem. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the Phase 3 architecture review, where you defend an event-driven design to a reviewer who will ask "is this CQRS or event sourcing, and why?" Do it. The skill — reading a design and naming what kind of event system it actually is (versus what its authors *think* it is) in under ten minutes — is exactly what separates an engineer who's "used Kafka" from one who can keep an event-driven platform from quietly corrupting its own state.
