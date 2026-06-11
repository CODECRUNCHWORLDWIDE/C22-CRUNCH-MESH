# Week 5 — Challenges

The exercises drill the mechanics — author, generate, serve, call. **The challenge makes you the contract owner.** A schema you can't evolve is a schema you'll break in anger, so this challenge is about the hardest part of owning a contract: changing it without breaking the consumers already running against it.

## Index

1. **[Challenge 1 — Evolve `catalog.v1` without breaking the consumers](challenge-01-evolve-without-breaking.md)** — apply three changes to the contract (two safe, one breaking), prove with a running old client and `buf breaking` which is which, and reserve a retired field so a future engineer can't recycle its number. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for owning a service contract in production — and for the Week 12 architecture review, where you'll defend the versioning strategy of your `cart` system's APIs. The skill — making a change and *knowing*, before you ship, whether it breaks anyone — is exactly what separates an engineer who "uses gRPC" from one who can own a contract that fifty services depend on. A breaking change you didn't know was breaking is the 3 a.m. page this challenge teaches you to prevent.
